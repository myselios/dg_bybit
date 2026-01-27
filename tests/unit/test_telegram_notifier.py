"""
tests/unit/test_telegram_notifier.py

Phase 12a-5: Telegram Notifier Unit Tests

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
    result = notifier.send_entry(
        side="Buy",
        qty=0.012,
        price=104500,
        entry_reason="가격이 하락하여 자동 매수 ($104,500 도달)",
        equity_before=100500.0,
        position_size_pct=2.5,
        wallet_balance=100500.0,
        positions_count=1,
        total_invested=1254.0,
        total_value=1254.0,
        total_pnl_pct=0.0,
        total_pnl_usd=0.0,
    )

    assert result is True
    mock_urlopen.assert_called_once()


# Test 6: send_entry() disabled
def test_send_entry_disabled():
    """Disabled 상태에서 send_entry() 호출 → 즉시 False 반환"""
    notifier = TelegramNotifier(bot_token=None, chat_id=None)
    result = notifier.send_entry(
        side="Buy",
        qty=0.012,
        price=104500,
        entry_reason="Test entry",
        equity_before=100000.0,
        position_size_pct=1.0,
        wallet_balance=100000.0,
        positions_count=1,
        total_invested=0.0,
        total_value=0.0,
        total_pnl_pct=0.0,
        total_pnl_usd=0.0,
    )

    assert result is False


# Test 7: send_exit() profit
@patch("infrastructure.notification.telegram_notifier.request.urlopen")
def test_send_exit_profit(mock_urlopen):
    """Exit 알림 (profit) 전송"""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_urlopen.return_value.__enter__.return_value = mock_response

    notifier = TelegramNotifier(bot_token="test_token", chat_id="12345")
    result = notifier.send_exit(
        side="Sell",
        qty=0.012,
        entry_price=104500.0,
        exit_price=105200.0,
        pnl_usd=15.23,
        pnl_pct=1.47,
        exit_reason="목표 수익 달성으로 자동 청산",
        equity_after=100515.0,
        hold_duration="2시간 35분",
        wallet_balance=100515.0,
        positions_count=0,
        total_invested=0.0,
        total_value=0.0,
        total_pnl_pct=0.02,
        total_pnl_usd=15.0,
    )

    assert result is True


# Test 8: send_exit() loss
@patch("infrastructure.notification.telegram_notifier.request.urlopen")
def test_send_exit_loss(mock_urlopen):
    """Exit 알림 (loss) 전송"""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_urlopen.return_value.__enter__.return_value = mock_response

    notifier = TelegramNotifier(bot_token="test_token", chat_id="12345")
    result = notifier.send_exit(
        side="Sell",
        qty=0.012,
        entry_price=104500.0,
        exit_price=103800.0,
        pnl_usd=-8.40,
        pnl_pct=-0.67,
        exit_reason="손절가 도달하여 손실 제한 (-2% 기준)",
        equity_after=100492.0,
        hold_duration="15분",
        wallet_balance=100492.0,
        positions_count=0,
        total_invested=0.0,
        total_value=0.0,
        total_pnl_pct=-0.01,
        total_pnl_usd=-8.0,
    )

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
    result = notifier.send_entry(
        side="Buy",
        qty=0.012,
        price=104500,
        entry_reason="Test",
        equity_before=100000.0,
        position_size_pct=1.0,
        wallet_balance=100000.0,
        positions_count=1,
        total_invested=0.0,
        total_value=0.0,
        total_pnl_pct=0.0,
        total_pnl_usd=0.0,
    )

    assert result is False  # Silent fail


# Test 13: API HTTP 에러 (HTTP 500)
@patch("infrastructure.notification.telegram_notifier.request.urlopen")
def test_send_message_http_error(mock_urlopen):
    """API HTTP 에러 (500) 발생 시 False 반환"""
    mock_response = MagicMock()
    mock_response.status = 500
    mock_urlopen.return_value.__enter__.return_value = mock_response

    notifier = TelegramNotifier(bot_token="test_token", chat_id="12345")
    result = notifier.send_entry(
        side="Buy",
        qty=0.012,
        price=104500,
        entry_reason="Test",
        equity_before=100000.0,
        position_size_pct=1.0,
        wallet_balance=100000.0,
        positions_count=1,
        total_invested=0.0,
        total_value=0.0,
        total_pnl_pct=0.0,
        total_pnl_usd=0.0,
    )

    assert result is False


# Test 14: API Timeout
@patch("infrastructure.notification.telegram_notifier.request.urlopen")
def test_send_message_timeout(mock_urlopen):
    """API timeout 발생 시 False 반환"""
    import socket
    mock_urlopen.side_effect = socket.timeout("Timeout")

    notifier = TelegramNotifier(bot_token="test_token", chat_id="12345")
    result = notifier.send_entry(
        side="Buy",
        qty=0.012,
        price=104500,
        entry_reason="Test",
        equity_before=100000.0,
        position_size_pct=1.0,
        wallet_balance=100000.0,
        positions_count=1,
        total_invested=0.0,
        total_value=0.0,
        total_pnl_pct=0.0,
        total_pnl_usd=0.0,
    )

    assert result is False
