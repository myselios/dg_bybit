"""
src/application/tsm_trader.py

ADR-0015 Strategy v4 — Daily TSM 애플리케이션 서비스.

일봉 확정 후 1일 1회 판정:
  1. 포지션 보유 시 → should_flip_exit 판정 (플립이면 청산, 아니면 hold)
  2. 무포지션 시 → decide() 신호 → funding 필터 → 리스크 기반 사이징 → 진입

원칙 (CLAUDE.md / hard-rules):
- 금융 계산(qty/리스크)은 Decimal.
- shadow 모드는 주문을 내지 않는다. live 모드만 place_order 호출.
- 예외 발생 시 부분 체결 상태를 만들지 않고 {"action":"error"} 구조화 반환.
- 상태 전이 로직 없음(순수 판정 + I/O 위임).

신호 모듈(application.tsm_signal)은 병렬 구현 중이므로 import 실패를 허용한다
(런타임에 decide/should_flip_exit가 None이면 명시적 에러). 유닛 테스트는 이 심볼을
monkeypatch로 대체한다.
"""

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, cast

try:  # 신호 모듈은 병렬 구현 중 — 없으면 None, 유닛 테스트가 monkeypatch로 주입
    from application.tsm_signal import (  # type: ignore
        DailyBar,
        TsmDecision,
        decide,
        should_flip_exit,
    )
except ImportError:  # pragma: no cover - 통합 완료 후엔 항상 성공
    DailyBar = None  # type: ignore
    TsmDecision = None  # type: ignore
    decide = None  # type: ignore
    should_flip_exit = None  # type: ignore


logger = logging.getLogger(__name__)

# Bybit: 레버리지가 이미 목표값이면 이 코드로 응답 — 성공 취급.
_LEVERAGE_NOT_MODIFIED = 110043


@dataclass(frozen=True)
class TsmConfig:
    """Daily TSM 정책 수치 (ADR-0015)."""

    risk_pct: Decimal = Decimal("0.05")  # 거래당 리스크 (사용자 승인 5%)
    leverage_cap: Decimal = Decimal("3")
    funding_limit: float = 0.0005  # 진입 방향 부담 0.05%/8h 초과 시 스킵
    symbol: str = "BTCUSDT"
    qty_step: Decimal = Decimal("0.001")  # BTC lot step
    min_qty: Decimal = Decimal("0.001")
    look: int = 30
    ema_period: int = 50
    atr_mult: float = 2.5


def compute_order_qty(
    equity_usdt: Decimal,
    entry: Decimal,
    stop: Decimal,
    cfg: TsmConfig,
) -> Decimal:
    """리스크 기반 주문 수량 (BTC) 계산.

    risk_usd = equity * risk_pct
    qty      = risk_usd / |entry - stop|
    cap      = equity * leverage_cap / entry   (3x 레버리지 상한)
    result   = floor(min(qty, cap), qty_step)  → min_qty 미만이면 0

    모든 계산은 Decimal. 스텝 내림은 반올림이 아니라 floor.
    """
    stop_distance = abs(entry - stop)
    if stop_distance == 0 or entry <= 0 or equity_usdt <= 0:
        return Decimal("0")

    risk_usd = equity_usdt * cfg.risk_pct
    risk_qty = risk_usd / stop_distance
    leverage_qty = equity_usdt * cfg.leverage_cap / entry

    raw_qty = min(risk_qty, leverage_qty)
    floored = _floor_to_step(raw_qty, cfg.qty_step)

    if floored < cfg.min_qty:
        return Decimal("0")
    return floored


def _floor_to_step(qty: Decimal, step: Decimal) -> Decimal:
    """qty를 step 배수로 내림(floor). 결과는 step 스케일에 정규화."""
    steps = (qty / step).to_integral_value(rounding=ROUND_DOWN)
    return (steps * step).quantize(step)


