# Placeholder 테스트 제거 증거 (Phase 8)
Date: 2026-01-23
Phase: 8 (Testnet Validation)

## 문제 (Gate 1b 위반)

**CLAUDE.md Section 5.7 Gate 1b**:
```bash
# (1b) Skip/Xfail decorator 금지 (정당한 사유 없으면 FAIL)
grep -RInE "pytest\.mark\.(skip|xfail)|@pytest\.mark\.(skip|xfail)" tests/ 2>/dev/null | grep -v "\.pyc"
# → 출력: 비어있음 (또는 특정 allowlist 경로만)
```

**Before (2026-01-23, Gate 1b FAIL)**:
```bash
$ grep -RInE "@pytest\.mark\.skip" tests/
tests/integration_real/test_execution_event_mapping.py:104:@pytest.mark.skip(reason="Requires actual order placement, implement after REST order flow is ready")

# → 1개 검출 → FAIL
```

**테스트 함수 내용**:
```python
@pytest.mark.skip(reason="Requires actual order placement, implement after REST order flow is ready")
def test_ws_execution_message_from_order_fill(api_credentials):
    """시나리오 3: 실제 주문 발주 → 체결 → execution 메시지 수신"""
    # TODO: REST 클라이언트로 주문 발주
    # TODO: WS로 execution 메시지 수신
    # TODO: ExecutionEvent로 변환
    pass
```

**CLAUDE.md Section 5.1 Zero Tolerance**:
- "`assert True`, `pass`, `TODO` 포함 테스트는 **테스트가 아니다**"
- → `# TODO` 3개 + `pass` → **완전한 placeholder**

**task_plan.md Section 7 Oracle Backlog 규칙**:
> 규칙: 미래 Phase를 위한 테스트 케이스는 **테스트 파일에 placeholder로 존재하지 않는다** (Gate 1 위반).
> 대신 이 섹션에 문서화하고, 해당 Phase 시작 시 **TDD (RED→GREEN)** 로 작성한다.

---

## 수정 조치

### 1. Placeholder 테스트 함수 제거

**파일**: `tests/integration_real/test_execution_event_mapping.py`

**Before** (Line 103-119):
```python
@pytest.mark.testnet
@pytest.mark.skip(reason="Requires actual order placement, implement after REST order flow is ready")
def test_ws_execution_message_from_order_fill(api_credentials):
    """시나리오 3: 실제 주문 발주 → 체결 → execution 메시지 수신"""
    # TODO: REST 클라이언트로 주문 발주
    # TODO: WS로 execution 메시지 수신
    # TODO: ExecutionEvent로 변환
    pass
```

**After**: 삭제 (Line 103-119 전체 제거)

---

### 2. Oracle Backlog 섹션에 문서화

**파일**: `docs/plans/task_plan.md`

**추가**: Section 7 "Oracle Backlog" → "Execution Event Mapping from Order Fill (Phase 9+)"

```markdown
### Execution Event Mapping from Order Fill (Phase 9+)

> 실제 주문 발주 → 체결 → execution 메시지 수신 → 도메인 이벤트 변환

| ID | Preconditions | Event | Expected State | Expected Intents | Evidence |
|----|---------------|-------|----------------|------------------|----------|
| EX-1 | REST로 소액 주문 발주 (Market order, BTCUSD, 1 contract) | WS execution 메시지 수신 | - | ExecutionEvent(FILL) 변환 성공, orderId/execQty 일치 | TBD |
| EX-2 | REST로 소액 주문 발주 (Limit order, BTCUSD, 10 contracts, 부분 체결 가능) | WS execution 메시지 수신 (부분 체결) | - | ExecutionEvent(PARTIAL_FILL) 변환 성공, execQty < orderQty | TBD |
| EX-3 | REST로 주문 발주 후 즉시 취소 | WS execution 메시지 수신 (CANCEL) | - | ExecutionEvent(CANCEL) 변환 성공, execQty=0 | TBD |

**Notes:**
- EX-1~EX-3: Phase 9에서 구현 예정 (REST order flow 완성 후)
- 삭제된 placeholder 테스트: `test_ws_execution_message_from_order_fill` (2026-01-23, Gate 1b 위반 수정)
```

