# Phase 12a-4a: Force Entry 모드 구현 Evidence

**Date**: 2026-01-25
**Phase**: 12a-4a (Force Entry 모드 구현)
**Status**: ✅ COMPLETE

---

## 1. 목적 (Purpose)

**문제**: Grid Signal 블로커로 Testnet 자동 거래 불가
- 현재 ATR: $2,024.93 (2.4% of price)
- Grid spacing: $4,049.86 (4.8% of price)
- 필요 가격 이동: $3,331 (현재 가격에서)
- 결과: 자연적인 Grid 신호 발생까지 수 시간~수일 소요

**해결**: Force Entry 모드 구현
- Grid spacing 체크 무시
- 즉시 Buy 신호 생성
- 테스트 전용 (Testnet 자동 거래용)

---

## 2. 구현 내용 (Implementation)

### 2.1 signal_generator.py

**변경 사항**:
```python
def generate_signal(
    current_price: float,
    last_fill_price: Optional[float],
    grid_spacing: float,
    qty: int = 0,
    force_entry: bool = False,  # ← 추가
) -> Optional[Signal]:
    """
    Grid 전략 기반 신호 생성

    규칙:
    - Force Entry 모드 (force_entry=True): Grid spacing 무시, 즉시 Buy 신호
    - Grid up: current_price >= last_fill_price + grid_spacing → Sell
    - Grid down: current_price <= last_fill_price - grid_spacing → Buy
    - 그 외: No signal
    """
    # Force Entry 모드: Grid spacing 무시, 즉시 Buy 신호
    if force_entry:
        return Signal(side="Buy", price=current_price, qty=qty)

    # 기존 Grid 로직 (변경 없음)
    # ...
```

