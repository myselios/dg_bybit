"""시계열 모멘텀(TSM) 신호 — 순수 함수 레이어.

일봉 시계열 모멘텀 전략(백테스트 S2)의 신호 판정 로직을 I/O 없이 제공한다.
검증된 백테스트(scratchpad/bt_v4.py의 ema/atr_wilder/s2_tsm)와 수치가
비트 단위로 일치하도록 정의를 고정한다.

주의:
  - 이 모듈은 순수(pure)하다. 네트워크/디스크/시간 접근 금지.
  - `decide`/`should_flip_exit`에 넘기는 bars는 **확정된(closed) 일봉만**
    포함해야 한다. 미완성 현재봉 제외는 호출자 책임이다.
"""
from dataclasses import dataclass
from typing import Optional, Sequence


@dataclass(frozen=True)
class DailyBar:
    ts: int  # ms epoch
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class TsmDecision:
    direction: Optional[str]  # "LONG" | "SHORT" | None
    stop_price: Optional[float]
    entry_price: Optional[float]  # 판정 기준가 = 마지막 확정봉 close
    reason: str  # momentum_long | momentum_short | no_signal | insufficient_data
    momentum_up: bool
    momentum_down: bool


def ema(values: Sequence[float], period: int) -> list[float]:
    """지수이동평균. seed = values[0] (SMA 시드 아님), k = 2/(period+1).

    out[i] = out[i-1] + k*(values[i] - out[i-1]).
    백테스트 bt_v4.ema와 동일 정의.
    """
    if not values:
        return []
    k = 2.0 / (period + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(out[-1] + k * (v - out[-1]))
    return out


def atr_wilder(bars: Sequence[DailyBar], period: int = 14) -> list[float]:
    """Wilder ATR. 백테스트 bt_v4.atr_wilder와 동일 정의.

    TR[0] = high-low.
    TR[i] = max(high-low, |high-prev_close|, |prev_close-low|).
    처음 period개 원소는 sum(TR[:period])/period로 채우고,
    이후 out[i] = (out[i-1]*(period-1) + TR[i]) / period.
    """
    if not bars:
        return []
    trs = [bars[0].high - bars[0].low]
    for i in range(1, len(bars)):
        pc = bars[i - 1].close
        trs.append(max(bars[i].high - bars[i].low,
                       abs(bars[i].high - pc), abs(pc - bars[i].low)))
    seed = sum(trs[:period]) / period
    out = [seed] * min(period, len(trs))
    for i in range(period, len(trs)):
        out.append((out[-1] * (period - 1) + trs[i]) / period)
    return out


def _momentum(bars: Sequence[DailyBar], look: int,
              ema_period: int) -> tuple[bool, bool, float]:
    """(momentum_up, momentum_down, last_close). 데이터 충분 가정."""
    closes = [b.close for b in bars]
    e = ema(closes, ema_period)
    c = closes[-1]
    prior = closes[-1 - look]
    up = c > prior and c > e[-1]
    down = c < prior and c < e[-1]
    return up, down, c


def decide(bars: Sequence[DailyBar], look: int = 30, ema_period: int = 50,
           atr_mult: float = 2.5) -> TsmDecision:
    """확정 일봉 시퀀스에서 진입 신호를 판정한다.

    c = bars[-1].close 기준:
      momentum_up   = c > bars[-1-look].close AND c > ema(closes, ema_period)[-1]
      momentum_down = c < bars[-1-look].close AND c < ema[-1]
    LONG이면 stop = c - atr_mult*atr[-1], SHORT이면 c + atr_mult*atr[-1].
    데이터 < max(look+1, ema_period) → insufficient_data.
    """
    if len(bars) < max(look + 1, ema_period):
        return TsmDecision(None, None, None, "insufficient_data", False, False)
    up, down, c = _momentum(bars, look, ema_period)
    if up:
        stop = c - atr_mult * atr_wilder(bars)[-1]
        return TsmDecision("LONG", stop, c, "momentum_long", True, False)
    if down:
        stop = c + atr_mult * atr_wilder(bars)[-1]
        return TsmDecision("SHORT", stop, c, "momentum_short", False, True)
    return TsmDecision(None, None, c, "no_signal", False, False)


def should_flip_exit(bars: Sequence[DailyBar], position_direction: str,
                     look: int = 30, ema_period: int = 50) -> bool:
    """보유 방향의 모멘텀이 깨졌으면 True (플립 청산 신호).

    LONG 보유 중 momentum_up이 False가 되면 True. SHORT는 대칭.
    데이터 부족 시 False (청산하지 않음).
    """
    if len(bars) < max(look + 1, ema_period):
        return False
    up, down, _ = _momentum(bars, look, ema_period)
    if position_direction == "LONG":
        return not up
    if position_direction == "SHORT":
        return not down
    return False
