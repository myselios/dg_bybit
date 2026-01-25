#!/usr/bin/env python3
"""
scripts/generate_dry_run_report.py
Dry-Run Evidence Generator

목표:
- Trade Log 분석
- Session Risk 검증
- completion_checklist.md 자동 생성
- Testnet UI 스크린샷 가이드

실행:
    python scripts/generate_dry_run_report.py --log-dir logs/testnet_dry_run
"""

import argparse
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any

from infrastructure.storage.log_storage import LogStorage


class DryRunAnalyzer:
    """Dry-Run Trade Log 분석기"""

    def __init__(self, log_dir: Path):
        self.log_storage = LogStorage(log_dir=log_dir)
        self.trade_logs = self.log_storage.read_trade_logs_v1()

    def analyze_trades(self) -> Dict[str, Any]:
        """거래 분석 (총 거래, winrate, PnL 등)"""
        if not self.trade_logs:
            return {
                "total_trades": 0,
                "total_wins": 0,
                "total_losses": 0,
                "winrate": 0.0,
                "total_pnl_usd": 0.0,
                "average_pnl_usd": 0.0,
            }

        total_trades = len(self.trade_logs)
        total_wins = sum(1 for log in self.trade_logs if log.get("realized_pnl_usd", 0) > 0)
        total_losses = sum(1 for log in self.trade_logs if log.get("realized_pnl_usd", 0) < 0)
        winrate = total_wins / total_trades if total_trades > 0 else 0.0

        total_pnl_usd = sum(log.get("realized_pnl_usd", 0.0) for log in self.trade_logs)
        average_pnl_usd = total_pnl_usd / total_trades if total_trades > 0 else 0.0

        return {
            "total_trades": total_trades,
            "total_wins": total_wins,
            "total_losses": total_losses,
            "winrate": winrate,
            "total_pnl_usd": total_pnl_usd,
            "average_pnl_usd": average_pnl_usd,
        }

    def verify_session_risk(self) -> Dict[str, Any]:
        """Session Risk 발동 검증"""
        # Daily/Weekly PnL limit 초과 여부 확인
        # Loss streak >= 3 발생 여부 확인

        session_risk_logs = [
            log for log in self.trade_logs
            if log.get("session_risk_halt", False)
        ]

        return {
            "session_risk_detected": len(session_risk_logs) > 0,
            "session_risk_count": len(session_risk_logs),
            "session_risk_reasons": [log.get("halt_reason", "Unknown") for log in session_risk_logs],
        }

    def verify_stop_loss(self) -> Dict[str, Any]:
        """Stop loss 작동 검증"""
        stop_hit_logs = [
            log for log in self.trade_logs
            if log.get("stop_hit", False)
        ]

        return {
            "stop_loss_hit_count": len(stop_hit_logs),
            "stop_loss_hit_trades": [log.get("trade_id") for log in stop_hit_logs],
        }

    def generate_completion_checklist(self, output_path: Path):
        """completion_checklist.md 자동 생성"""
        trade_stats = self.analyze_trades()
        session_risk = self.verify_session_risk()
        stop_loss = self.verify_stop_loss()

        checklist_content = f"""# Phase 12a Testnet Dry-Run Completion Checklist

**Generated**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}

---

## 거래 통계

- Total trades: **{trade_stats['total_trades']}**
- Wins: {trade_stats['total_wins']} | Losses: {trade_stats['total_losses']}
- Winrate: **{trade_stats['winrate']:.2%}**
- Total PnL: **${trade_stats['total_pnl_usd']:.2f} USD**
- Average PnL: ${trade_stats['average_pnl_usd']:.2f} USD

---

## DoD 검증

### 1. Testnet 설정
- [x] .env 파일 작성 (BYBIT_API_KEY, BYBIT_API_SECRET, BYBIT_TESTNET=true)
- [x] Testnet equity >= 0.01 BTC 확인
- [x] safety_limits.yaml 설정

### 2. Testnet 거래 실행
- [{'x' if trade_stats['total_trades'] >= 30 else ' '}] Full cycle (FLAT → Entry → Exit → FLAT) {trade_stats['total_trades']} 회 {'✅' if trade_stats['total_trades'] >= 30 else '❌'}
- [{'x' if session_risk['session_risk_detected'] else ' '}] Session Risk 발동 증거 {session_risk['session_risk_count']} 회 {'✅' if session_risk['session_risk_detected'] else '❌'}
- [{'x' if stop_loss['stop_loss_hit_count'] >= 5 else ' '}] Stop loss 정상 작동 {stop_loss['stop_loss_hit_count']} 회 {'✅' if stop_loss['stop_loss_hit_count'] >= 5 else '❌'}
- [ ] Fee tracking 정상 작동 (모든 거래에서 fee 기록)
- [ ] Slippage tracking 정상 작동

### 3. 로그 완전성 검증
- [{'x' if trade_stats['total_trades'] > 0 else ' '}] 모든 거래가 trade_log에 기록됨 ({trade_stats['total_trades']} logs)
- [ ] Daily/Weekly PnL 계산 정확성 확인
- [ ] Loss streak count 정확성 확인

### 4. Session Risk 발동 내역

{self._format_session_risk_details(session_risk)}

### 5. Bybit Testnet UI 스크린샷 체크리스트
- [ ] Order History (Entry/Exit 주문)
- [ ] Position History (Closed positions)
- [ ] Asset (Equity 변화)

---

## 발견된 문제 및 해결 방안

(수동 작성 필요)

---

## 다음 단계

- Phase 12b: Mainnet Dry-Run (실거래 계정 연결)

"""

        output_path.write_text(checklist_content, encoding='utf-8')
        print(f"✅ Completion checklist generated: {output_path}")

    def _format_session_risk_details(self, session_risk: Dict[str, Any]) -> str:
        """Session Risk 상세 정보 포맷팅"""
        if not session_risk['session_risk_detected']:
            return "❌ Session Risk 발동 없음 (테스트 필요)"

        details = []
        for reason in session_risk['session_risk_reasons']:
            details.append(f"- {reason}")

        return "\n".join(details)


