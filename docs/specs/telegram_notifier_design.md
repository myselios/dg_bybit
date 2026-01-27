# Telegram Notifier 설계 문서

**Phase**: 12a-5a
**작성일**: 2026-01-27
**목적**: Testnet 거래 실시간 모니터링용 Telegram 알림 인프라

---

## 1. 책임 (Responsibility)

TelegramNotifier는 **Infrastructure Layer의 Notification 전용 컴포넌트**로, 다음 책임을 갖는다:

1. **거래 이벤트 → Telegram 메시지 변환**
   - Entry/Exit 거래 알림 (가격, 수량, PnL)
   - HALT/Session Risk 발동 알림
   - 거래 요약 통계

2. **Telegram Bot API 호출**
   - `sendMessage` endpoint 사용
   - Markdown formatting 지원

3. **에러 핸들링 (Silent Fail)**
   - Bot token/chat ID 없으면 disabled 상태
   - API 실패 시 로그만 출력, 예외 전파 안 함
   - **근거**: Telegram 실패가 거래 중단 원인이 되어서는 안 됨

**Non-Responsibility**:
- 거래 로직 개입 (read-only observer)
- 메시지 재전송/큐잉 (실패 시 즉시 포기)
- Rate limit 관리 (거래 빈도가 낮아 불필요)

---

## 2. 의존성 (Dependencies)

### 외부 의존성
- **Telegram Bot API**: `https://api.telegram.org/bot{token}/sendMessage`
- **Python 표준 라이브러리**: `urllib.request` (HTTP POST)

### 환경 변수
- `TELEGRAM_BOT_TOKEN`: Telegram bot token (from @BotFather)
- `TELEGRAM_CHAT_ID`: Target chat ID (from @userinfobot)

### 내부 의존성
- **없음** (Pure infrastructure layer, Domain/Application과 독립)

---

## 3. 클래스 설계

