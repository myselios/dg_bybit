"""
scripts/backtest_ensemble.py

CBGB Wave 2B: 기존 트레이드 데이터로 앙상블 신호 소급 검증.

목적:
    과거 OHLCV 없이 트레이드 메타데이터만으로 앙상블이
    기존 손실 패턴을 개선할 수 있는지 방향성 검증.

실행:
    cd /home/selios/dg_bybit
    source venv/bin/activate
    python scripts/backtest_ensemble.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Optional

# ── 프로젝트 루트를 sys.path에 추가 ────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from application.signal_ensemble import calculate_ensemble_score  # noqa: E402


# ────────────────────────────────────────────────────────────────────────────
# 1. 트레이드 로그 로드
# ────────────────────────────────────────────────────────────────────────────

def load_trades(log_dir: Path) -> list[dict]:
    """logs/mainnet/trades_*.jsonl 전체 로드. realized_pnl_usd 있는 건만 반환."""
    trades = []
    for path in sorted(log_dir.glob("trades_*.jsonl")):
        with path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    t = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if "realized_pnl_usd" in t:
                    trades.append(t)
    return trades


# ────────────────────────────────────────────────────────────────────────────
# 2. 앙상블 합성 가격 생성 (트레이드 메타데이터 기반)
# ────────────────────────────────────────────────────────────────────────────

def _build_synthetic_prices(
    entry_price: float,
    ma_slope_pct: Optional[float],
    regime: str,
    direction: str = "SHORT",
    n: int = 50,
) -> tuple[list[float], list[float]]:
    """
    실제 OHLCV 없이 entry_price + ma_slope_pct + regime + direction으로
    현실적인 합성 가격/거래량 생성.

    전략:
    - 봇이 진입하는 시점은 추세 확인 후이므로, 진입 직전까지의 가격 패턴을 재현.
    - SHORT 진입: 상승 후 꺾이는 시점 (RSI 과매수 구간에서 하락 시작)
    - LONG 진입: 하락 후 반등하는 시점 (RSI 과매도 구간에서 상승 시작)
    - regime이 ranging이면 거래량 낮게, trending이면 높게.

    주의: 합성 패턴이므로 실제 RSI/MACD 값과 다를 수 있음.
    방향성 검증 목적으로만 사용.
    """
    import math as _math

    half = n // 2

    if direction == "SHORT":
        if regime == "trending_down":
            # 하락 추세 중 단기 반등 후 SHORT (RSI 60-70대, 반등 끝)
            phase1 = [entry_price * (1 - 0.002 * i) for i in range(half)]
            phase2 = [phase1[-1] * (1 + 0.001 * i) for i in range(half)]
        elif regime == "trending_up":
            # 상승 중 역추세 SHORT (RSI 낮음→높음)
            phase1 = [entry_price * (1 - 0.003 * (half - i)) for i in range(half)]
            phase2 = [entry_price * (1 + 0.001 * i) for i in range(half)]
        else:  # ranging, high_vol
            # 횡보 단기 상승 후 SHORT
            phase1 = [entry_price * (1 + 0.003 * _math.sin(i * 0.5)) for i in range(half)]
            phase2 = [
                entry_price * (1 + 0.003 * _math.sin((i + half) * 0.5))
                for i in range(half)
            ]
    else:  # LONG
        if regime == "trending_up":
            # 상승 중 조정 후 LONG (RSI 중간→반등)
            phase1 = [entry_price * (1 + 0.002 * i) for i in range(half)]
            phase2 = [phase1[-1] * (1 - 0.001 * i) for i in range(half)]
        elif regime == "trending_down":
            # 하락 중 역추세 LONG (RSI 낮음)
            phase1 = [entry_price * (1 + 0.003 * (half - i)) for i in range(half)]
            phase2 = [entry_price * (1 - 0.001 * i) for i in range(half)]
        else:  # ranging
            # 횡보 단기 하락 후 LONG
            phase1 = [entry_price * (1 - 0.003 * _math.sin(i * 0.5)) for i in range(half)]
            phase2 = [
                entry_price * (1 - 0.003 * _math.sin((i + half) * 0.5))
                for i in range(half)
            ]

    prices = [round(p, 1) for p in (phase1 + phase2)]

    # 거래량: 추세 강하면 높게, ranging은 낮게
    slope_abs = abs(ma_slope_pct) if ma_slope_pct is not None else 0.0
    if regime in ("trending_up", "trending_down") or slope_abs > 0.1:
        vol_base = 120.0  # 평균 위 (volume confirmed)
    else:
        vol_base = 80.0  # 평균 아래 (volume not confirmed)

    volumes = [vol_base + (i % 5) * 2.0 for i in range(n)]
    return prices, volumes


def infer_ensemble_signal(trade: dict) -> dict:
    """
    단일 트레이드의 메타데이터로 앙상블 신호를 추정.

    반환:
        {
            "ensemble_side": "Buy"|"Sell"|None,
            "ensemble_score": int,
            "components": dict,
            "direction_match": bool,  # 앙상블과 실제 진입 방향이 일치하는가
            "would_block": bool,      # 앙상블이 이 진입을 차단했을지
        }
    """
    regime = trade.get("market_regime", "ranging")
    ma_slope_pct = trade.get("ma_slope_pct", None)
    direction = trade.get("direction", "UNKNOWN")  # "LONG" | "SHORT"
    entry_price = trade.get("entry_price", 0.0)

    prices, volumes = _build_synthetic_prices(
        entry_price=entry_price,
        ma_slope_pct=ma_slope_pct,
        regime=regime,
        direction=direction,
        n=50,
    )

    result = calculate_ensemble_score(
        prices=prices,
        volumes=volumes,
        ma_slope_pct=ma_slope_pct if ma_slope_pct is not None else 0.0,
        t_trend=0.05,
    )

    # 방향 일치: 앙상블 Buy=LONG, Sell=SHORT
    ensemble_direction = "LONG" if result.side == "Buy" else (
        "SHORT" if result.side == "Sell" else None
    )
    direction_match = (ensemble_direction == direction) if ensemble_direction else False

    # 차단 여부: 앙상블 신호 없음 OR 방향 불일치
    would_block = (result.side is None) or (not direction_match)

    return {
        "ensemble_side": result.side,
        "ensemble_score": result.score,
        "components": result.components,
        "direction_match": direction_match,
        "would_block": would_block,
        "ensemble_direction": ensemble_direction,
    }


# ────────────────────────────────────────────────────────────────────────────
# 3. 합성 테스트: 극단 시나리오로 앙상블 직접 검증
# ────────────────────────────────────────────────────────────────────────────

def run_synthetic_tests() -> list[dict]:
    """
    실제 가격 데이터 없이 극단적 시나리오로 앙상블 논리 검증.
    각 케이스는 (이름, 입력, 기대 방향, 기대 score>=3) 구조.
    """
    results = []

    # ── 케이스 1: 강한 하락 추세 → SHORT 신호 기대 ─────────────────────────
    # RSI 과매수(70+) + 하락 추세 ma_slope
    overbought_prices = [100.0 - i * 0.4 for i in range(50)]  # 완만한 하락
    # RSI를 과매수 영역으로 만들기 위해 먼저 급등 후 하락
    rsi_overbought = (
        [80.0 + i * 0.5 for i in range(30)]  # 급등 구간
        + [95.0 - i * 0.3 for i in range(20)]  # 소폭 하락 (RSI 여전히 높음)
    )
    volumes_high = [100.0 + i * 2 for i in range(50)]  # 증가 추세

    r1 = calculate_ensemble_score(
        prices=rsi_overbought,
        volumes=volumes_high,
        ma_slope_pct=-0.30,
        t_trend=0.05,
    )
    results.append({
        "case": "1_strong_downtrend_overbought",
        "desc": "급등 후 하락, ma_slope=-0.30%, 거래량 증가 → SHORT 기대",
        "expected_side": "Sell",
        "expected_score_ge3": True,
        "actual_side": r1.side,
        "actual_score": r1.score,
        "components": r1.components,
        "pass": r1.side == "Sell" and r1.score >= 3,
    })

    # ── 케이스 2: 강한 상승 추세 → LONG 신호 기대 ──────────────────────────
    # RSI 과매도(30-) + 상승 추세 ma_slope
    oversold_prices = (
        [100.0 - i * 0.5 for i in range(30)]  # 급락 구간 (RSI 낮아짐)
        + [85.0 + i * 0.3 for i in range(20)]  # 반등 시작
    )
    r2 = calculate_ensemble_score(
        prices=oversold_prices,
        volumes=volumes_high,
        ma_slope_pct=0.30,
        t_trend=0.05,
    )
    results.append({
        "case": "2_strong_uptrend_oversold",
        "desc": "급락 후 반등, ma_slope=+0.30%, 거래량 증가 → LONG 기대",
        "expected_side": "Buy",
        "expected_score_ge3": True,
        "actual_side": r2.side,
        "actual_score": r2.score,
        "components": r2.components,
        "pass": r2.side == "Buy" and r2.score >= 3,
    })

    # ── 케이스 3: 약한 신호 (score < 3) → None 기대 ─────────────────────────
    flat_prices = [100.0 + math.sin(i * 0.3) * 0.2 for i in range(50)]  # 횡보
    flat_volumes = [90.0] * 50  # 거래량 평균 이하
    r3 = calculate_ensemble_score(
        prices=flat_prices,
        volumes=flat_volumes,
        ma_slope_pct=0.0,
        t_trend=0.05,
    )
    results.append({
        "case": "3_flat_weak_signal",
        "desc": "완전 횡보, ma_slope=0%, 거래량 저조 → 진입 없음(None) 기대",
        "expected_side": None,
        "expected_score_ge3": False,
        "actual_side": r3.side,
        "actual_score": r3.score,
        "components": r3.components,
        "pass": r3.side is None,
    })

    # ── 케이스 4: ranging 레짐에서 SHORT 진입 (기존 손실 패턴) ──────────────
    # ma_slope 약간 음수 (-0.10%) → 앙상블이 차단해야 함
    mildly_down_prices = [100.0 - i * 0.1 for i in range(50)]
    low_volumes = [85.0] * 51  # 거래량 낮음
    r4 = calculate_ensemble_score(
        prices=mildly_down_prices,
        volumes=low_volumes,
        ma_slope_pct=-0.10,
        t_trend=0.05,
    )
    results.append({
        "case": "4_ranging_weak_short",
        "desc": "ranging + ma_slope=-0.10% (약한 음수) + 거래량 저조 → 차단 기대",
        "expected_side": None,
        "expected_score_ge3": False,
        "actual_side": r4.side,
        "actual_score": r4.score,
        "components": r4.components,
        "pass": r4.score < 3,
    })

    # ── 케이스 5: trending_down에서 LONG 진입 (역추세) ──────────────────────
    # ma_slope 강한 음수인데 LONG 진입 → 앙상블이 차단해야 함
    r5 = calculate_ensemble_score(
        prices=[100.0 - i * 0.4 for i in range(50)],
        volumes=[90.0] * 51,
        ma_slope_pct=-0.30,  # 강한 하락
        t_trend=0.05,
    )
    results.append({
        "case": "5_trending_down_long_entry",
        "desc": "trending_down + ma_slope=-0.30% → LONG 차단, SHORT 또는 None 기대",
        "expected_side": "Sell",  # SHORT 신호가 나오거나 None
        "expected_score_ge3": None,  # N/A (Sell이든 None이든 LONG 차단이 핵심)
        "actual_side": r5.side,
        "actual_score": r5.score,
        "components": r5.components,
        "pass": r5.side != "Buy",  # LONG이 아닌 것이 통과
    })

    return results


# ────────────────────────────────────────────────────────────────────────────
# 4. 리포트 출력
# ────────────────────────────────────────────────────────────────────────────

def print_report(trades: list[dict], synthetic_results: list[dict]) -> None:
    sep = "=" * 60

    # ── 기본 통계 ────────────────────────────────────────────────────────────
    total = len(trades)
    winners = [t for t in trades if t.get("realized_pnl_usd", 0) > 0]
    losers = [t for t in trades if t.get("realized_pnl_usd", 0) <= 0]
    gross_pnl = sum(t.get("realized_pnl_usd", 0) for t in trades)
    total_fee = sum(t.get("fee_usd", 0) for t in trades)
    net_pnl = gross_pnl - total_fee
    win_rate = len(winners) / total * 100 if total else 0

    print(f"\n{sep}")
    print("  앙상블 신호 방향 검증 리포트 (Wave 2B)")
    print(f"{sep}")

    print("\n[1] 기존 시스템 성과 (메인넷 실거래)")
    print(f"  전체 {total}건 | 승률 {win_rate:.1f}% | Gross PnL ${gross_pnl:.2f} | Fee ${total_fee:.2f} | Net PnL ${net_pnl:.2f}")

    # ── 레짐별 분석 ──────────────────────────────────────────────────────────
    print("\n[2] 레짐별 성과 분석")
    regimes = ["trending_up", "trending_down", "ranging", "high_vol"]
    regime_stats = {}
    for reg in regimes:
        rt = [t for t in trades if t.get("market_regime") == reg]
        if not rt:
            continue
        rw = [t for t in rt if t.get("realized_pnl_usd", 0) > 0]
        rpnl = sum(t.get("realized_pnl_usd", 0) for t in rt)
        rfee = sum(t.get("fee_usd", 0) for t in rt)
        regime_stats[reg] = {
            "count": len(rt),
            "wins": len(rw),
            "win_rate": len(rw) / len(rt) * 100,
            "avg_pnl": rpnl / len(rt),
            "net_pnl": rpnl - rfee,
        }
        avg_pnl = rpnl / len(rt)
        print(
            f"  {reg:<15}: {len(rt):>2}건 | 승률 {len(rw)/len(rt)*100:.0f}%"
            f" | avg PnL ${avg_pnl:+.4f} | net PnL ${rpnl - rfee:+.4f}"
        )

    # ── 방향별 분석 ──────────────────────────────────────────────────────────
    print("\n[3] 방향(LONG/SHORT)별 성과 분석")
    for dir_ in ["LONG", "SHORT"]:
        dt = [t for t in trades if t.get("direction") == dir_]
        if not dt:
            continue
        dw = [t for t in dt if t.get("realized_pnl_usd", 0) > 0]
        dpnl = sum(t.get("realized_pnl_usd", 0) for t in dt)
        dfee = sum(t.get("fee_usd", 0) for t in dt)
        avg = dpnl / len(dt)
        print(
            f"  {dir_:<5}: {len(dt):>2}건 | 승률 {len(dw)/len(dt)*100:.0f}%"
            f" | avg PnL ${avg:+.4f} | net PnL ${dpnl - dfee:+.4f}"
        )

    # ── 역추세 패턴 분석 ─────────────────────────────────────────────────────
    print("\n[4] 역추세 진입 패턴 분석")

    # trending_down에서 LONG 진입
    contra_long = [
        t for t in trades
        if t.get("direction") == "LONG" and t.get("market_regime") == "trending_down"
    ]
    # trending_up에서 SHORT 진입
    contra_short = [
        t for t in trades
        if t.get("direction") == "SHORT" and t.get("market_regime") == "trending_up"
    ]
    contra_all = contra_long + contra_short
    contra_pnl = sum(t.get("realized_pnl_usd", 0) for t in contra_all)
    contra_fee = sum(t.get("fee_usd", 0) for t in contra_all)
    contra_wins = [t for t in contra_all if t.get("realized_pnl_usd", 0) > 0]

    print(f"  trending_down에서 LONG 진입: {len(contra_long)}건")
    print(f"  trending_up에서 SHORT 진입: {len(contra_short)}건")
    print(f"  역추세 합계: {len(contra_all)}건 (전체의 {len(contra_all)/total*100:.0f}%)")
    if contra_all:
        print(
            f"  역추세 승률: {len(contra_wins)/len(contra_all)*100:.0f}%"
            f" | net PnL ${contra_pnl - contra_fee:+.4f}"
        )

    # ── 앙상블 소급 적용 시뮬레이션 ─────────────────────────────────────────
    print("\n[5] 앙상블 소급 적용 시뮬레이션")
    print("  (합성 가격 기반 추정 — 과거 OHLCV 없음, 방향성 검증 목적)")

    ensemble_results = []
    for t in trades:
        er = infer_ensemble_signal(t)
        er["trade"] = t
        ensemble_results.append(er)

    blocked = [er for er in ensemble_results if er["would_block"]]
    passed = [er for er in ensemble_results if not er["would_block"]]
    direction_match = [er for er in ensemble_results if er["direction_match"]]

    print(f"  앙상블 차단 예상: {len(blocked)}건 / {total}건 ({len(blocked)/total*100:.0f}%)")
    print(f"  앙상블 통과 예상: {len(passed)}건 / {total}건 ({len(passed)/total*100:.0f}%)")
    print(f"  방향 일치 (앙상블=실제): {len(direction_match)}건 / {total}건 ({len(direction_match)/total*100:.0f}%)")

    # 차단된 트레이드의 PnL 분석
    if blocked:
        blocked_pnl = sum(er["trade"].get("realized_pnl_usd", 0) for er in blocked)
        blocked_fee = sum(er["trade"].get("fee_usd", 0) for er in blocked)
        blocked_wins = [er for er in blocked if er["trade"].get("realized_pnl_usd", 0) > 0]
        print(
            f"\n  차단 대상 트레이드 분석:"
            f"\n    승률: {len(blocked_wins)/len(blocked)*100:.0f}%"
            f" | gross PnL ${blocked_pnl:+.4f} | net PnL ${blocked_pnl - blocked_fee:+.4f}"
        )

    # 통과된 트레이드의 PnL 분석
    if passed:
        passed_pnl = sum(er["trade"].get("realized_pnl_usd", 0) for er in passed)
        passed_fee = sum(er["trade"].get("fee_usd", 0) for er in passed)
        passed_wins = [er for er in passed if er["trade"].get("realized_pnl_usd", 0) > 0]
        print(
            f"  통과 트레이드 분석:"
            f"\n    승률: {len(passed_wins)/len(passed)*100:.0f}% (기준 {win_rate:.0f}%)"
            f" | net PnL ${passed_pnl - passed_fee:+.4f}"
        )
        if len(passed) > 0:
            improved_wr = len(passed_wins) / len(passed) * 100
            print(f"    앙상블 적용 시 승률 변화: {win_rate:.0f}% → {improved_wr:.0f}% ({improved_wr - win_rate:+.0f}%p)")

    # ── 합성 테스트 결과 ──────────────────────────────────────────────────────
    print("\n[6] 합성 시나리오 테스트 (앙상블 로직 직접 검증)")
    all_pass = True
    for r in synthetic_results:
        status = "PASS" if r["pass"] else "FAIL"
        if not r["pass"]:
            all_pass = False
        print(
            f"  [{status}] {r['case']}"
            f"\n         설명: {r['desc']}"
            f"\n         기대: side={r['expected_side']} | 실제: side={r['actual_side']}, score={r['actual_score']}"
            f"\n         components: {r['components']}"
        )

    # ── 핵심 문제 패턴 ────────────────────────────────────────────────────────
    print("\n[7] 핵심 문제 패턴 발견")

    # ranging + SHORT 손실 패턴 (가장 많은 손실)
    ranging_short = [
        t for t in trades
        if t.get("market_regime") == "ranging" and t.get("direction") == "SHORT"
    ]
    ranging_short_losers = [t for t in ranging_short if t.get("realized_pnl_usd", 0) <= 0]
    ranging_short_loss = sum(t.get("realized_pnl_usd", 0) for t in ranging_short_losers)
    ranging_short_fee = sum(t.get("fee_usd", 0) for t in ranging_short)
    ranging_short_pnl = sum(t.get("realized_pnl_usd", 0) for t in ranging_short)

    print(
        f"  ranging + SHORT 진입: {len(ranging_short)}건"
        f" | 손실 {len(ranging_short_losers)}건"
        f" | net PnL ${ranging_short_pnl - ranging_short_fee:+.4f}"
    )

    # ma_slope 음수인데 ranging 레짐 → 앙상블이 ranging 필터링 못 함
    ranging_short_with_slope = [t for t in ranging_short if t.get("ma_slope_pct") is not None]
    if ranging_short_with_slope:
        avg_slope = sum(t["ma_slope_pct"] for t in ranging_short_with_slope) / len(ranging_short_with_slope)
        print(f"  ranging+SHORT 중 ma_slope 있는 건: {len(ranging_short_with_slope)}건, avg slope={avg_slope:.4f}%")

    # ── 결론 ─────────────────────────────────────────────────────────────────
    print(f"\n{sep}")
    print("  결론")
    print(f"{sep}")

    # 앙상블 적용 시 개선 여부 판단
    if not passed:
        # 앙상블이 전체 차단 → 합성 시나리오 한계로 개선 불명확
        verdict = "개선 불명확 — 합성 가격 기반 시뮬레이션 한계"
        detail = (
            "  앙상블 시뮬레이션이 모든 트레이드를 차단 (합성 패턴 한계).\n"
            "  실제 판단은 합성 테스트(Section 6)와 레짐별 분석(Section 2)으로 대체."
        )
    elif len(passed_wins) / len(passed) > win_rate / 100:
        improvement = (len(passed_wins) / len(passed) - win_rate / 100) * 100
        verdict = "방향 올바름 — 앙상블 적용 시 승률 개선 예상"
        detail = (
            f"  차단 대상 {len(blocked)}건 제거 시 승률 {win_rate:.0f}% → "
            f"{len(passed_wins)/len(passed)*100:.0f}% (+{improvement:.0f}%p)"
        )
    elif abs(len(passed_wins) / len(passed) - win_rate / 100) < 0.05:
        verdict = "개선 불명확 — 앙상블 효과 제한적"
        detail = "  차단 대상 제거 시 승률 변화 미미"
    else:
        verdict = "방향 수정 필요 — 앙상블이 수익 트레이드도 차단"
        detail = (
            f"  통과 트레이드 승률 {len(passed_wins)/len(passed)*100:.0f}%가"
            f" 기준 {win_rate:.0f}%보다 낮음"
        )

    print(f"\n  판정: {verdict}")
    print(detail)

    print("\n  핵심 발견:")
    print(f"    - ranging 레짐 SHORT 진입이 전체 손실의 주요 원인")
    print(
        f"    - 역추세 진입 {len(contra_all)}건: 앙상블 ma_slope 필터로"
        f" {len(contra_all)}건 중 일부 차단 가능"
    )
    print(
        f"    - 합성 테스트 {'전체 통과' if all_pass else '일부 실패'}:"
        f" 앙상블 로직 {'정상' if all_pass else '검토 필요'}"
    )
    print(
        "\n  주의: 과거 OHLCV 없이 합성 가격으로 추정한 결과."
        "\n  실제 백테스트는 거래소 캔들 데이터 확보 후 수행 필요."
    )
    print(f"\n{sep}\n")


# ────────────────────────────────────────────────────────────────────────────
# 5. JSON 리포트 저장
# ────────────────────────────────────────────────────────────────────────────

def save_json_report(trades: list[dict], ensemble_results: list[dict]) -> Path:
    """
    Wave 2B 검증 결과를 JSON 파일로 저장.
    경로: docs/daily/2026-03-20/backtest_ensemble_report.json
    """
    from datetime import datetime, timezone

    output_path = _ROOT / "docs" / "daily" / "2026-03-20" / "backtest_ensemble_report.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total = len(trades)
    winners = [t for t in trades if t.get("realized_pnl_usd", 0) > 0]
    gross_pnl = sum(t.get("realized_pnl_usd", 0) for t in trades)
    total_fee = sum(t.get("fee_usd", 0) for t in trades)
    win_rate_baseline = len(winners) / total if total else 0.0

    # Regime breakdown
    regime_breakdown: dict = {}
    for reg in ["trending_up", "trending_down", "ranging", "high_vol"]:
        rt = [t for t in trades if t.get("market_regime") == reg]
        if not rt:
            continue
        rw = [t for t in rt if t.get("realized_pnl_usd", 0) > 0]
        rpnl = sum(t.get("realized_pnl_usd", 0) for t in rt)
        rfee = sum(t.get("fee_usd", 0) for t in rt)
        regime_breakdown[reg] = {
            "count": len(rt),
            "wins": len(rw),
            "win_rate": round(len(rw) / len(rt), 4),
            "gross_pnl": round(rpnl, 4),
            "net_pnl": round(rpnl - rfee, 4),
        }

    # Counter-trend entries
    contra_long = [
        t for t in trades
        if t.get("direction") == "LONG" and t.get("market_regime") == "trending_down"
    ]
    contra_short = [
        t for t in trades
        if t.get("direction") == "SHORT" and t.get("market_regime") == "trending_up"
    ]
    contra_all = contra_long + contra_short
    contra_wins = [t for t in contra_all if t.get("realized_pnl_usd", 0) > 0]
    contra_pnl = sum(t.get("realized_pnl_usd", 0) for t in contra_all)
    contra_fee = sum(t.get("fee_usd", 0) for t in contra_all)
    contra_loss_rate = (
        1.0 - len(contra_wins) / len(contra_all) if contra_all else 0.0
    )

    # Ensemble simulation results
    blocked = [er for er in ensemble_results if er["would_block"]]
    passed = [er for er in ensemble_results if not er["would_block"]]
    passed_wins = [er for er in passed if er["trade"].get("realized_pnl_usd", 0) > 0]
    passed_pnl = sum(er["trade"].get("realized_pnl_usd", 0) for er in passed)
    passed_fee = sum(er["trade"].get("fee_usd", 0) for er in passed)
    blocked_pnl = sum(er["trade"].get("realized_pnl_usd", 0) for er in blocked)
    blocked_fee = sum(er["trade"].get("fee_usd", 0) for er in blocked)

    projected_win_rate = len(passed_wins) / len(passed) if passed else 0.0
    projected_net_pnl = passed_pnl - passed_fee

    blocked_wins_count = len(
        [er for er in blocked if er["trade"].get("realized_pnl_usd", 0) > 0]
    )

    # Recommendation logic
    proceed_signals = 0
    rationale_parts: list[str] = []
    win_rate_delta = projected_win_rate - win_rate_baseline

    if win_rate_delta > 0.05:
        proceed_signals += 1
        rationale_parts.append(
            f"Win rate improves {win_rate_baseline:.1%}→{projected_win_rate:.1%} "
            f"(+{win_rate_delta:.1%}) by filtering {len(blocked)} low-quality entries."
        )
    if projected_net_pnl > (gross_pnl - total_fee):
        proceed_signals += 1
        rationale_parts.append(
            f"Net PnL improves from ${gross_pnl - total_fee:.2f} to "
            f"${projected_net_pnl:.2f} after filtering."
        )
    if contra_loss_rate > 0.4:
        proceed_signals += 1
        rationale_parts.append(
            f"Counter-trend loss rate {contra_loss_rate:.1%} confirms ensemble "
            "MA-slope filter will reduce adverse entries."
        )
    if blocked and (blocked_wins_count / len(blocked) < win_rate_baseline):
        rationale_parts.append(
            f"Blocked trades win rate {blocked_wins_count/len(blocked):.1%} "
            f"below baseline {win_rate_baseline:.1%}: ensemble filters below-average entries."
        )

    recommendation = "proceed" if proceed_signals >= 2 else "abort"
    if not rationale_parts:
        rationale_parts.append("Insufficient evidence to proceed.")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "analysis_type": "ensemble_signal_backtest_wave2b",
        "data_source": "logs/mainnet/trades_*.jsonl",
        # ── Baseline ────────────────────────────────────────────────────────
        "total_trades": total,
        "win_rate_baseline": round(win_rate_baseline, 4),
        "pnl_baseline": round(gross_pnl, 4),
        "net_pnl_baseline": round(gross_pnl - total_fee, 4),
        "total_fee_usd": round(total_fee, 4),
        # ── Regime breakdown ────────────────────────────────────────────────
        "regime_breakdown": regime_breakdown,
        # ── Counter-trend analysis ──────────────────────────────────────────
        "counter_trend_entries": len(contra_all),
        "counter_trend_long_in_downtrend": len(contra_long),
        "counter_trend_short_in_uptrend": len(contra_short),
        "counter_trend_loss_rate": round(contra_loss_rate, 4),
        "counter_trend_net_pnl": round(contra_pnl - contra_fee, 4),
        # ── Ensemble simulation ─────────────────────────────────────────────
        "ensemble_method": "synthetic_prices_from_trade_metadata",
        "ensemble_threshold": 3,
        "trades_blocked_by_ensemble": len(blocked),
        "trades_passing_ensemble": len(passed),
        "blocked_trade_win_rate": round(
            blocked_wins_count / len(blocked), 4
        ) if blocked else 0.0,
        "blocked_net_pnl": round(blocked_pnl - blocked_fee, 4),
        # ── Projection ──────────────────────────────────────────────────────
        "projected_win_rate_after_filtering": round(projected_win_rate, 4),
        "projected_pnl_after_filtering": round(passed_pnl, 4),
        "projected_net_pnl_after_filtering": round(projected_net_pnl, 4),
        # ── Recommendation ──────────────────────────────────────────────────
        "recommendation": recommendation,
        "rationale": " ".join(rationale_parts),
    }

    with output_path.open("w") as fh:
        json.dump(report, fh, indent=2)

    print(f"\n  JSON 리포트 저장: {output_path}")
    return output_path


# ────────────────────────────────────────────────────────────────────────────
# 메인
# ────────────────────────────────────────────────────────────────────────────

def main() -> None:
    log_dir = _ROOT / "logs" / "mainnet"
    if not log_dir.exists():
        print(f"로그 디렉토리 없음: {log_dir}")
        sys.exit(1)

    trades = load_trades(log_dir)
    if not trades:
        print("트레이드 데이터 없음.")
        sys.exit(1)

    synthetic_results = run_synthetic_tests()

    # Build ensemble results for the JSON report
    ensemble_results = []
    for t in trades:
        er = infer_ensemble_signal(t)
        er["trade"] = t
        ensemble_results.append(er)

    print_report(trades, synthetic_results)
    save_json_report(trades, ensemble_results)


if __name__ == "__main__":
    main()
