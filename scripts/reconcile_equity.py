#!/usr/bin/env python3
"""
reconcile_equity.py

logs/mainnet/trades_*.jsonl 전체를 읽어 실현 PnL과 수수료로 계좌 equity를 재구성한다.

배경: 리포트의 rolling equity가 2026-03-07부터 가산 오류로 과대계상되었다.
이 스크립트는 원장(trade log)에서 직접 equity를 재계산해 대사(reconciliation)한다.

정의:
- realized_pnl_usd 는 gross(수수료 차감 전) 값이다.
  검증: (exit_price - entry_price) * qty_btc == realized_pnl_usd (LONG 기준).
- net_pnl = gross_pnl - total_fees
- equity  = starting_capital + net_pnl

테스트 잔재 필터:
- config_hash == "test_config_hash"
- realized_pnl_usd 필드 부재

Usage:
    python scripts/reconcile_equity.py [--log-dir logs/mainnet] [--starting-capital 100.0]
"""

import sys
import json
import argparse
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Tuple

TEST_CONFIG_HASH = "test_config_hash"


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class MonthStat:
    """월별 분해 지표"""
    trades: int = 0
    wins: int = 0
    losses: int = 0
    gross_pnl: float = 0.0
    fees: float = 0.0

    @property
    def net_pnl(self) -> float:
        return self.gross_pnl - self.fees


@dataclass
class ReconcileResult:
    """Equity 재구성 결과"""
    starting_capital: float
    total_records: int
    valid_trades: int
    win_count: int
    loss_count: int
    gross_pnl: float
    total_fees: float
    monthly: Dict[str, MonthStat] = field(default_factory=dict)

    @property
    def net_pnl(self) -> float:
        return self.gross_pnl - self.total_fees

    @property
    def equity(self) -> float:
        return self.starting_capital + self.net_pnl


# ============================================================================
# Pure Logic (테스트 대상)
# ============================================================================

def is_valid_record(record: dict) -> bool:
    """테스트 잔재/불완전 레코드 제외 여부."""
    if record.get("config_hash") == TEST_CONFIG_HASH:
        return False
    if "realized_pnl_usd" not in record:
        return False
    return True


def _record_fee(record: dict) -> float:
    """fee_usd 추출 (None/부재 → 0.0)."""
    return float(record.get("fee_usd") or 0.0)


def reconcile(
    dated_records: List[Tuple[str, dict]],
    starting_capital: float = 100.0,
) -> ReconcileResult:
    """
    (YYYY-MM-DD, record) 목록에서 equity를 재구성한다.

    Args:
        dated_records: (파일 날짜, 원시 레코드) 튜플 목록
        starting_capital: 시작 자본 (USDT)

    Returns:
        ReconcileResult
    """
    result = ReconcileResult(
        starting_capital=starting_capital,
        total_records=len(dated_records),
        valid_trades=0,
        win_count=0,
        loss_count=0,
        gross_pnl=0.0,
        total_fees=0.0,
    )
    monthly: Dict[str, MonthStat] = {}

    for date_str, record in dated_records:
        if not is_valid_record(record):
            continue
        pnl = float(record["realized_pnl_usd"])
        fee = _record_fee(record)
        is_win = pnl > 0

        result.valid_trades += 1
        result.gross_pnl += pnl
        result.total_fees += fee
        if is_win:
            result.win_count += 1
        else:
            result.loss_count += 1

        month = date_str[:7]  # YYYY-MM
        stat = monthly.setdefault(month, MonthStat())
        stat.trades += 1
        stat.gross_pnl += pnl
        stat.fees += fee
        if is_win:
            stat.wins += 1
        else:
            stat.losses += 1

    result.monthly = dict(sorted(monthly.items()))
    return result


# ============================================================================
# I/O
# ============================================================================

def iter_log_records(log_dir: Path) -> Iterator[Tuple[str, dict]]:
    """trades_YYYY-MM-DD.jsonl 파일들을 읽어 (날짜, 레코드)를 순회한다."""
    for file_path in sorted(log_dir.glob("trades_*.jsonl")):
        date_str = file_path.stem.replace("trades_", "")
        with open(file_path, "r") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    yield date_str, json.loads(line)
                except json.JSONDecodeError as e:
                    print(f"Warning: Invalid JSON at {file_path}:{line_num} - {e}",
                          file=sys.stderr)


def format_report(result: ReconcileResult) -> str:
    """사람이 읽는 리포트 문자열."""
    lines = [
        "=" * 60,
        "Equity Reconciliation (원장 기반 재계산)",
        "=" * 60,
        f"시작 자본        : ${result.starting_capital:,.2f}",
        f"총 레코드        : {result.total_records}",
        f"유효 거래        : {result.valid_trades} "
        f"(제외 {result.total_records - result.valid_trades})",
        f"승/패            : {result.win_count} / {result.loss_count}",
        "-" * 60,
        f"Gross PnL        : ${result.gross_pnl:+,.4f}",
        f"수수료 합계      : ${result.total_fees:,.4f}",
        f"Net PnL          : ${result.net_pnl:+,.4f}",
        f"재구성 Equity    : ${result.equity:,.2f}",
        "-" * 60,
        "월별 분해 (month: trades W/L gross fees net):",
    ]
    for month, stat in result.monthly.items():
        lines.append(
            f"  {month}: {stat.trades:>3} trades  "
            f"{stat.wins}W/{stat.losses}L  "
            f"gross ${stat.gross_pnl:+.4f}  "
            f"fees ${stat.fees:.4f}  "
            f"net ${stat.net_pnl:+.4f}"
        )
    lines.append("=" * 60)
    return "\n".join(lines)


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconcile account equity from trade logs")
    parser.add_argument("--log-dir", default="logs/mainnet", help="Trade log 디렉토리")
    parser.add_argument("--starting-capital", type=float, default=100.0, help="시작 자본 (USDT)")
    args = parser.parse_args(argv)

    log_dir = Path(args.log_dir)
    if not log_dir.exists():
        print(f"Error: log directory not found: {log_dir}", file=sys.stderr)
        return 1

    dated_records = list(iter_log_records(log_dir))
    result = reconcile(dated_records, starting_capital=args.starting_capital)
    print(format_report(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
