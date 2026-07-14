#!/usr/bin/env python3
"""
scripts/param_advisor.py

CBGB 파라미터 어드바이저 CLI

사용법:
    # Phase 1: 통계 기반 추천 (즉시 사용 가능)
    python scripts/param_advisor.py

    # Phase 2: Bayesian Optimization (50+ trades)
    python scripts/param_advisor.py --phase2

    # 특정 로그 디렉토리 지정
    python scripts/param_advisor.py --log-dir logs/mainnet

    # JSON 출력 (자동화용)
    python scripts/param_advisor.py --json
"""

import argparse
import json
import sys
from pathlib import Path

# ── 프로젝트 루트를 sys.path에 추가 ──
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.application.param_advisor import (
    TradingParams,
    compute_stats,
    format_report,
    generate_recommendations,
    load_all_trades,
    run_bayesian_optimization,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CBGB 파라미터 어드바이저",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--log-dir",
        default="logs/mainnet",
        help="트레이드 로그 디렉토리 (default: logs/mainnet)",
    )
    parser.add_argument(
        "--phase2",
        action="store_true",
        help="Phase 2: Bayesian Optimization 실행 (optuna 필요)",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=200,
        help="Bayesian 시도 횟수 (default: 200)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON 형식으로 출력",
    )
    parser.add_argument(
        "--t-trend",
        type=float,
        default=0.5,
        help="현재 T_TREND 값 (default: 0.5)",
    )
    parser.add_argument(
        "--t-range",
        type=float,
        default=0.02,
        help="현재 T_RANGE_ENTRY 값 (default: 0.02)",
    )
    parser.add_argument(
        "--f-extreme",
        type=float,
        default=0.01,
        help="현재 F_EXTREME 값 (default: 0.01)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    log_dir = ROOT / args.log_dir
    if not log_dir.exists():
        print(f"[ERROR] 로그 디렉토리 없음: {log_dir}", file=sys.stderr)
        return 1

    # ── 데이터 로드 ──
    print(f"로그 로드 중: {log_dir}", file=sys.stderr)
    trades = load_all_trades(log_dir)

    if not trades:
        print("[ERROR] 완료된 트레이드 없음 (exit_price 필요)", file=sys.stderr)
        return 1

    print(f"로드된 트레이드: {len(trades)}건", file=sys.stderr)

    # ── 현재 파라미터 ──
    current_params = TradingParams(
        t_trend=args.t_trend,
        t_range_entry=args.t_range,
        f_extreme=args.f_extreme,
    )

    # ── 통계 계산 ──
    stats = compute_stats(trades)

    # ── Phase 2: Bayesian Optimization ──
    if args.phase2:
        if len(trades) < 20:
            print(f"[WARNING] Phase 2는 50건 이상 권장. 현재 {len(trades)}건 (계속 진행...)", file=sys.stderr)
        print(f"Bayesian Optimization 실행 중 ({args.trials}회 시도)...", file=sys.stderr)
        try:
            optimal = run_bayesian_optimization(trades, n_trials=args.trials)
            if args.json:
                result = {
                    "phase": 2,
                    "trades": len(trades),
                    "optimal_params": {
                        "t_trend": optimal.t_trend,
                        "t_range_entry": optimal.t_range_entry,
                        "f_extreme": optimal.f_extreme,
                        "atr_sl_mult": optimal.atr_sl_mult,
                        "atr_trail_mult": optimal.atr_trail_mult,
                    },
                }
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print("\n[ Phase 2: Bayesian Optimization 결과 ]")
                print(f"  T_TREND:        {current_params.t_trend} → {optimal.t_trend}")
                print(f"  T_RANGE_ENTRY:  {current_params.t_range_entry} → {optimal.t_range_entry}")
                print(f"  F_EXTREME:      {current_params.f_extreme} → {optimal.f_extreme}")
                print(f"  ATR_SL_MULT:    {current_params.atr_sl_mult} → {optimal.atr_sl_mult}")
                print(f"  ATR_TRAIL_MULT: {current_params.atr_trail_mult} → {optimal.atr_trail_mult}")
                print("\n주의: 수동으로 signal_generator.py에 적용하세요.")
        except ImportError as e:
            print(f"[ERROR] {e}", file=sys.stderr)
            return 1
        return 0

    # ── Phase 1: 통계 기반 추천 ──
    recs = generate_recommendations(stats, current_params)

    if args.json:
        result = {
            "phase": 1,
            "trades": stats.total_trades,
            "win_rate": stats.win_rate,
            "avg_pnl": stats.avg_pnl,
            "net_pnl": stats.net_pnl,
            "sharpe": stats.sharpe_approx,
            "by_regime": {
                r: {
                    "count": rs.count,
                    "win_rate": rs.win_rate,
                    "avg_pnl": rs.avg_pnl,
                }
                for r, rs in stats.by_regime.items()
            },
            "recommendations": [
                {
                    "param": r.param,
                    "current": r.current,
                    "suggested": r.suggested,
                    "reason": r.reason,
                    "confidence": r.confidence,
                    "sample_size": r.sample_size,
                }
                for r in recs
                if r.param != "_WARNING"
            ],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        report = format_report(stats, recs, current_params)
        print(report)

    return 0


if __name__ == "__main__":
    sys.exit(main())