```python
"""
src/infrastructure/notification/telegram_notifier.py

Telegram 알림 전송 (Infrastructure Layer)
"""

import os
import logging
from typing import Optional
from urllib import request, parse, error


logger = logging.getLogger(__name__)


class TelegramNotifier:
    """
    Telegram Bot API를 통한 거래 알림 전송

    특징:
    - 환경변수에서 bot token/chat ID 자동 로드
    - token/chat ID 없으면 disabled 상태 (silent)
    - API 실패 시 로그만 출력, 예외 전파 안 함 (거래 중단 방지)
    """

    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
    ):
        """
        Args:
            bot_token: Telegram bot token (default: 환경변수 TELEGRAM_BOT_TOKEN)
            chat_id: Target chat ID (default: 환경변수 TELEGRAM_CHAT_ID)
        """
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")

        if not self.enabled:
            logger.warning("TelegramNotifier disabled: bot_token or chat_id missing")

    @property
    def enabled(self) -> bool:
        """Telegram 알림 활성화 여부 (bot_token과 chat_id 있으면 True)"""
        return bool(self.bot_token and self.chat_id)

    def send_entry(
        self,
        side: str,
        qty: float,
        price: float,
        entry_reason: str,
        equity_before: float,
        position_size_pct: float,
        wallet_balance: float,
        positions_count: int,
        total_invested: float,
        total_value: float,
        total_pnl_pct: float,
        total_pnl_usd: float,
    ) -> bool:
        """
        Entry 알림 전송

        Args:
            side: "Buy" or "Sell"
            qty: 수량 (BTC)
            price: 진입 가격 (USD)
            entry_reason: 진입 이유 (예: "가격이 하락하여 자동 매수 ($104,500 도달)")
            equity_before: 진입 전 통합잔고 (USDT)
            position_size_pct: 투자 비중 (전체 자산 대비 %)
            wallet_balance: USDT 잔고
            positions_count: 보유 포지션 개수
            total_invested: 투자 금액 (USD)
            total_value: 평가 금액 (USD)
            total_pnl_pct: 총 손익 (%)
            total_pnl_usd: 총 손익 (USD)

        Returns:
            bool: 전송 성공 여부

        Example:
            🟢 *Entry Buy*
            Qty: 0.012 BTC ($1,254)
            Entry Price: $104,500

            📍 진입 이유: 가격이 하락하여 자동 매수 ($104,500 도달)
            💰 진입 전 잔고: $100,500 USDT
            📊 투자 비중: 전체 자산의 2.5%

            💼 전체 포트폴리오
            ━━━━━━━━━━━━━━━━━━━━
            💵 USDT 잔고: $100,500
            📊 보유 포지션: 1개
            💰 투자 금액: $1,254
            📈 평가 금액: $1,254
            📉 총 손익: 0.00% ($0)
        """
        if not self.enabled:
            return False

        emoji = "🟢" if side == "Buy" else "🔴"
        qty_usd = qty * price

        text = f"{emoji} *Entry {side}*\n"
        text += f"Qty: {qty:.3f} BTC (${qty_usd:,.0f})\n"
        text += f"Entry Price: ${price:,.2f}\n\n"
        text += f"📍 진입 이유: {entry_reason}\n"
        text += f"💰 진입 전 잔고: ${equity_before:,.0f} USDT\n"
        text += f"📊 투자 비중: 전체 자산의 {position_size_pct:.1f}%\n\n"
        text += self._format_portfolio(
            wallet_balance, positions_count, total_invested,
            total_value, total_pnl_pct, total_pnl_usd
        )

        return self._send_message(text)

    def send_exit(
        self,
        side: str,
        qty: float,
        entry_price: float,
        exit_price: float,
        pnl_usd: float,
        pnl_pct: float,
        exit_reason: str,
        equity_after: float,
        hold_duration: str,
        wallet_balance: float,
        positions_count: int,
        total_invested: float,
        total_value: float,
        total_pnl_pct: float,
        total_pnl_usd: float,
    ) -> bool:
        """
        Exit 알림 전송

        Args:
            side: "Buy" or "Sell"
            qty: 청산 수량 (BTC)
            entry_price: 진입 가격 (USD)
            exit_price: 청산 가격 (USD)
            pnl_usd: 실현 손익 (USD)
            pnl_pct: 실현 손익 (%)
            exit_reason: 청산 이유 (예: "목표 수익 달성으로 자동 청산")
            equity_after: 청산 후 통합잔고 (USDT)
            hold_duration: 보유 시간 (예: "2시간 35분")
            wallet_balance: USDT 잔고
            positions_count: 보유 포지션 개수
            total_invested: 투자 금액 (USD)
            total_value: 평가 금액 (USD)
            total_pnl_pct: 총 손익 (%)
            total_pnl_usd: 총 손익 (USD)

        Returns:
            bool: 전송 성공 여부

        Example (Profit):
            ✅ *Exit Sell - 익절 성공*
            Qty: 0.012 BTC
            매수가: $104,500 → 청산가: $105,200
            수익: +$15.23 USD (+1.47%)

            📍 청산 이유: 목표 수익 달성으로 자동 청산
            💰 청산 후 잔고: $100,515 USDT
            ⏱️ 보유 시간: 2시간 35분

            💼 전체 포트폴리오
            ━━━━━━━━━━━━━━━━━━━━
            💵 USDT 잔고: $100,515
            📊 보유 포지션: 0개
            💰 투자 금액: $0
            📈 평가 금액: $0
            📉 총 손익: +0.02% (+$15)
        """
        if not self.enabled:
            return False

        if pnl_usd >= 0:
            emoji = "✅"
            status = "익절 성공"
        else:
            emoji = "❌"
            status = "손절 실행"

        text = f"{emoji} *Exit {side} - {status}*\n"
        text += f"Qty: {qty:.3f} BTC\n"
        text += f"매수가: ${entry_price:,.2f} → 청산가: ${exit_price:,.2f}\n"

        pnl_sign = "+" if pnl_usd >= 0 else ""
        pnl_label = "수익" if pnl_usd >= 0 else "손실"
        text += f"{pnl_label}: {pnl_sign}${pnl_usd:.2f} USD ({pnl_sign}{pnl_pct:.2f}%)\n\n"

        text += f"📍 청산 이유: {exit_reason}\n"
        text += f"💰 청산 후 잔고: ${equity_after:,.0f} USDT\n"
        text += f"⏱️ 보유 시간: {hold_duration}\n\n"
        text += self._format_portfolio(
            wallet_balance, positions_count, total_invested,
            total_value, total_pnl_pct, total_pnl_usd
        )

        return self._send_message(text)

    def _format_portfolio(
        self,
        wallet_balance: float,
        positions_count: int,
        total_invested: float,
        total_value: float,
        total_pnl_pct: float,
        total_pnl_usd: float,
    ) -> str:
        """
        포트폴리오 요약 포맷 (공통 Helper)

        Args:
            wallet_balance: USDT 잔고
            positions_count: 보유 포지션 개수
            total_invested: 투자 금액 (USD)
            total_value: 평가 금액 (USD)
            total_pnl_pct: 총 손익 (%)
            total_pnl_usd: 총 손익 (USD)

        Returns:
            str: 포트폴리오 요약 텍스트
        """
        pnl_sign = "+" if total_pnl_usd >= 0 else ""
        text = "💼 전체 포트폴리오\n"
        text += "━━━━━━━━━━━━━━━━━━━━\n"
        text += f"💵 USDT 잔고: ${wallet_balance:,.0f}\n"
        text += f"📊 보유 포지션: {positions_count}개\n"
        text += f"💰 투자 금액: ${total_invested:,.0f}\n"
        text += f"📈 평가 금액: ${total_value:,.0f}\n"
        text += f"📉 총 손익: {pnl_sign}{total_pnl_pct:.2f}% ({pnl_sign}${total_pnl_usd:,.0f})"
        return text

    def send_halt(
        self,
        reason: str,
        equity: float = 0.0,
    ) -> bool:
        """
        HALT 알림 전송

        Args:
            reason: HALT 사유
            equity: 현재 잔고 (USD, optional)

        Returns:
            bool: 전송 성공 여부

        Example:
            🚨 *HALT*
            Reason: Daily loss cap
            Equity: $95.00
        """
        if not self.enabled:
            return False

        text = "🚨 *HALT*\n"
        text += f"Reason: {reason}"
        if equity > 0:
            text += f"\nEquity: ${equity:.2f}"

        return self._send_message(text)

    def send_session_risk(
        self,
        trigger: str,
        details: str = "",
    ) -> bool:
        """
        Session Risk 발동 알림 전송

        Args:
            trigger: 발동 트리거 (예: "Loss streak 3")
            details: 상세 정보 (optional)

        Returns:
            bool: 전송 성공 여부

        Example:
            ⚠️ *Session Risk*
            Trigger: Loss streak 3
            Details: Entries blocked for 10min
        """
        if not self.enabled:
            return False

        text = "⚠️ *Session Risk*\n"
        text += f"Trigger: {trigger}"
        if details:
            text += f"\nDetails: {details}"

        return self._send_message(text)

    def send_summary(
        self,
        trades: int,
        wins: int,
        losses: int,
        pnl: float,
    ) -> bool:
        """
        거래 요약 알림 전송

        Args:
            trades: 총 거래 횟수
            wins: 승리 횟수
            losses: 손실 횟수
            pnl: 총 손익 (USD)

        Returns:
            bool: 전송 성공 여부

        Example:
            📊 *Trading Summary*
            Trades: 30
            Wins: 18 | Losses: 12
            PnL: +$45.67
        """
        if not self.enabled:
            return False

        text = "📊 *Trading Summary*\n"
        text += f"Trades: {trades}\n"
        text += f"Wins: {wins} | Losses: {losses}\n"
        text += f"PnL: {'+' if pnl >= 0 else ''}{pnl:.2f} USD"

        return self._send_message(text)

    def _send_message(self, text: str) -> bool:
        """
        Telegram sendMessage API 호출 (internal)

        Args:
            text: 메시지 본문 (Markdown 지원)

        Returns:
            bool: 전송 성공 여부 (실패 시 로그만 출력)
        """
        if not self.enabled:
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        data = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }

        try:
            req = request.Request(
                url,
                data=parse.urlencode(data).encode("utf-8"),
                method="POST",
            )
            with request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    logger.debug(f"Telegram message sent: {text[:50]}...")
                    return True
                else:
                    logger.error(f"Telegram API error: HTTP {response.status}")
                    return False

        except error.URLError as e:
            logger.error(f"Telegram API network error: {e}")
            return False

        except Exception as e:
            logger.error(f"Telegram API unexpected error: {type(e).__name__}: {e}")
            return False
```

