"""
src/application/agents/hypothesis_loop.py

S12: 자율 가설-실험-평가 루프
트레이드 이력에서 패턴을 분석하여 파라미터 조정 가설을 생성하고 검증한다.
"""

import uuid
from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class HypothesisRecord:
    """가설 레코드 (불변).

    Attributes:
        hypothesis_id: 고유 가설 ID
        hypothesis_text: 가설 설명 텍스트
        param_candidate: 실험할 파라미터 조정 후보
        confidence: 가설 신뢰도 (0.0~1.0)
        status: 가설 상태 (pending / confirmed / rejected)
    """

    hypothesis_id: str
    hypothesis_text: str
    param_candidate: Dict[str, Any]
    confidence: float
    status: str


class HypothesisLoop:
    """트레이드 이력 기반 가설 생성 및 평가.

    generate() → 이력 분석 → HypothesisRecord(status='pending')
    evaluate() → 실험 결과 → HypothesisRecord(status='confirmed'|'rejected')
    """

    # 손실 트레이드 비율 임계값 (이 이상이면 T_TREND 조정 가설 생성)
    _LOSS_RATE_THRESHOLD = 0.5
    # 실험 성공 기준: net_pnl > 0 AND win_rate > 0.5
    _EXPERIMENT_WIN_RATE = 0.5

    def generate(self, trade_history: List[Dict[str, Any]]) -> HypothesisRecord:
        """트레이드 이력에서 가설 생성.

        Args:
            trade_history: 트레이드 레코드 목록 (pnl_usd, pattern, ma_slope_pct 포함)

        Returns:
            HypothesisRecord(status='pending')
        """
        if not trade_history:
            return self._empty_hypothesis()

        loss_count = sum(1 for t in trade_history if t.get("pnl_usd", 0) < 0)
        loss_rate = loss_count / len(trade_history)
        dominant_pattern = self._dominant_pattern(trade_history)

        hypothesis_text, param_candidate, confidence = self._build_hypothesis(
            loss_rate, dominant_pattern, trade_history
        )

        return HypothesisRecord(
            hypothesis_id=str(uuid.uuid4()),
            hypothesis_text=hypothesis_text,
            param_candidate=param_candidate,
            confidence=confidence,
            status="pending",
        )

    def evaluate(
        self,
        hypothesis: HypothesisRecord,
        experiment_result: Dict[str, Any],
    ) -> HypothesisRecord:
        """실험 결과로 가설 검증.

        Args:
            hypothesis: 검증할 가설
            experiment_result: {net_pnl_usd, trade_count, win_rate}

        Returns:
            HypothesisRecord(status='confirmed' or 'rejected')
        """
        net_pnl = experiment_result.get("net_pnl_usd", 0.0)
        win_rate = experiment_result.get("win_rate", 0.0)

        if net_pnl > 0 and win_rate >= self._EXPERIMENT_WIN_RATE:
            new_status = "confirmed"
        else:
            new_status = "rejected"

        # frozen이므로 새 인스턴스 반환
        return HypothesisRecord(
            hypothesis_id=hypothesis.hypothesis_id,
            hypothesis_text=hypothesis.hypothesis_text,
            param_candidate=hypothesis.param_candidate,
            confidence=hypothesis.confidence,
            status=new_status,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _dominant_pattern(self, trade_history: List[Dict[str, Any]]) -> str:
        counts: Dict[str, int] = {}
        for t in trade_history:
            p = t.get("pattern", "unknown")
            counts[p] = counts.get(p, 0) + 1
        return max(counts, key=lambda k: counts[k]) if counts else "unknown"

    def _build_hypothesis(
        self,
        loss_rate: float,
        dominant_pattern: str,
        trade_history: List[Dict[str, Any]],
    ) -> tuple[str, Dict[str, Any], float]:
        if loss_rate >= self._LOSS_RATE_THRESHOLD:
            if dominant_pattern == "regime_mismatch":
                avg_slope = sum(abs(t.get("ma_slope_pct", 0)) for t in trade_history) / len(trade_history)
                suggested_t_trend = round(avg_slope * 0.8, 4)
                return (
                    f"regime_mismatch 패턴 손실 {loss_rate:.0%} — "
                    f"T_TREND을 {suggested_t_trend:.4f}%로 낮추면 진입 빈도가 증가할 것이다.",
                    {"T_TREND": suggested_t_trend},
                    min(0.5 + loss_rate * 0.3, 0.9),
                )
            if dominant_pattern in ("threshold_too_low", "threshold_too_high"):
                return (
                    f"{dominant_pattern} 패턴 손실 {loss_rate:.0%} — "
                    "T_TREND 임계값 재보정이 필요하다.",
                    {"T_TREND": None},  # calibration 필요
                    0.5,
                )

        # 승리 또는 혼합 — 파라미터 유지
        return (
            f"현재 파라미터 적절 — 손실률 {loss_rate:.0%}, 패턴 {dominant_pattern}",
            {},
            0.3,
        )

    def _empty_hypothesis(self) -> HypothesisRecord:
        return HypothesisRecord(
            hypothesis_id=str(uuid.uuid4()),
            hypothesis_text="트레이드 이력 없음 — 데이터 축적 후 재분석 필요",
            param_candidate={},
            confidence=0.0,
            status="pending",
        )