---

### 3. conftest.py 생성 (pytest.skip() 중복 제거)

**파일**: `tests/integration_real/conftest.py` (신규 생성)

```python
"""
tests/integration_real/conftest.py
Shared fixtures for integration_real tests (live Testnet tests)

SSOT: CLAUDE.md Section 5.7 Gate 1a/1b (중복 제거)
"""

import os
import pytest


@pytest.fixture
def api_credentials():
    """
    Testnet API credentials from environment variables

    Auto-skip if credentials not available (정당한 사유: API key 누락)

    Returns:
        dict: {"api_key": str, "api_secret": str}

    Raises:
        pytest.skip: If credentials not available
    """
    api_key = os.getenv("BYBIT_TESTNET_API_KEY")
    api_secret = os.getenv("BYBIT_TESTNET_API_SECRET")

    if not api_key or not api_secret:
        pytest.skip("Testnet API credentials not available (set BYBIT_TESTNET_API_KEY/API_SECRET)")

    return {"api_key": api_key, "api_secret": api_secret}
```

**Before**: 5개 파일에서 동일한 fixture 중복 (pytest.skip() 5회 반복)
**After**: conftest.py 1개로 통합 (pytest.skip() 1회만)

**제거된 중복 fixture** (5개 파일):
- test_testnet_order_flow.py
- test_ws_reconnection.py
- test_rate_limit_handling.py
- test_testnet_connection.py
- test_execution_event_mapping.py

---

## 검증 결과

### Gate 1b 재검증 (2026-01-23)

```bash
$ grep -RInE "@pytest\.mark\.(skip|xfail)" tests/ 2>/dev/null | grep -v "\.pyc" | wc -l
0

# → 출력: 0 → ✅ PASS
```

### Gate 1a 재검증 (중복 제거)

```bash
$ grep -RInE "pytest\.skip\(" tests/ 2>/dev/null | grep -v "\.pyc" | grep -v conftest.py | wc -l
0

# → 출력: 0 (conftest.py 제외) → ✅ PASS
```

### pytest 실행 결과

```bash
$ pytest -q
........................................................................ [ 76%]
............................................                             [100%]
188 passed, 15 deselected in 0.22s

# → Before: 188 passed, 16 deselected (placeholder 포함)
# → After: 188 passed, 15 deselected (placeholder 제거)
```

---

## RED→GREEN 증거

**RED (Before)**:
- Gate 1b FAIL: @pytest.mark.skip decorator 1개 검출
- Gate 1a 경고: pytest.skip() 5회 반복 (중복)
- CLAUDE.md Zero Tolerance 위반: `# TODO` 3개 + `pass`

**GREEN (After)**:
- Gate 1b PASS: @pytest.mark.skip decorator 0개
- Gate 1a PASS: pytest.skip() 중복 제거 (conftest.py 1회만)
- CLAUDE.md Oracle Backlog 규칙 준수: 미래 테스트는 문서화만
- 구조 개선: 중복 fixture 제거 (5개 → 1개)

---

## 최종 결론

✅ **Placeholder 테스트 제거 완료**
- test_ws_execution_message_from_order_fill 함수 삭제
- Oracle Backlog 섹션으로 이동 (EX-1~EX-3)
- Gate 1b FAIL → PASS
- Gate 1a 중복 제거 (conftest.py 추상화)

✅ **Phase 8 재검증 완료**
- CLAUDE.md Section 5.7 모든 Gate 통과
- Zero Tolerance 규칙 준수
- Oracle Backlog 규칙 준수
- pytest 188 passed, 15 deselected (정상)
