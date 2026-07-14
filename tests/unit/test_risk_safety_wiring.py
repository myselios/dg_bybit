"""
tests/unit/test_risk_safety_wiring.py
Phase 2 재가동 전 안전장치 배선 검증.

Coverage:
1. SL 계산 단일화 (build_sizing_params == stop_manager, 죽은 상수 제거)
2. 진입 주문 SL 첨부 (place_order stop_loss 전달, retCode/payload)
3. set_leverage 기동 시 호출 + 실패 시 진입 차단 (110043 성공 처리)
4. liquidation_gate 진입 흐름 연결 (REJECT → 차단, haircut → contracts 축소)
"""

import pytest

from application import stop_manager
from application.stop_manager import calculate_stop_distance_pct, calculate_stop_price
from application.entry_coordinator import (
    build_sizing_params,
    get_stage_id,
    get_stage_leverage,
)
from application.signal_generator import Signal
from application.liquidation_gate import (
    LiquidationParams,
    LiquidationGateResult,
    check_liquidation_gate,
)
from application.orchestrator import Orchestrator
from infrastructure.exchange.fake_market_data import FakeMarketData
from domain.state import State, Direction


# =========================================================================
# 공용 Fixtures / Mock
# =========================================================================


class CapturingRestClient:
    """place_order/set_leverage를 캡처하는 Mock REST client."""

    def __init__(self, leverage_ret_code: int = 0, leverage_raises: bool = False):
        self.orders = []
        self.place_order_kwargs = []
        self.set_leverage_calls = []
        self._leverage_ret_code = leverage_ret_code
        self._leverage_raises = leverage_raises
        self._position_size = 0.0

    def get_position(self, symbol: str = "BTCUSDT", category: str = "linear"):
        if self._position_size > 0:
            return {"retCode": 0, "result": {"list": [{"size": str(self._position_size)}]}}
        return {"retCode": 0, "result": {"list": []}}

    def set_trading_stop(self, symbol, stop_loss, category="linear",
                         position_idx=0, sl_trigger_by="MarkPrice"):
        return {"retCode": 0, "retMsg": "OK"}

    def set_leverage(self, symbol, buy_leverage, sell_leverage, category="linear"):
        self.set_leverage_calls.append(
            {"symbol": symbol, "buy_leverage": buy_leverage,
             "sell_leverage": sell_leverage, "category": category}
        )
        if self._leverage_raises:
            raise RuntimeError("network error")
        return {"retCode": self._leverage_ret_code, "retMsg": "x"}

    def place_order(self, symbol, side, order_type, qty, price, time_in_force,
                    order_link_id, category="linear", reduce_only=False,
                    is_post_only=False, stop_loss=None, sl_trigger_by="MarkPrice",
                    **kwargs):
        self.place_order_kwargs.append(
            {"stop_loss": stop_loss, "sl_trigger_by": sl_trigger_by,
             "side": side, "qty": qty, "price": price}
        )
        order = {
            "retCode": 0,
            "retMsg": "OK",
            "result": {"orderId": "cap_order_1", "orderLinkId": order_link_id},
        }
        self.orders.append(order)
        return order


def _entry_ready_market_data(equity_usdt: float = 1000.0) -> FakeMarketData:
    """test_entry_flow_success와 동일한, 진입이 성사되는 시장 데이터."""
    fd = FakeMarketData(current_price=50000.0, equity_usdt=equity_usdt)
    fd.inject_atr(100.0)
    fd.inject_last_fill_price(49800.0)
    fd.inject_trades_today(0)
    fd.inject_atr_pct_24h(0.03)
    fd.inject_winrate(0.6)
    fd.inject_position_mode("MergedSingle")
    return fd


# =========================================================================
# Item 2: SL 계산 단일화
# =========================================================================