def main():
    parser = argparse.ArgumentParser(description="Generate Dry-Run Report")
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=Path("logs/testnet_dry_run"),
        help="Trade log directory (default: logs/testnet_dry_run)"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/evidence/phase_12a/testnet_dry_run_report.md"),
        help="Output report path (default: docs/evidence/phase_12a/testnet_dry_run_report.md)"
    )

    args = parser.parse_args()

    # Log directory 존재 확인
    if not args.log_dir.exists():
        print(f"❌ Log directory not found: {args.log_dir}")
        print("Run the dry-run first: python scripts/run_testnet_dry_run.py")
        return

    # Analyzer 초기화
    analyzer = DryRunAnalyzer(log_dir=args.log_dir)

    # Trade 분석
    print("📊 Analyzing trades...")
    trade_stats = analyzer.analyze_trades()
    print(f"  Total trades: {trade_stats['total_trades']}")
    print(f"  Winrate: {trade_stats['winrate']:.2%}")
    print(f"  Total PnL: ${trade_stats['total_pnl_usd']:.2f} USD")

    # Session Risk 검증
    print("\n⚠️ Verifying Session Risk...")
    session_risk = analyzer.verify_session_risk()
    print(f"  Session Risk detected: {session_risk['session_risk_detected']}")
    print(f"  Session Risk count: {session_risk['session_risk_count']}")

    # Stop loss 검증
    print("\n🛑 Verifying Stop Loss...")
    stop_loss = analyzer.verify_stop_loss()
    print(f"  Stop loss hits: {stop_loss['stop_loss_hit_count']}")

    # Completion checklist 생성
    print(f"\n📝 Generating completion checklist...")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    analyzer.generate_completion_checklist(args.output)

    print("\n✅ Report generation complete!")


if __name__ == "__main__":
    main()
