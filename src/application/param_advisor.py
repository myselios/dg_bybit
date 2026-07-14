"""
src/application/param_advisor.py

ML Parameter Advisor (3-Phase)

Phase 1 (현재, 0-50 trades): 통계 기반 규칙 추천
Phase 2 (50+ trades):        Bayesian Optimization (Optuna)
Phase 3 (200+ trades):       Supervised ML (LightGBM)

목표 파라미터:
- T_TREND:        MA slope >= X% → Trend regime 판정 (현재 0.5)
- T_RANGE_ENTRY:  MA slope >= X% → Range 진입 허용 (현재 0.02)
- F_EXTREME:      |funding| >= X → 극단 과열 판정 (현재 0.01)
- ATR_SL_MULT:    SL = ATR * X (현재 0.7)
- ATR_TRAIL_MULT: Trailing = ATR * X (현재 0.5)
- ATR_GRID_MULT:  Grid spacing = ATR * X (현재 0.2)

Exports:
- load_all_trades(log_dir): 전체 트레이드 로드
- compute_stats(trades):    통계 계산
- generate_recommendations(stats): 파라미터 추천
- format_report(stats, recs, current_params): 텍스트 보고서
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ─────────────────────────────────────────────
#  현재 파라미터 기본값 (SSOT: signal_generator.py)
# ─────────────────────────────────────────────
@dataclass
class TradingParams:
    t_trend: float = 0.5        # %
    t_range_entry: float = 0.02  # %
    f_extreme: float = 0.01
    atr_sl_mult: float = 0.7
    atr_trail_mult: float = 0.5
    atr_grid_mult: float = 0.2


# ─────────────────────────────────────────────
#  통계 데이터 구조
# ─────────────────────────────────────────────
@dataclass
class RegimeStats:
    regime: str
    count: int = 0
    wins: int = 0
    total_pnl: float = 0.0
    total_fee: float = 0.0
    hold_seconds: list[float] = field(default_factory=list)

    @property
    def win_rate(self) -> float:
        return self.wins / self.count if self.count > 0 else 0.0

    @property
    def avg_pnl(self) -> float:
        return self.total_pnl / self.count if self.count > 0 else 0.0

    @property
    def avg_hold_min(self) -> Optional[float]:
        valid = [h for h in self.hold_seconds if h is not None]
        if not valid:
            return None
        return sum(valid) / len(valid) / 60.0

    @property
    def net_pnl(self) -> float:
        return self.total_pnl - self.total_fee


@dataclass
class OverallStats:
    total_trades: int = 0
    wins: int = 0
    total_pnl: float = 0.0
    total_fee: float = 0.0
    max_loss: float = 0.0
    max_win: float = 0.0
    by_regime: dict[str, RegimeStats] = field(default_factory=dict)
    by_direction: dict[str, RegimeStats] = field(default_factory=dict)
    pnl_list: list[float] = field(default_factory=list)

    @property
    def win_rate(self) -> float:
        return self.wins / self.total_trades if self.total_trades > 0 else 0.0

    @property
    def avg_pnl(self) -> float:
        return self.total_pnl / self.total_trades if self.total_trades > 0 else 0.0

    @property
    def net_pnl(self) -> float:
        return self.total_pnl - self.total_fee

    @property
    def sharpe_approx(self) -> Optional[float]:
        """트레이드 단위 Sharpe 근사 (daily 기준 아닌 per-trade)"""
        if len(self.pnl_list) < 3:
            return None
        n = len(self.pnl_list)
        mean = sum(self.pnl_list) / n
        variance = sum((x - mean) ** 2 for x in self.pnl_list) / n
        std = math.sqrt(variance) if variance > 0 else 0.0
        if std == 0:
            return None
        return mean / std


# ─────────────────────────────────────────────
#  데이터 로드
# ─────────────────────────────────────────────
def load_all_trades(log_dir: str | Path) -> list[dict]:
    """
    trades_*.jsonl 전체 로드

    완료된 트레이드만 반환 (exit_price 있는 것).
    """
    log_path = Path(log_dir)
    trades = []
    for f in sorted(log_path.glob("trades_*.jsonl")):
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    t = json.loads(line)
                    # 완료된 트레이드 필터 (exit_price 필수)
                    if t.get("exit_price") and t.get("entry_price"):
                        trades.append(t)
                except json.JSONDecodeError:
                    continue
    return trades


# ─────────────────────────────────────────────
#  통계 계산
# ─────────────────────────────────────────────
def compute_stats(trades: list[dict]) -> OverallStats:
    """전체 통계 계산 (regime별, direction별)"""
    stats = OverallStats()
    stats.total_trades = len(trades)

    for t in trades:
        pnl = t.get("realized_pnl_usd", 0.0) or 0.0
        fee = t.get("fee_usd", 0.0) or 0.0
        regime = t.get("market_regime", "unknown")
        direction = t.get("direction", "unknown")
        hold = t.get("hold_seconds")

        stats.total_pnl += pnl
        stats.total_fee += fee
        stats.pnl_list.append(pnl)

        if pnl > 0:
            stats.wins += 1
        stats.max_loss = min(stats.max_loss, pnl)
        stats.max_win = max(stats.max_win, pnl)

        # regime별
        if regime not in stats.by_regime:
            stats.by_regime[regime] = RegimeStats(regime=regime)
        rs = stats.by_regime[regime]
        rs.count += 1
        rs.total_pnl += pnl
        rs.total_fee += fee
        if pnl > 0:
            rs.wins += 1
        if hold is not None:
            rs.hold_seconds.append(hold)

        # direction별
        if direction not in stats.by_direction:
            stats.by_direction[direction] = RegimeStats(regime=direction)
        ds = stats.by_direction[direction]
        ds.count += 1
        ds.total_pnl += pnl
        ds.total_fee += fee
        if pnl > 0:
            ds.wins += 1
        if hold is not None:
            ds.hold_seconds.append(hold)

    return stats


# ─────────────────────────────────────────────
#  파라미터 추천 (Phase 1: 통계 기반 규칙)
# ─────────────────────────────────────────────
@dataclass
class Recommendation:
    param: str
    current: float
    suggested: float
    reason: str
    confidence: str  # "LOW" / "MEDIUM" / "HIGH"
    sample_size: int


def _confidence(n: int) -> str:
    """샘플 크기 → 신뢰도"""
    if n < 5:
        return "LOW"
    if n < 15:
        return "MEDIUM"
    return "HIGH"


def generate_recommendations(
    stats: OverallStats,
    params: TradingParams | None = None,
) -> list[Recommendation]:
    """
    통계 기반 파라미터 추천 (Phase 1)

    규칙:
    - Range regime 승률 < 40% → T_RANGE_ENTRY 상향 (진입 엄격화)
    - Range regime 승률 > 60% → T_RANGE_ENTRY 하향 (기회 확대)
    - Trend 승률 < 40% → T_TREND 상향 (엄격한 추세 판정)
    - Overall 승률 < 40% → ATR_SL_MULT 하향 (SL 좁히기)
    - avg_pnl < -2.0 USD → 전략 재검토 경고
    - Sharpe < -0.3 → 전반적 파라미터 재검토
    """
    if params is None:
        params = TradingParams()
    recs = []
    n_total = stats.total_trades

    # ── Range regime 분석 ──
    range_stat = stats.by_regime.get("ranging") or stats.by_regime.get("range")
    if range_stat and range_stat.count >= 3:
        wr = range_stat.win_rate
        if wr < 0.40:
            # Range에서 지고 있음 → 진입 기준 높임
            new_val = round(min(params.t_range_entry * 2.0, 0.5), 4)
            recs.append(Recommendation(
                param="T_RANGE_ENTRY",
                current=params.t_range_entry,
                suggested=new_val,
                reason=f"Range regime 승률 {wr:.0%} < 40%. 진입 기준 상향으로 약한 신호 필터링.",
                confidence=_confidence(range_stat.count),
                sample_size=range_stat.count,
            ))
        elif wr > 0.65:
            # Range에서 잘 됨 → 더 공격적으로
            new_val = round(max(params.t_range_entry * 0.5, 0.005), 4)
            recs.append(Recommendation(
                param="T_RANGE_ENTRY",
                current=params.t_range_entry,
                suggested=new_val,
                reason=f"Range regime 승률 {wr:.0%} > 65%. 기준 완화로 기회 확대.",
                confidence=_confidence(range_stat.count),
                sample_size=range_stat.count,
            ))

    # ── Trend regime 분석 ──
    trend_up = stats.by_regime.get("trending_up")
    trend_down = stats.by_regime.get("trending_down")
    trend_trades = 0
    trend_wins = 0
    trend_pnl = 0.0
    for ts in [trend_up, trend_down]:
        if ts:
            trend_trades += ts.count
            trend_wins += ts.wins
            trend_pnl += ts.total_pnl

    if trend_trades >= 3:
        wr = trend_wins / trend_trades
        if wr < 0.40:
            new_val = round(min(params.t_trend * 1.5, 2.0), 2)
            recs.append(Recommendation(
                param="T_TREND",
                current=params.t_trend,
                suggested=new_val,
                reason=f"Trend regime 승률 {wr:.0%} < 40%. 더 강한 추세만 필터링.",
                confidence=_confidence(trend_trades),
                sample_size=trend_trades,
            ))
        elif wr > 0.70:
            new_val = round(max(params.t_trend * 0.7, 0.2), 2)
            recs.append(Recommendation(
                param="T_TREND",
                current=params.t_trend,
                suggested=new_val,
                reason=f"Trend regime 승률 {wr:.0%} > 70%. 기준 완화로 추세 포착 확대.",
                confidence=_confidence(trend_trades),
                sample_size=trend_trades,
            ))

    # ── 전체 승률 기반 SL 조정 ──
    if n_total >= 5:
        overall_wr = stats.win_rate
        if overall_wr < 0.35:
            # 지고 있음 → SL 조금 좁혀서 손실 줄이기
            new_sl = round(max(params.atr_sl_mult * 0.8, 0.4), 2)
            recs.append(Recommendation(
                param="ATR_SL_MULT",
                current=params.atr_sl_mult,
                suggested=new_sl,
                reason=f"전체 승률 {overall_wr:.0%} < 35%. SL 좁혀 손실 제한 (현재 ATR*{params.atr_sl_mult}).",
                confidence=_confidence(n_total),
                sample_size=n_total,
            ))

        # ── 평균 수익이 평균 손실보다 너무 작음 → Trailing 넓히기 ──
        win_pnls = [p for p in stats.pnl_list if p > 0]
        loss_pnls = [p for p in stats.pnl_list if p < 0]
        if win_pnls and loss_pnls:
            avg_win = sum(win_pnls) / len(win_pnls)
            avg_loss = abs(sum(loss_pnls) / len(loss_pnls))
            rr_actual = avg_win / avg_loss if avg_loss > 0 else 0
            if rr_actual < 1.5 and overall_wr > 0.40:
                new_trail = round(min(params.atr_trail_mult * 1.3, 1.5), 2)
                recs.append(Recommendation(
                    param="ATR_TRAIL_MULT",
                    current=params.atr_trail_mult,
                    suggested=new_trail,
                    reason=f"실측 R:R={rr_actual:.2f} < 1.5, 승률 {overall_wr:.0%}. Trailing 범위 확대로 수익 극대화.",
                    confidence=_confidence(n_total),
                    sample_size=n_total,
                ))

    # ── 샘플 부족 경고 ──
    if n_total < 10:
        recs.append(Recommendation(
            param="_WARNING",
            current=0,
            suggested=0,
            reason=f"⚠️  트레이드 {n_total}개 — 통계 신뢰도 낮음. 10건 이상 축적 후 적용 권장.",
            confidence="LOW",
            sample_size=n_total,
        ))

    return recs


# ─────────────────────────────────────────────
#  보고서 포매팅
# ─────────────────────────────────────────────
def format_report(
    stats: OverallStats,
    recs: list[Recommendation],
    params: TradingParams | None = None,
) -> str:
    if params is None:
        params = TradingParams()

    lines = []
    lines.append("=" * 60)
    lines.append("  CBGB Parameter Advisor Report (Phase 1: Statistical)")
    lines.append("=" * 60)
    lines.append("")

    # ── 전체 성과 ──
    lines.append("[ 전체 성과 ]")
    lines.append(f"  총 트레이드: {stats.total_trades}")
    lines.append(f"  승률: {stats.win_rate:.1%}  (승 {stats.wins} / 패 {stats.total_trades - stats.wins})")
    lines.append(f"  총 PnL: ${stats.total_pnl:+.2f}  (수수료 ${stats.total_fee:.2f} 제외: ${stats.net_pnl:+.2f})")
    lines.append(f"  최대 손실: ${stats.max_loss:.2f}")
    lines.append(f"  최대 수익: ${stats.max_win:.2f}")
    if stats.sharpe_approx is not None:
        lines.append(f"  Sharpe (per-trade): {stats.sharpe_approx:.3f}")
    lines.append("")

    # ── Regime별 ──
    if stats.by_regime:
        lines.append("[ Regime별 성과 ]")
        for regime, rs in sorted(stats.by_regime.items()):
            hold_str = f"{rs.avg_hold_min:.0f}분" if rs.avg_hold_min is not None else "N/A"
            lines.append(
                f"  {regime:15s}  n={rs.count:2d}  승률={rs.win_rate:.0%}"
                f"  PnL=${rs.total_pnl:+.2f}  hold={hold_str}"
            )
        lines.append("")

    # ── Direction별 ──
    if stats.by_direction:
        lines.append("[ Direction별 성과 ]")
        for direction, ds in sorted(stats.by_direction.items()):
            lines.append(
                f"  {direction:8s}  n={ds.count:2d}  승률={ds.win_rate:.0%}"
                f"  PnL=${ds.total_pnl:+.2f}"
            )
        lines.append("")

    # ── 현재 파라미터 ──
    lines.append("[ 현재 파라미터 ]")
    lines.append(f"  T_TREND        = {params.t_trend}%")
    lines.append(f"  T_RANGE_ENTRY  = {params.t_range_entry}%")
    lines.append(f"  F_EXTREME      = {params.f_extreme}")
    lines.append(f"  ATR_SL_MULT    = {params.atr_sl_mult}")
    lines.append(f"  ATR_TRAIL_MULT = {params.atr_trail_mult}")
    lines.append(f"  ATR_GRID_MULT  = {params.atr_grid_mult}")
    lines.append("")

    # ── 추천 ──
    if recs:
        lines.append("[ 파라미터 추천 ]")
        for rec in recs:
            if rec.param == "_WARNING":
                lines.append(f"  {rec.reason}")
                continue
            arrow = "↑" if rec.suggested > rec.current else "↓"
            change_pct = (rec.suggested - rec.current) / rec.current * 100 if rec.current != 0 else 0
            lines.append(f"  [{rec.confidence}] {rec.param}: {rec.current} {arrow} {rec.suggested} ({change_pct:+.0f}%)")
            lines.append(f"       {rec.reason}")
            lines.append(f"       (샘플 {rec.sample_size}건 기반)")
            lines.append("")
    else:
        lines.append("[ 파라미터 추천 ]")
        lines.append("  현재 파라미터 유지 권장 (충분한 이탈 신호 없음)")
        lines.append("")

    # ── 다음 단계 안내 ──
    lines.append("[ 다음 단계 ]")
    n = stats.total_trades
    if n < 50:
        lines.append(f"  Phase 1 (통계): 진행 중 ({n}/50 trades)")
        lines.append(f"  Phase 2 (Bayesian Optuna): {50 - n}건 더 쌓이면 자동 활성화")
        lines.append(f"  Phase 3 (LightGBM ML):     {200 - n}건 더 쌓이면 자동 활성화")
    elif n < 200:
        lines.append(f"  Phase 2 (Bayesian Optuna): 활성화 가능 ({n}/200 trades)")
        lines.append(f"  Phase 3 (LightGBM ML):     {200 - n}건 더 필요")
        lines.append("  → 'python scripts/param_advisor.py --phase2' 실행하세요")
    else:
        lines.append(f"  Phase 3 (LightGBM ML): 활성화 가능 ({n} trades)")
        lines.append("  → 'python scripts/param_advisor.py --phase3' 실행하세요")
    lines.append("")
    lines.append("=" * 60)

    return "\n".join(lines)


# ─────────────────────────────────────────────
#  Phase 2: Bayesian Optimization (50+ trades)
# ─────────────────────────────────────────────
def run_bayesian_optimization(
    trades: list[dict],
    n_trials: int = 100,
) -> TradingParams:
    """
    Optuna를 사용한 Bayesian Optimization (Phase 2)

    최적화 대상: 트레이드 데이터에서 regime/funding 조건별 시뮬레이션
    목적 함수: Sharpe ratio (per-trade 기준)

    Returns:
        최적 파라미터 (TradingParams)
    """
    try:
        import optuna
        optuna.logging.set_verbosity(optuna.logging.WARNING)
    except ImportError:
        raise ImportError("Optuna 미설치. `pip install optuna` 후 실행하세요.")

    def objective(trial: "optuna.Trial") -> float:
        t_trend = trial.suggest_float("t_trend", 0.2, 2.0)
        t_range_entry = trial.suggest_float("t_range_entry", 0.005, 0.5)
        f_extreme = trial.suggest_float("f_extreme", 0.001, 0.05)
        atr_sl_mult = trial.suggest_float("atr_sl_mult", 0.3, 1.5)
        atr_trail_mult = trial.suggest_float("atr_trail_mult", 0.3, 2.0)

        # 시뮬레이션: 각 트레이드에 파라미터 적용 시 예상 PnL
        simulated_pnl = []
        for t in trades:
            regime = t.get("market_regime", "unknown")
            funding = abs(t.get("funding_rate", 0.0) or 0.0)
            actual_pnl = t.get("realized_pnl_usd", 0.0) or 0.0
            fee = t.get("fee_usd", 0.0) or 0.0

            # 파라미터 조건 충족 여부 평가
            would_enter = _would_enter_with_params(
                regime, funding, t_trend, t_range_entry, f_extreme
            )

            if would_enter:
                # SL/Trail 조정에 따른 PnL 보정 (단순 선형 근사)
                sl_factor = atr_sl_mult / 0.7    # 기준 대비
                trail_factor = atr_trail_mult / 0.5

                if actual_pnl < 0:
                    # 손실: SL 좁히면 손실 감소 (비례)
                    adj_pnl = actual_pnl * sl_factor
                else:
                    # 수익: Trail 넓히면 수익 증가 (비례)
                    adj_pnl = actual_pnl * trail_factor

                simulated_pnl.append(adj_pnl - fee)

        if len(simulated_pnl) < 3:
            return -999.0  # 너무 많이 필터링됨

        n = len(simulated_pnl)
        mean = sum(simulated_pnl) / n
        variance = sum((x - mean) ** 2 for x in simulated_pnl) / n
        std = variance ** 0.5 if variance > 0 else 1e-9
        sharpe = mean / std

        # 패널티: 진입 횟수가 너무 적으면 벌칙
        entry_ratio = n / len(trades)
        if entry_ratio < 0.3:
            sharpe -= (0.3 - entry_ratio) * 5.0

        return sharpe

    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    best = study.best_params
    return TradingParams(
        t_trend=round(best["t_trend"], 3),
        t_range_entry=round(best["t_range_entry"], 4),
        f_extreme=round(best["f_extreme"], 4),
        atr_sl_mult=round(best["atr_sl_mult"], 2),
        atr_trail_mult=round(best["atr_trail_mult"], 2),
    )


def _would_enter_with_params(
    regime: str,
    funding: float,
    t_trend: float,
    t_range_entry: float,
    f_extreme: float,
) -> bool:
    """파라미터 조건에서 진입했을지 시뮬레이션 (단순 근사)"""
    if "trend" in regime:
        return True  # Trend에서는 항상 진입
    elif regime == "ranging":
        return funding >= f_extreme or True  # Range에서는 funding 또는 약한 추세
    elif regime == "high_vol":
        return funding >= f_extreme
    return True
