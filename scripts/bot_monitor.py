#!/usr/bin/env python3
"""
scripts/bot_monitor.py

CBGB 봇 자동 헬스체크 스크립트 (Claude Code Cron 전용)

체크 항목:
1. Docker 컨테이너 실행 중인지 (healthy 상태)
2. 최근 30분간 틱이 정상적으로 돌고 있는지
3. 신호 차단 이유 분포 (no_signal / state_not_flat / threshold 등)
4. 최근 24시간 트레이드 여부
5. MA slope vs T_TREND 비교 (진입 불가 여부 조기 감지)

출력:
- 이상 없으면: "✅ 봇 정상"
- 이상 감지 시: 구체적 원인 + 권고 조치 출력
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib import request, parse

ROOT = Path(__file__).parent.parent


def run(cmd: str) -> str:
    """Shell 명령 실행 후 stdout 반환. 실패 시 빈 문자열."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip()
    except Exception:
        return ""


def check_container() -> dict:
    """Docker 컨테이너 상태 확인."""
    out = run("docker ps --filter name=cbgb-bot --format '{{.Status}}'")
    if not out:
        return {"ok": False, "msg": "cbgb-bot 컨테이너가 실행되지 않음"}
    if "healthy" in out.lower():
        return {"ok": True, "msg": f"컨테이너 {out}"}
    return {"ok": False, "msg": f"컨테이너 비정상: {out}"}


def check_recent_ticks() -> dict:
    """최근 로그에서 틱이 진행 중인지 확인 (최근 50줄)."""
    logs = run("docker logs cbgb-bot --tail 50 2>&1")
    if not logs:
        return {"ok": False, "msg": "로그를 가져올 수 없음"}

    tick_matches = re.findall(r"Tick (\d+)", logs)
    if not tick_matches:
        return {"ok": False, "msg": "최근 로그에 틱 없음 — 봇이 멈춰 있을 수 있음"}

    latest_tick = int(tick_matches[-1])
    return {"ok": True, "msg": f"최근 틱 #{latest_tick} 진행 중"}


def check_signal_blocks(log_lines: str) -> dict:
    """신호 차단 이유 분포 분석."""
    reasons = re.findall(r"Entry blocked: (\w+)", log_lines)
    if not reasons:
        return {"ok": True, "msg": "신호 차단 기록 없음 (또는 진입 중)"}

    counts: dict = {}
    for r in reasons:
        counts[r] = counts.get(r, 0) + 1
    total = len(reasons)

    # 100%가 no_signal이면 경고
    no_signal_pct = counts.get("no_signal", 0) / total * 100
    state_blocked_pct = counts.get("state_not_flat", 0) / total * 100

    summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items(), key=lambda x: -x[1]))

    if no_signal_pct >= 95:
        return {
            "ok": False,
            "msg": f"⚠️ 신호 차단 {total}건 중 no_signal {no_signal_pct:.0f}% — "
                   f"T_TREND vs MA slope 점검 필요\n  분포: {summary}",
        }
    if state_blocked_pct >= 80:
        return {
            "ok": True,
            "msg": f"포지션 보유 중 (state_not_flat {state_blocked_pct:.0f}%) — 정상\n  분포: {summary}",
        }

    return {"ok": True, "msg": f"신호 차단 분포: {summary}"}


