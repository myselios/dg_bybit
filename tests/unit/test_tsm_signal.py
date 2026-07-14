"""TSM 신호 순수 모듈 테스트.

- EMA/ATR 손계산 대조
- decide: LONG/SHORT/no_signal/insufficient_data
- should_flip_exit 양방향
- frozen dataclass 뮤테이션 불가
- 백테스트 패리티 (scratchpad bt_v4 / klines 캐시 사용, 없으면 skip)
"""
import dataclasses
import json
import math
import os
import sys

import pytest

from application.tsm_signal import (
    DailyBar,
    TsmDecision,
    atr_wilder,
    decide,
    ema,
    should_flip_exit,
)

SCRATCH = (
    "/tmp/claude-1000/-home-selios-work-dg-bybit/"
    "45b159c8-3f65-4cb0-8400-0670e9c2fdb5/scratchpad"
)


def _bar(c: float, h: float | None = None, l: float | None = None) -> DailyBar:
    """close 중심의 헬퍼. h/l 미지정 시 close 기준 ±0."""
    return DailyBar(ts=0, open=c, high=c if h is None else h,
                    low=c if l is None else l, close=c)


# ---------------------------------------------------------------- EMA
def test_ema_matches_hand_calc():
    out = ema([1.0, 2.0, 3.0, 4.0], 2)
    # seed=values[0]=1, k=2/3
    expected = [1.0, 1.0 + (2 / 3) * 1, 0.0, 0.0]
    expected[2] = expected[1] + (2 / 3) * (3 - expected[1])
    expected[3] = expected[2] + (2 / 3) * (4 - expected[2])
    assert len(out) == 4
    for a, b in zip(out, expected):
        assert math.isclose(a, b, rel_tol=1e-12)


def test_ema_seed_is_first_value_not_sma():
    out = ema([5.0, 5.0, 5.0], 2)
    assert out[0] == 5.0
    assert all(math.isclose(v, 5.0) for v in out)


# ---------------------------------------------------------------- ATR
def test_atr_wilder_matches_hand_calc():
    bars = [
        _bar(9.0, h=10.0, l=8.0),
        _bar(11.0, h=12.0, l=9.0),
        _bar(12.0, h=13.0, l=11.0),
        _bar(14.0, h=15.0, l=12.0),
    ]
    out = atr_wilder(bars, period=2)
    # TR = [2, 3, 2, 3]; seed = (2+3)/2 = 2.5 for first `period` slots
    expected = [2.5, 2.5, 2.25, 2.625]
    assert len(out) == 4
    for a, b in zip(out, expected):
        assert math.isclose(a, b, rel_tol=1e-12)


# ---------------------------------------------------------------- decide
def test_decide_insufficient_data():
    bars = [_bar(float(i)) for i in range(10)]
    d = decide(bars, look=30, ema_period=50)
    assert d.reason == "insufficient_data"
    assert d.direction is None
    assert d.stop_price is None


def test_decide_long_momentum():
    # 강한 상승 추세: 마지막 close가 30봉 전보다 크고 EMA 위
    bars = [_bar(100.0 + i, h=100.0 + i + 1, l=100.0 + i - 1) for i in range(60)]
    d = decide(bars, look=30, ema_period=50, atr_mult=2.5)
    assert d.direction == "LONG"
    assert d.reason == "momentum_long"
    assert d.momentum_up is True
    assert d.momentum_down is False
    assert d.entry_price == bars[-1].close
    assert d.stop_price is not None
    assert d.stop_price < bars[-1].close  # LONG 스탑은 진입가 아래


def test_decide_short_momentum():
    bars = [_bar(200.0 - i, h=200.0 - i + 1, l=200.0 - i - 1) for i in range(60)]
    d = decide(bars, look=30, ema_period=50, atr_mult=2.5)
    assert d.direction == "SHORT"
    assert d.reason == "momentum_short"
    assert d.momentum_down is True
    assert d.momentum_up is False
    assert d.entry_price == bars[-1].close
    assert d.stop_price > bars[-1].close  # SHORT 스탑은 진입가 위


def test_decide_no_signal_flat():
    # 완전 횡보: 모멘텀 없음
    bars = [_bar(100.0, h=101.0, l=99.0) for _ in range(60)]
    d = decide(bars, look=30, ema_period=50)
    assert d.direction is None
    assert d.reason == "no_signal"
    assert d.momentum_up is False
    assert d.momentum_down is False
    assert d.entry_price == bars[-1].close


def test_decide_stop_uses_atr_mult():
    bars = [_bar(100.0 + i, h=100.0 + i + 1, l=100.0 + i - 1) for i in range(60)]
    a = atr_wilder(bars)
    c = bars[-1].close
    d = decide(bars, look=30, ema_period=50, atr_mult=2.5)
    assert math.isclose(d.stop_price, c - 2.5 * a[-1], rel_tol=1e-12)


# --------------------------------------------------- should_flip_exit
def test_flip_exit_long_stays_when_momentum_holds():
    bars = [_bar(100.0 + i, h=100.0 + i + 1, l=100.0 + i - 1) for i in range(60)]
    # 상승 지속 → LONG 유지 (flip 안 함)
    assert should_flip_exit(bars, "LONG", look=30, ema_period=50) is False