def test_stop_distance_pct_matches_between_sizing_and_stop_manager():
    """build_sizing_params의 stop_distance_pct가 stop_manager 공용 함수와 일치."""
    fd = _entry_ready_market_data()
    signal = Signal(side="Sell", price=50000.0, qty=0)
    atr = 100.0

    params = build_sizing_params(signal=signal, market_data=fd, atr=atr)
    expected = calculate_stop_distance_pct(50000.0, atr)

    assert params.stop_distance_pct == expected
    # ATR*0.7/price = 70/50000 = 0.0014 → clamp 하한 0.5%
    assert params.stop_distance_pct == pytest.approx(0.005)


def test_calculate_stop_distance_pct_clamps():
    """clamp 상/하한 및 fallback 검증."""
    # 하한 0.5%
    assert calculate_stop_distance_pct(50000.0, 100.0) == pytest.approx(0.005)
    # 상한 2.0% (거대한 ATR)
    assert calculate_stop_distance_pct(50000.0, 5000.0) == pytest.approx(0.020)
    # 중간값: ATR 1000 → 700/50000 = 0.014
    assert calculate_stop_distance_pct(50000.0, 1000.0) == pytest.approx(0.014)
    # ATR 없음/0 → 1.0% fallback
    assert calculate_stop_distance_pct(50000.0, None) == pytest.approx(0.01)
    assert calculate_stop_distance_pct(50000.0, 0.0) == pytest.approx(0.01)


def test_calculate_stop_price_uses_unified_distance():
    """calculate_stop_price가 공용 거리(pct)를 그대로 사용."""
    price = 50000.0
    atr = 1000.0  # → 1.4%
    long_sl = calculate_stop_price(price, Direction.LONG, atr)
    short_sl = calculate_stop_price(price, Direction.SHORT, atr)
    assert long_sl == pytest.approx(price * (1 - 0.014))
    assert short_sl == pytest.approx(price * (1 + 0.014))


def test_dead_sl_multiplier_constant_removed():
    """죽은 상수 SL_MULTIPLIER=1.2 제거 확인."""
    assert not hasattr(stop_manager, "SL_MULTIPLIER")


def test_stage_leverage_and_id_single_source():
    """Stage id/leverage 단일 소스 값 검증."""
    assert get_stage_id(100.0) == 1 and get_stage_leverage(100.0) == 5.0
    assert get_stage_id(500.0) == 2 and get_stage_leverage(500.0) == 5.0
    assert get_stage_id(800.0) == 3 and get_stage_leverage(800.0) == 3.0


# =========================================================================
# Item 1: 진입 주문 SL 첨부
# =========================================================================


def test_entry_order_attaches_stop_loss():
    """진입 place_order에 calculate_stop_price 결과가 stop_loss로 첨부된다."""
    fd = _entry_ready_market_data(equity_usdt=1000.0)
    client = CapturingRestClient()
    orch = Orchestrator(market_data=fd, rest_client=client)

    result = orch.run_tick()

    assert result.entry_blocked is False, result.entry_block_reason
    assert orch.state == State.ENTRY_PENDING
    assert len(client.place_order_kwargs) == 1
    call = client.place_order_kwargs[0]
    assert call["stop_loss"] is not None
    assert call["sl_trigger_by"] == "MarkPrice"

    # SL 값이 stop_manager 계산과 일치 (SHORT 진입 → entry 위)
    direction = Direction.SHORT if call["side"] == "Sell" else Direction.LONG
    expected_sl = calculate_stop_price(float(call["price"]), direction, atr=100.0)
    assert float(call["stop_loss"]) == pytest.approx(round(expected_sl, 2))