class TsmTrader:
    """Daily TSM 트레이더 서비스.

    rest_client는 BybitRestClient 인터페이스
    (get_kline / get_position / get_tickers / get_wallet_balance / place_order).
    """

    def __init__(self, rest_client: Any, config: TsmConfig = TsmConfig()):
        self.client = rest_client
        self.cfg = config

    def run_daily_check(self, shadow: bool = True) -> Dict[str, Any]:
        """일봉 1회 판정. 모든 경로에서 구조화된 dict 반환.

        예외는 액션 없이 {"action":"error","error":...}로 수렴 (부분 상태 금지).
        """
        try:
            return self._run(shadow)
        except Exception as exc:  # noqa: BLE001 - 부분 체결 방지 위해 광범위 포착
            return {
                "action": "error",
                "error": str(exc),
                "shadow": shadow,
            }

    # ------------------------------------------------------------------
    # 내부 실행 경로
    # ------------------------------------------------------------------

    def _run(self, shadow: bool) -> Dict[str, Any]:
        bars = self._fetch_bars()

        position = self._current_position()
        if position is not None:
            return self._handle_open_position(bars, position, shadow)

        return self._handle_flat(bars, shadow)

    def _handle_open_position(
        self, bars: List[Any], position: Dict[str, Any], shadow: bool
    ) -> Dict[str, Any]:
        pos_side = "LONG" if position["side"] == "Buy" else "SHORT"
        if should_flip_exit is None:  # pragma: no cover - 통합 후 항상 존재
            raise RuntimeError("tsm_signal.should_flip_exit unavailable")

        flip = should_flip_exit(
            bars, pos_side, look=self.cfg.look, ema_period=self.cfg.ema_period
        )
        if not flip:
            return self._result("hold", shadow, direction=pos_side)

        size = position["size"]
        exit_side = "Sell" if pos_side == "LONG" else "Buy"
        if not shadow:
            self.client.place_order(
                symbol=self.cfg.symbol,
                side=exit_side,
                qty=str(size),
                order_link_id=self._link_id("flip"),
                order_type="Market",
                reduce_only=True,
            )
        return self._result(
            "flip_exit", shadow, direction=pos_side, qty=Decimal(str(size))
        )

    def _handle_flat(self, bars: List[Any], shadow: bool) -> Dict[str, Any]:
        if decide is None:  # pragma: no cover - 통합 후 항상 존재
            raise RuntimeError("tsm_signal.decide unavailable")

        decision = decide(
            bars,
            look=self.cfg.look,
            ema_period=self.cfg.ema_period,
            atr_mult=self.cfg.atr_mult,
        )
        if decision.direction is None:
            return self._result("no_signal", shadow, reason=getattr(decision, "reason", ""))

        # 신호 DTO는 float — 금융 계산 전에 Decimal로 강제 (hard-rules).
        entry = Decimal(str(decision.entry_price))
        stop = Decimal(str(decision.stop_price))

        if self._funding_blocks(decision.direction):
            return self._result(
                "skip_funding",
                shadow,
                direction=decision.direction,
                entry_ref=entry,
                stop_price=stop,
            )

        equity = self._equity_usdt()
        qty = compute_order_qty(equity, entry, stop, self.cfg)
        if qty == 0:
            return self._result(
                "qty_zero",
                shadow,
                direction=decision.direction,
                entry_ref=entry,
                stop_price=stop,
                equity=equity,
            )

        return self._open_entry(decision.direction, entry, stop, qty, equity, shadow)

    def _ensure_leverage(self) -> None:
        """진입 전 레버리지를 정책값(cfg.leverage_cap)으로 강제한다 (ADR-0015: 3x isolated).

        마진 모드는 계좌 단위(UTA)에서 ISOLATED로 이미 설정되어 있어 여기서 변경하지 않는다.
        retCode 110043(이미 목표값)은 성공. 그 외 I/O 실패는 경고 로그만 남기고 진입을 막지
        않는다 — 스탑이 손실을 고정하고, 이 사이즈에서 레버리지는 리스크에 비критично하며,
        월 2~3건 저빈도 특성상 유효 신호를 API 일시 오류로 스킵하는 비용이 더 크다.
        """
        try:
            resp = self.client.set_leverage(
                symbol=self.cfg.symbol,
                buy_leverage=str(self.cfg.leverage_cap),
                sell_leverage=str(self.cfg.leverage_cap),
            )
        except Exception as exc:  # noqa: BLE001 - I/O 실패는 진입 차단하지 않음
            logger.warning("set_leverage 실패, 진입 계속: %s", exc)
            return
        code = resp.get("retCode") if isinstance(resp, dict) else None
        if code not in (0, _LEVERAGE_NOT_MODIFIED, None):
            logger.warning(
                "set_leverage 비정상 retCode=%s (%s)", code, resp.get("retMsg")
            )

    def _open_entry(
        self,
        direction: str,
        entry: Decimal,
        stop: Decimal,
        qty: Decimal,
        equity: Decimal,
        shadow: bool,
    ) -> Dict[str, Any]:
        """진입 주문 발주(live) 또는 미발주(shadow) 후 구조화 결과 반환."""
        entry_side = "Buy" if direction == "LONG" else "Sell"
        if not shadow:
            self._ensure_leverage()
            self.client.place_order(
                symbol=self.cfg.symbol,
                side=entry_side,
                qty=str(qty),
                order_link_id=self._link_id("entry"),
                order_type="Market",
                stop_loss=str(stop),
                sl_trigger_by="MarkPrice",
            )
        return self._result(
            "entry",
            shadow,
            direction=direction,
            qty=qty,
            entry_ref=entry,
            stop_price=stop,
            equity=equity,
        )

    # ------------------------------------------------------------------
    # I/O 어댑터 (Bybit v5 응답 파싱)
    # ------------------------------------------------------------------

    def _fetch_bars(self) -> List[Any]:
        resp = self.client.get_kline(
            category="linear", symbol=self.cfg.symbol, interval="D", limit=100
        )
        rows = resp["result"]["list"]
        return self._to_daily_bars(rows)

    def _to_daily_bars(self, rows: List[List[str]]) -> List[Any]:
        """Bybit kline(newest-first) → DailyBar 리스트(오름차순, 미완성 최신봉 제외).

        rows[0]가 진행 중(미완성) 봉이므로 제외한 뒤 시간 오름차순으로 뒤집는다.
        row = [ts, open, high, low, close, volume, turnover] (DailyBar는 volume 미사용).
        """
        if DailyBar is None:  # pragma: no cover - 통합 후 항상 존재
            raise RuntimeError("tsm_signal.DailyBar unavailable")
        completed = rows[1:]  # 미완성 최신봉(index 0) 제외
        bars = []
        for row in reversed(completed):  # 오름차순(과거→최신)
            bars.append(
                DailyBar(
                    ts=int(row[0]),
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                )
            )
        return bars

    def _current_position(self) -> Optional[Dict[str, Any]]:
        resp = self.client.get_position(category="linear", symbol=self.cfg.symbol)
        for entry in resp["result"]["list"]:
            size = entry.get("size", "0")
            try:
                has_size = Decimal(str(size)) != 0
            except (InvalidOperation, ValueError):
                has_size = False
            if has_size and entry.get("side") in ("Buy", "Sell"):
                return cast(Dict[str, Any], entry)
        return None

    def _funding_blocks(self, direction: str) -> bool:
        resp = self.client.get_tickers(category="linear", symbol=self.cfg.symbol)
        funding = float(resp["result"]["list"][0]["fundingRate"])
        limit = self.cfg.funding_limit
        if direction == "LONG":
            return funding > limit  # LONG은 롱이 펀딩 지불(양수) 시 부담
        return funding < -limit  # SHORT는 숏이 펀딩 지불(음수) 시 부담

    def _equity_usdt(self) -> Decimal:
        resp = self.client.get_wallet_balance(accountType="UNIFIED", coin="USDT")
        account = resp["result"]["list"][0]
        for coin in account.get("coin", []):
            if coin.get("coin") == "USDT":
                return Decimal(str(coin["equity"]))
        # 폴백: totalEquity 필드
        return Decimal(str(account.get("totalEquity", "0")))

    # ------------------------------------------------------------------
    # 헬퍼
    # ------------------------------------------------------------------

    def _link_id(self, prefix: str) -> str:
        stamp = int(datetime.now(timezone.utc).timestamp())
        return f"tsm-{prefix}-{stamp}"[:36]

    def _result(self, action: str, shadow: bool, **fields: Any) -> Dict[str, Any]:
        base: Dict[str, Any] = {
            "action": action,
            "direction": fields.get("direction"),
            "qty": fields.get("qty"),
            "stop_price": fields.get("stop_price"),
            "entry_ref": fields.get("entry_ref"),
            "shadow": shadow,
            "symbol": self.cfg.symbol,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        for key in ("reason", "equity"):
            if key in fields:
                base[key] = fields[key]
        return base


def log_shadow_signal(
    record: Dict[str, Any],
    log_dir: str = "logs/tsm_shadow",
    date_str: Optional[str] = None,
) -> str:
    """run_daily_check 결과를 signals_YYYY-MM-DD.jsonl에 append.

    - 디렉토리 자동 생성.
    - Decimal 등 비직렬화 타입은 str로 변환.
    - live/shadow 모두 기록 (record["shadow"] 값이 구분).

    Returns: 기록한 파일 경로.
    """
    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, f"signals_{date_str}.jsonl")
    line = json.dumps(record, default=str, ensure_ascii=False)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return path
