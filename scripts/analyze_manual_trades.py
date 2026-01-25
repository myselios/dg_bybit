#!/usr/bin/env python3
"""
scripts/analyze_manual_trades.py
Manual Dry-Run 거래 분석 스크립트

실행:
    python scripts/analyze_manual_trades.py logs/testnet_dry_run/trades_manual.csv
"""

import csv
import argparse
from pathlib import Path
from datetime import datetime


def analyze_trades(csv_file: Path):
    """
    Manual Dry-Run CSV 파일 분석

    Args:
        csv_file: CSV 파일 경로
    """
    if not csv_file.exists():
        print(f"❌ File not found: {csv_file}")
        return

    # CSV 읽기
    trades = []
    with open(csv_file, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            trades.append(row)

    if not trades:
        print("❌ No trades found in CSV")
        return

    # 분석
    total_trades = len(trades)
    win_count = 0
    loss_count = 0
    total_pnl = 0.0
    loss_streak = 0
    max_loss_streak = 0

    for trade in trades:
        pnl = float(trade["pnl_usd"])
        total_pnl += pnl

        if pnl >= 0:
            win_count += 1
            loss_streak = 0
        else:
            loss_count += 1
            loss_streak += 1
            max_loss_streak = max(max_loss_streak, loss_streak)

    winrate = win_count / total_trades if total_trades > 0 else 0.0

    # Session Risk 체크
    equity_usd = 125.0  # 0.0025 BTC × $50,000
    daily_loss_cap = equity_usd * 0.05  # -5%
    weekly_loss_cap = equity_usd * 0.125  # -12.5%

    daily_cap_exceeded = total_pnl < -daily_loss_cap
    weekly_cap_exceeded = total_pnl < -weekly_loss_cap
    loss_streak_kill = max_loss_streak >= 3

    # 결과 출력
    print("=" * 60)
    print("Manual Trades Analysis")
    print("=" * 60)
    print(f"Total trades: {total_trades}")
    print(f"Win/Loss: {win_count}/{loss_count}")
    print(f"Winrate: {winrate*100:.1f}%")
    print(f"Total PnL: ${total_pnl:.2f}")
    print(f"Max loss streak: {max_loss_streak}")
    print()
    print("=" * 60)
    print("Session Risk Status")
    print("=" * 60)
    print(f"Equity: ${equity_usd:.2f}")
    print(f"Daily Loss Cap: -${daily_loss_cap:.2f} (-5%)")
    print(f"Weekly Loss Cap: -${weekly_loss_cap:.2f} (-12.5%)")
    print()

    if daily_cap_exceeded:
        print(f"⚠️ Daily Loss Cap EXCEEDED: ${total_pnl:.2f} < -${daily_loss_cap:.2f}")
    else:
        print(f"✅ Daily Loss Cap OK: ${total_pnl:.2f} > -${daily_loss_cap:.2f}")

    if weekly_cap_exceeded:
        print(f"⚠️ Weekly Loss Cap EXCEEDED: ${total_pnl:.2f} < -${weekly_loss_cap:.2f}")
    else:
        print(f"✅ Weekly Loss Cap OK: ${total_pnl:.2f} > -${weekly_loss_cap:.2f}")

    if loss_streak_kill:
        print(f"⚠️ Loss Streak Kill: {max_loss_streak} >= 3")
    else:
        print(f"✅ Loss Streak OK: {max_loss_streak} < 3")

    print("=" * 60)

    # DoD 체크
    print()
    print("=" * 60)
    print("Phase 12a DoD Verification")
    print("=" * 60)

    dod_trades = total_trades >= 30
    dod_session_risk = daily_cap_exceeded or weekly_cap_exceeded or loss_streak_kill
    dod_stop_loss = loss_count >= 5  # 최소 5회 stop hit

    print(f"✅ Total trades >= 30: {dod_trades} ({total_trades}/30)")
    print(f"✅ Session Risk 발동 >= 1: {dod_session_risk}")
    print(f"✅ Stop loss hits >= 5: {dod_stop_loss} ({loss_count}/5)")

    if dod_trades and dod_session_risk and dod_stop_loss:
        print("\n🎯 Phase 12a DoD: ✅ COMPLETE")
    else:
        print("\n⏳ Phase 12a DoD: IN PROGRESS")

    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Analyze Manual Dry-Run Trades")
    parser.add_argument("csv_file", type=Path, help="CSV file path")

    args = parser.parse_args()

    analyze_trades(args.csv_file)


if __name__ == "__main__":
    main()
