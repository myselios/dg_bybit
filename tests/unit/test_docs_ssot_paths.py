"""
tests/unit/test_docs_ssot_paths.py

Gate: Documentation-Code Path Alignment

Purpose:
  SSOT 문서(task_plan.md)가 실제 코드 경로와 일치하는지 검증한다.

  문서에 폐기된 경로가 남아있으면 실패한다.
  - 검증 실패 = SSOT 신뢰도 붕괴
  - 방치 시 결과 = "문서상 PASS / 실제 PASS" 분리

Failure Impact:
  - 회귀 테스트 기준이 잘못된 경로를 가리킴
  - Gate 1-8 증거가 재현 불가능해짐
  - Phase 0 검증 체계 붕괴

Execution:
  pytest tests/unit/test_docs_ssot_paths.py -v
"""

from pathlib import Path


def test_task_plan_has_no_deprecated_oracle_path():
    """
    SSOT 문서에 폐기된 오라클 경로가 없어야 한다.

    Given: task_plan.md 존재
    When: 파일 내용 읽기
    Then: "state_transition_test.py" 문자열이 0개 존재

    치명성: 폐기된 경로가 문서에 남으면
           - Primary truth 기준이 실제 파일과 불일치
           - Gate Evidence 재현 불가
           - SSOT 붕괴
    """
    task_plan_path = Path("docs/plans/task_plan.md")
    assert task_plan_path.exists(), "task_plan.md must exist"

    content = task_plan_path.read_text()

    # 폐기된 경로 존재 시 FAIL
    assert "state_transition_test.py" not in content, (
        "Deprecated path 'state_transition_test.py' found in task_plan.md. "
        "All references must use 'test_state_transition_oracle.py' instead."
    )


def test_task_plan_has_correct_oracle_path():
    """
    SSOT 문서에 올바른 오라클 경로가 존재해야 한다.

    Given: task_plan.md 존재
    When: 파일 내용 읽기
    Then: "test_state_transition_oracle.py" 문자열이 존재

    치명성: 올바른 경로가 없으면
           - Primary truth를 찾을 수 없음
           - 회귀 테스트 실행 불가
    """
    task_plan_path = Path("docs/plans/task_plan.md")
    assert task_plan_path.exists(), "task_plan.md must exist"

    content = task_plan_path.read_text()

    # 올바른 경로 존재해야 함
    assert "test_state_transition_oracle.py" in content, (
        "Correct path 'test_state_transition_oracle.py' not found in task_plan.md. "
        "This is the primary oracle file for Phase 0."
    )


def test_oracle_file_exists():
    """
    문서에서 참조하는 오라클 파일이 실제로 존재해야 한다.

    Given: task_plan.md가 test_state_transition_oracle.py를 참조
    When: 파일 시스템 확인
    Then: tests/oracles/test_state_transition_oracle.py 존재

    치명성: 문서가 존재하지 않는 파일을 가리키면
           - pytest 실행 시 ModuleNotFoundError
           - Primary truth 접근 불가
    """
    oracle_path = Path("tests/oracles/test_state_transition_oracle.py")
    assert oracle_path.exists(), (
        f"Oracle file {oracle_path} does not exist. "
        "This file is referenced in task_plan.md as the primary truth."
    )

    # 최소 크기 검증 (빈 파일 방지)
    assert oracle_path.stat().st_size > 1000, (
        f"Oracle file {oracle_path} is too small (< 1KB). "
        "Expected to contain at least 10 test cases."
    )


def test_deprecated_oracle_file_does_not_exist():
    """
    폐기된 오라클 파일이 존재하지 않아야 한다.

    Given: 파일명 변경 완료 (state_transition_test.py → test_state_transition_oracle.py)
    When: 파일 시스템 확인
    Then: tests/oracles/state_transition_test.py 존재하지 않음

    치명성: 폐기된 파일이 남아있으면
           - 어느 파일이 Primary truth인지 혼란
           - 잘못된 파일로 테스트 실행 가능
    """
    deprecated_path = Path("tests/oracles/state_transition_test.py")
    assert not deprecated_path.exists(), (
        f"Deprecated oracle file {deprecated_path} still exists. "
        "It should be renamed to test_state_transition_oracle.py."
    )
