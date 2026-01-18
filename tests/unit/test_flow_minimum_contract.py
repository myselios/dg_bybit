"""
tests/unit/test_flow_minimum_contract.py

Gate: FLOW.md 최소 계약 검증

Purpose:
  FLOW.md가 강제하는 Tick Execution Flow와 Emergency Check가
  코드에 최소 골격으로 존재하는지 검증한다.

  골격 부재 시 실패한다.
  - 검증 실패 = Phase 1 작업이 구조적 기반 없이 진행됨
  - 방치 시 결과 = emergency/ws_health가 "어디서 호출되는지" 미정의

Failure Impact:
  - Tick 오케스트레이터 없음 → 실행 순서 강제 불가
  - Emergency Check 골격 없음 → Phase 1 emergency.py가 호출 위치 불명
  - FLOW 헌법 위반 → "코드는 우회 불가" 선언 붕괴

Execution:
  pytest tests/unit/test_flow_minimum_contract.py -v

FLOW_REF: docs/constitution/FLOW.md#2 (Tick Execution Flow)
"""

from pathlib import Path
import inspect


def test_tick_engine_module_exists():
    """
    tick_engine 모듈이 존재해야 한다.

    Given: FLOW.md Section 2 "Tick Execution Flow (1 Cycle)" 요구사항
    When: src/application/tick_engine.py import 시도
    Then: 모듈 import 성공, tick() 함수 호출 가능

    치명성: Tick 오케스트레이터 없으면
           - Snapshot → Emergency → Event → Position 순서 강제 불가
           - Phase 1 emergency/ws_health가 호출될 구조적 위치 없음
    """
    # Import 가능 여부 검증
    try:
        from application.tick_engine import tick
    except ImportError as e:
        raise AssertionError(
            f"tick_engine module not found: {e}\n"
            "FLOW.md Section 2 requires Tick Execution Flow orchestrator. "
            "Create src/application/tick_engine.py with tick() function."
        )

    # tick() 함수가 호출 가능한지 검증
    assert callable(tick), "tick() must be callable"


def test_emergency_gate_module_exists():
    """
    emergency 모듈이 존재해야 한다.

    Given: FLOW.md Section 1.5 "Emergency Check (최우선, 항상)" 요구사항
    When: src/application/emergency.py import 시도
    Then: 모듈 import 성공, evaluate() 함수 호출 가능

    치명성: Emergency Check 골격 없으면
           - Priority 0 (Signal보다 먼저) 실행 불가
           - Phase 1 emergency.py가 구조적 위치 불명
    """
    # Import 가능 여부 검증
    try:
        from application.emergency import evaluate
    except ImportError as e:
        raise AssertionError(
            f"emergency module not found: {e}\n"
            "FLOW.md Section 1.5 requires Emergency Check (Priority 0). "
            "Create src/application/emergency.py with evaluate() function."
        )

    # evaluate() 함수가 호출 가능한지 검증
    assert callable(evaluate), "evaluate() must be callable"


def test_emergency_evaluated_before_transition():
    """
    Emergency Check가 transition보다 먼저 평가되어야 한다.

    Given: FLOW.md Section 2 Tick Flow "Emergency Check (최우선, 항상)"
    When: tick() 소스 코드 읽기
    Then: "Emergency" 문자열이 "transition" 문자열보다 먼저 등장

    치명성: Emergency가 Signal 이후에 평가되면
           - 지연/장애 상황에서 잘못된 주문 체결 후 뒤늦게 HALT
           - "Emergency는 Signal보다 항상 먼저" 헌법 위반
    """
    from application import tick_engine

    # tick() 소스 읽기
    source = inspect.getsource(tick_engine.tick)

    # "Emergency" 위치 검색
    emergency_keywords = ["Emergency", "emergency", "evaluate"]
    emergency_positions = [source.find(kw) for kw in emergency_keywords if source.find(kw) > 0]

    # "transition" 위치 검색
    transition_keywords = ["transition", "Handle Events"]
    transition_positions = [source.find(kw) for kw in transition_keywords if source.find(kw) > 0]

    # 둘 다 존재해야 함
    assert len(emergency_positions) > 0, (
        "tick() must contain Emergency Check. "
        "Add emergency.evaluate() call or 'Emergency Check' comment."
    )

    assert len(transition_positions) > 0, (
        "tick() must contain transition call or reference. "
        "Add transition() call or '[2] Handle Events' comment."
    )

    # Emergency가 먼저 등장해야 함
    min_emergency_pos = min(emergency_positions)
    min_transition_pos = min(transition_positions)

    assert min_emergency_pos < min_transition_pos, (
        f"Emergency Check must appear BEFORE transition in tick() source.\n"
        f"Found Emergency at position {min_emergency_pos}, "
        f"transition at {min_transition_pos}.\n"
        f"FLOW.md Section 2 requires '[1.5] Emergency Check (최우선, 항상)' "
        f"to execute before '[2] Handle Execution Events'."
    )


def test_tick_engine_file_has_flow_reference():
    """
    tick_engine.py가 FLOW.md를 참조해야 한다.

    Given: tick_engine.py 존재
    When: 파일 헤더 읽기
    Then: "FLOW.md" 또는 "FLOW_REF" 문자열 존재

    치명성: FLOW 참조 없으면
           - 구현이 어느 헌법 섹션을 따르는지 불명
           - 헌법 업데이트 시 코드 추적 불가
    """
    tick_engine_path = Path("src/application/tick_engine.py")
    assert tick_engine_path.exists(), "tick_engine.py must exist"

    content = tick_engine_path.read_text()

    assert "FLOW.md" in content or "FLOW_REF" in content, (
        "tick_engine.py must reference FLOW.md as the constitutional source. "
        "Add 'FLOW_REF: docs/constitution/FLOW.md#2' to the docstring."
    )


def test_emergency_gate_file_has_flow_reference():
    """
    emergency.py가 FLOW.md를 참조해야 한다.

    Given: emergency.py 존재
    When: 파일 헤더 읽기
    Then: "FLOW.md" 또는 "FLOW_REF" 문자열 존재

    치명성: FLOW 참조 없으면
           - Emergency Check 구현이 헌법 어느 섹션을 따르는지 불명
    """
    emergency_path = Path("src/application/emergency.py")
    assert emergency_path.exists(), "emergency.py must exist"

    content = emergency_path.read_text()

    assert "FLOW.md" in content or "FLOW_REF" in content, (
        "emergency.py must reference FLOW.md as the constitutional source. "
        "Add 'FLOW_REF: docs/constitution/FLOW.md#1.5' to the docstring."
    )
