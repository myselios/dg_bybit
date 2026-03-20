"""ReflectionAgent — S7 post-trade analysis agent.

Analyzes completed trade logs to classify patterns and generate
improvement hypotheses for parameter tuning.

Enhanced (2026-03-20): Multi-indicator pattern recognition
- rsi_oversold_miss: RSI<30이었는데 LONG 안 들어간 경우
- high_score_loss: score>=4인데 손실 → 시장 급변 패턴
- low_score_win: score<3인데 수익 → 운 좋은 진입 (신뢰도 낮음)
- score_threshold 연속 실패 시 자동 조정 (+1)
"""

from dataclasses import dataclass, field
from collections import deque


@dataclass(frozen=True)
class ReflectionResult:
    """Immutable result of a single trade reflection analysis."""

    trade_id: str
    outcome: str       # "win" | "loss" | "breakeven"
    pattern: str       # 패턴명 (아래 목록)
    hypothesis: str    # improvement hypothesis text
    param_delta: dict  # suggested param changes {"T_TREND": "+0.01%"} etc.

    # Pattern 목록:
    # "regime_mismatch"   — ranging market 진입 (slope 낮음)
    # "good_entry"        — 정상 수익 진입
    # "threshold_too_high"— slope 과도 (이미 많이 움직임)
    # "threshold_too_low" — slope 부족 (trend 약함)
    # "rsi_oversold_miss" — RSI<30 인데 LONG 미진입 (기회 손실)
    # "high_score_loss"   — 고점수 진입인데 손실 (급변)
    # "low_score_win"     — 저점수 진입인데 수익 (운)
    # "unknown"           — 분류 불가


