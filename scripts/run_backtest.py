"""
scripts/run_backtest.py

CBGB Backtest Framework — Bybit Historical Kline API 기반.

목적:
    실제 7일 1분봉 데이터로 앙상블 신호 엔진 백테스트.
    threshold=2/3/4 비교 후 최적값 도출.

실행:
    cd /home/selios/dg_bybit
    source venv/bin/activate
    python scripts/run_backtest.py
"""

from __future__ import annotations

import json
import math
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

# ── 프로젝트 루트를 sys.path에 추가 ────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from application.indicators.rsi import calculate_rsi  # noqa: E402
from application.indicators.macd import calculate_macd  # noqa: E402
from application.indicators.bollinger import calculate_bollinger  # noqa: E402
from application.indicators.volume import is_volume_confirmed  # noqa: E402


# ────────────────────────────────────────────────────────────────────────────
# 1. Kline Fetch (Public API — no auth required)
# ────────────────────────────────────────────────────────────────────────────

_BASE_URL = "https://api.bybit.com"
_KLINE_ENDPOINT = "/v5/market/kline"


def _fetch_kline_page(
    symbol: str,
    interval: str,
    limit: int,
    end_ts_ms: Optional[int] = None,
) -> list[list]:
    """단일 페이지 kline 조회 (최신→과거 순)."""
    params: dict = {
        "category": "linear",
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
    }
    if end_ts_ms is not None:
        params["end"] = end_ts_ms

    for attempt in range(3):
        try:
            resp = requests.get(
                _BASE_URL + _KLINE_ENDPOINT,
                params=params,
                timeout=15,
            )
            data = resp.json()
            if data.get("retCode") != 0:
                print(f"  [WARN] kline retCode={data.get('retCode')}: {data.get('retMsg')}")
                return []
            return data["result"]["list"]
        except Exception as exc:
            print(f"  [WARN] kline fetch attempt {attempt+1} failed: {exc}")
            time.sleep(1)
    return []


def fetch_historical_klines(
    symbol: str = "BTCUSDT",
    interval: str = "1",
    days: int = 7,
) -> list[dict]:
    """
    days일치 1분봉 kline 로드 (오래된 순 정렬).

    Returns:
        [{"ts": int_ms, "open": float, "high": float, "low": float,
          "close": float, "volume": float}, ...]
    """
    total_needed = days * 24 * 60  # 7d * 1440 = 10080
    page_size = 1000
    pages = math.ceil(total_needed / page_size)  # 11 pages

    print(f"Fetching {total_needed} candles ({pages} pages)...")

    raw: list[list] = []
    end_ts: Optional[int] = None

    for page in range(pages):
        batch = _fetch_kline_page(symbol, interval, page_size, end_ts)
        if not batch:
            print(f"  [WARN] Page {page+1} returned empty — stopping fetch")
            break

        raw.extend(batch)
        oldest_ts = int(batch[-1][0])
        end_ts = oldest_ts - 60_000  # 1min in ms

        print(f"  Page {page+1}/{pages}: {len(batch)} candles, "
              f"oldest={datetime.fromtimestamp(oldest_ts/1000, tz=timezone.utc).strftime('%m-%d %H:%M')}")

        if len(raw) >= total_needed:
            break

    raw.sort(key=lambda c: int(c[0]))
    raw = raw[-total_needed:]

    candles = [
        {
            "ts": int(c[0]),
            "open": float(c[1]),
            "high": float(c[2]),
            "low": float(c[3]),
            "close": float(c[4]),
            "volume": float(c[5]),
        }
        for c in raw
    ]

    print(f"Total candles loaded: {len(candles)}")
    if candles:
        first = datetime.fromtimestamp(candles[0]["ts"] / 1000, tz=timezone.utc)
        last = datetime.fromtimestamp(candles[-1]["ts"] / 1000, tz=timezone.utc)
        print(f"Period: {first.strftime('%Y-%m-%d %H:%M')} → {last.strftime('%Y-%m-%d %H:%M')} UTC")

    return candles


