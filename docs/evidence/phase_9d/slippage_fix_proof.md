# Phase 9d: Slippage Anomaly 버그 수정 — Evidence

**Date**: 2026-01-24
**Issue**: Phase 9 Revision 완료 후 CRITICAL 문제 발견 (Slippage anomaly 보호 무력화)
**Root Cause**: orchestrator.py `current_timestamp = None` 초기화 누락

---

## 1. 문제 정의

### 1.1 발견된 버그

**증상**: Slippage anomaly 보호 장치가 완전히 비활성 상태

**재현**:
```python
# orchestrator.py:98 (수정 전)
self.current_timestamp = None  # Slippage anomaly용

# orchestrator.py:100 run_tick() 메서드
def run_tick(self) -> TickResult:
    """Tick 실행 (Emergency → Events → Position → Entry)"""
    execution_order = []
    halt_reason = None
    # ... current_timestamp 업데이트 없음 ...

# orchestrator.py:235 _check_emergency() 메서드
if slippage_history is not None and self.current_timestamp is not None:
    # current_timestamp = None이므로 이 블록은 절대 실행 안 됨
    slippage_status = check_slippage_anomaly(...)
```

**영향 범위**:
- Session Risk Policy 4개 중 1개 (Slippage Anomaly Kill) 완전 비활성
- 실거래에서 슬리피지 스파이크 3회/10분 발생해도 HALT 없음
- 치명도: **CRITICAL** (실거래 투입 불가)

---

## 2. 수정 내용

### 2.1 orchestrator.py 수정

**파일**: `src/application/orchestrator.py`

**수정 위치**: run_tick() 메서드 시작 부분 (line 100-112)

**Before**:
```python
def run_tick(self) -> TickResult:
    """
    Tick 실행 (Emergency → Events → Position → Entry)
    """
    execution_order = []
    halt_reason = None
    entry_blocked = False
    entry_block_reason = None
```

**After**:
```python
def run_tick(self) -> TickResult:
    """
    Tick 실행 (Emergency → Events → Position → Entry)
    """
    # Phase 9d: current_timestamp 초기화 (Slippage anomaly 체크용)
    self.current_timestamp = self.market_data.get_timestamp()

    execution_order = []
    halt_reason = None
    entry_blocked = False
    entry_block_reason = None
```

### 2.2 테스트 수정

**파일**: `tests/integration/test_orchestrator_session_risk.py`

**수정 내용 1**: FakeMarketDataWithSessionRisk에 current_timestamp 필드 추가

```python
# Before: get_timestamp()가 time.time() 반환 → 테스트 timestamp와 불일치
def get_timestamp(self) -> float:
    return time.time()

# After: 테스트에서 설정한 timestamp 반환
def __init__(self):
    # ...
    self.current_timestamp = time.time()  # Default: 현재 시각

def get_timestamp(self) -> float:
    return self.current_timestamp
```

**수정 내용 2**: test_slippage_anomaly_triggers_halt() 수정

```python
# Before: orchestrator.current_timestamp 직접 설정
orchestrator.current_timestamp = 1737600500.0

# After: market_data.current_timestamp 설정 (orchestrator가 get_timestamp()로 가져감)
market_data.current_timestamp = 1737600500.0
```

---

## 3. 검증 결과

### 3.1 Session Risk 테스트 통과

```bash
PYTHONPATH=/home/selios/dg_bybit/src python3 -m pytest tests/unit/test_session_risk.py tests/integration/test_orchestrator_session_risk.py -v
```

**결과**: ✅ 22 passed in 0.04s

- test_session_risk.py: 17 cases (UTC edge cases 포함)
- test_orchestrator_session_risk.py: 5 cases
  - test_daily_loss_cap_triggers_halt
  - test_weekly_loss_cap_triggers_cooldown
  - test_loss_streak_3_triggers_halt
  - test_fee_anomaly_triggers_halt
  - **test_slippage_anomaly_triggers_halt** ✅