class ReflectionAgent:
    """Post-trade reflection: pattern classification + hypothesis generation.

    상태 추적:
    - _recent_high_score_losses: 최근 high_score_loss 연속 횟수 추적
    - _recent_low_score_wins: 최근 low_score_win 연속 횟수 추적
    """

    _HIGH_SCORE_LOSS_TRIGGER = 3   # 연속 N회 → score_threshold +1
    _RSI_OVERSOLD_THRESHOLD = 30.0
    _HIGH_SCORE_MIN = 4
    _LOW_SCORE_MAX = 2

    def __init__(self) -> None:
        self._high_score_loss_streak: int = 0
        self._low_score_win_streak: int = 0

    def analyze(self, trade_log_entry: dict) -> ReflectionResult:
        """
        Analyze a single trade log entry -> pattern classification + hypothesis.

        trade_log_entry schema:
        {
          "trade_id": str,
          "direction": "Buy"|"Sell",
          "entry_price": float,
          "exit_price": float,
          "pnl_usd": float,
          "hold_seconds": int,
          "ma_slope_pct": float,   # MA slope at entry
          "funding_rate": float,
          "rsi": float (optional),        # RSI at entry
          "score": int (optional),        # signal score
        }
        """
        pnl_usd: float = trade_log_entry["pnl_usd"]
        ma_slope_pct: float = trade_log_entry["ma_slope_pct"]
        trade_id: str = trade_log_entry["trade_id"]
        rsi: float | None = trade_log_entry.get("rsi")
        score: int | None = trade_log_entry.get("score")
        direction: str = trade_log_entry.get("direction", "Buy")

        outcome = self._classify_outcome(pnl_usd)
        pattern = self._classify_pattern(outcome, ma_slope_pct, rsi, score, direction)
        self._update_streaks(pattern)
        hypothesis = self._generate_hypothesis(pattern, ma_slope_pct, rsi, score)
        param_delta = self._suggest_param_delta(pattern)

        return ReflectionResult(
            trade_id=trade_id,
            outcome=outcome,
            pattern=pattern,
            hypothesis=hypothesis,
            param_delta=param_delta,
        )

    def _update_streaks(self, pattern: str) -> None:
        """연속 패턴 카운터 업데이트 (불변성: 내부 상태 추적용)."""
        if pattern == "high_score_loss":
            self._high_score_loss_streak += 1
        else:
            self._high_score_loss_streak = 0

        if pattern == "low_score_win":
            self._low_score_win_streak += 1
        else:
            self._low_score_win_streak = 0

    @property
    def high_score_loss_streak(self) -> int:
        """현재 high_score_loss 연속 횟수."""
        return self._high_score_loss_streak

    @property
    def low_score_win_streak(self) -> int:
        """현재 low_score_win 연속 횟수."""
        return self._low_score_win_streak

    @staticmethod
    def _classify_outcome(pnl_usd: float) -> str:
        if pnl_usd > 0:
            return "win"
        if pnl_usd < 0:
            return "loss"
        return "breakeven"

    @classmethod
    def _classify_pattern(
        cls,
        outcome: str,
        ma_slope_pct: float,
        rsi: float | None,
        score: int | None,
        direction: str,
    ) -> str:
        """다중지표 패턴 분류 (우선순위 순)."""
        # 1. RSI oversold miss: RSI<30인데 LONG이 아닌 경우 (기회 손실)
        if (
            rsi is not None
            and rsi < cls._RSI_OVERSOLD_THRESHOLD
            and direction != "Buy"
            and outcome == "loss"
        ):
            return "rsi_oversold_miss"

        # 2. High score loss: score>=4인데 손실 → 시장 급변 패턴
        if score is not None and score >= cls._HIGH_SCORE_MIN and outcome == "loss":
            return "high_score_loss"

        # 3. Low score win: score<3인데 수익 → 운 좋은 진입
        if score is not None and score <= cls._LOW_SCORE_MAX and outcome == "win":
            return "low_score_win"

        # 4. 기존 slope 기반 패턴
        if outcome == "win":
            return "good_entry"
        if outcome == "loss":
            abs_slope = abs(ma_slope_pct)
            if abs_slope < 0.05:
                return "regime_mismatch"
            if abs_slope < 0.1:
                return "threshold_too_low"
            return "threshold_too_high"
        return "unknown"

    @classmethod
    def _generate_hypothesis(
        cls,
        pattern: str,
        ma_slope_pct: float,
        rsi: float | None,
        score: int | None,
    ) -> str:
        if pattern == "good_entry":
            return "Entry signal was aligned with trend direction. Current parameters effective."
        if pattern == "regime_mismatch":
            return (
                f"Entry occurred in ranging market (slope={ma_slope_pct:.3f}%). "
                "Consider raising T_RANGE_ENTRY."
            )
        if pattern == "threshold_too_low":
            return (
                f"Slope {ma_slope_pct:.3f}% was above T_RANGE_ENTRY but too weak for "
                "profitable trend. Raise T_TREND."
            )
        if pattern == "threshold_too_high":
            return (
                f"Entry slope {ma_slope_pct:.3f}% suggests market already moved far. "
                "Consider earlier entry."
            )
        if pattern == "rsi_oversold_miss":
            rsi_str = f"{rsi:.1f}" if rsi is not None else "N/A"
            return (
                f"RSI={rsi_str} was oversold but SHORT was taken instead of LONG. "
                "Review directional bias when RSI<30."
            )
        if pattern == "high_score_loss":
            score_str = str(score) if score is not None else "N/A"
            return (
                f"High-confidence signal (score={score_str}) resulted in loss. "
                "Likely sudden market reversal. Consider tightening SL on high-score entries."
            )
        if pattern == "low_score_win":
            score_str = str(score) if score is not None else "N/A"
            return (
                f"Low-confidence signal (score={score_str}) produced a win. "
                "Outcome may be luck-driven — reduce position size for low-score entries."
            )
        return "No hypothesis available."

    def _suggest_param_delta(self, pattern: str) -> dict:
        """파라미터 조정 제안. 연속 패턴 시 자동 score_threshold 조정."""
        base_deltas: dict[str, dict] = {
            "good_entry": {},
            "regime_mismatch": {"T_RANGE_ENTRY": "+0.01%"},
            "threshold_too_low": {"T_TREND": "+0.01%"},
            "threshold_too_high": {"T_TREND": "-0.005%"},
            "rsi_oversold_miss": {"rsi_oversold_threshold": "+2"},
            "high_score_loss": {"SL_tighten_on_high_score": "true"},
            "low_score_win": {"ma_slope_weight": "-0.1"},
        }

        delta = dict(base_deltas.get(pattern, {}))

        # high_score_loss 3회 연속 → score_threshold +1
        if (
            pattern == "high_score_loss"
            and self._high_score_loss_streak >= self._HIGH_SCORE_LOSS_TRIGGER
        ):
            delta["score_threshold"] = "+1"

        # low_score_win 지속 → ma_slope 의존도 낮추기 강화
        if pattern == "low_score_win" and self._low_score_win_streak >= 3:
            delta["ma_slope_weight"] = "-0.2"

        return delta
