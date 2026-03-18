"""TDD RED — S11 Multi-Agent Orchestration tests.

These tests define the expected interface for:
- AgentMessage (frozen dataclass for inter-agent communication)
- MarketAnalystAgent (regime detection)
- StrategyAgent (signal decision)
- RiskAgent (risk validation)

All tests should FAIL until the corresponding modules are implemented.
"""

import time

import pytest


# ---------------------------------------------------------------------------
# 1. AgentMessage — frozen dataclass
# ---------------------------------------------------------------------------

class TestAgentMessage:
    """AgentMessage must be an immutable dataclass with required fields."""

    def test_agent_message_immutable(self):
        """AgentMessage은 frozen=True dataclass여야 한다."""
        from application.agents.agent_message import AgentMessage

        msg = AgentMessage(
            from_agent="market_analyst",
            to_agent="strategy",
            msg_type="regime_update",
            payload={"regime": "trending_up"},
            timestamp=1710000000.0,
        )

        # frozen이므로 attribute 변경 시 FrozenInstanceError 발생
        with pytest.raises(AttributeError):
            msg.msg_type = "tampered"

        # 필드 값 검증
        assert msg.from_agent == "market_analyst"
        assert msg.to_agent == "strategy"
        assert msg.msg_type == "regime_update"
        assert msg.payload == {"regime": "trending_up"}
        assert msg.timestamp == 1710000000.0


# ---------------------------------------------------------------------------
# 2–4. MarketAnalystAgent
# ---------------------------------------------------------------------------

class TestMarketAnalystAgent:
    """MarketAnalystAgent.analyze() returns AgentMessage with regime info."""

    def test_market_analyst_returns_regime_message(self):
        """analyze()는 msg_type='regime_update'인 AgentMessage를 반환해야 한다."""
        from application.agents.agent_message import AgentMessage
        from application.agents.market_analyst_agent import MarketAnalystAgent

        agent = MarketAnalystAgent()
        result = agent.analyze(ma_slope_pct=0.5, atr_pct=1.2)

        assert isinstance(result, AgentMessage)
        assert result.msg_type == "regime_update"
        assert result.from_agent == "market_analyst"

    def test_market_analyst_trending_up_payload(self):
        """slope=0.5 (강한 상승 기울기) → payload['regime'] == 'trending_up'."""
        from application.agents.market_analyst_agent import MarketAnalystAgent

        agent = MarketAnalystAgent()
        result = agent.analyze(ma_slope_pct=0.5, atr_pct=1.2)

        assert result.payload["regime"] == "trending_up"
        assert "atr_pct" in result.payload

    def test_market_analyst_ranging_payload(self):
        """slope=0.01 (거의 평평) → payload['regime'] == 'ranging'."""
        from application.agents.market_analyst_agent import MarketAnalystAgent

        agent = MarketAnalystAgent()
        result = agent.analyze(ma_slope_pct=0.01, atr_pct=0.8)

        assert result.payload["regime"] == "ranging"

    def test_market_analyst_trending_down_payload(self):
        """slope=-0.5 (강한 하락 기울기) → payload['regime'] == 'trending_down'."""
        from application.agents.market_analyst_agent import MarketAnalystAgent

        agent = MarketAnalystAgent()
        result = agent.analyze(ma_slope_pct=-0.5, atr_pct=1.0)

        assert result.payload["regime"] == "trending_down"


# ---------------------------------------------------------------------------
# 5. StrategyAgent
# ---------------------------------------------------------------------------

