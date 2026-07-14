# CBGB v3 Architecture (버그 수정 + 매매일지)

## Overview
CBGB — Bybit BTCUSDT 트레이딩 봇 ($100→$1,000). 핵심 버그 수정 + 대시보드 매매일지 추가.

## 수정 대상 레이어 맵

```
Application Layer (수정 대상)
  orchestrator.py        ← S1(Trailing Stop), S3(exchange_position_not_flat 복구)
  sizing.py              ← S2(Max Contracts 5, margin buffer 정합성)
  entry_coordinator.py   ← S4(SL sizing ATR*0.7)

Dashboard Layer (추가 대상)
  src/dashboard/ui_components.py   ← S5(매매일지 탭 UI)
  src/dashboard/data_pipeline.py   ← S5(매매일지 데이터 집계)

Domain Layer (변경 없음)
  src/domain/state.py

Infrastructure Layer (변경 없음)
  src/infrastructure/exchange/
  src/infrastructure/logging/trade_logger_v1.py
```

## Wave 구조

```
Wave 1 (병렬 가능 — 독립적 버그 수정):
  T-001: S1 Trailing Stop ATR*0.5    (orchestrator.py:538)
  T-002: S2 Max Contracts 5          (sizing.py:72)

Wave 2 (Wave 1 이후):
  T-003: S3 exchange_position_not_flat 복구  (orchestrator.py:718)
  T-004: S4 SL sizing ATR*0.7               (entry_coordinator.py:138)

Wave 3 (독립 — 대시보드):
  T-005: S5 매매일지 탭                      (dashboard/)
```

## 핵심 설계 결정

### S1: Trailing Stop
- `trail_distance = trail_atr * 0.5` (정책 v2.5 준수)
- Fallback: `trail_price * 0.015` (1.5%, 기존 1%에서 상향)
- 변경 함수: `orchestrator._check_trailing_stop()`

### S2: Max Contracts
- `MAX_CONTRACTS_HARD_CAP = 5`
- Margin 재검증 기준을 `available_usdt * 0.8`으로 통일
- 변경 위치: `sizing.py` 72행 + 146행

### S3: exchange_position_not_flat 복구
```python
# 현재 (차단만):
if ex_size > 0.0:
    return {"blocked": True, "reason": "exchange_position_not_flat"}

# 수정 후 (복구 시도):
if ex_size > 0.0:
    try:
        recovered = _recover_position_from_api(self.rest_client)
        if recovered:
            self.position = recovered
            self.state = State.IN_POSITION
            logger.warning("exchange_position_not_flat: recovered to IN_POSITION")
            return {"blocked": True, "reason": "state_not_flat"}  # 이번 tick은 entry 차단
    except Exception as e:
        logger.warning(f"exchange_position_not_flat recovery failed: {e}")
    return {"blocked": True, "reason": "exchange_position_not_flat"}
```

### S4: SL Sizing 정합성
- entry_coordinator: `raw_stop_pct = (atr * 0.7) / signal.price`
- stop_manager와 동일한 ATR*0.7 사용

### S5: 매매일지 탭
- trades_*.jsonl → DataFrame → Plotly 테이블 + 라인 차트
- 기존 data_pipeline.parse_jsonl() 활용
- ui_components.py에 `create_journal_tab()` 추가
- app.py에 탭 등록

## 디렉토리 구조 (변경 파일만)

```
src/
  application/
    orchestrator.py       ← S1, S3
    sizing.py             ← S2
    entry_coordinator.py  ← S4
  dashboard/
    ui_components.py      ← S5
    data_pipeline.py      ← S5
    app.py                ← S5 탭 등록
tests/
  unit/
    test_orchestrator_event_processing.py  ← S1, S3 테스트
    test_sizing.py                         ← S2 테스트
    test_signal_generator.py               ← S4 테스트 (entry_coordinator)
    test_dashboard_journal.py              ← S5 테스트 (신규)
```