---

## 4. 메시지 포맷 (Markdown + Emoji)

### Entry 알림 (진입)
```
🟢 *Entry Buy*
Qty: 0.012 BTC ($1,254)
Entry Price: $104,500

📍 진입 이유: 가격이 하락하여 자동 매수 ($104,500 도달)
💰 진입 전 잔고: $100,500 USDT
📊 투자 비중: 전체 자산의 2.5%

💼 전체 포트폴리오
━━━━━━━━━━━━━━━━━━━━
💵 USDT 잔고: $100,500
📊 보유 포지션: 1개
💰 투자 금액: $1,254
📈 평가 금액: $1,254
📉 총 손익: 0.00% ($0)
```

**필드**:
- **Qty**: 매수 수량 (BTC) + USD 가치
- **Entry Price**: 진입 가격
- **진입 이유**:
  - "가격이 하락하여 자동 매수 (목표가 도달)"
  - "가격이 상승하여 자동 매도 (목표가 도달)"
  - "강제 진입 모드 (테스트)" 등
- **진입 전 잔고**: 매수 전 총 잔고 (USDT)
- **투자 비중**: 전체 자산 대비 포지션 크기 (%)
- **Portfolio**: 전체 포트폴리오 현황

### Exit 알림 - Profit (익절)
```
✅ *Exit Sell - 익절 성공*
Qty: 0.012 BTC
매수가: $104,500 → 청산가: $105,200
수익: +$15.23 USD (+1.47%)

📍 청산 이유: 목표 수익 달성으로 자동 청산
💰 청산 후 잔고: $100,515 USDT
⏱️ 보유 시간: 2시간 35분

💼 전체 포트폴리오
━━━━━━━━━━━━━━━━━━━━
💵 USDT 잔고: $100,515
📊 보유 포지션: 0개
💰 투자 금액: $0
📈 평가 금액: $0
📉 총 손익: +0.02% (+$15)
```

