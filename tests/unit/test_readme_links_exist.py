"""
tests/unit/test_readme_links_exist.py

Gate: README-Docs File Alignment

Purpose:
  README.md에서 링크된 모든 파일이 실제로 존재하는지 검증한다.

  존재하지 않는 파일 링크가 있으면 실패한다.
  - 검증 실패 = SSOT 신뢰도 붕괴
  - 방치 시 결과 = 문서 기준이 404 → 임의 추측 → 레포 상태와 어긋남

Failure Impact:
  - 운영/리뷰 기준이 존재하지 않는 파일을 가리킴
  - 배포 기준이 "문서 장식"으로 전락
  - Phase 1+ 작업이 잘못된 문서 기준으로 진행

Execution:
  pytest tests/unit/test_readme_links_exist.py -v
"""

from pathlib import Path
import re


def test_readme_markdown_links_all_exist():
    """
    README.md에서 링크된 모든 .md 파일이 존재해야 한다.

    Given: README.md 존재
    When: 파일 내용에서 [text](path.md) 패턴 추출
    Then: 모든 .md 링크가 실제 파일 시스템에 존재

    치명성: 존재하지 않는 파일 링크가 있으면
           - 문서 기준으로 작업 시 404
           - 운영/리뷰 기준점이 거짓
           - SSOT 선언 붕괴

    SSOT 3문서 (허용):
        - docs/constitution/FLOW.md
        - docs/specs/account_builder_policy.md
        - docs/plans/task_plan.md
    """
    readme_path = Path("README.md")
    assert readme_path.exists(), "README.md must exist"

    content = readme_path.read_text()

    # [text](path.md) 패턴 추출
    # 절대 경로, 상대 경로, http(s) URL 모두 매칭
    link_pattern = r'\[([^\]]+)\]\(([^)]+\.md)\)'
    matches = re.findall(link_pattern, content)

    # http(s) URL 제외 (외부 링크)
    local_links = [
        (text, path) for text, path in matches
        if not path.startswith('http://') and not path.startswith('https://')
    ]

    # 각 로컬 링크가 존재하는지 확인
    missing_links = []
    for text, path in local_links:
        # 상대 경로 처리 (README.md는 repo root에 있음)
        full_path = Path(path)
        if not full_path.exists():
            missing_links.append((text, path))

    # 실패 시 자세한 에러 메시지
    if missing_links:
        error_msg = (
            f"README.md contains {len(missing_links)} broken link(s):\n"
        )
        for text, path in missing_links:
            error_msg += f"  - [{text}]({path}) → FILE NOT FOUND\n"

        error_msg += (
            "\nAllowed SSOT documents:\n"
            "  - docs/constitution/FLOW.md\n"
            "  - docs/specs/account_builder_policy.md\n"
            "  - docs/plans/task_plan.md\n"
            "\nAction: Remove broken links or create the referenced files."
        )

        raise AssertionError(error_msg)


def test_readme_references_ssot_documents():
    """
    README.md가 SSOT 3문서를 참조해야 한다.

    Given: README.md 존재
    When: 파일 내용 읽기
    Then: FLOW.md, account_builder_policy.md, task_plan.md 중 최소 1개 언급

    치명성: SSOT 문서 참조가 없으면
           - README가 실제 운영 기준을 가리키지 않음
           - 신규 기여자가 헌법/정책/계획을 찾을 수 없음
    """
    readme_path = Path("README.md")
    assert readme_path.exists(), "README.md must exist"

    content = readme_path.read_text()

    ssot_docs = [
        "FLOW.md",
        "account_builder_policy.md",
        "task_plan.md"
    ]

    found_ssot = [doc for doc in ssot_docs if doc in content]

    assert len(found_ssot) > 0, (
        f"README.md must reference at least one SSOT document.\n"
        f"Required: {ssot_docs}\n"
        f"Found: {found_ssot}\n"
        f"Add links to SSOT documents in README.md."
    )
