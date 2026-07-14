"""
tests/unit/test_tsm_trader.py

ADR-0015 Strategy v4 — Daily TSM 트레이더 서비스 유닛 테스트.

범위:
- compute_order_qty: Decimal 정밀도, qty_step 내림, leverage cap 바인딩, min_qty 미만 → 0
- TsmTrader.run_daily_check: entry / flip_exit / hold / skip_funding / no_signal / qty_zero / error
- shadow 모드에서 place_order 미호출, live 모드에서 stop_loss 첨부
- log_shadow_signal: jsonl append, 디렉토리 자동 생성, Decimal 직렬화

신호 모듈(application.tsm_signal)은 병렬 구현 중이므로 decide/should_flip_exit는
tsm_trader 모듈 레벨에서 monkeypatch로 대체한다. DailyBar 변환도 monkeypatch로
격리하여 신호 DTO의 정확한 필드명과 무관하게 트레이더 로직을 검증한다.
"""

import json
from decimal import Decimal

import pytest

from application import tsm_trader as trader_mod
from application.tsm_trader import (
    TsmConfig,
    TsmTrader,
    compute_order_qty,
    log_shadow_signal,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeDecision:
    """TsmDecision 대역 (필드만 일치)."""

    def __init__(self, direction, stop_price, entry_price, reason="", up=False, down=False):
        self.direction = direction
        self.stop_price = stop_price
        self.entry_price = entry_price
        self.reason = reason
        self.momentum_up = up
        self.momentum_down = down


class FakeRestClient:
    """BybitRestClient 대역. 응답을 주입하고 place_order 호출을 기록한다."""

    def __init__(
        self,
        kline=None,
        position=None,
        tickers=None,
        wallet=None,
        raise_on=None,
    ):
        self._kline = kline if kline is not None else _kline_resp()
        self._position = position if position is not None else _empty_position()
        self._tickers = tickers if tickers is not None else _tickers_resp("0.0")
        self._wallet = wallet if wallet is not None else _wallet_resp("1000")
        self._raise_on = raise_on or set()
        self.orders = []
        self.leverage_calls = []
        self.leverage_ret_code = 0

    def _maybe_raise(self, name):
        if name in self._raise_on:
            raise RuntimeError(f"boom:{name}")

    def set_leverage(self, symbol="BTCUSDT", buy_leverage="3", sell_leverage="3", category="linear"):
        self._maybe_raise("set_leverage")
        self.leverage_calls.append({"buy": buy_leverage, "sell": sell_leverage})
        return {"retCode": self.leverage_ret_code, "retMsg": "x"}

    def get_kline(self, category="linear", symbol="BTCUSDT", interval="60", limit=200):
        self._maybe_raise("get_kline")
        return self._kline

    def get_position(self, category="linear", symbol="BTCUSDT"):
        self._maybe_raise("get_position")
        return self._position

    def get_tickers(self, category="linear", symbol="BTCUSDT"):
        self._maybe_raise("get_tickers")
        return self._tickers

    def get_wallet_balance(self, accountType="UNIFIED", coin="USDT"):
        self._maybe_raise("get_wallet_balance")
        return self._wallet

    def place_order(self, **kwargs):
        self._maybe_raise("place_order")
        self.orders.append(kwargs)
        return {"retCode": 0, "result": {"orderId": "fake-1"}}


# ---------------------------------------------------------------------------
# Response builders (Bybit v5 형식)
# ---------------------------------------------------------------------------


def _kline_resp(n=60):
    # 최신순(newest first). row = [ts, o, h, l, c, vol, turnover].
    rows = []
    for i in range(n):
        px = str(50000 + i)
        rows.append([str(1_600_000_000_000 + i * 86_400_000), px, px, px, px, "1", "1"])
    rows.reverse()  # newest first
    return {"result": {"list": rows}}


def _empty_position():
    return {"result": {"list": [{"symbol": "BTCUSDT", "side": "", "size": "0"}]}}


def _long_position(size="0.01"):
    return {"result": {"list": [{"symbol": "BTCUSDT", "side": "Buy", "size": size, "avgPrice": "50000"}]}}


def _short_position(size="0.01"):
    return {"result": {"list": [{"symbol": "BTCUSDT", "side": "Sell", "size": size, "avgPrice": "50000"}]}}


def _tickers_resp(funding="0.0"):
    return {"result": {"list": [{"symbol": "BTCUSDT", "fundingRate": funding, "markPrice": "50000"}]}}


def _wallet_resp(equity="1000"):
    return {
        "result": {
            "list": [
                {"coin": [{"coin": "USDT", "equity": equity, "walletBalance": equity}]}
            ]
        }
    }


@pytest.fixture(autouse=True)
def _patch_signal(monkeypatch):
    """DailyBar 변환을 신호 DTO와 무관하게 만든다 (필드명 비의존)."""
    monkeypatch.setattr(trader_mod, "DailyBar", lambda **kw: kw, raising=False)
    yield


def _patch_decide(monkeypatch, decision):
    monkeypatch.setattr(trader_mod, "decide", lambda *a, **k: decision, raising=False)


def _patch_flip(monkeypatch, value):
    monkeypatch.setattr(trader_mod, "should_flip_exit", lambda *a, **k: value, raising=False)


# ===========================================================================
# compute_order_qty
# ===========================================================================


def test_compute_order_qty_risk_based_floor():
    # equity 1000, risk 5% = 50 USD. entry 50000, stop 49000 → dist 1000.
    # qty = 50/1000 = 0.05 BTC. cap = 1000*3/50000 = 0.06 → risk binds.
    # floor to 0.001 step → 0.05
    cfg = TsmConfig()
    qty = compute_order_qty(Decimal("1000"), Decimal("50000"), Decimal("49000"), cfg)
    assert qty == Decimal("0.050")


def test_compute_order_qty_leverage_cap_binds():
    # tight stop → risk qty huge, cap must bind.
    # equity 1000, risk 50. entry 50000, stop 49900 → dist 100 → risk qty = 0.5 BTC.
    # cap = 1000*3/50000 = 0.06 BTC → cap binds → floor 0.06
    cfg = TsmConfig()
    qty = compute_order_qty(Decimal("1000"), Decimal("50000"), Decimal("49900"), cfg)
    assert qty == Decimal("0.060")


def test_compute_order_qty_step_floor_not_round():
    # produce a value that must floor down, not round to nearest.
    # equity 1000, risk 50. dist chosen so qty = 0.0559 → floor to 0.055
    cfg = TsmConfig()
    # dist = 50 / 0.0559 ≈ 894.45 ; pick entry/stop giving qty just under a step boundary
    qty = compute_order_qty(Decimal("1000"), Decimal("50000"), Decimal("49105"), cfg)
    # risk qty = 50/895 = 0.055865...; cap = 0.06 → risk binds; floor → 0.055
    assert qty == Decimal("0.055")


def test_compute_order_qty_below_min_returns_zero():
    # tiny equity → qty below min_qty (0.001) → 0
    cfg = TsmConfig()
    qty = compute_order_qty(Decimal("10"), Decimal("50000"), Decimal("40000"), cfg)
    # risk = 0.5 USD, dist = 10000 → qty = 0.00005 → below min → 0
    assert qty == Decimal("0")


def test_compute_order_qty_zero_distance_returns_zero():
    cfg = TsmConfig()
    qty = compute_order_qty(Decimal("1000"), Decimal("50000"), Decimal("50000"), cfg)
    assert qty == Decimal("0")


def test_compute_order_qty_returns_decimal_type():
    cfg = TsmConfig()
    qty = compute_order_qty(Decimal("1000"), Decimal("50000"), Decimal("49000"), cfg)
    assert isinstance(qty, Decimal)


# ===========================================================================
# run_daily_check — entry path
# ===========================================================================


def test_run_daily_check_entry_shadow_no_order(monkeypatch):
    _patch_decide(monkeypatch, _FakeDecision("LONG", Decimal("49000"), Decimal("50000"), "mom_up"))
    client = FakeRestClient()
    trader = TsmTrader(client, TsmConfig())

    result = trader.run_daily_check(shadow=True)

    assert result["action"] == "entry"
    assert result["direction"] == "LONG"
    assert result["qty"] == Decimal("0.050")
    assert result["stop_price"] == Decimal("49000")
    assert result["shadow"] is True
    assert client.orders == []  # shadow: 주문 미발주


def test_run_daily_check_entry_live_attaches_stop(monkeypatch):
    _patch_decide(monkeypatch, _FakeDecision("LONG", Decimal("49000"), Decimal("50000"), "mom_up"))
    client = FakeRestClient()
    trader = TsmTrader(client, TsmConfig())

    result = trader.run_daily_check(shadow=False)

    assert result["action"] == "entry"
    assert result["shadow"] is False
    assert len(client.orders) == 1
    order = client.orders[0]
    assert order["side"] == "Buy"
    assert order["order_type"] == "Market"
    assert order["qty"] == "0.050"
    assert order["stop_loss"] == "49000"
    assert order["sl_trigger_by"] == "MarkPrice"


def test_run_daily_check_entry_short_side_sell(monkeypatch):
    _patch_decide(monkeypatch, _FakeDecision("SHORT", Decimal("51000"), Decimal("50000"), "mom_down"))
    client = FakeRestClient()
    trader = TsmTrader(client, TsmConfig())

    result = trader.run_daily_check(shadow=False)

    assert result["action"] == "entry"
    assert result["direction"] == "SHORT"
    assert client.orders[0]["side"] == "Sell"


def test_live_entry_sets_leverage_3x_before_order(monkeypatch):
    """live 진입 시 정책 레버리지(3x)를 place_order 전에 강제한다 (ADR-0015)."""
    _patch_decide(monkeypatch, _FakeDecision("LONG", Decimal("49000"), Decimal("50000"), "mom_up"))
    client = FakeRestClient()
    trader = TsmTrader(client, TsmConfig())

    trader.run_daily_check(shadow=False)

    assert client.leverage_calls == [{"buy": "3", "sell": "3"}]
    assert len(client.orders) == 1  # 레버리지 설정 후 주문 발주


def test_shadow_entry_does_not_set_leverage(monkeypatch):
    """shadow 모드는 주문도 레버리지 설정도 하지 않는다."""
    _patch_decide(monkeypatch, _FakeDecision("LONG", Decimal("49000"), Decimal("50000"), "mom_up"))
    client = FakeRestClient()
    trader = TsmTrader(client, TsmConfig())

    trader.run_daily_check(shadow=True)

    assert client.leverage_calls == []


def test_live_entry_proceeds_when_leverage_not_modified(monkeypatch):
    """retCode 110043(이미 설정됨)은 성공 취급 — 진입 계속."""
    _patch_decide(monkeypatch, _FakeDecision("LONG", Decimal("49000"), Decimal("50000"), "mom_up"))
    client = FakeRestClient()
    client.leverage_ret_code = 110043
    trader = TsmTrader(client, TsmConfig())

    result = trader.run_daily_check(shadow=False)

    assert result["action"] == "entry"
    assert len(client.orders) == 1


def test_live_entry_proceeds_when_set_leverage_raises(monkeypatch):
    """set_leverage I/O 실패는 진입을 막지 않는다 (스탑이 손실 고정, 유효 신호 스킵 방지)."""
    _patch_decide(monkeypatch, _FakeDecision("LONG", Decimal("49000"), Decimal("50000"), "mom_up"))
    client = FakeRestClient(raise_on={"set_leverage"})
    trader = TsmTrader(client, TsmConfig())

    result = trader.run_daily_check(shadow=False)

    assert result["action"] == "entry"
    assert len(client.orders) == 1  # 주문은 그대로 발주


# ===========================================================================
# run_daily_check — flip / hold
# ===========================================================================


def test_run_daily_check_flip_exit_live_reduce_only(monkeypatch):
    _patch_flip(monkeypatch, True)
    client = FakeRestClient(position=_long_position("0.01"))
    trader = TsmTrader(client, TsmConfig())

    result = trader.run_daily_check(shadow=False)

    assert result["action"] == "flip_exit"
    assert len(client.orders) == 1
    order = client.orders[0]
    assert order["side"] == "Sell"  # LONG 청산 → Sell
    assert order["reduce_only"] is True
    assert order["qty"] == "0.01"


def test_run_daily_check_flip_exit_shadow_no_order(monkeypatch):
    _patch_flip(monkeypatch, True)
    client = FakeRestClient(position=_short_position("0.02"))
    trader = TsmTrader(client, TsmConfig())

    result = trader.run_daily_check(shadow=True)

    assert result["action"] == "flip_exit"
    assert client.orders == []


def test_run_daily_check_hold_when_position_and_no_flip(monkeypatch):
    _patch_flip(monkeypatch, False)
    # decide must never be called when position exists; make it explode if called
    monkeypatch.setattr(
        trader_mod, "decide", lambda *a, **k: (_ for _ in ()).throw(AssertionError("decide called")), raising=False
    )
    client = FakeRestClient(position=_long_position("0.01"))
    trader = TsmTrader(client, TsmConfig())

    result = trader.run_daily_check(shadow=False)

    assert result["action"] == "hold"
    assert client.orders == []


# ===========================================================================
# run_daily_check — no_signal / funding / qty_zero
# ===========================================================================


def test_run_daily_check_no_signal(monkeypatch):
    _patch_decide(monkeypatch, _FakeDecision(None, None, None, "flat"))
    client = FakeRestClient()
    trader = TsmTrader(client, TsmConfig())

    result = trader.run_daily_check(shadow=True)

    assert result["action"] == "no_signal"
    assert client.orders == []


def test_run_daily_check_skip_funding_long(monkeypatch):
    # LONG + funding > +limit → skip
    _patch_decide(monkeypatch, _FakeDecision("LONG", Decimal("49000"), Decimal("50000"), "mom_up"))
    client = FakeRestClient(tickers=_tickers_resp("0.001"))  # 0.1% > 0.05%
    trader = TsmTrader(client, TsmConfig())

    result = trader.run_daily_check(shadow=True)

    assert result["action"] == "skip_funding"
    assert client.orders == []


def test_run_daily_check_short_funding_negative_skips(monkeypatch):
    # SHORT + funding < -limit → skip (SHORT는 음수 funding이 부담)
    _patch_decide(monkeypatch, _FakeDecision("SHORT", Decimal("51000"), Decimal("50000"), "mom_down"))
    client = FakeRestClient(tickers=_tickers_resp("-0.001"))
    trader = TsmTrader(client, TsmConfig())

    result = trader.run_daily_check(shadow=True)

    assert result["action"] == "skip_funding"


def test_run_daily_check_long_negative_funding_ok(monkeypatch):
    # LONG + funding 음수는 오히려 수령 → 진입 진행
    _patch_decide(monkeypatch, _FakeDecision("LONG", Decimal("49000"), Decimal("50000"), "mom_up"))
    client = FakeRestClient(tickers=_tickers_resp("-0.001"))
    trader = TsmTrader(client, TsmConfig())

    result = trader.run_daily_check(shadow=True)

    assert result["action"] == "entry"


def test_run_daily_check_qty_zero(monkeypatch):
    _patch_decide(monkeypatch, _FakeDecision("LONG", Decimal("40000"), Decimal("50000"), "mom_up"))
    client = FakeRestClient(wallet=_wallet_resp("10"))  # 소액 → qty 0
    trader = TsmTrader(client, TsmConfig())

    result = trader.run_daily_check(shadow=False)

    assert result["action"] == "qty_zero"
    assert client.orders == []


# ===========================================================================
# run_daily_check — error handling
# ===========================================================================


def test_run_daily_check_api_error_returns_structured(monkeypatch):
    client = FakeRestClient(raise_on={"get_kline"})
    trader = TsmTrader(client, TsmConfig())

    result = trader.run_daily_check(shadow=True)

    assert result["action"] == "error"
    assert "boom" in result["error"]
    assert client.orders == []


def test_run_daily_check_place_order_error_no_partial(monkeypatch):
    # place_order 실패 시 error 반환, 부분 상태 없음
    _patch_decide(monkeypatch, _FakeDecision("LONG", Decimal("49000"), Decimal("50000"), "mom_up"))
    client = FakeRestClient(raise_on={"place_order"})
    trader = TsmTrader(client, TsmConfig())

    result = trader.run_daily_check(shadow=False)

    assert result["action"] == "error"


# ===========================================================================
# log_shadow_signal
# ===========================================================================


def test_log_shadow_signal_appends_jsonl(tmp_path):
    log_dir = tmp_path / "tsm_shadow"
    record = {"action": "entry", "direction": "LONG", "qty": Decimal("0.05"), "shadow": True}

    path = log_shadow_signal(record, log_dir=str(log_dir), date_str="2026-07-13")

    assert path.endswith("signals_2026-07-13.jsonl")
    lines = [ln for ln in open(path).read().splitlines() if ln]
    assert len(lines) == 1
    loaded = json.loads(lines[0])
    assert loaded["action"] == "entry"
    assert loaded["qty"] == "0.05"  # Decimal → str 직렬화


def test_log_shadow_signal_appends_second_line(tmp_path):
    log_dir = tmp_path / "tsm_shadow"
    log_shadow_signal({"action": "no_signal"}, log_dir=str(log_dir), date_str="2026-07-13")
    path = log_shadow_signal({"action": "entry", "qty": Decimal("0.1")}, log_dir=str(log_dir), date_str="2026-07-13")

    lines = [ln for ln in open(path).read().splitlines() if ln]
    assert len(lines) == 2


# ===========================================================================
# Integration with real signal module (skip if not yet built)
# ===========================================================================

_signal = pytest.importorskip("application.tsm_signal", reason="tsm_signal 병렬 구현 중")


def test_to_daily_bars_real_constructor(monkeypatch):
    # autouse 패치를 걷어내고 실제 DailyBar 생성자로 _to_daily_bars 검증.
    from application.tsm_signal import DailyBar as RealBar

    monkeypatch.setattr(trader_mod, "DailyBar", RealBar)
    client = FakeRestClient()
    trader = TsmTrader(client, TsmConfig())
    bars = trader._to_daily_bars(client.get_kline(interval="D")["result"]["list"])
    assert len(bars) == 59  # 60개 중 미완성 최신봉 1개 제외
    assert bars[0].ts < bars[-1].ts  # 오름차순(과거→최신)
    assert bars[-1].close == 50000.0 + 58  # 최신 완성봉


def test_run_daily_check_real_signal_call_signature(monkeypatch):
    # 실제 decide/should_flip_exit 시그니처 정합성 — mock 없이 호출해 TypeError 없어야.
    from application.tsm_signal import DailyBar as RealBar

    monkeypatch.setattr(trader_mod, "DailyBar", RealBar)
    client = FakeRestClient()  # 무포지션, 60 상승봉 → decide 실제 실행
    trader = TsmTrader(client, TsmConfig())
    result = trader.run_daily_check(shadow=True)
    assert result["action"] in {"entry", "no_signal", "skip_funding", "qty_zero"}
    assert result["action"] != "error"


def test_run_daily_check_real_signal_flip_signature(monkeypatch):
    # 포지션 보유 경로에서 실제 should_flip_exit 시그니처 검증.
    from application.tsm_signal import DailyBar as RealBar

    monkeypatch.setattr(trader_mod, "DailyBar", RealBar)
    client = FakeRestClient(position=_long_position("0.01"))
    trader = TsmTrader(client, TsmConfig())
    result = trader.run_daily_check(shadow=True)
    assert result["action"] in {"hold", "flip_exit"}
    assert result["action"] != "error"