**필드**:
- **Qty**: 청산 수량 (BTC)
- **매수가 → 청산가**: 진입 → 청산 가격 흐름
- **수익**: 실현 손익 (USD + 수익률 %)
- **청산 이유**:
  - "목표 수익 달성으로 자동 청산"
  - "수동 청산 (사용자 요청)"
  - "시장 상황에 따른 조기 청산" 등
- **청산 후 잔고**: 청산 후 총 잔고 (USDT)
- **보유 시간**: 포지션 보유 기간
- **Portfolio**: 전체 포트폴리오 현황

### Exit 알림 - Loss (손절)
```
❌ *Exit Sell - 손절 실행*
Qty: 0.012 BTC
매수가: $104,500 → 청산가: $103,800
손실: -$8.40 USD (-0.67%)

📍 청산 이유: 손절가 도달하여 손실 제한 (-2% 기준)
💰 청산 후 잔고: $100,492 USDT
⏱️ 보유 시간: 15분

💼 전체 포트폴리오
━━━━━━━━━━━━━━━━━━━━
💵 USDT 잔고: $100,492
📊 보유 포지션: 0개
💰 투자 금액: $0
📈 평가 금액: $0
📉 총 손익: -0.01% (-$8)
```

**필드**:
- **손실**: 실현 손실 (USD + 손실률 %)
- **청산 이유**:
  - "손절가 도달하여 손실 제한 (설정 -2%)"
  - "연속 손실 발생으로 자동 중단 (세션 리스크)"
  - "일일 손실 한도 도달로 자동 중단" 등