def test_rest_client_place_order_includes_stoploss_in_payload():
    """bybit_rest_client.place_order가 stopLoss/slTriggerBy를 payload에 넣는다."""
    from infrastructure.exchange.bybit_rest_client import BybitRestClient

    captured = {}

    def fake_make_request(method, endpoint, params):
        captured["params"] = params
        return {"retCode": 0, "result": {"orderId": "x"}}

    client = BybitRestClient(
        api_key="k", api_secret="s",
        base_url="https://api-testnet.bybit.com",
    )
    client._make_request = fake_make_request

    client.place_order(
        symbol="BTCUSDT", side="Buy", qty="0.001", order_link_id="e1",
        order_type="Limit", price="50000", stop_loss="49500",
    )
    assert captured["params"]["stopLoss"] == "49500"
    assert captured["params"]["slTriggerBy"] == "MarkPrice"

    # stop_loss 미지정 시 payload에 stopLoss 없음
    captured.clear()
    client.place_order(
        symbol="BTCUSDT", side="Buy", qty="0.001", order_link_id="e2",
        order_type="Limit", price="50000",
    )
    assert "stopLoss" not in captured["params"]


# =========================================================================
# Item 3: set_leverage 기동 호출 + 실패 시 진입 차단
# =========================================================================


def test_leverage_configured_on_startup_success():
    """기동 시 set_leverage 호출 + retCode 0 → leverage_configured True."""
    fd = _entry_ready_market_data(equity_usdt=1000.0)  # stage 3 → 3x
    client = CapturingRestClient(leverage_ret_code=0)
    orch = Orchestrator(market_data=fd, rest_client=client)

    assert orch.leverage_configured is True
    assert len(client.set_leverage_calls) == 1
    assert client.set_leverage_calls[0]["buy_leverage"] == "3"
    assert client.set_leverage_calls[0]["sell_leverage"] == "3"


def test_leverage_not_modified_110043_treated_as_success():
    """retCode 110043(leverage not modified) → 성공 처리."""
    fd = _entry_ready_market_data(equity_usdt=200.0)  # stage 1 → 5x
    client = CapturingRestClient(leverage_ret_code=110043)
    orch = Orchestrator(market_data=fd, rest_client=client)

    assert orch.leverage_configured is True
    assert client.set_leverage_calls[0]["buy_leverage"] == "5"


def test_leverage_failure_blocks_entry():
    """set_leverage 실패(에러 retCode) → leverage_configured False → 진입 차단."""
    fd = _entry_ready_market_data(equity_usdt=1000.0)
    client = CapturingRestClient(leverage_ret_code=10001)  # 임의 실패코드
    orch = Orchestrator(market_data=fd, rest_client=client)

    assert orch.leverage_configured is False
    result = orch.run_tick()
    assert result.entry_blocked is True
    assert result.entry_block_reason == "leverage_not_configured"
    assert len(client.place_order_kwargs) == 0  # 주문 발주 안 됨


def test_leverage_exception_blocks_entry():
    """set_leverage 예외 → leverage_configured False → 진입 차단."""
    fd = _entry_ready_market_data(equity_usdt=1000.0)
    client = CapturingRestClient(leverage_raises=True)
    orch = Orchestrator(market_data=fd, rest_client=client)

    assert orch.leverage_configured is False


# =========================================================================
# Item 4: liquidation_gate 진입 흐름 연결
# =========================================================================


def test_liquidation_gate_reject_blocks_entry(monkeypatch):
    """liq gate가 REJECT 반환 시 진입 차단 + 주문 미발주."""
    import application.orchestrator as orch_mod

    def fake_gate(params):
        # gate가 실제 orchestrator에서 호출되는지 + 파라미터 형태 검증
        assert isinstance(params, LiquidationParams)
        assert params.contracts >= 1
        return LiquidationGateResult(allowed=False, reject_reason="liquidation_too_close")

    monkeypatch.setattr(orch_mod, "check_liquidation_gate", fake_gate)

    fd = _entry_ready_market_data(equity_usdt=1000.0)
    client = CapturingRestClient()
    orch = Orchestrator(market_data=fd, rest_client=client)

    result = orch.run_tick()
    assert result.entry_blocked is True
    assert result.entry_block_reason == "liquidation_too_close"
    assert len(client.place_order_kwargs) == 0


