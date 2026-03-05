"""
src/application/emergency_stop.py
Emergency Stop Loss — 백업 안전장치

목적:
- Primary Stop Loss 실패 시 백업
- 시스템 오류, API 타임아웃, WebSocket 끊김 대비
- 청산 방지 최후 방어선

3단계 안전장치:
1. Primary SL: 0.5 ATR (~$140, 0.4% Equity)
2. Emergency SL: Equity -5% (~$5.4)
3. Hard Stop: Equity -10% (~$10.8)
4. Liquidation: -20% (거래소 강제)
"""

import logging
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class EmergencyStopConfig:
    """Emergency Stop 설정"""
    # Emergency SL: Equity 대비 손실 비율
    emergency_loss_pct: float = 0.05  # 5%
    
    # Hard Stop: Equity 대비 손실 비율 (강제 청산)
    hard_stop_loss_pct: float = 0.10  # 10%
    
    # Primary SL 미작동 감지 (초)
    primary_sl_timeout_seconds: float = 10.0


class EmergencyStopManager:
    """
    Emergency Stop Loss Manager
    
    역할:
    - Equity 기반 손실 모니터링
    - Primary SL 실패 감지
    - Emergency/Hard Stop 트리거
    """
    
    def __init__(self, config: EmergencyStopConfig):
        self.config = config
        self.initial_equity: Optional[float] = None
        self.max_equity: Optional[float] = None  # 세션 중 최대 Equity
        
    def set_initial_equity(self, equity: float):
        """세션 시작 Equity 설정"""
        self.initial_equity = equity
        self.max_equity = equity
        logger.info(f"💰 Initial Equity set: ${equity:.2f}")
        
    def update_equity(self, current_equity: float):
        """Equity 업데이트 (최대값 추적)"""
        if self.max_equity is None or current_equity > self.max_equity:
            self.max_equity = current_equity
            
    def check_emergency_stop(
        self,
        current_equity: float,
        unrealized_pnl: float = 0.0,
    ) -> tuple[bool, str]:
        """
        Emergency Stop 체크
        
        Args:
            current_equity: 현재 Equity
            unrealized_pnl: 미실현 손익
            
        Returns:
            (should_stop, reason)
        """
        if self.initial_equity is None:
            return False, ""
            
        # 실현 + 미실현 손실
        total_pnl = current_equity - self.initial_equity
        total_loss_pct = abs(total_pnl / self.initial_equity)
        
        # Hard Stop (10% 손실)
        if total_loss_pct >= self.config.hard_stop_loss_pct:
            reason = f"🚨 HARD STOP: Equity -{total_loss_pct*100:.1f}% (${abs(total_pnl):.2f})"
            logger.critical(reason)
            return True, reason
            
        # Emergency Stop (5% 손실)
        if total_loss_pct >= self.config.emergency_loss_pct:
            reason = f"⚠️ EMERGENCY STOP: Equity -{total_loss_pct*100:.1f}% (${abs(total_pnl):.2f})"
            logger.error(reason)
            return True, reason
            
        return False, ""
        
    def check_primary_sl_failure(
        self,
        mark_price: float,
        stop_price: Optional[float],
        last_stop_update_ts: float,
        current_ts: float,
    ) -> tuple[bool, str]:
        """
        Primary SL 미작동 감지
        
        Args:
            mark_price: 현재가
            stop_price: 설정된 손절가
            last_stop_update_ts: 마지막 손절 업데이트 시각
            current_ts: 현재 시각
            
        Returns:
            (is_failed, reason)
        """
        if stop_price is None:
            return False, ""
            
        # SL이 관통되었는데 포지션이 아직 있는 경우
        time_since_update = current_ts - last_stop_update_ts
        
        # 손절가 관통 후 10초 이상 경과
        if time_since_update > self.config.primary_sl_timeout_seconds:
            # SHORT: mark_price > stop_price
            # LONG: mark_price < stop_price
            # (여기서는 간단히 distance로 체크)
            distance_pct = abs(mark_price - stop_price) / stop_price
            
            if distance_pct > 0.05:  # 5% 이상 벗어남
                reason = f"⚠️ Primary SL 미작동 감지 (가격 차이: {distance_pct*100:.1f}%)"
                logger.warning(reason)
                return True, reason
                
        return False, ""
        
    def get_status(self) -> dict:
        """현재 상태 반환"""
        return {
            "initial_equity": self.initial_equity,
            "max_equity": self.max_equity,
            "emergency_threshold": self.config.emergency_loss_pct,
            "hard_stop_threshold": self.config.hard_stop_loss_pct,
        }