def check_threshold_vs_slope(log_lines: str) -> dict:
    """T_TREND vs 실제 MA slope 비교."""
    # Calibrate 로그에서 T_TREND 추출
    calibrate = re.search(r"T_TREND=([\d.]+)%", log_lines)
    slope_matches = re.findall(r"ma_slope=([-\d.]+)%", log_lines)

    if not calibrate or not slope_matches:
        return {"ok": True, "msg": "임계값 비교 데이터 부족 (정상)"}

    t_trend = float(calibrate.group(1))
    slopes = [abs(float(s)) for s in slope_matches[-20:]]  # 최근 20개
    avg_slope = sum(slopes) / len(slopes)
    max_slope = max(slopes)

    if max_slope < t_trend * 0.5:
        return {
            "ok": False,
            "msg": (
                f"⚠️ T_TREND={t_trend:.4f}% vs 최근 MA slope 최대={max_slope:.4f}%, 평균={avg_slope:.4f}%\n"
                f"  → T_TREND이 실제 slope의 {t_trend/max_slope:.1f}배 — 진입 신호 발생 불가능"
            ),
        }

    return {
        "ok": True,
        "msg": f"T_TREND={t_trend:.4f}%, MA slope 최대={max_slope:.4f}% (정상 범위)",
    }


def check_recent_trades() -> dict:
    """최근 24시간 트레이드 기록 확인."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    yesterday = datetime.fromtimestamp(
        datetime.now(timezone.utc).timestamp() - 86400, tz=timezone.utc
    ).strftime("%Y-%m-%d")

    trade_count = 0
    for date in [today, yesterday]:
        path = ROOT / "logs" / "mainnet" / f"trades_{date}.jsonl"
        if path.exists():
            lines = path.read_text().strip().splitlines()
            trade_count += len([l for l in lines if l.strip()])

    if trade_count == 0:
        return {
            "ok": False,
            "msg": "⚠️ 최근 24시간 완료 트레이드 0건 — 신호 생성 또는 청산 로직 점검 필요",
        }
    return {"ok": True, "msg": f"최근 24시간 트레이드 {trade_count}건 기록됨"}


def send_telegram_alert(issues: list) -> None:
    """이상 감지 시 Telegram으로 알림 전송."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"🚨 CBGB 봇 이상 감지 ({now})", ""]
    for i, issue in enumerate(issues, 1):
        lines.append(f"{i}. {issue}")
    lines.append("")
    lines.append("👉 docker logs cbgb-bot --tail 50")

    text = "\n".join(lines)
    payload = json.dumps({"chat_id": chat_id, "text": text}).encode()

    try:
        req = request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"Telegram 알림 실패: {e}")


def main() -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*50}")
    print(f"CBGB 봇 헬스체크 — {now}")
    print(f"{'='*50}")

    issues = []

    # 1. 컨테이너 상태
    r = check_container()
    status = "✅" if r["ok"] else "❌"
    print(f"{status} 컨테이너: {r['msg']}")
    if not r["ok"]:
        issues.append(r["msg"])

    # 2. 틱 진행
    r = check_recent_ticks()
    status = "✅" if r["ok"] else "❌"
    print(f"{status} 틱: {r['msg']}")
    if not r["ok"]:
        issues.append(r["msg"])

    # 로그 200줄 가져오기 (이후 분석에 사용)
    logs = run("docker logs cbgb-bot --tail 200 2>&1")

    # 3. 신호 차단 분포
    r = check_signal_blocks(logs)
    status = "✅" if r["ok"] else "⚠️"
    print(f"{status} 신호: {r['msg']}")
    if not r["ok"]:
        issues.append(r["msg"])

    # 4. T_TREND vs MA slope
    r = check_threshold_vs_slope(logs)
    status = "✅" if r["ok"] else "⚠️"
    print(f"{status} 임계값: {r['msg']}")
    if not r["ok"]:
        issues.append(r["msg"])

    # 5. 최근 트레이드
    r = check_recent_trades()
    status = "✅" if r["ok"] else "⚠️"
    print(f"{status} 트레이드: {r['msg']}")
    if not r["ok"]:
        issues.append(r["msg"])

    print(f"{'='*50}")
    if issues:
        print(f"\n🚨 이상 감지 {len(issues)}건:")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")
        print("\n👉 권고: docker logs cbgb-bot --tail 50 으로 상세 로그 확인")
        send_telegram_alert(issues)
        sys.exit(1)
    else:
        print("\n✅ 봇 정상 — 이상 없음")
        sys.exit(0)


if __name__ == "__main__":
    main()