- **청산 후 잔고**: 손절 후 총 잔고 (USDT)
- **보유 시간**: 포지션 보유 기간
- **Portfolio**: 전체 포트폴리오 현황

### HALT 알림
```
🚨 *HALT*
Reason: Daily loss cap
Equity: $95.00
```

### Session Risk 알림
```
⚠️ *Session Risk*
Trigger: Loss streak 3
Details: Entries blocked for 10min
```

### Trading Summary
```
📊 *Trading Summary*
Trades: 30
Wins: 18 | Losses: 12
PnL: +$45.67
```

---

## 5. 에러 처리 (Silent Fail)

### 원칙
**Telegram 실패가 거래 중단 원인이 되어서는 안 됨**

### 구현
1. **Bot token/chat ID 없음**:
   - `enabled = False`
   - 모든 메서드 호출 시 즉시 `return False`
   - 로그 1회 출력 (WARNING level, 초기화 시)

2. **API 호출 실패**:
   - 네트워크 에러 (`URLError`)
   - Rate limit (HTTP 429)
   - Timeout (5초)
   - **처리**: 로그만 출력 (ERROR level), 예외 전파 안 함

3. **예외 처리 스택**:
   ```python
   try:
       # Telegram API call
   except error.URLError as e:
       logger.error(f"Telegram API network error: {e}")
       return False
   except Exception as e:
       logger.error(f"Telegram API unexpected error: {e}")
       return False
   ```

---

## 6. Integration Point

### run_testnet_dry_run.py

```python
from infrastructure.notification.telegram_notifier import TelegramNotifier

# 초기화 (환경변수 자동 로드)
telegram = TelegramNotifier()

if telegram.enabled:
    logger.info("✅ Telegram notifier enabled")
else:
    logger.info("ℹ️ Telegram notifier disabled (no bot token/chat ID)")

# Main loop
previous_state = State.FLAT

for tick in range(1, max_ticks + 1):
    result = orchestrator.run_tick()
    current_state = result.state

    # State 전환 감지
    if previous_state == State.FLAT and current_state == State.IN_POSITION:
        # Entry 발생
        if orchestrator.position:
            telegram.send_entry(
                side=orchestrator.position.side,
                qty=orchestrator.position.qty,
                price=orchestrator.position.entry_price,
                signal_id=orchestrator.position.signal_id,
            )

    elif previous_state == State.IN_POSITION and current_state == State.FLAT:
        # Exit 발생 (Trade log에서 PnL 가져오기)
        trade_logs = log_storage.read_trade_logs_v1()
        if trade_logs:
            last_trade = trade_logs[-1]
            pnl = last_trade.get("realized_pnl_usd", 0.0)
            telegram.send_exit(
                side="Sell",  # Exit은 항상 포지션 반대 방향
                qty=last_trade.get("qty_btc", 0.0),
                price=last_trade.get("exit_price", 0.0),
                pnl=pnl,
                reason="Grid exit",
            )

    # HALT 감지
    if current_state == State.HALT:
        halt_reason = result.halt_reason or "Unknown"
        equity = market_data.get_equity_usdt()
        telegram.send_halt(reason=halt_reason, equity=equity)

    previous_state = current_state

# 최종 요약
telegram.send_summary(
    trades=monitor.total_trades,
    wins=monitor.successful_cycles,
    losses=monitor.failed_cycles,
    pnl=total_pnl,
)
```

---

## 7. Unit Tests (10+ Cases)

### tests/unit/test_telegram_notifier.py

