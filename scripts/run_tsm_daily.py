#!/usr/bin/env python3
"""
scripts/run_tsm_daily.py

ADR-0015 Strategy v4 — Daily TSM 러너.

일봉 확정(00:00 UTC) 직후 1일 1회 판정을 실행한다.

사용:
  python scripts/run_tsm_daily.py                 # shadow, 1회 실행
  python scripts/run_tsm_daily.py --mode shadow --once
  python scripts/run_tsm_daily.py --mode live --once   # G2 게이트 경고 출력
  python scripts/run_tsm_daily.py --loop          # 매일 00:10 UTC 대기 루프

.env에서 Testnet/Mainnet 키를 로드하고 BybitRestClient를 생성한 뒤
TsmTrader.run_daily_check를 호출, 결과를 stdout + logs/tsm_shadow/에 기록한다.

live 모드는 ADR-0015 G2 게이트(shadow 60일/신호 5건 통과 전 live 금지)를
경고로 출력한다 — 게이트 자체 강제는 운영자 판단.
"""

import argparse
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

# 패키지 루트(src) 등록 — editable 설치가 없는 실행 환경 대비
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from application.tsm_trader import TsmConfig, TsmTrader, log_shadow_signal  # noqa: E402
from infrastructure.exchange.bybit_rest_client import BybitRestClient  # noqa: E402


def build_client() -> BybitRestClient:
    """.env 기반 BybitRestClient 생성. Testnet/Mainnet은 BYBIT_TESTNET로 분기."""
    load_dotenv()
    testnet = os.getenv("BYBIT_TESTNET", "true").lower() == "true"
    if testnet:
        api_key = os.getenv("BYBIT_TESTNET_API_KEY")
        api_secret = os.getenv("BYBIT_TESTNET_API_SECRET")
        base_url = "https://api-testnet.bybit.com"
    else:
        api_key = os.getenv("BYBIT_API_KEY")
        api_secret = os.getenv("BYBIT_API_SECRET")
        base_url = "https://api.bybit.com"

    if not api_key or not api_secret:
        raise SystemExit("ERROR: API 자격 증명이 .env에 없습니다.")

    return BybitRestClient(api_key=api_key, api_secret=api_secret, base_url=base_url)


def run_once(trader: TsmTrader, shadow: bool) -> dict:
    result = trader.run_daily_check(shadow=shadow)
    path = log_shadow_signal(result)
    print(f"[{result.get('ts', '')}] action={result['action']} "
          f"direction={result.get('direction')} qty={result.get('qty')} "
          f"stop={result.get('stop_price')} shadow={result.get('shadow')}")
    if result["action"] == "error":
        print(f"  error: {result.get('error')}", file=sys.stderr)
    print(f"  logged → {path}")
    return result


def _seconds_until_next_run(now: datetime) -> float:
    """다음 00:10 UTC까지 초. 일봉 확정(00:00) 후 10분 여유."""
    target = now.replace(hour=0, minute=10, second=0, microsecond=0)
    if now >= target:
        target = target + timedelta(days=1)
    return (target - now).total_seconds()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Daily TSM 러너 (ADR-0015)")
    parser.add_argument("--mode", choices=["shadow", "live"], default="shadow")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--once", action="store_true", help="1회 실행 후 종료 (기본)")
    group.add_argument("--loop", action="store_true", help="매일 00:10 UTC 대기 루프")
    args = parser.parse_args(argv)

    shadow = args.mode == "shadow"
    if not shadow:
        print("=" * 70)
        print("⚠️  ADR-0015 G2 게이트: shadow 60일/신호 5건 통과 전 live 금지.")
        print("    live 모드는 실주문을 발주합니다. 게이트 미통과 시 중단하십시오.")
        print("=" * 70)

    trader = TsmTrader(build_client(), TsmConfig())

    if args.loop:
        print("Daily TSM loop 시작 (00:10 UTC 대기). Ctrl-C로 종료.")
        while True:
            wait = _seconds_until_next_run(datetime.now(timezone.utc))
            print(f"다음 실행까지 {wait/3600:.2f}시간 대기...")
            time.sleep(wait)
            run_once(trader, shadow)
    else:
        run_once(trader, shadow)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