# ────────────────────────────────────────────────────────────────────────────
# 2. ATR (14-period, rolling)
# ────────────────────────────────────────────────────────────────────────────

def _calc_atr14(highs: list[float], lows: list[float], closes: list[float]) -> float:
    """14-period ATR (EMA of TR). 최소 15개 필요."""
    n = len(closes)
    if n < 15:
        return 0.0

    trs = [
        max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(closes[i - 1] - lows[i]))
        for i in range(1, n)
    ]

    atr = sum(trs[:14]) / 14
    mult = 2.0 / 15  # 2/(14+1)
    for tr in trs[14:]:
        atr = tr * mult + atr * (1 - mult)
    return atr


# ────────────────────────────────────────────────────────────────────────────
# 3. MA slope (10-period SMA, 5-bar comparison)
# ────────────────────────────────────────────────────────────────────────────

def _calc_ma_slope(closes: list[float], period: int = 10) -> float:
    """(SMA_current - SMA_5bars_ago) / SMA_5bars_ago * 100."""
    if len(closes) < period + 5:
        return 0.0
    sma_now = sum(closes[-period:]) / period
    sma_prev = sum(closes[-(period + 5):-5]) / period
    if sma_prev == 0:
        return 0.0
    return (sma_now - sma_prev) / sma_prev * 100.0


# ────────────────────────────────────────────────────────────────────────────
# 4. Raw Ensemble Score (bypass internal threshold — for threshold comparison)
# ────────────────────────────────────────────────────────────────────────────

def _raw_ensemble(
    prices: list[float],
    volumes: list[float],
    ma_slope_pct: float,
    t_trend: float = 0.05,
) -> tuple[int, int]:
    """
    5-indicator raw scores without entry threshold gate.

    Returns:
        (long_score, short_score)  — each 0..6
    """
    current_price = prices[-1] if prices else 0.0

    rsi_val = calculate_rsi(prices, period=14) if len(prices) >= 15 else None
    long_rsi = 2 if (rsi_val is not None and rsi_val < 30) else 0
    short_rsi = 2 if (rsi_val is not None and rsi_val > 70) else 0

    macd_result = calculate_macd(prices) if len(prices) >= 35 else None
    crossover = macd_result["crossover"] if macd_result else "none"
    long_macd = 1 if crossover == "bullish" else 0
    short_macd = 1 if crossover == "bearish" else 0

    bb_result = calculate_bollinger(prices, period=20) if len(prices) >= 20 else None
    long_bb = 0
    short_bb = 0
    if bb_result and current_price > 0:
        long_bb = 1 if current_price <= bb_result["lower"] else 0
        short_bb = 1 if current_price >= bb_result["upper"] else 0

    vol_confirmed = is_volume_confirmed(volumes) if len(volumes) >= 21 else False
    vol_score = 1 if vol_confirmed else 0

    long_slope = 1 if ma_slope_pct > t_trend else 0
    short_slope = 1 if ma_slope_pct < -t_trend else 0

    long_score = long_rsi + long_macd + long_bb + vol_score + long_slope
    short_score = short_rsi + short_macd + short_bb + vol_score + short_slope

    return long_score, short_score


# ────────────────────────────────────────────────────────────────────────────
# 5. Trade Simulation
# ────────────────────────────────────────────────────────────────────────────

@dataclass
class Trade:
    entry_time: str
    exit_time: str
    side: str
    entry_price: float
    exit_price: float
    pnl_pct: float
    pnl_usd: float
    exit_reason: str