```python
"""
Unit tests for TelegramNotifier

Coverage:
- 초기화 (환경변수 로드, enabled 속성)
- send_entry() (Buy/Sell, 성공/실패)
- send_exit() (profit/loss, reason 포함/미포함)
- send_halt()
- send_session_risk()
- send_summary()
- _send_message() (API 호출 모킹)
- 에러 처리 (network error, timeout, HTTP error)
"""

import pytest
from unittest.mock import patch, MagicMock
from infrastructure.notification.telegram_notifier import TelegramNotifier


# Test 1: 환경변수 로드
def test_init_from_env_vars():
    """환경변수에서 bot token/chat ID 로드"""
    with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_CHAT_ID": "12345"}):
        notifier = TelegramNotifier()
        assert notifier.bot_token == "test_token"
        assert notifier.chat_id == "12345"
        assert notifier.enabled is True


# Test 2: 직접 전달 (환경변수 우선순위 낮음)
def test_init_with_args():
    """생성자 인자로 bot token/chat ID 전달"""
    notifier = TelegramNotifier(bot_token="arg_token", chat_id="67890")
    assert notifier.bot_token == "arg_token"
    assert notifier.chat_id == "67890"
    assert notifier.enabled is True


# Test 3: Disabled 상태 (bot token 없음)
def test_disabled_when_no_token():
    """bot token 없으면 disabled"""
    notifier = TelegramNotifier(bot_token=None, chat_id="12345")
    assert notifier.enabled is False


# Test 4: Disabled 상태 (chat ID 없음)
def test_disabled_when_no_chat_id():
    """chat ID 없으면 disabled"""
    notifier = TelegramNotifier(bot_token="test_token", chat_id=None)
    assert notifier.enabled is False


# Test 5: send_entry() 성공
@patch("infrastructure.notification.telegram_notifier.request.urlopen")
def test_send_entry_success(mock_urlopen):
    """Entry 알림 전송 성공"""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_urlopen.return_value.__enter__.return_value = mock_response

    notifier = TelegramNotifier(bot_token="test_token", chat_id="12345")
    result = notifier.send_entry(side="Buy", qty=0.012, price=104500, signal_id="abc123")

    assert result is True
    mock_urlopen.assert_called_once()


# Test 6: send_entry() disabled
def test_send_entry_disabled():
    """Disabled 상태에서 send_entry() 호출 → 즉시 False 반환"""
    notifier = TelegramNotifier(bot_token=None, chat_id=None)
    result = notifier.send_entry(side="Buy", qty=0.012, price=104500)

    assert result is False


# Test 7: send_exit() profit
@patch("infrastructure.notification.telegram_notifier.request.urlopen")
def test_send_exit_profit(mock_urlopen):
    """Exit 알림 (profit) 전송"""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_urlopen.return_value.__enter__.return_value = mock_response

    notifier = TelegramNotifier(bot_token="test_token", chat_id="12345")
    result = notifier.send_exit(side="Sell", qty=0.012, price=105200, pnl=15.23, reason="Grid exit")

    assert result is True


# Test 8: send_exit() loss
@patch("infrastructure.notification.telegram_notifier.request.urlopen")
def test_send_exit_loss(mock_urlopen):
    """Exit 알림 (loss) 전송"""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_urlopen.return_value.__enter__.return_value = mock_response

    notifier = TelegramNotifier(bot_token="test_token", chat_id="12345")
    result = notifier.send_exit(side="Sell", qty=0.012, price=103800, pnl=-8.40, reason="Stop hit")

    assert result is True
    # 메시지에 "❌" emoji 포함 확인 (call_args로 검증 가능)


# Test 9: send_halt()
@patch("infrastructure.notification.telegram_notifier.request.urlopen")
def test_send_halt(mock_urlopen):
    """HALT 알림 전송"""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_urlopen.return_value.__enter__.return_value = mock_response

    notifier = TelegramNotifier(bot_token="test_token", chat_id="12345")
    result = notifier.send_halt(reason="Daily loss cap", equity=95.00)

    assert result is True


# Test 10: send_session_risk()
@patch("infrastructure.notification.telegram_notifier.request.urlopen")
def test_send_session_risk(mock_urlopen):
    """Session Risk 알림 전송"""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_urlopen.return_value.__enter__.return_value = mock_response

    notifier = TelegramNotifier(bot_token="test_token", chat_id="12345")
    result = notifier.send_session_risk(trigger="Loss streak 3", details="Entries blocked for 10min")

    assert result is True


# Test 11: send_summary()
@patch("infrastructure.notification.telegram_notifier.request.urlopen")
def test_send_summary(mock_urlopen):
    """거래 요약 알림 전송"""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_urlopen.return_value.__enter__.return_value = mock_response

    notifier = TelegramNotifier(bot_token="test_token", chat_id="12345")
    result = notifier.send_summary(trades=30, wins=18, losses=12, pnl=45.67)

    assert result is True


# Test 12: API 네트워크 에러 (silent fail)
@patch("infrastructure.notification.telegram_notifier.request.urlopen")
def test_send_message_network_error(mock_urlopen):
    """API 네트워크 에러 발생 시 False 반환 (예외 전파 안 함)"""
    from urllib.error import URLError
    mock_urlopen.side_effect = URLError("Network error")

    notifier = TelegramNotifier(bot_token="test_token", chat_id="12345")
    result = notifier.send_entry(side="Buy", qty=0.012, price=104500)

    assert result is False  # Silent fail


# Test 13: API HTTP 에러 (HTTP 500)
@patch("infrastructure.notification.telegram_notifier.request.urlopen")
def test_send_message_http_error(mock_urlopen):
    """API HTTP 에러 (500) 발생 시 False 반환"""
    mock_response = MagicMock()
    mock_response.status = 500
    mock_urlopen.return_value.__enter__.return_value = mock_response

    notifier = TelegramNotifier(bot_token="test_token", chat_id="12345")
    result = notifier.send_entry(side="Buy", qty=0.012, price=104500)

    assert result is False


# Test 14: API Timeout
@patch("infrastructure.notification.telegram_notifier.request.urlopen")
def test_send_message_timeout(mock_urlopen):
    """API timeout 발생 시 False 반환"""
    import socket
    mock_urlopen.side_effect = socket.timeout("Timeout")

    notifier = TelegramNotifier(bot_token="test_token", chat_id="12345")
    result = notifier.send_entry(side="Buy", qty=0.012, price=104500)

    assert result is False
```