**위치**: [src/application/signal_generator.py:48-53](../../src/application/signal_generator.py#L48-L53)

---

### 2.2 orchestrator.py

**변경 사항 1**: `__init__()` 파라미터 추가
```python
def __init__(
    self,
    market_data: MarketDataInterface,
    rest_client=None,
    log_storage: Optional[LogStorage] = None,
    force_entry: bool = False,  # ← 추가
):
    # ...
    self.force_entry = force_entry
```

**위치**: [src/application/orchestrator.py:76-93](../../src/application/orchestrator.py#L76-L93)

**변경 사항 2**: `_decide_entry()` 내 `generate_signal()` 호출
```python
signal: Optional[Signal] = generate_signal(
    current_price=current_price,
    last_fill_price=last_fill_price,
    grid_spacing=self.grid_spacing,
    qty=0,
    force_entry=self.force_entry,  # ← 추가
)
```

**위치**: [src/application/orchestrator.py:458-465](../../src/application/orchestrator.py#L458-L465)

---

### 2.3 run_testnet_dry_run.py

**변경 사항 1**: `run_dry_run()` 파라미터 추가
```python
def run_dry_run(target_trades: int = 30, max_duration_hours: int = 72, force_entry: bool = False):
    """
    Testnet Dry-Run 실행

    Args:
        target_trades: 목표 거래 횟수 (default: 30)
        max_duration_hours: 최대 실행 시간 (default: 72시간 = 3일)
        force_entry: Force Entry 모드 (테스트용, Grid spacing 무시)
    """
    logger.info(f"🚀 Starting Testnet Dry-Run (target: {target_trades} trades)")

    if force_entry:
        logger.warning("⚠️  Force Entry Mode: Grid spacing ignored (TEST MODE ONLY)")
```

**위치**: [scripts/run_testnet_dry_run.py:93-104](../../scripts/run_testnet_dry_run.py#L93-L104)

**변경 사항 2**: Orchestrator 초기화
```python
orchestrator = Orchestrator(
    market_data=bybit_adapter,
    rest_client=rest_client,
    log_storage=log_storage,
    force_entry=force_entry,  # ← 추가
)
```

**위치**: [scripts/run_testnet_dry_run.py:119-124](../../scripts/run_testnet_dry_run.py#L119-L124)

**변경 사항 3**: `main()` argparse 플래그 추가
```python
parser.add_argument(
    "--force-entry",
    action="store_true",
    help="Force Entry mode (TEST MODE ONLY, bypasses Grid spacing check)"
)

args = parser.parse_args()

run_dry_run(
    target_trades=args.target_trades,
    max_duration_hours=args.max_hours,
    force_entry=args.force_entry,  # ← 추가
)
```

**위치**: [scripts/run_testnet_dry_run.py:214-222](../../scripts/run_testnet_dry_run.py#L214-L222)

---

## 3. 테스트 (Tests)

### 3.1 Unit Tests

**파일**: [tests/unit/test_signal_generator_force_entry.py](../../tests/unit/test_signal_generator_force_entry.py)

**Test Cases**:
1. `test_force_entry_ignores_grid_spacing()`: force_entry=True → Grid spacing 무시, 즉시 Buy 신호
2. `test_force_entry_works_when_flat()`: force_entry=True + last_fill_price=None → Buy 신호
3. `test_force_entry_false_follows_normal_grid_logic()`: force_entry=False → 정상 Grid 로직

**실행 결과**:
```bash
$ pytest -xvs tests/unit/test_signal_generator_force_entry.py
============================= test session starts ==============================
tests/unit/test_signal_generator_force_entry.py::test_force_entry_ignores_grid_spacing PASSED
tests/unit/test_signal_generator_force_entry.py::test_force_entry_works_when_flat PASSED
tests/unit/test_signal_generator_force_entry.py::test_force_entry_false_follows_normal_grid_logic PASSED

============================== 3 passed in 0.01s ===============================
```

---

### 3.2 회귀 테스트

**실행 결과**:
```bash
$ pytest -q
........................................................................ [ 22%]
........................................................................ [ 44%]
........................................................................ [ 66%]
........................................................................ [ 88%]
......................................                                   [100%]
326 passed, 15 deselected in 0.44s
```

**변화**:
- 이전: 320 passed
- 이후: 326 passed (+6)
- 회귀: 없음

---

## 4. RED → GREEN 증거

### RED 단계 (테스트 실패)
```bash
$ pytest -xvs tests/unit/test_signal_generator_force_entry.py
tests/unit/test_signal_generator_force_entry.py::test_force_entry_ignores_grid_spacing FAILED

=================================== FAILURES ===================================
____________________ test_force_entry_ignores_grid_spacing _____________________
...
E       TypeError: generate_signal() got an unexpected keyword argument 'force_entry'
```

### GREEN 단계 (구현 후 통과)
```bash
$ pytest -xvs tests/unit/test_signal_generator_force_entry.py
============================== 3 passed in 0.01s ===============================
```

---

## 5. 사용법 (Usage)

### 일반 모드 (Grid Signal 대기)
```bash
python scripts/run_testnet_dry_run.py --target-trades 30
```

### Force Entry 모드 (Grid spacing 무시)
```bash
python scripts/run_testnet_dry_run.py --target-trades 30 --force-entry
```

**로그 출력**:
```
🚀 Starting Testnet Dry-Run (target: 30 trades)
⚠️  Force Entry Mode: Grid spacing ignored (TEST MODE ONLY)
```

---

## 6. 설계 결정 (Design Decisions)

### 6.1 Force Entry는 Buy만 생성
- **근거**: Testnet 초기 상태는 FLAT (포지션 없음)
- Entry는 항상 Buy로 시작 (Directional-filtered Grid 전략)
- Sell은 Grid up 또는 Exit에서만 발생

### 6.2 force_entry는 모든 Gate를 우회하지 않음
- **Force Entry가 우회하는 것**: Grid spacing 체크만
- **여전히 검증되는 것**:
  - Entry gates (8개: HALT, COOLDOWN, hedge mode, liquidation, EV, winrate 등)
  - Position sizing (loss budget, margin, tick/lot)
  - Session Risk (Daily/Weekly loss cap, Loss streak)
- **근거**: Force Entry는 "신호 생성 타이밍"만 조작, 안전장치는 모두 유지

### 6.3 force_entry는 기본값 False
- **기본 동작**: 정상 Grid 로직
- **명시적 활성화**: `--force-entry` 플래그 필요
- **로그 경고**: "TEST MODE ONLY" 명시
- **근거**: 실수로 실거래에서 사용하는 것 방지

---

## 7. DoD 검증 (Definition of Done)

### Sub-task 12a-4a 체크리스트:
- [x] TDD: `test_signal_generator_force_entry.py` 작성 (3 cases)
- [x] `signal_generator.py`: `force_entry` 파라미터 추가
- [x] `orchestrator.py`: `force_entry` 전달 (__init__ + _decide_entry)
- [x] `run_testnet_dry_run.py`: `--force-entry` 플래그 추가 (argparse + 로그 경고)
- [x] 회귀 테스트: `pytest -q` 통과 (326 passed)
- [x] Evidence: `force_entry_implementation.md` (본 파일)

---

## 8. 다음 단계 (Next Steps)

**Phase 12a-4 나머지 Sub-tasks**:
- [ ] Sub-task 12a-4b: Testnet 설정 완료
- [ ] Sub-task 12a-4c: Testnet 30-50회 거래 실행
- [ ] Sub-task 12a-4d: 로그 완전성 검증
- [ ] Sub-task 12a-4e: Testnet Dry-Run Report 작성

**실행 명령어**:
```bash
# Testnet 자동 거래 실행 (Force Entry 모드)
python scripts/run_testnet_dry_run.py --target-trades 30 --force-entry

# 로그 모니터링
tail -f logs/testnet_dry_run/testnet_dry_run.log
```

---

## 9. 파일 변경 요약

| 파일 | 변경 내용 | LOC 변화 |
|------|-----------|----------|
| [signal_generator.py](../../src/application/signal_generator.py) | `force_entry` 파라미터 추가 | +5 |
| [orchestrator.py](../../src/application/orchestrator.py) | `force_entry` 파라미터 추가 + 전달 | +3 |
| [run_testnet_dry_run.py](../../scripts/run_testnet_dry_run.py) | `--force-entry` 플래그 + Orchestrator 전달 | +12 |
| [test_signal_generator_force_entry.py](../../tests/unit/test_signal_generator_force_entry.py) | Force Entry 테스트 3개 | +121 (NEW) |

---

## 10. 최종 판정

**Sub-task 12a-4a: Force Entry 모드 구현** → ✅ **COMPLETE**

**근거**:
1. TDD: RED → GREEN 증거 (TypeError → 3 passed)
2. 회귀 테스트 통과 (326 passed, 회귀 없음)
3. DoD 6개 항목 모두 완료
4. Evidence Artifacts 생성 완료

**다음**: Sub-task 12a-4b (Testnet 설정 완료)