def _simulate_trades(candles: list[dict], threshold: int) -> list[Trade]:
    """
    각 캔들에서 앙상블 신호 확인 후 트레이드 시뮬레이션.

    - 초기 자본: $100 USDT (레버리지 3x 적용)
    - 포지션 크기: 자본의 10% (Kelly-lite)
    - SL: entry * (1 ± atr_pct * 0.7)
    - TP trailing: peak에서 ATR*0.5 되돌림 시 청산
    - 수수료: taker 0.055% (진입+청산)
    """
    INITIAL_CAPITAL = 100.0
    LEVERAGE = 3.0
    POSITION_PCT = 0.10
    FEE_RATE = 0.00055
    WARM_UP = 200

    trades: list[Trade] = []
    in_position = False
    side = ""
    entry_price = 0.0
    entry_ts = 0
    sl_price = 0.0
    atr_for_tp = 0.0
    peak_price = 0.0

    capital = INITIAL_CAPITAL

    for i in range(WARM_UP, len(candles)):
        c = candles[i]
        window = candles[i - WARM_UP:i + 1]
        closes = [x["close"] for x in window]
        highs = [x["high"] for x in window]
        lows = [x["low"] for x in window]
        volumes = [x["volume"] for x in window]

        atr = _calc_atr14(highs, lows, closes)
        atr_pct = (atr / c["close"] * 100) if c["close"] > 0 else 0.0

        if in_position:
            curr_close = c["close"]

            if side == "Buy":
                peak_price = max(peak_price, c["high"])
                sl_hit = c["low"] <= sl_price
                tp_hit = (
                    peak_price > entry_price
                    and (peak_price - curr_close) >= atr_for_tp * 0.5
                )
            else:
                peak_price = min(peak_price, c["low"])
                sl_hit = c["high"] >= sl_price
                tp_hit = (
                    peak_price < entry_price
                    and (curr_close - peak_price) >= atr_for_tp * 0.5
                )

            if sl_hit or tp_hit:
                exit_price = sl_price if sl_hit else curr_close
                exit_reason = "SL" if sl_hit else "trailing_TP"
                exit_ts = c["ts"]

                pnl_pct = (
                    (exit_price - entry_price) / entry_price
                    if side == "Buy"
                    else (entry_price - exit_price) / entry_price
                )

                notional = capital * POSITION_PCT * LEVERAGE
                pnl_usd = notional * pnl_pct - notional * FEE_RATE * 2
                capital += pnl_usd

                trades.append(Trade(
                    entry_time=datetime.fromtimestamp(
                        entry_ts / 1000, tz=timezone.utc
                    ).strftime("%Y-%m-%d %H:%M"),
                    exit_time=datetime.fromtimestamp(
                        exit_ts / 1000, tz=timezone.utc
                    ).strftime("%Y-%m-%d %H:%M"),
                    side=side,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    pnl_pct=round(pnl_pct * 100, 4),
                    pnl_usd=round(pnl_usd, 4),
                    exit_reason=exit_reason,
                ))
                in_position = False

        else:
            ma_slope = _calc_ma_slope(closes)
            long_score, short_score = _raw_ensemble(closes, volumes, ma_slope)

            # Determine side: long priority when tied (BTC upside bias)
            if long_score >= threshold and long_score >= short_score:
                bt_side = "Buy"
                fire = True
            elif short_score >= threshold:
                bt_side = "Sell"
                fire = True
            else:
                fire = False

            if fire:
                in_position = True
                side = bt_side
                entry_price = c["close"]
                entry_ts = c["ts"]
                atr_for_tp = atr

                sl_atr_mult = 0.7
                if side == "Buy":
                    sl_price = entry_price * (1 - atr_pct / 100 * sl_atr_mult)
                    peak_price = entry_price
                else:
                    sl_price = entry_price * (1 + atr_pct / 100 * sl_atr_mult)
                    peak_price = entry_price

    return trades


# ────────────────────────────────────────────────────────────────────────────
# 6. Metrics Calculation
# ────────────────────────────────────────────────────────────────────────────