---

## 8. Evidence

### Sub-task 12a-5e: Testnet 재실행 검증

1. **Telegram bot 생성** (@BotFather):
   - `/newbot` 명령어로 bot 생성
   - Bot token 획득
   - Chat ID 획득 (@userinfobot)

2. **.env 설정**:
   ```bash
   echo "TELEGRAM_BOT_TOKEN=your_bot_token_here" >> .env
   echo "TELEGRAM_CHAT_ID=your_chat_id_here" >> .env
   ```

3. **Testnet 실행** (5-10회 거래):
   ```bash
   python scripts/run_testnet_dry_run.py --target-trades 5
   ```

4. **Telegram 알림 스크린샷** (Evidence):
   - Entry 알림 수신 확인
   - Exit 알림 수신 확인 (PnL 표시)
   - Trading Summary 수신 확인
   - 스크린샷 저장: `docs/evidence/phase_12a-5/telegram_notifications.png`

5. **로그 확인**:
   ```bash
   tail -f logs/testnet_dry_run.log | grep "Telegram"
   ```
   - "Telegram notifier enabled" 확인
   - "Telegram message sent" 확인
   - 에러 없음 확인

---

## 요약

**TelegramNotifier 설계 핵심**:
1. **Silent Fail**: Telegram 실패가 거래를 중단하지 않음
2. **Pure Infrastructure**: Domain/Application과 독립, 환경변수로 제어
3. **Simple Integration**: `run_testnet_dry_run.py`에 3줄 추가로 통합 완료
4. **Testable**: 10+ unit tests, HTTP 모킹으로 API 호출 검증

**다음 단계**: Sub-task 12a-5b (TelegramNotifier 구현)
