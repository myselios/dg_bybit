"""
src/infrastructure/notification/telegram_notifier.py

Phase 12a-5: Telegram 알림 전송 (Infrastructure Layer)

Telegram Bot API를 통한 거래 알림 전송
- Entry/Exit 거래 알림
- HALT/Session Risk 발동 알림
- 거래 요약 통계

특징:
- 환경변수에서 bot token/chat ID 자동 로드
- token/chat ID 없으면 disabled 상태 (silent)
- API 실패 시 로그만 출력, 예외 전파 안 함 (거래 중단 방지)
"""

import json
import os
import logging
from typing import Any, Dict, List, Optional
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

    def send_error(
        self,
        error_type: str,
        error_message: str,
        context: str = "",
    ) -> bool:
        """
        에러 알림 전송 (봇 실행 중 예외 발생 시)

        Args:
            error_type: 에러 타입 (예: "TickError", "InitializationError")
            error_message: 에러 메시지
            context: 추가 컨텍스트 (optional, 예: "Tick 125", "Entry flow")

        Returns:
            bool: 전송 성공 여부

        Example:
            🔥 *BOT ERROR*
            Type: TickError
            Context: Tick 125
            Message: Connection timeout

            ⚠️ 봇이 중단되었습니다. 로그를 확인하세요.
        """
        if not self.enabled:
            return False

        text = "🔥 *BOT ERROR*\n"
        text += f"Type: {error_type}\n"
        if context:
            text += f"Context: {context}\n"
        text += f"Message: {error_message}\n\n"
        text += "⚠️ 봇이 중단되었습니다. 로그를 확인하세요."

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

    def send_param_change(
        self,
        param_name: str,
        old_val: float,
        new_val: float,
        reason: str,
    ) -> bool:
        """파라미터 자동 변경 알림 (단방향, 승인 불필요).

        Args:
            param_name: 변경된 파라미터 이름
            old_val: 기존 값
            new_val: 변경된 값
            reason: 변경 근거 (ReflectionAgent hypothesis)

        Returns:
            bool: 전송 성공 여부
        """
        if not self.enabled:
            return False

        direction = "▲" if new_val > old_val else "▼"
        change_pct = abs(new_val - old_val) / old_val * 100 if old_val != 0 else 0

        text = (
            f"🔧 *파라미터 자동 조정*\n\n"
            f"*{param_name}*: `{old_val:.4f}%` → `{new_val:.4f}%` "
            f"({direction}{change_pct:.0f}%)\n\n"
            f"📋 근거: {reason}"
        )
        return self._send_message(text)

    def send_approval_request(
        self,
        approval_id: str,
        param_name: str,
        old_val: float,
        new_val: float,
        reason: str,
    ) -> bool:
        """파라미터 변경 승인 요청 (Inline Keyboard 버튼 포함).

        Args:
            approval_id: 승인 요청 고유 ID
            param_name: 변경할 파라미터 이름 (예: T_TREND)
            old_val: 기존 값
            new_val: 변경 제안 값
            reason: 변경 근거

        Returns:
            bool: 전송 성공 여부
        """
        if not self.enabled:
            return False

        change_pct = abs(new_val - old_val) / old_val * 100 if old_val != 0 else 0
        direction = "▲" if new_val > old_val else "▼"

        text = (
            f"🤖 *파라미터 변경 승인 요청*\n\n"
            f"*{param_name}*: `{old_val:.4f}%` → `{new_val:.4f}%` "
            f"({direction}{change_pct:.0f}%, MAJOR)\n\n"
            f"📋 근거: {reason}\n\n"
            f"승인하면 다음 틱부터 즉시 적용됩니다."
        )

        buttons = [
            [
                {"text": "✅ 승인", "callback_data": f"approve_{approval_id}"},
                {"text": "❌ 거부", "callback_data": f"reject_{approval_id}"},
            ]
        ]
        return self._send_message_with_buttons(text, buttons)

    def get_updates(self, offset: int = 0) -> List[Dict[str, Any]]:
        """Telegram getUpdates polling.

        Args:
            offset: 이전 update_id + 1 (처리된 메시지 skip)

        Returns:
            list: update 목록 (빈 리스트면 새 메시지 없음)
        """
        if not self.enabled:
            return []

        url = (
            f"https://api.telegram.org/bot{self.bot_token}"
            f"/getUpdates?offset={offset}&timeout=0&limit=10"
        )

        try:
            req = request.Request(url, method="GET")
            with request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    body = json.loads(response.read().decode("utf-8"))
                    return body.get("result", [])
                return []
        except Exception as e:
            logger.error(f"Telegram getUpdates error: {type(e).__name__}: {e}")
            return []

    def answer_callback_query(self, callback_query_id: str, text: str = "") -> bool:
        """버튼 클릭 후 스피너 해제.

        Args:
            callback_query_id: Telegram callback query ID
            text: 팝업 텍스트 (선택)

        Returns:
            bool: 성공 여부
        """
        if not self.enabled:
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/answerCallbackQuery"
        data: Dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            data["text"] = text

        try:
            req = request.Request(
                url,
                data=parse.urlencode(data).encode("utf-8"),
                method="POST",
            )
            with request.urlopen(req, timeout=5) as response:
                return response.status == 200
        except Exception as e:
            logger.error(f"Telegram answerCallbackQuery error: {e}")
            return False

    def _send_message_with_buttons(
        self, text: str, buttons: List[List[Dict[str, str]]]
    ) -> bool:
        """Inline Keyboard 버튼이 포함된 메시지 전송.

        Args:
            text: 메시지 본문
            buttons: inline_keyboard 배열 (행 × 열)

        Returns:
            bool: 전송 성공 여부
        """
        if not self.enabled:
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        reply_markup = json.dumps({"inline_keyboard": buttons})
        data = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "reply_markup": reply_markup,
        }

        try:
            req = request.Request(
                url,
                data=parse.urlencode(data).encode("utf-8"),
                method="POST",
            )
            with request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    logger.debug("Telegram approval request sent")
                    return True
                logger.error(f"Telegram API error: HTTP {response.status}")
                return False
        except Exception as e:
            logger.error(f"Telegram _send_message_with_buttons error: {e}")
            return False

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