def _calc_metrics(trades: list[Trade]) -> dict:
    """win_rate, net_pnl, max_drawdown, sharpe 계산."""
    if not trades:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "net_pnl": 0.0,
            "max_dd": 0.0,
            "sharpe": 0.0,
        }

    wins = sum(1 for t in trades if t.pnl_usd > 0)
    pnls = [t.pnl_usd for t in trades]
    net_pnl = sum(pnls)

    # Max Drawdown (equity curve)
    equity = 0.0
    peak_eq = 0.0
    max_dd = 0.0
    for p in pnls:
        equity += p
        peak_eq = max(peak_eq, equity)
        dd = peak_eq - equity
        max_dd = max(max_dd, dd)

    # Sharpe (annualized per-trade, rf=0)
    n = len(pnls)
    avg = net_pnl / n
    if n > 1:
        variance = sum((p - avg) ** 2 for p in pnls) / (n - 1)
        std = math.sqrt(variance)
        # annualize: 1-min candle, 525600 min/year
        sharpe = (avg / std * math.sqrt(525600)) if std > 0 else 0.0
    else:
        sharpe = 0.0

    return {
        "trades": n,
        "win_rate": round(wins / n, 4),
        "net_pnl": round(net_pnl, 4),
        "max_dd": round(max_dd, 4),
        "sharpe": round(sharpe, 4),
    }


# ────────────────────────────────────────────────────────────────────────────
# 7. Main
# ────────────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print("CBGB Backtest Framework")
    print("=" * 60)

    candles = fetch_historical_klines(symbol="BTCUSDT", interval="1", days=7)
    if len(candles) < 210:
        print(f"[ERROR] Insufficient candles: {len(candles)} < 210")
        sys.exit(1)

    results: dict[str, dict] = {}
    for threshold in [2, 3, 4]:
        print(f"\nRunning backtest threshold={threshold}...")
        trades = _simulate_trades(candles, threshold)
        metrics = _calc_metrics(trades)
        results[f"threshold_{threshold}"] = metrics
        print(
            f"  threshold={threshold}: {metrics['trades']} trades, "
            f"win_rate={metrics['win_rate']:.2%}, "
            f"net_pnl=${metrics['net_pnl']:.2f}, "
            f"max_dd=${metrics['max_dd']:.2f}, "
            f"sharpe={metrics['sharpe']:.2f}"
        )

    # Optimal: net_pnl 최대 + max_dd 최소 (두 지표 모두 음수인 경우 올바른 비교)
    # sharpe * win_rate 조합은 모두 음수일 때 왜곡됨 → net_pnl 기반으로 전환
    def _score(m: dict) -> float:
        if m["trades"] == 0:
            return -999.0
        # net_pnl이 클수록(음수면 절대값 작을수록), max_dd가 작을수록 좋음
        return m["net_pnl"] - m["max_dd"] * 0.5

    optimal_t = max([2, 3, 4], key=lambda t: _score(results[f"threshold_{t}"]))
    opt_metrics = results[f"threshold_{optimal_t}"]

    recommendation = (
        f"threshold={optimal_t} 권장: "
        f"Sharpe={opt_metrics['sharpe']:.2f}, "
        f"win_rate={opt_metrics['win_rate']:.1%}, "
        f"net_pnl=${opt_metrics['net_pnl']:.2f}, "
        f"max_dd=${opt_metrics['max_dd']:.2f}. "
    )
    if optimal_t == 3:
        recommendation += "threshold=2 대비 과매매 방지, threshold=4 대비 신호 민감도 유지."
    elif optimal_t == 2:
        recommendation += "신호 빈도 높음 — 수수료 영향 모니터링 필요."
    else:
        recommendation += "신호 선별적 — 기회 손실 주의. win_rate 개선 효과 있음."

    report = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "period": "7d",
        "symbol": "BTCUSDT",
        "interval": "1min",
        "total_candles": len(candles),
        "results": results,
        "optimal_threshold": optimal_t,
        "recommendation": recommendation,
    }

    out_dir = _ROOT / "docs" / "daily" / "2026-03-20"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "backtest_framework_report.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    print("\n" + "=" * 60)
    print("BACKTEST RESULTS")
    print("=" * 60)
    for key, m in results.items():
        print(
            f"{key}: trades={m['trades']}, win={m['win_rate']:.1%}, "
            f"pnl=${m['net_pnl']:.2f}, dd=${m['max_dd']:.2f}, sharpe={m['sharpe']:.2f}"
        )
    print(f"\n[OPTIMAL] threshold={optimal_t}")
    print(f"[RECOMMENDATION] {recommendation}")
    print(f"\nReport saved: {out_path}")


if __name__ == "__main__":
    main()