def test_flip_exit_long_flips_when_momentum_lost():
    # 상승 후 급락 마지막봉 → up 조건 깨짐 → LONG flip True
    bars = [_bar(100.0 + i, h=100.0 + i + 1, l=100.0 + i - 1) for i in range(59)]
    bars.append(_bar(50.0, h=51.0, l=49.0))
    assert should_flip_exit(bars, "LONG", look=30, ema_period=50) is True


def test_flip_exit_short_stays_when_momentum_holds():
    bars = [_bar(200.0 - i, h=200.0 - i + 1, l=200.0 - i - 1) for i in range(60)]
    assert should_flip_exit(bars, "SHORT", look=30, ema_period=50) is False


def test_flip_exit_short_flips_when_momentum_lost():
    bars = [_bar(200.0 - i, h=200.0 - i + 1, l=200.0 - i - 1) for i in range(59)]
    bars.append(_bar(300.0, h=301.0, l=299.0))
    assert should_flip_exit(bars, "SHORT", look=30, ema_period=50) is True


def test_flip_exit_insufficient_data_returns_false():
    bars = [_bar(float(i)) for i in range(10)]
    assert should_flip_exit(bars, "LONG") is False


# --------------------------------------------------- 뮤테이션 불가
def test_dailybar_is_frozen():
    b = _bar(100.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        b.close = 999.0  # type: ignore[misc]


def test_tsmdecision_is_frozen():
    d = decide([_bar(float(i)) for i in range(60)], look=30, ema_period=50)
    with pytest.raises(dataclasses.FrozenInstanceError):
        d.direction = "LONG"  # type: ignore[misc]


def test_decide_does_not_mutate_input():
    bars = [_bar(100.0 + i, h=100.0 + i + 1, l=100.0 + i - 1) for i in range(60)]
    snapshot = [(b.ts, b.open, b.high, b.low, b.close) for b in bars]
    decide(bars)
    after = [(b.ts, b.open, b.high, b.low, b.close) for b in bars]
    assert snapshot == after


# --------------------------------------------------- 백테스트 패리티
def _load_backtest():
    """scratchpad bt_v4 + klines 캐시 로드. 없으면 None."""
    cache = os.path.join(SCRATCH, "klines_1h_2y.json")
    if not (os.path.isdir(SCRATCH) and os.path.exists(cache)):
        return None
    if SCRATCH not in sys.path:
        sys.path.insert(0, SCRATCH)  # 검증 픽스처 예외 (프로젝트 코드 아님)
    try:
        from bt_v4 import agg  # noqa: PLC0415
        from bt_v4_robust import s2_tsm_f  # noqa: PLC0415
    except Exception:
        return None
    k = json.load(open(cache))
    b1d = agg(k, 24)
    return b1d, s2_tsm_f


def _reproduce_trades(b1d, look, ema_p, atr_mult):
    """decide/should_flip_exit로 백테스트 상태기계를 그대로 재현.

    stop-hit는 low/high로 판정(호출자 책임 영역), 진입 방향/가격/스탑은
    decide()에서, flip 청산은 should_flip_exit()에서 가져온다.
    """
    def to_bars(seq):
        return [DailyBar(ts=x["ts"], open=x["o"], high=x["h"],
                         low=x["l"], close=x["c"]) for x in seq]

    dir_map = {"LONG": 1, "SHORT": -1}
    name_map = {1: "LONG", -1: "SHORT"}
    out = []
    pos = None
    for i in range(max(look, ema_p), len(b1d)):
        window = to_bars(b1d[: i + 1])
        c = b1d[i]["c"]
        if pos is not None:
            hit = (pos["dir"] == 1 and b1d[i]["l"] <= pos["stop"]) or (
                pos["dir"] == -1 and b1d[i]["h"] >= pos["stop"])
            flip = should_flip_exit(window, name_map[pos["dir"]],
                                    look=look, ema_period=ema_p)
            if hit:
                out.append({**pos, "exit": pos["stop"]})
                pos = None
            elif flip:
                out.append({**pos, "exit": c})
                pos = None
        if pos is None:
            d = decide(window, look=look, ema_period=ema_p, atr_mult=atr_mult)
            if d.direction in ("LONG", "SHORT"):
                pos = {"entry": d.entry_price, "stop": d.stop_price,
                       "dir": dir_map[d.direction]}
    return out


@pytest.mark.skipif(_load_backtest() is None, reason="scratchpad 백테스트 픽스처 없음")
def test_parity_with_backtest_s2_tsm():
    """모듈로 재현한 트레이드 = 백테스트 s2_tsm_f 트레이드 (방향/진입/스탑/청산)."""
    b1d, s2_tsm_f = _load_backtest()
    look, ema_p, atr_mult = 30, 50, 2.5
    bt = s2_tsm_f(b1d, look=look, ema_p=ema_p, atr_mult=atr_mult)
    mine = _reproduce_trades(b1d, look, ema_p, atr_mult)

    assert len(bt) > 0, "백테스트 트레이드 0개 — 픽스처 이상"
    assert len(mine) == len(bt), f"트레이드 수 {len(mine)} != {len(bt)}"
    for j, (m, t) in enumerate(zip(mine, bt)):
        assert m["dir"] == t["dir"], f"trade[{j}] 방향 불일치"
        assert math.isclose(m["entry"], t["entry"], rel_tol=1e-12), (
            f"trade[{j}] entry 불일치")
        assert math.isclose(m["stop"], t["stop"], rel_tol=1e-12), (
            f"trade[{j}] stop 불일치")
        assert math.isclose(m["exit"], t["exit"], rel_tol=1e-12), (
            f"trade[{j}] exit 불일치")
