"""ReflectionAgent — S7 post-trade analysis agent.

Analyzes completed trade logs to classify patterns and generate
improvement hypotheses for parameter tuning.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ReflectionResult:
    """Immutable result of a single trade reflection analysis."""

    trade_id: str
    outcome: str       # "win" | "loss" | "breakeven"
    pattern: str       # "regime_mismatch" | "good_entry" | "threshold_too_high" | "threshold_too_low" | "unknown"
    hypothesis: str    # improvement hypothesis text
    param_delta: dict  # suggested param changes {"T_TREND": "+0.01%"} etc.


class ReflectionAgent:
    """Post-trade reflection: pattern classification + hypothesis generation."""

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
        }
        """
        pnl_usd: float = trade_log_entry["pnl_usd"]
        ma_slope_pct: float = trade_log_entry["ma_slope_pct"]
        trade_id: str = trade_log_entry["trade_id"]

        outcome = self._classify_outcome(pnl_usd)
        pattern = self._classify_pattern(outcome, ma_slope_pct)
        hypothesis = self._generate_hypothesis(pattern, ma_slope_pct)
        param_delta = self._suggest_param_delta(pattern)

        return ReflectionResult(
            trade_id=trade_id,
            outcome=outcome,
            pattern=pattern,
            hypothesis=hypothesis,
            param_delta=param_delta,
        )

    @staticmethod
    def _classify_outcome(pnl_usd: float) -> str:
        if pnl_usd > 0:
            return "win"
        if pnl_usd < 0:
            return "loss"
        return "breakeven"

    @staticmethod
    def _classify_pattern(outcome: str, ma_slope_pct: float) -> str:
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

    @staticmethod
    def _generate_hypothesis(pattern: str, ma_slope_pct: float) -> str:
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
        return "No hypothesis available."

    @staticmethod
    def _suggest_param_delta(pattern: str) -> dict:
        deltas: dict[str, dict] = {
            "good_entry": {},
            "regime_mismatch": {"T_RANGE_ENTRY": "+0.01%"},
            "threshold_too_low": {"T_TREND": "+0.01%"},
            "threshold_too_high": {"T_TREND": "-0.005%"},
        }
        return deltas.get(pattern, {})
