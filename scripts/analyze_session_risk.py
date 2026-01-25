#!/usr/bin/env python3
"""
scripts/analyze_session_risk.py
Session Risk 분석 스크립트

실행:
    python scripts/analyze_session_risk.py logs/testnet_dry_run/
"""

import json
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any


def analyze_trade_logs(log_dir: Path) -> Dict[str, Any]:
    """Trade log 분석 → Daily/Weekly PnL 계산"""

    # 모든 JSONL 파일 읽기
    trade_logs = []
    for jsonl_file in sorted(log_dir.glob("trades_*.jsonl")):
        with open(jsonl_file, "r") as f:
            for line in f:
                trade_logs.append(json.loads(line))

    if not trade_logs:
        print("❌ No trade logs found")
        return {}

    # PnL 계산 (간단히 fills의 price 차이로 계산, 실제로는 더 복잡함)
    total_pnl = 0.0
    win_count = 0
    loss_count = 0
    loss_streak = 0
    max_loss_streak = 0

    for log in trade_logs:
        # 간단한 PnL 추정 (실제로는 entry_price - exit_price 계산 필요)
        # 여기서는 slippage_usd를 PnL 대신 사용 (임시)
        pnl = -log.get("slippage_usd", 0.0)  # 임시: slippage를 손실로 간주
        total_pnl += pnl

        if pnl >= 0:
            win_count += 1
            loss_streak = 0
        else:
            loss_count += 1
            loss_streak += 1
            max_loss_streak = max(max_loss_streak, loss_streak)

    # 분석 결과
    total_trades = len(trade_logs)
    winrate = win_count / total_trades if total_trades > 0 else 0.0

    return {
        "total_trades": total_trades,
        "total_pnl_usd": total_pnl,
        "win_count": win_count,
        "loss_count": loss_count,
        "winrate": winrate,
        "max_loss_streak": max_loss_streak,
    }


def main():
    parser = argparse.ArgumentParser(description="Session Risk Analysis")
    parser.add_argument("log_dir", type=Path, help="Trade log directory")

    args = parser.parse_args()

    if not args.log_dir.exists():
        print(f"❌ Directory not found: {args.log_dir}")
        return

    print("=" * 60)
    print("Session Risk Analysis")
    print("=" * 60)

    result = analyze_trade_logs(args.log_dir)

    if not result:
        return

    # 결과 출력
    print(f"Total trades: {result['total_trades']}")
    print(f"Total PnL: ${result['total_pnl_usd']:.2f}")
    print(f"Win/Loss: {result['win_count']}/{result['loss_count']}")
    print(f"Winrate: {result['winrate']*100:.1f}%")
    print(f"Max loss streak: {result['max_loss_streak']}")

    # Session Risk 체크 (예시, equity는 별도 계산 필요)
    equity_usd = 125.0  # 예: 0.0025 BTC × $50,000
    daily_loss_cap = equity_usd * 0.05  # -5%

    print("\n" + "=" * 60)
    print("Session Risk Status")
    print("=" * 60)
    print(f"Equity: ${equity_usd:.2f}")
    print(f"Daily Loss Cap: -${daily_loss_cap:.2f} (-5%)")

    if result['total_pnl_usd'] < -daily_loss_cap:
        print(f"⚠️ Daily Loss Cap EXCEEDED: ${result['total_pnl_usd']:.2f} < -${daily_loss_cap:.2f}")
    else:
        print(f"✅ Daily Loss Cap OK: ${result['total_pnl_usd']:.2f} > -${daily_loss_cap:.2f}")

    if result['max_loss_streak'] >= 3:
        print(f"⚠️ Loss Streak Kill: {result['max_loss_streak']} >= 3")
    else:
        print(f"✅ Loss Streak OK: {result['max_loss_streak']} < 3")

    print("=" * 60)


if __name__ == "__main__":
    main()
