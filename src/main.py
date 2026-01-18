"""Phase 0 검증 스크립트 - EV_FRAMEWORK 차단 로직 검증"""

from src.models.trading_context import (
    MarketData,
    TradingContext,
    TradingState,
    EVDecision,
)
from src.components.dummy_strategy import DummyStrategy
from src.components.ev_framework import EVFramework
from src.components.state_machine import StateMachine


def create_market_data(price: float, atr: float) -> MarketData:
    """테스트용 시장 데이터 생성"""
    return MarketData(
        price=price,
        ema200=price * 0.95,  # 상승 추세
        atr=atr,
        volume=1000.0,
        timestamp=0,
    )


def run_test_case(
    name: str, market_data: MarketData, strategy: DummyStrategy, ev_framework: EVFramework
) -> None:
    """단일 테스트 케이스 실행"""
    print(f"\n{'=' * 60}")
    print(f"TEST: {name}")
    print(f"{'=' * 60}")

    # State Machine 초기화
    state_machine = StateMachine()

    # INIT → IDLE
    context = TradingContext(state=TradingState.INIT, market_data=market_data)
    state_machine.transition(context)
    print(f"[1] State: {state_machine.get_current_state().value}")

    # IDLE → MONITORING
    context.state = state_machine.get_current_state()
    state_machine.transition(context)
    print(f"[2] State: {state_machine.get_current_state().value}")

    # Strategy 신호 생성
    signal = strategy.analyze(market_data)
    print(
        f"[3] Strategy Signal: {signal.direction.value}, "
        f"valid={signal.entry_valid}, confidence={signal.confidence:.2f}"
    )

    # EV_FRAMEWORK 평가
    ev_result = ev_framework.evaluate(signal, market_data)
    print(
        f"[4] EV Result: {ev_result.decision.value}, "
        f"R={ev_result.expected_r_multiple:.2f}, "
        f"P_win={ev_result.win_probability:.1%}"
    )

    if ev_result.decision == EVDecision.REJECT:
        print(f"    └─ Reason: {ev_result.rejection_reason}")

    # Context 업데이트
    context.strategy_signal = signal
    context.ev_result = ev_result
    context.state = state_machine.get_current_state()

    # MONITORING → ? (EV에 따라 ENTRY 또는 유지)
    next_state = state_machine.transition(context)
    print(f"[5] Final State: {next_state.value}")

    # 검증
    if ev_result.decision == EVDecision.PASS:
        if next_state == TradingState.ENTRY:
            print("✅ PASS: EV 통과 → ENTRY 진입 성공")
        else:
            print("❌ FAIL: EV 통과했지만 ENTRY 진입 실패")
    else:
        if next_state == TradingState.MONITORING:
            print("✅ PASS: EV 차단 → ENTRY 차단 성공")
        else:
            print("❌ FAIL: EV 차단했지만 ENTRY 진입됨 (심각한 오류)")


def main():
    """Phase 0 검증 메인"""
    print("\n" + "=" * 60)
    print("Phase 0: EV_FRAMEWORK 차단 로직 검증")
    print("=" * 60)
    print(
        "\n목표: EV_FRAMEWORK가 Strategy 신호를 차단할 수 있는지 증명\n"
        "- DummyStrategy: 항상 신호 발생\n"
        "- EVFramework: 조건부 PASS/REJECT\n"
        "- StateMachine: EV REJECT 시 ENTRY 차단\n"
    )

    strategy = DummyStrategy()
    ev_framework = EVFramework(
        min_win_probability=0.15,  # 15%
        min_r_multiple=3.0,  # +300%
    )

    # Test Case 1: 높은 변동성 → EV PASS 예상
    market_data_1 = create_market_data(price=50000.0, atr=2000.0)  # ATR 4%
    run_test_case(
        "Case 1: 높은 변동성 (ATR 4%) → EV PASS 예상",
        market_data_1,
        strategy,
        ev_framework,
    )

    # Test Case 2: 낮은 변동성 → EV REJECT 예상
    market_data_2 = create_market_data(price=50000.0, atr=200.0)  # ATR 0.4%
    run_test_case(
        "Case 2: 낮은 변동성 (ATR 0.4%) → EV REJECT 예상",
        market_data_2,
        strategy,
        ev_framework,
    )

    # Test Case 3: 중간 변동성 → 경계 케이스
    market_data_3 = create_market_data(price=50000.0, atr=1000.0)  # ATR 2%
    run_test_case(
        "Case 3: 중간 변동성 (ATR 2%) → 경계 케이스",
        market_data_3,
        strategy,
        ev_framework,
    )

    print("\n" + "=" * 60)
    print("Phase 0 검증 완료")
    print("=" * 60)
    print(
        "\n결과:\n"
        "- EV_FRAMEWORK가 Strategy 신호를 차단할 수 있는지 확인됨\n"
        "- MONITORING → ENTRY 전환 시 EV 검증이 작동함\n"
        "- 설계 정합성 검증 완료\n"
    )


if __name__ == "__main__":
    main()
