#!/usr/bin/env python3
"""
analyze_trades.py

Phase 13a: Trade Log Analysis CLI Tool

Usage:
    # Normal analysis mode
    python analyze_trades.py --period 2026-01-01:2026-01-31 --output reports/jan_2026.md

    # A/B comparison mode
    python analyze_trades.py --compare --before 2026-01-01:2026-01-15 --after 2026-01-16:2026-01-31 --output reports/comparison.md
"""

import sys
import argparse
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analysis import (
    TradeAnalyzer,
    ABComparator,
    ReportGenerator,
)


def parse_period(period_str: str) -> tuple:
    """
    기간 문자열 파싱

    Args:
        period_str: "YYYY-MM-DD:YYYY-MM-DD" 형식

    Returns:
        tuple: (start_date, end_date)
    """
    try:
        start, end = period_str.split(':')
        return start, end
    except ValueError:
        raise ValueError(f"Invalid period format: {period_str}. Expected YYYY-MM-DD:YYYY-MM-DD")


def main():
    parser = argparse.ArgumentParser(
        description='CBGB Trade Log Analysis Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Analyze trades for January 2026
    python analyze_trades.py --period 2026-01-01:2026-01-31 --output reports/jan_2026.md

    # Compare two periods
    python analyze_trades.py --compare --before 2026-01-01:2026-01-15 --after 2026-01-16:2026-01-31 --output reports/comparison.md

    # Analyze with JSON output
    python analyze_trades.py --period 2026-01-01:2026-01-31 --output reports/jan_2026.json --format json
        """
    )

    # Mode
    parser.add_argument(
        '--compare',
        action='store_true',
        help='A/B comparison mode'
    )

    # Period arguments
    parser.add_argument(
        '--period',
        help='Analysis period (YYYY-MM-DD:YYYY-MM-DD)'
    )
    parser.add_argument(
        '--before',
        help='Before period for A/B comparison (YYYY-MM-DD:YYYY-MM-DD)'
    )
    parser.add_argument(
        '--after',
        help='After period for A/B comparison (YYYY-MM-DD:YYYY-MM-DD)'
    )

    # Output arguments
    parser.add_argument(
        '--output',
        default='reports/analysis.md',
        help='Output file path (default: reports/analysis.md)'
    )
    parser.add_argument(
        '--format',
        choices=['markdown', 'json'],
        default='markdown',
        help='Output format (default: markdown)'
    )

    # Input arguments
    parser.add_argument(
        '--log-dir',
        default='logs/mainnet',
        help='Trade log directory (default: logs/mainnet)'
    )

    args = parser.parse_args()

    # Validate arguments
    if args.compare:
        if not args.before or not args.after:
            parser.error("--compare requires --before and --after")
    else:
        if not args.period:
            parser.error("--period is required for normal analysis mode")

    # Initialize analyzer
    try:
        analyzer = TradeAnalyzer(log_dir=args.log_dir)
    except FileNotFoundError as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

    generator = ReportGenerator()

    try:
        if args.compare:
            # A/B comparison mode
            print("🔍 A/B Comparison Mode")
            print(f"Before: {args.before}")
            print(f"After: {args.after}")

            start_before, end_before = parse_period(args.before)
            start_after, end_after = parse_period(args.after)

            print("\n📊 Loading trades...")
            before_trades = analyzer.load_trades(start_before, end_before)
            after_trades = analyzer.load_trades(start_after, end_after)

            print(f"✅ Loaded {len(before_trades)} before trades, {len(after_trades)} after trades")

            if not before_trades or not after_trades:
                print("❌ Error: Not enough trades to compare")
                sys.exit(1)

            print("\n📈 Running A/B comparison...")
            comparator = ABComparator()
            result = comparator.compare(before_trades, after_trades)

            print(f"\n✅ Comparison complete:")
            print(f"  Recommendation: {result.recommendation}")
            print(f"  Significant: {'Yes' if result.is_significant else 'No'}")
            print(f"  Winrate delta: {result.winrate_delta_pct*100:+.1f}%")
            print(f"  PnL delta: ${result.pnl_delta_usd:+.2f}")

            # Generate report
            generator.generate_comparison_report(result, args.output)

        else:
            # Normal analysis mode
            print("🔍 Analysis Mode")
            print(f"Period: {args.period}")

            start_date, end_date = parse_period(args.period)

            print("\n📊 Loading trades...")
            trades = analyzer.load_trades(start_date, end_date)
            print(f"✅ Loaded {len(trades)} trades")

            if not trades:
                print("❌ Error: No trades found for the specified period")
                sys.exit(1)

            print("\n📈 Calculating metrics...")
            metrics = analyzer.calculate_metrics(trades)

            print(f"\n✅ Analysis complete:")
            print(f"  Total Trades: {metrics.total_trades}")
            print(f"  Winrate: {metrics.winrate*100:.1f}%")
            print(f"  Total PnL: ${metrics.total_pnl:.2f}")
            print(f"  Sharpe Ratio: {metrics.sharpe_ratio if metrics.sharpe_ratio else 'N/A'}")

            # Generate report
            if args.format == 'json':
                generator.generate_json(metrics, args.output, period=args.period)
            else:
                generator.generate_markdown(metrics, args.output, period=args.period)

    except ValueError as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