def test_liquidation_gate_haircut_reduces_contracts(monkeypatch):
    """liq gate haircut 시 contracts 축소 후 주문."""
    import application.orchestrator as orch_mod

    def fake_gate(params):
        return LiquidationGateResult(
            allowed=True, adjusted_contracts=1, haircut_applied=True
        )

    monkeypatch.setattr(orch_mod, "check_liquidation_gate", fake_gate)

    fd = _entry_ready_market_data(equity_usdt=1000.0)
    client = CapturingRestClient()
    orch = Orchestrator(market_data=fd, rest_client=client)

    result = orch.run_tick()
    assert result.entry_blocked is False, result.entry_block_reason
    # 1 contract = 0.001 BTC
    assert float(client.place_order_kwargs[0]["qty"]) == pytest.approx(0.001)


def test_liquidation_gate_haircut_zero_blocks(monkeypatch):
    """haircut 결과 contracts=0 → 진입 차단."""
    import application.orchestrator as orch_mod

    def fake_gate(params):
        return LiquidationGateResult(
            allowed=True, adjusted_contracts=0, haircut_applied=True
        )

    monkeypatch.setattr(orch_mod, "check_liquidation_gate", fake_gate)

    fd = _entry_ready_market_data(equity_usdt=1000.0)
    client = CapturingRestClient()
    orch = Orchestrator(market_data=fd, rest_client=client)

    result = orch.run_tick()
    assert result.entry_blocked is True
    assert result.entry_block_reason == "liquidation_haircut_zero"


def test_liquidation_gate_normal_pass_allows_entry():
    """정상 조건(equity 1000, 3x)에서는 liq gate 통과하여 진입 성사."""
    fd = _entry_ready_market_data(equity_usdt=1000.0)
    client = CapturingRestClient()
    orch = Orchestrator(market_data=fd, rest_client=client)

    result = orch.run_tick()
    assert result.entry_blocked is False, result.entry_block_reason
    assert orch.state == State.ENTRY_PENDING


# =========================================================================
# Item 5: DrawdownRecovery size_multiplier가 실제 주문 qty에 반영
# =========================================================================


def test_drawdown_reduce_multiplier_applied_to_order_qty():
    """REDUCE(×0.7) 상태에서 실제 place_order qty가 축소된다.

    회귀 방지: signal.qty에만 반영되고 주문은 sizing_result.contracts
    원본을 쓰던 버그 (Wave 5 Stream C 통합 누락).
    """
    # 기준: NORMAL 상태의 주문 qty
    fd_normal = _entry_ready_market_data(equity_usdt=1000.0)
    client_normal = CapturingRestClient()
    orch_normal = Orchestrator(market_data=fd_normal, rest_client=client_normal)
    result = orch_normal.run_tick()
    assert result.entry_blocked is False, result.entry_block_reason
    qty_normal = float(client_normal.place_order_kwargs[0]["qty"])
    contracts_normal = round(qty_normal / 0.001)
    assert contracts_normal >= 2, "축소 검증에는 contracts >= 2 필요"

    # REDUCE: equity 1000 → Stage 3 max_loss $45, 일일 손실 $27 = 60% (50~80% 밴드)
    fd_reduce = _entry_ready_market_data(equity_usdt=1000.0)
    fd_reduce.inject_daily_realized_pnl(-27.0)
    client_reduce = CapturingRestClient()
    orch_reduce = Orchestrator(market_data=fd_reduce, rest_client=client_reduce)
    result = orch_reduce.run_tick()
    assert result.entry_blocked is False, result.entry_block_reason

    qty_reduced = float(client_reduce.place_order_kwargs[0]["qty"])
    contracts_reduced = round(qty_reduced / 0.001)
    assert contracts_reduced == int(contracts_normal * 0.7), (
        f"REDUCE 미반영: normal={contracts_normal}, reduced={contracts_reduced}"
    )