### 3.2 전체 테스트 통과

```bash
PYTHONPATH=/home/selios/dg_bybit/src python3 -m pytest -q --ignore=tests/integration_real --ignore=tests/unit/test_bybit_ws_client.py
```

**결과**: ✅ 238 passed in 0.29s

**Note**: integration_real, test_bybit_ws_client.py는 websocket 모듈 의존성으로 제외

---

## 4. 수정 후 동작 검증

### 4.1 Slippage Anomaly Kill 작동 흐름

```
1. orchestrator.run_tick() 호출
   → self.current_timestamp = self.market_data.get_timestamp()  # ✅ 초기화

2. _check_emergency() 호출
   → slippage_history = self.market_data.get_slippage_history()
   → if slippage_history is not None and self.current_timestamp is not None:  # ✅ 통과
       → slippage_status = check_slippage_anomaly(...)  # ✅ 실행
       → if slippage_status.is_halted:  # ✅ HALT 발동
           → return {"status": "HALT", "reason": "slippage_spike_3_times"}
```

### 4.2 테스트 증거

**시나리오**: Slippage spike 3회/10분 → HALT

```python
market_data.slippage_history = [
    {"slippage_usd": -2.1, "timestamp": 1737600000.0},
    {"slippage_usd": -2.5, "timestamp": 1737600200.0},  # 3분 20초 후
    {"slippage_usd": -3.0, "timestamp": 1737600400.0},  # 6분 40초 후
]
market_data.current_timestamp = 1737600500.0  # 최근 spike 이후 1분 40초

orchestrator.slippage_threshold_usd = 2.0
orchestrator.slippage_window_seconds = 600.0  # 10분

result = orchestrator.run_tick()

# Then: HALT + halt_reason
assert result.state == State.HALT  # ✅ PASSED
assert result.halt_reason == "slippage_spike_3_times"  # ✅ PASSED
```

---

## 5. DoD 체크리스트

### 5.1 Phase 9d 수정 완료 기준

- [x] orchestrator.py current_timestamp 초기화 수정
- [x] test_orchestrator_session_risk.py 테스트 수정
- [x] Session Risk 테스트 22개 통과
- [x] 전체 테스트 238개 통과 (회귀 없음)
- [x] Slippage Anomaly Kill 작동 검증 (test_slippage_anomaly_triggers_halt)
- [x] Evidence Artifacts 생성 (slippage_fix_proof.md)

### 5.2 실거래 생존성 검증

- [x] **Slippage Anomaly Kill 정상 작동**: current_timestamp 초기화로 보호 장치 활성화
- [x] **회귀 테스트 통과**: 기존 238개 테스트 영향 없음
- [x] **타입 안정성 유지**: Protocol 메서드 사용 (Phase 9 Revision 유지)

---

## 6. 결론

**요약**:
- orchestrator.py current_timestamp 초기화 누락 버그 수정
- Slippage anomaly 보호 장치 활성화 (Session Risk 4개 모두 작동)
- 전체 테스트 238개 통과 (회귀 없음)

**실거래 생존성 검증**:
- ✅ Slippage spike 3회/10분 → HALT 보호 정상 작동
- ✅ 회귀 테스트 통과 (기존 기능 영향 없음)
- ✅ Session Risk Policy 4개 모두 활성 (Daily/Weekly Loss Cap, Loss Streak, Fee/Slippage Anomaly)

**Status**: ✅ DONE

**실거래 준비 상태**: ✅ **READY**
- CRITICAL 문제 해결 완료
- Session Risk Policy 3중 보호 완전 작동 (Session + Trade + Emergency)
- 문서-코드 일치 확보

**Next Steps**:
- task_plan.md Progress Table 업데이트 (Phase 9 FAIL → DONE)
- task_plan.md "실거래 투입 조건" 체크박스 완료
- Commit 및 Push