class TestStrategyAgent:
    """StrategyAgent.decide() returns signal AgentMessage."""

    def test_strategy_agent_returns_signal_message(self):
        """decide()는 msg_type='signal'인 AgentMessage를 반환해야 한다."""
        from application.agents.agent_message import AgentMessage
        from application.agents.strategy_agent import StrategyAgent

        regime_msg = AgentMessage(
            from_agent="market_analyst",
            to_agent="strategy",
            msg_type="regime_update",
            payload={"regime": "trending_up", "atr_pct": 1.2},
            timestamp=time.time(),
        )

        agent = StrategyAgent()
        result = agent.decide(
            regime_msg=regime_msg,
            current_price=85000.0,
            last_fill_price=None,
        )

        assert isinstance(result, AgentMessage)
        assert result.msg_type == "signal"
        assert result.from_agent == "strategy"
        assert result.to_agent == "risk"
        assert "direction" in result.payload

    def test_strategy_agent_no_signal_in_ranging(self):
        """ranging 레짐에서는 direction='NONE' (진입 안 함)."""
        from application.agents.agent_message import AgentMessage
        from application.agents.strategy_agent import StrategyAgent

        regime_msg = AgentMessage(
            from_agent="market_analyst",
            to_agent="strategy",
            msg_type="regime_update",
            payload={"regime": "ranging", "atr_pct": 0.5},
            timestamp=time.time(),
        )

        agent = StrategyAgent()
        result = agent.decide(
            regime_msg=regime_msg,
            current_price=85000.0,
            last_fill_price=None,
        )

        assert result.payload["direction"] == "NONE"


# ---------------------------------------------------------------------------
# 6. RiskAgent
# ---------------------------------------------------------------------------

class TestRiskAgent:
    """RiskAgent.validate() returns risk-validated AgentMessage."""

    def test_risk_agent_returns_validation_message(self):
        """validate()는 msg_type='risk_validated'인 AgentMessage를 반환해야 한다."""
        from application.agents.agent_message import AgentMessage
        from application.agents.risk_agent import RiskAgent

        signal_msg = AgentMessage(
            from_agent="strategy",
            to_agent="risk",
            msg_type="signal",
            payload={"direction": "LONG", "strength": 0.8},
            timestamp=time.time(),
        )

        agent = RiskAgent()
        result = agent.validate(signal_msg=signal_msg, equity_usdt=150.0)

        assert isinstance(result, AgentMessage)
        assert result.msg_type == "risk_validated"
        assert result.from_agent == "risk"
        assert "approved" in result.payload

    def test_risk_agent_rejects_low_equity(self):
        """equity가 너무 낮으면 approved=False."""
        from application.agents.agent_message import AgentMessage
        from application.agents.risk_agent import RiskAgent

        signal_msg = AgentMessage(
            from_agent="strategy",
            to_agent="risk",
            msg_type="signal",
            payload={"direction": "LONG", "strength": 0.8},
            timestamp=time.time(),
        )

        agent = RiskAgent()
        result = agent.validate(signal_msg=signal_msg, equity_usdt=1.0)

        assert result.payload["approved"] is False
        assert "reason" in result.payload


# ---------------------------------------------------------------------------
# 7. Full Pipeline: MarketAnalyst → Strategy → Risk
# ---------------------------------------------------------------------------

class TestAgentPipeline:
    """End-to-end message chain through all three agents."""

    def test_agent_message_pipeline(self):
        """MarketAnalyst → Strategy → Risk 메시지 체인이 작동해야 한다."""
        from application.agents.agent_message import AgentMessage
        from application.agents.market_analyst_agent import MarketAnalystAgent
        from application.agents.risk_agent import RiskAgent
        from application.agents.strategy_agent import StrategyAgent

        # Step 1: MarketAnalyst가 regime 분석
        analyst = MarketAnalystAgent()
        regime_msg = analyst.analyze(ma_slope_pct=0.5, atr_pct=1.2)

        assert isinstance(regime_msg, AgentMessage)
        assert regime_msg.msg_type == "regime_update"

        # Step 2: StrategyAgent가 regime 기반 signal 결정
        strategist = StrategyAgent()
        signal_msg = strategist.decide(
            regime_msg=regime_msg,
            current_price=85000.0,
            last_fill_price=None,
        )

        assert isinstance(signal_msg, AgentMessage)
        assert signal_msg.msg_type == "signal"

        # Step 3: RiskAgent가 signal 검증
        risk = RiskAgent()
        validated_msg = risk.validate(
            signal_msg=signal_msg,
            equity_usdt=150.0,
        )

        assert isinstance(validated_msg, AgentMessage)
        assert validated_msg.msg_type == "risk_validated"
        assert "approved" in validated_msg.payload

        # 전체 체인 검증: from/to가 올바르게 연결
        assert regime_msg.from_agent == "market_analyst"
        assert signal_msg.from_agent == "strategy"
        assert validated_msg.from_agent == "risk"
