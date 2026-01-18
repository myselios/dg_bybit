"""거래 의사결정 흐름에서 사용되는 데이터 모델"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class TradeDirection(Enum):
    """거래 방향"""
    LONG = "LONG"
    SHORT = "SHORT"
    NONE = "NONE"


class EVDecision(Enum):
    """EV_FRAMEWORK 판정 결과"""
    PASS = "PASS"      # EV 기준 통과
    REJECT = "REJECT"  # EV 기준 미달


class RiskPermission(Enum):
    """Risk Model 허가 결과"""
    ALLOW = "ALLOW"
    DENY = "DENY"


class TradingState(Enum):
    """시스템 상태"""
    INIT = "INIT"
    IDLE = "IDLE"
    MONITORING = "MONITORING"
    ENTRY = "ENTRY"
    EXPANSION = "EXPANSION"
    EXIT_SUCCESS = "EXIT_SUCCESS"
    EXIT_FAILURE = "EXIT_FAILURE"
    COOLDOWN = "COOLDOWN"
    TERMINATED = "TERMINATED"


@dataclass
class StrategySignal:
    """Strategy 출력"""
    direction: TradeDirection
    entry_valid: bool
    confidence: float  # 0.0 ~ 1.0
    context_tag: str


@dataclass
class EVResult:
    """EV_FRAMEWORK 출력"""
    decision: EVDecision
    expected_r_multiple: float
    win_probability: float
    rejection_reason: Optional[str] = None


@dataclass
class RiskResult:
    """Risk Model 출력"""
    permission: RiskPermission
    max_exposure: float
    emergency_flag: bool
    cooldown_trigger: bool


@dataclass
class PositionSize:
    """Position Model 출력"""
    entry_size: float
    expansion_size: float
    stop_threshold: float
    target_r_multiple: float


@dataclass
class MarketData:
    """시장 데이터 (더미)"""
    price: float
    ema200: float
    atr: float
    volume: float
    timestamp: int


@dataclass
class TradingContext:
    """거래 의사결정 컨텍스트"""
    state: TradingState
    market_data: MarketData
    strategy_signal: Optional[StrategySignal] = None
    ev_result: Optional[EVResult] = None
    risk_result: Optional[RiskResult] = None
    position_size: Optional[PositionSize] = None
