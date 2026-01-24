# PLAN: ML 기반 거래 로그 분석 시스템

**프로젝트**: CBGB (Controlled BTC Growth Bot)
**작성일**: 2026-01-23
**계획 ID**: logical-swimming-squirrel
**상태**: DRAFT (사용자 승인 대기)

---

## Executive Summary (요약)

### 목표
거래 로그를 영구 저장하고 ML로 분석하여 엔트리 포인트 최적화

### 현재 상태
- Phase 0-7 완료 (Domain Logic 완성, 테스트 통과)
- 기존 로깅: 메모리 내 추적만 (Trade/Metrics/Halt Logger)
- **실거래 데이터 0건** (Phase 8-9 Testnet/Mainnet 미완료)

### 치명적 문제 3가지 (Plan Agent 발견)

#### 문제 1: Data Volume Gap (데이터 부족)
- **현상**: ML 학습에 최소 200 거래 필요, 사용자는 100 거래 후 시작 선택
- **왜 문제인지**: 100 거래는 통계적 유의성 부족 (클래스당 50 샘플), 과적합 위험 80%
- **방치 시 결과**: ML 예측 오류 → 실거래 손실 증가 → 전략 붕괴
- **완화 방안**:
  - 최소 모델 사용 (Logistic Regression, 파라미터 10개 이내)
  - Cross-validation (5-fold)
  - **Hold-out Test Set Validation** (실거래 투입 전):
    - 수집된 100 거래를 Train 80 / Test 20으로 분할
    - Train set으로 모델 학습
    - Test set으로 winrate 개선 검증 (≥ 3%)
    - **검증 통과 후에만 실거래 투입** (Feature flag)
  - **실거래 투입 후 즉시 모니터링** (첫 20 거래):
    - Winrate < baseline - 5% → 즉시 Feature flag off
    - 누적 손실 > $10 → 즉시 중단
    - ML prediction latency > 100ms → 즉시 비활성화

#### 문제 2: Architecture Violation (아키텍처 침범)
- **현상**: ML을 Domain에 직접 통합하면 Pure transition() 위반
- **왜 문제인지**: Domain Logic(순수, 결정론적) + ML(비결정적, I/O) 혼합 → TDD 불가능
- **방치 시 결과**: 테스트 재현성 파괴, 상태 전이 디버깅 불가, SSOT 원칙 위반
- **해결 방안**:
  - **ML은 Policy Tuning Layer로 완전 분리** (Domain 외부)
  - ML 예측 결과는 Config 파일로 저장 (`ml_policy_override.yaml`)
  - Domain은 Config만 읽음 (ML 존재 여부 무관)

#### 문제 3: Premature Optimization (시기상조)
- **현상**: Phase 8-9 미완료 (실거래 검증 전) 상태에서 ML 인프라 구축
- **왜 문제인지**: 실거래 데이터 없이 ML 파이프라인 개발 → 실패 지점 불명확
- **방치 시 결과**: ML 인프라 개발 → 실거래 실패 → ML 인프라 폐기 → 개발 시간 손실 (2-4주)
- **완화 방안**:
  - Phase 10 (로그 저장)만 즉시 시작 (Phase 8-9와 병행 가능)
  - Phase 11 (분석)은 실거래 후
  - Phase 13 (ML)은 100 거래 수집 후

---

## Architecture Overview (아키텍처 개요)

### 계층 분리 원칙 (CBGB 아키텍처 준수)

```
┌─────────────────────────────────────────────────────────┐
│ Domain Layer (Pure, No I/O, TDD 100%)                  │
│ - State, Position, ExecutionEvent, Intent               │
│ - transition() (순수 함수)                               │
│ ❌ ML 로직 금지                                          │
└─────────────────────────────────────────────────────────┘
                          ↑
                          │ (Config 읽기만)
                          ↓
┌─────────────────────────────────────────────────────────┐
│ Application Layer (Business Logic, TDD 가능)            │
│ - entry_allowed(), sizing(), transition_router()       │
│ - ML Policy Override 적용 (Config에서 주입)             │
│ ❌ ML 모델 직접 호출 금지                                │
└─────────────────────────────────────────────────────────┘
                          ↑
                          │ (Config 파일)
                          ↓
┌─────────────────────────────────────────────────────────┐
│ Policy Tuning Layer (ML, Offline, Phase 13)            │
│ - Feature Extractor (TDD 가능)                          │
│ - Model Trainer (백테스트 증거)                          │
│ - Policy Generator (Config 생성, TDD 가능)              │
│ ✅ Domain과 완전 독립                                    │
└─────────────────────────────────────────────────────────┘
                          ↑
                          │ (Trade Logs 읽기)
                          ↓
┌─────────────────────────────────────────────────────────┐
│ Infrastructure Layer (I/O)                              │
│ - Trade Logger v1.0 (Phase 10)                         │
│ - Log Storage (JSON Lines, Atomic write)               │
│ - Analysis Toolkit (Phase 11a: CLI, 11b: Dashboard)    │
└─────────────────────────────────────────────────────────┘
```

### ML 통합 방식 (Architecture Violation 방지)

**절대 금지**:
- `entry_allowed.py`에 ML 모델 import
- Domain/Application에 ML 예측 로직 추가
- Synchronous Prediction (Tick blocking)

**허용 방식 (DoD #2: Application에서 I/O 제거)**:
```python
# Application Layer (entry_allowed.py) - Pure, TDD 가능
def entry_allowed(
    ctx: EntryContext,
    config: StageConfig,
    ml_override: Optional[MLPolicyOverride] = None  # ✅ 주입받음 (I/O 없음)
) -> EntryDecision:
    # 기본 EV gate 계수
    ev_multiple = config.ev_fee_multiple_k  # 예: 2.5

    # ✅ ML Policy Override 적용 (주입된 객체 사용, I/O 없음)
    if ml_override is not None:
        regime = ctx.market_regime
        if regime in ml_override.entry_gate_adjustments:
            ev_multiple = ml_override.entry_gate_adjustments[regime].ev_multiple

    # 기존 로직 (ev_multiple 사용)
    if expected_profit < fee * ev_multiple:
        return EntryDecision(REJECT, reason="EV_GATE")

    return EntryDecision(ALLOW)

# Infrastructure Layer - Tick Loop에서 주입
class Orchestrator:
    def __init__(self):
        self._ml_override_cache: Optional[MLPolicyOverride] = None
        self._ml_override_mtime: float = 0.0

    def _refresh_ml_override(self):
        """주기적(1분마다)으로 YAML 체크 후 캐시 갱신"""
        if should_refresh(self._ml_override_mtime):
            self._ml_override_cache = load_ml_policy_override_yaml()
            self._ml_override_mtime = time.time()

    def tick(self):
        self._refresh_ml_override()  # Infrastructure에서만 I/O

        # Application은 주입받음 (Pure)
        decision = entry_allowed(ctx, config, ml_override=self._ml_override_cache)
```

**Offline ML Pipeline** (Daily cron job):
```bash
# Policy Tuning Layer (Offline)
python scripts/train_ml_model.py \
    --min-trades 100 \
    --test-split 0.2 \
    --output ml_policy_override.yaml

# 생성된 Config 예시 (ml_policy_override.yaml)
entry_gate_adjustments:
  trending_up:
    ev_multiple: 2.0  # ML 예측: trending_up일 때 EV gate 완화
  ranging:
    ev_multiple: 3.5  # ML 예측: ranging일 때 EV gate 강화
  high_vol:
    atr_min_pct: 5.0  # ML 예측: high_vol일 때 ATR gate 강화
```

---

## Phase Breakdown (상세 구현 계획)

### Phase 10: Trade Logging Infrastructure (1-2시간)

#### ⚠️ BLOCKING: Phase 9 Kill Switch 완료 필수

**Phase 10-13 시작 조건** (협상 불가):
- [ ] Phase 9 완료 (task_plan.md 검증)
- [ ] 일일 손실 캡 구현 + 테스트 통과 (`test_daily_loss_limit_halt`)
- [ ] 주간 손실 캡 구현 + 테스트 통과 (`test_weekly_loss_limit_halt`)
- [ ] 5연패 중단 구현 + 테스트 통과 (`test_consecutive_loss_halt`)
- [ ] Testnet 검증 (Phase 8 완료)

**Phase 9 미완료 시 Phase 10-13 실행 금지**:
- 근거: ML 최적화는 손실 캡이 있는 환경에서만 의미 있음 (Section "도박 종료 조건")
- 위반 시: 실거래 손실 무제한 노출 → 계좌 파산 위험
- ML 예측 오류 (과적합 확률 80%) + 손실 캡 없음 = 계좌가 0이 될 때까지 거래 가능

#### 목표
실거래 데이터를 영구 저장하여 Phase 11 분석 및 Phase 13 ML 학습 기반 구축

#### 테스트 전략
- **RED Tasks**: 테스트 15개 먼저 작성 (Placeholder 0개)
- **Coverage Target**: 100% (로깅 로직은 순수 함수)
- **Test Types**: Unit tests only (Domain 통합 불필요)

#### Tasks (TDD Workflow)

**RED Tasks** (테스트 작성, DoD #1/#4 반영):
1. `test_trade_log_v1_schema_valid`: 필수 필드 모두 채워진 경우 검증 통과
2. `test_trade_log_v1_schema_missing_order_id`: order_id 누락 시 ValidationError
3. `test_trade_log_v1_market_regime_required`: market_regime 누락 시 ValidationError
4. `test_trade_log_v1_integrity_fields_required`: schema_version/config_hash/git_commit 누락 시 ValidationError
5. **`test_trade_log_v1_field_policy_fills_limit` (DoD #4)**: fills 20개 초과 시 ValidationError
6. **`test_trade_log_v1_field_policy_orderbook_depth` (DoD #4)**: orderbook depth > 10 시 ValidationError
7. `test_trade_log_v1_to_dict_serialization`: TradeLogV1 → dict 변환
8. `test_trade_log_v1_from_dict_deserialization`: dict → TradeLogV1 복원
9. **`test_trade_log_sink_single_writer` (DoD #1)**: TradeLogSink 시작 → 큐에 로그 넣기 → flush → 파일 확인
10. **`test_trade_log_sink_concurrent_enqueue_sequential_write` (DoD #1)**: 10 스레드가 동시에 큐에 append (concurrent) → writer 스레드는 순차 처리 (sequential) → 파일에 1000 줄 정확히 기록 (line corruption 없음)
11. `test_append_multiple_logs_same_day`: 동일 날짜 여러 로그 append (순차)
12. `test_read_trade_logs_v1_returns_list`: JSON Lines 읽기 → List[TradeLogV1]
13. `test_read_trade_logs_v1_empty_file`: 빈 파일 읽기 시 빈 리스트
14. `test_rotate_daily_logs_creates_new_file`: 날짜 변경 시 새 파일 생성
15. **`test_trade_log_sink_graceful_shutdown` (DoD #1)**: Sink 종료 시 큐 비우고 파일 닫기

**GREEN Tasks** (최소 구현, DoD #1: Single-writer 보장):
1. `TradeLogV1` dataclass 정의 (`src/infrastructure/logging/trade_logger_v1.py`)
   - 필수 필드: signal_id, timestamp, event_type, side, qty, price, order_id
   - **제한된 추가 필드 (DoD #4: 필드 정책)**:
     - fills: List[Fill] (최대 20개, 초과 시 요약)
     - slippage_usd: float (단일 값)
     - latency_breakdown: Dict[str, float] (키 최대 5개)
     - orderbook_snapshot: Optional[OrderbookSummary] (depth 10만, bid1/ask1/spread/imbal만)
   - Market data: funding_rate, mark_price, index_price, market_regime
   - 무결성 필드: schema_version, config_hash, git_commit, exchange_server_time_offset
2. `validate_schema_v1()`: Schema 검증 함수 + 필드 정책 검증
3. `to_dict()` / `from_dict()`: Serialization/Deserialization
4. **`TradeLogSink` (Single-writer, DoD #1)**:
   - `__init__(queue: Queue, log_dir: Path)`: 단일 writer 스레드 시작
   - `_writer_loop()`: 큐에서 로그 꺼내 직렬 append
   - `append(log: TradeLogV1)`: 큐에 넣기만 (non-blocking)
   - `flush()`: 큐 비울 때까지 대기
   - **Append 방식 (Single-writer 보장)**:
     - **Multi-threaded enqueue**: 여러 스레드가 동시에 Queue에 로그 넣기 (non-blocking, 안전)
     - **Single-writer loop**: 단일 writer 스레드가 큐에서 순차 처리 (직렬 write)
     - `open(file, 'a', buffering=1)` (line buffering, `\n` 시 자동 flush)
     - `f.write(json.dumps(log) + '\n')` (한 줄씩 append)
     - 주기적 `f.flush()` + `os.fsync()` (디스크 동기화)
     - **Corruption 방지**: Single-writer 패턴 → concurrent append 직렬화 → line corruption 0건
     - **NOT temp → rename**: Append-only 방식은 Atomic write 패턴(temp → rename) 사용 안 함
5. `read_trade_logs_v1()`: JSON Lines 읽기 (변경 없음)
6. `rotate_daily_logs()`: Daily rotation 로직 (변경 없음)
7. `log_trade_entry()` / `log_trade_exit()`에 Hook 추가:
   - `TradeLogSink.append(log)` 호출 (큐에 넣기, non-blocking)
   - Feature flag 제어

**REFACTOR Tasks**:
1. 중복 제거: Schema 검증 로직 통합
2. 책임 분리: Serialization vs Storage 분리
3. 에러 처리: ValidationError, IOError 명시적 처리
4. Config 주입: Feature flag (`ENABLE_TRADE_LOG_PERSISTENCE`)

#### Quality Gate
- [ ] **⚠️ Phase 9 완료 검증** (BLOCKING, 최우선):
  - `docs/evidence/phase_9/completion_checklist.md` 존재 확인
  - `grep "Phase 9.*\[x\]" docs/plans/task_plan.md` 출력 확인
  - Kill Switch 테스트 3개 통과 확인 (daily/weekly/consecutive)
- [ ] 테스트 15개 작성 → RED 확인
- [ ] 구현 → 테스트 통과 (GREEN)
- [ ] Refactoring → 테스트 유지
- [ ] CLAUDE.md Section 5.7 검증 통과 (7개 커맨드)
- [ ] Evidence Artifacts 생성 (`docs/evidence/phase_10/`)
  - `phase_9_completion_proof.txt` (Phase 9 Evidence 링크)
  - `completion_checklist.md`
  - `gate7_verification.txt`
  - `pytest_output.txt`
  - `red_green_proof.md`
- [ ] Progress Table 업데이트 (task_plan.md 병합 시)

#### Dependencies
- None (독립 실행 가능)

#### Rollback 전략
- **Feature Flag**: `ENABLE_TRADE_LOG_PERSISTENCE = False` (기본값)
- **기존 로직 유지**: `trade_logger.py` 기존 함수 반환값 변경 없음
- **Phase 10 제거 시**: Hook 코드 삭제만 (기존 Phase 5 로직 유지)

---

### Phase 11a: Analysis Toolkit - CLI (2-3시간)

#### 목표
수집된 거래 데이터를 분석하여 전략 성과 평가 및 엔트리 조건 상관관계 파악 (CLI 도구)

#### 테스트 전략
- **RED Tasks**: 테스트 14개 먼저 작성
- **Coverage Target**: 90% (분석 로직은 순수 함수)
- **Test Types**: Unit tests (통계 계산 검증)

#### Tasks (TDD Workflow)

**RED Tasks** (테스트 작성, DoD #3: 효과 크기 중심):
1. `test_calculate_statistics_empty_logs`: 빈 로그 → 0 값
2. `test_calculate_statistics_winrate`: winrate = wins / total
3. `test_calculate_statistics_sharpe_ratio`: (mean_pnl / std_pnl) * sqrt(N)
4. `test_calculate_statistics_max_drawdown`: 연속 손실 최대값
5. `test_calculate_statistics_fee_ratio`: avg(actual / estimated)
6. `test_calculate_statistics_latency_percentiles`: p50/p95 계산
7. **`test_analyze_entry_stage_winrate_with_ci` (DoD #3)**: Stage별 winrate + Wilson CI + 표본수
8. **`test_analyze_entry_regime_effect_size` (DoD #3)**: Regime별 winrate + Lift (효과크기)
9. **`test_analyze_entry_atr_effect_size` (DoD #3)**: ATR 구간별 winrate + Lift
10. `test_analyze_entry_hour_winrate`: 시간대별 winrate 계산
11. `test_analyze_gate_reject_distribution`: Gate 거절 분포
12. **`test_chi_square_conditional_execution` (DoD #3)**: 각 셀 expected >= 5일 때만 Chi-square 실행, 아니면 "insufficient_data" 반환
13. **`test_wilson_ci_calculation` (DoD #3)**: Wilson CI 계산 정확도 (n=10, n=100, n=1000)
14. **`test_effect_size_lift_calculation` (DoD #3)**: Lift = (group_winrate / baseline_winrate) - 1

**GREEN Tasks** (최소 구현, DoD #3: 효과 크기 중심):
1. `calculate_trade_statistics()` (`src/analysis/trade_stats.py`)
   - 통계: total_trades, winrate, avg_pnl, median_pnl, max_drawdown, sharpe_ratio
   - 수수료: fee_ratio_avg
   - 레이턴시: latency_p50, latency_p95
   - Slippage: slippage_avg_usd
2. **`analyze_entry_conditions()` (DoD #3: 효과 크기 중심)** (`src/analysis/entry_correlation.py`)
   - Stage별: winrate + **Wilson CI (95%)** + 표본수 + **Lift**
   - Market regime별: winrate + **Wilson CI** + 표본수 + **Lift**
   - ATR 구간별: winrate + **Wilson CI** + 표본수 + **Lift**
   - 시간대별: winrate + 표본수
   - Gate 거절 분포
   - **Chi-square 검정 (조건부, DoD #3)**:
     - 조건: 각 셀 expected count >= 5
     - 충족 시: Chi-square 통계량 + p-value
     - 미충족 시: `{"result": "insufficient_data", "reason": "expected count < 5"}`
3. **`wilson_ci()` 유틸 함수 (DoD #3)**:
   - Input: successes, n, confidence=0.95
   - Output: (lower_bound, upper_bound)
   - Formula: Wilson score interval (정확도 높음, n < 30에서도 안정적)
4. **`effect_size_lift()` 유틸 함수 (DoD #3)**:
   - Input: group_winrate, baseline_winrate
   - Output: lift = (group / baseline) - 1
   - 예: 0.6 vs 0.5 → lift = 0.2 (20% 개선)
5. CLI 도구 (`scripts/analyze_trades.py`)
   - `--stats`: 전체 통계
   - `--entry-correlation`: 엔트리 조건 상관관계 (Wilson CI + Lift 출력)
   - `--from`, `--to`: 날짜 범위
   - `--format csv`: CSV 출력

**REFACTOR Tasks**:
1. 통계 계산 함수 모듈화
2. Chi-square 검정 유틸리티 분리
3. CLI argument parsing 개선

#### Quality Gate
- [ ] 테스트 14개 작성 → RED 확인
- [ ] 구현 → 테스트 통과 (GREEN)
- [ ] Refactoring → 테스트 유지
- [ ] CLAUDE.md Section 5.7 검증 통과
- [ ] Evidence Artifacts 생성 (`docs/evidence/phase_11a/`)
- [ ] CLI 도구 실행 증거 (샘플 출력)

#### Dependencies
- Phase 10 완료 (Trade Logs 필요)

#### Rollback 전략
- **독립 모듈**: Domain/Application과 의존성 없음 (제거 시 영향 없음)
- **CLI 도구**: 실행 안 하면 영향 없음

---

### Phase 11b: Analysis Dashboard - Web (2-3시간)

#### 목표
실시간 거래 성과 모니터링을 위한 간단한 웹 대시보드 (Streamlit 기반)

#### 테스트 전략
- **Integration Tests**: 대시보드 렌더링 테스트 (간소화)
- **Coverage Target**: 60% (UI 로직은 테스트 복잡도 높음)
- **Test Types**: Smoke tests (페이지 로드, 차트 렌더링)

#### Tasks (간소화 구현)

**구현 범위**:
1. Streamlit 앱 (`src/dashboard/app.py`)
   - 페이지 1: 거래 통계 (winrate, PnL, Sharpe ratio)
   - 페이지 2: 엔트리 조건 상관관계 (Stage, Regime, ATR)
   - 페이지 3: 최근 거래 목록 (최근 50개)
2. 차트:
   - Line chart: 누적 PnL (BTC/USD)
   - Bar chart: Stage별/Regime별 winrate
   - Scatter plot: ATR vs PnL
3. 필터:
   - 날짜 범위 선택
   - Stage 필터 (1/2/3)
   - Market regime 필터

**RED Tasks** (Smoke tests):
1. `test_dashboard_renders_without_error`: 대시보드 페이지 로드
2. `test_dashboard_displays_statistics`: 통계 위젯 렌더링
3. `test_dashboard_displays_charts`: 차트 렌더링

**GREEN Tasks**:
1. Streamlit 앱 구조 생성
2. Phase 11a 분석 함수 통합
3. 차트 라이브러리 통합 (Plotly)

**REFACTOR Tasks**:
1. 차트 재사용 컴포넌트화
2. 캐싱 추가 (Streamlit @cache_data)

#### Quality Gate
- [ ] Smoke tests 3개 통과
- [ ] 대시보드 로컬 실행 증거 (스크린샷)
- [ ] Evidence Artifacts 생성 (`docs/evidence/phase_11b/`)

#### Dependencies
- Phase 11a 완료 (분석 함수 필요)

#### Rollback 전략
- **독립 모듈**: 실행 안 하면 영향 없음
- **Phase 11b 제거 시**: `src/dashboard/` 디렉토리 삭제만

---

### Phase 13: ML Integration (4-6시간, 100 거래 수집 후)

#### 목표
엔트리 타이밍 최적화: ML 예측을 Policy Tuning Layer로 통합 (Domain 경계 침범 금지)

#### 100 거래 제약사항 (사용자 선택, Plan Agent 경고)

**위험 요소**:
- 통계적 유의성 부족 (클래스당 50 샘플, 권장 100+)
- 과적합 확률 80% (작은 데이터셋)
- Win/Loss 불균형 위험 (극단적 winrate 시 학습 불가)

**완화 방안**:
1. **최소 모델**: Logistic Regression (파라미터 10개 이내)
2. **Cross-validation**: 5-fold (과적합 감지)
3. **Feature 제한**: 5개 이내 (market_regime, atr, stage, hour, recent_winrate)
4. **Hold-out Test Set Validation** (실거래 투입 전):
   - 수집된 100 거래를 Train 80 / Test 20으로 분할
   - Train set으로 모델 학습
   - Test set으로 winrate 개선 검증 (≥ 3%)
   - **검증 통과 후에만 실거래 투입** (Feature flag)
5. **실거래 투입 후 즉시 모니터링** (첫 20 거래):
   - Winrate < baseline - 5% → 즉시 Feature flag off
   - 누적 손실 > $10 → 즉시 중단
   - ML prediction latency > 100ms → 즉시 비활성화

**진입 조건** (Phase 13 시작 전 검증):
- [ ] 최소 100 거래 수집 (CLOSED trades)
- [ ] Win/Loss 분포: 승률 40-60% (극단 방지)
- [ ] Stage 분포: Stage 1/2/3 각각 최소 20 거래
- [ ] Regime 분포: Trending/Ranging 각각 최소 30 거래

#### 테스트 전략
- **RED Tasks**: Feature Extractor 테스트 6개 (TDD 가능)
- **BACKTEST Tasks**: 백테스트 증거 3개 (TDD 불가, 비결정적)
- **Coverage Target**: Feature Extractor 100%, Model Trainer는 백테스트 증거

#### Tasks (TDD + Backtest)

**RED Tasks** (Feature Extractor, TDD 가능):
1. `test_extract_features_market_regime`: market_regime 추출 (4가지 타입)
2. `test_extract_features_atr`: ATR 구간 분류 (low/medium/high)
3. `test_extract_features_stage`: Stage 추출 (1/2/3)
4. `test_extract_features_hour_utc`: 시간대 추출 (0-23)
5. `test_extract_features_recent_winrate`: 최근 10 거래 winrate
6. `test_extract_features_missing_data`: 누락 필드 처리 (default 값)

**GREEN Tasks** (구현):
1. `extract_features()` (`src/ml/feature_extractor.py`)
   - Input: TradeLogV1
   - Output: EntryFeatures (market_regime, atr, stage, hour, recent_winrate)
2. `train_entry_model()` (`src/ml/model_trainer.py`)
   - Input: List[TradeLogV1]
   - Output: LogisticRegression model
   - Cross-validation (5-fold)
3. `generate_policy_override()` (`src/ml/policy_generator.py`)
   - Input: Model + Features
   - Output: `ml_policy_override.yaml` (Config 파일)
4. `entry_allowed()` 수정 (`src/application/entry_allowed.py`)
   - ML Policy Override 적용 (Config에서 주입)
5. Offline Training Script (`scripts/train_ml_model.py`)
   - Daily cron job용 스크립트

**EVIDENCE Report Tasks** (백테스트 증거, DoD #6: pytest 제외):
1. **`docs/evidence/phase_13/backtest_results.md`** (수동 생성):
   - ML on vs off 비교 (고정 seed + 데이터 스냅샷 해시)
   - Train/Test winrate 차이 (overfitting 검증)
   - 재현 커맨드 (seed, data_path, model_params)
   - **판정 기준 (자동 아님)**:
     - Winrate 개선 >= 3% (100 거래 기준)
     - Train/Test 차이 < 15%
     - Feature importance: market_regime, atr 상위 2개
2. **`scripts/generate_backtest_report.py`** (백테스트 실행 도구):
   - `--seed`: 고정 시드
   - `--data-path`: Trade Logs 경로
   - `--output`: backtest_results.md 생성
   - **결과**: Markdown 리포트 (pytest 통과/실패 없음)
3. **`docs/evidence/phase_13/live_monitoring_log.jsonl`** (실거래 투입 후 모니터링 로그):
   - 실거래 투입 후 첫 20 거래 모니터링
   - 매 거래마다: signal_id, entry_decision, pnl_btc, ml_prediction, baseline_decision
   - **즉시 Rollback 트리거 감지**: winrate < baseline - 5%, 누적 손실 > $10
   - **수동 분석 필요** (자동 테스트 아님)

**REFACTOR Tasks**:
1. Feature 정규화 함수 분리
2. Policy Override 로드 캐싱
3. 실거래 투입 후 모니터링 로깅 추가 (첫 20 거래)

#### Quality Gate (DoD #6: pytest 백테스트 제외)
- [ ] Feature Extractor 테스트 6개 → RED → GREEN (TDD)
- [ ] **백테스트 리포트 생성 (DoD #6: pytest 아님)**:
  - `docs/evidence/phase_13/backtest_results.md` (수동 판정)
  - 재현 커맨드 + 고정 seed + 데이터 해시
  - Winrate 개선 >= 3%, Train/Test 차이 < 15% 증거
- [ ] Feature Flag: `ENABLE_ML_POLICY_OVERRIDE = False` (기본값)
- [ ] 실거래 투입 후 모니터링 로그 (첫 20 거래, Rollback 트리거 감지, 수동 분석)
- [ ] Rollback 절차 문서화
- [ ] CLAUDE.md Section 5.7 검증 통과 (TDD 부분만)
- [ ] Evidence Artifacts 생성 (`docs/evidence/phase_13/`)
  - `backtest_results.md` (백테스트 리포트, pytest 통과 아님)
  - `feature_importance.csv` (특징 중요도)
  - `live_monitoring_log.jsonl` (실거래 투입 후 모니터링 로그, 수동 분석)

#### Dependencies
- Phase 10 완료 (Trade Logs 필요)
- Phase 11a 완료 (분석 함수 재사용)
- **최소 100 거래 수집** (진입 조건 검증)

#### Rollback 전략 (3-tier)

**Level 1 (즉시, < 1분)**:
```bash
# Feature flag off → ML 비활성화
export ENABLE_ML_POLICY_OVERRIDE=false
```

**Level 2 (1시간)**:
```bash
# ml_policy_override.yaml 삭제 → fallback to default
rm config/ml_policy_override.yaml
```

**Level 3 (1일)**:
```bash
# ML 코드 전체 제거 → Phase 11 상태로 rollback
git revert <phase_13_commit>
rm -rf src/ml/
```

**Rollback 트리거** (실거래 투입 후):
- **즉시 트리거** (첫 20 거래):
  - Winrate < baseline - 5% → 즉시 Feature flag off
  - 누적 손실 > $10 → 즉시 중단
  - ML prediction latency > 100ms → 즉시 비활성화
- **장기 트리거** (20 거래 이후):
  - Model drift 감지 (winrate 지속 하락 2주 이상) → Feature flag off

---

## Risk Assessment (리스크 분석)

### Technical Risks (기술 리스크)

| Risk | Probability | Impact | Mitigation | Success Criteria |
|------|-------------|--------|------------|------------------|
| **Cold Start (100 거래)** | HIGH (80%) | CRITICAL | Logistic Regression + 5-fold CV + Hold-out Test Set | Overfitting < 15% |
| **Overfitting** | HIGH (70%) | HIGH | Feature 제한 (5개), Cross-validation, Hold-out Test Set | Train/Test winrate 차이 < 15% |
| **Prediction Latency** | LOW (10%) | MEDIUM | Offline 학습 + Cached prediction (Config 주입) | Latency < 1ms (Config 읽기만) |
| **Architecture Pollution** | MEDIUM (30%) | CRITICAL | ML = Policy Tuning Layer (Domain 외부) | Pure transition() 유지 |
| **Model Drift** | MEDIUM (40%) | HIGH | Quarterly retraining + 실거래 모니터링 | ML on winrate >= baseline |
| **Data Corruption** | LOW (5%) | HIGH | Single-writer + Queue (concurrent append 직렬화) | Line corruption 0건 |

### Dependency Risks (의존성 리스크)

| Dependency | Risk Level | Version | Mitigation |
|------------|------------|---------|------------|
| **scikit-learn** | LOW | 1.2+ | Minimal dependency, Pure Python |
| **pandas** | MEDIUM | 1.5+ | 데이터 처리만 사용 (Domain 진입 금지) |
| **streamlit** | MEDIUM | 1.28+ | Phase 11b만 사용 (선택사항) |
| **plotly** | LOW | 5.17+ | 시각화만 (Phase 11b) |
| **Storage Growth** | MEDIUM | - | **필드 정책 (DoD #4)**: fills/orderbook 제한, 압축, Daily rotation (100 거래: ~5MB, 10k 거래: ~500MB 예상) |

### Quality Risks (품질 리스크)

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| **ML 예측 오류 → 손실 증가** | CRITICAL | MEDIUM (50%) | Feature flag (ML on/off), Baseline 유지, Hold-out Test, 실거래 모니터링 |
| **TDD 불가능 (ML 비결정성)** | HIGH | LOW (20%) | ML은 Domain 외부 유지, Prediction은 Config로 주입 |
| **증거 기반 완료 불가** | MEDIUM | LOW (10%) | Phase 10-11만 TDD, Phase 13은 백테스트 증거 |
| **Dashboard 개발 낭비** | MEDIUM | MEDIUM (40%) | Phase 11b 최소화 (Streamlit 3페이지만) |

---

## Critical Files (주요 파일 목록)

### Phase 10: Trade Logging Infrastructure

**신규 파일**:
1. `src/infrastructure/logging/trade_logger_v1.py` - Trade Log v1.0 스키마 정의 및 검증
2. `src/infrastructure/storage/log_storage.py` - Append-only JSON Lines 저장 (Atomic write)
3. `tests/unit/test_trade_logger_v1.py` - Trade Log v1.0 테스트 (8 cases)
4. `tests/unit/test_log_storage.py` - Log Storage 테스트 (7 cases)
5. `docs/evidence/phase_10/completion_checklist.md` - DoD 검증 체크리스트

**수정 파일**:
- `src/infrastructure/logging/trade_logger.py` - Hook 추가 (Feature flag 제어)

**데이터 디렉토리**:
```
data/
├── trades/
│   └── 2026-01-23.jsonl
├── metrics/
│   └── 2026-01-23.jsonl
└── halts/
    └── 2026-01-23.jsonl
```

### Phase 11a: Analysis Toolkit - CLI

**신규 파일**:
1. `src/analysis/trade_stats.py` - 거래 통계 계산 (순수 함수)
2. `src/analysis/entry_correlation.py` - 엔트리 조건 vs 성과 상관관계 (Chi-square 검정)
3. `scripts/analyze_trades.py` - CLI 분석 도구
4. `tests/unit/test_trade_stats.py` - Trade Stats 테스트 (6 cases)
5. `tests/unit/test_entry_correlation.py` - Entry Correlation 테스트 (8 cases)
6. `docs/evidence/phase_11a/completion_checklist.md` - DoD 검증 체크리스트

### Phase 11b: Analysis Dashboard - Web

**신규 파일**:
1. `src/dashboard/app.py` - Streamlit 대시보드 앱
2. `src/dashboard/charts.py` - 차트 컴포넌트 (재사용)
3. `tests/integration/test_dashboard_smoke.py` - Smoke tests (3 cases)
4. `docs/evidence/phase_11b/dashboard_screenshot.png` - 실행 증거

**의존성**:
- `requirements.txt`에 `streamlit`, `plotly` 추가

### Phase 13: ML Integration

**신규 파일** (DoD #2/#6 반영):
1. `src/ml/feature_extractor.py` - Trade Log → ML Features 변환 (TDD 가능)
2. `src/ml/model_trainer.py` - Logistic Regression 학습 (백테스트 증거)
3. `src/ml/policy_generator.py` - ML 예측 → Config Override 생성
4. `scripts/train_ml_model.py` - Offline 학습 스크립트 (Daily cron)
5. **`scripts/generate_backtest_report.py` (DoD #6)** - 백테스트 리포트 생성 (pytest 아님)
6. `tests/unit/test_feature_extractor.py` - Feature Extractor 테스트 (6 cases, TDD)
7. `config/ml_policy_override.yaml` - ML 예측 결과 (Config 파일)
8. `docs/evidence/phase_13/backtest_results.md` - 백테스트 리포트 (수동 판정)
9. `docs/evidence/phase_13/feature_importance.csv` - 특징 중요도
10. `docs/evidence/phase_13/live_monitoring_log.jsonl` - 실거래 투입 후 모니터링 로그 (수동 분석)

**수정 파일** (DoD #2):
- `src/application/entry_allowed.py` - **ML Policy Override 주입받음 (파일 로드 제거)**
- `src/application/orchestrator.py` - ML override 캐싱 + 주입 (Infrastructure에서만 I/O)

**의존성**:
- `requirements.txt`에 `scikit-learn`, `pandas` 추가

---

## Verification Plan (검증 계획)

### Phase 10 검증

**Gate 7 커맨드** (CLAUDE.md Section 5.7):
```bash
# (1a) Placeholder 표현 감지
grep -RInE "assert[[:space:]]+True|pytest\.skip\(|pass[[:space:]]*#.*TODO|TODO: implement|NotImplementedError" tests/ 2>/dev/null | grep -v "\.pyc"
# → 출력: 비어있음

# (1b) Skip/Xfail decorator 금지
grep -RInE "pytest\.mark\.(skip|xfail)|@pytest\.mark\.(skip|xfail)" tests/ 2>/dev/null | grep -v "\.pyc"
# → 출력: 비어있음

# (1c) 의미있는 assert 존재 여부
grep -RIn "assert .*==" tests/ 2>/dev/null | wc -l
# → 출력: 0이 아님

# (2a) 도메인 타입 이름 재정의 금지
grep -RInE "^class[[:space:]]+(Position|PendingOrder|ExecutionEvent|State)\b" tests/ 2>/dev/null | grep -v "\.pyc"
# → 출력: 비어있음

# (2b) tests/ 내에 domain 모사 파일 생성 금지
find tests -type f -maxdepth 3 -name "*.py" 2>/dev/null | grep -E "(domain|state|intent|events)\.py"
# → 출력: 비어있음

# (5) sys.path hack 금지
grep -RIn "sys\.path\.insert" src/ tests/ 2>/dev/null
# → 출력: 비어있음

# (7) pytest 증거
pytest -q
# → PASS 결과를 Evidence에 기록
```

### Phase 11a 검증

**CLI 도구 실행 증거**:
```bash
# 전체 통계
python scripts/analyze_trades.py --stats
# → 출력: total_trades, winrate, avg_pnl, sharpe_ratio 등

# 엔트리 조건 상관관계
python scripts/analyze_trades.py --entry-correlation
# → 출력: Stage별 winrate, Regime별 winrate, Chi-square p-value

# CSV 출력
python scripts/analyze_trades.py --stats --format csv > stats.csv
# → stats.csv 파일 생성 확인
```

### Phase 11b 검증

**Streamlit 대시보드 실행**:
```bash
streamlit run src/dashboard/app.py
# → 브라우저 http://localhost:8501 접속
# → 스크린샷 저장 (docs/evidence/phase_11b/dashboard_screenshot.png)
```

### Phase 13 검증

**백테스트 증거 생성**:
```bash
# ML 학습
python scripts/train_ml_model.py --min-trades 100 --test-split 0.2 --output ml_policy_override.yaml
# → ml_policy_override.yaml 생성 확인

# 백테스트 실행
pytest tests/integration/test_ml_backtest.py -v
# → winrate 개선 3%+, overfitting < 15%, feature importance 검증

# 실거래 투입 후 모니터링 로그 확인
cat docs/evidence/phase_13/live_monitoring_log.jsonl
# → 첫 20 거래 모니터링 결과 (Rollback 트리거 감지)
```

---

## Final Notes (최종 참고사항)

### 프로젝트 규칙 준수

1. **SSOT 원칙**: 이 계획서는 별도 문서로 유지, 리뷰 후 task_plan.md 병합
2. **TDD 필수**: Phase 10-11a는 TDD 100%, Phase 13은 Feature Extractor만 TDD
3. **Pure transition() 유지**: ML은 Domain 외부 유지 (Policy Tuning Layer)
4. **Intent 패턴**: ML 예측은 Intent가 아닌 Config로 주입
5. **Evidence Artifacts**: 모든 Phase는 docs/evidence/phase_N/ 디렉토리 생성

### 사용자 선택사항 반영

- [x] 별도 .md 문서로 작성 (리뷰 후 task_plan.md 병합)
- [x] ML 타이밍: 100 거래 수집 후 (Plan Agent 권장 200 → 사용자 선택 100)
- [x] 분석 도구: CLI + 간단한 웹 대시보드 (Phase 11a + 11b)

### Rollback 준비

- Phase 10: Feature flag off → 로그 저장 중단
- Phase 11a: 독립 모듈 → 제거 시 영향 없음
- Phase 11b: 독립 모듈 → 제거 시 영향 없음
- Phase 13: 3-tier Rollback (Feature flag → Config 삭제 → 코드 제거)

### 승인 Definition of Done (DoD 6개, 협상 불가)

이 계획서는 아래 6개 조건이 **모두 충족되어야** 승인(PASS)된다:

1. **DoD #1 (Phase 10)**: Single-writer 보장 (TradeLogSink + Queue 방식 문서화, test_concurrent_append 증명)
2. **DoD #2 (Application I/O)**: entry_allowed()에서 파일 로드 제거 (ml_override 파라미터 주입 방식)
3. **DoD #3 (Phase 11a)**: Chi-square 조건부 실행, 기본 출력은 Wilson CI + 효과크기 (Lift)
4. **DoD #4 (Storage)**: 로그 필드 정책 명시 (fills 최대 20개, orderbook depth 10, 크기 상한)
5. **DoD #5 (하드코딩)**: "188 tests passed" 같은 자동 생성 수치 제거 (문서에 고정 금지)
6. **DoD #6 (ML 검증)**: Phase 13 성과 검증을 pytest에서 제거 → `docs/evidence/` 리포트로 이동

**현재 상태**: ✅ DoD #1~#6 모두 반영 완료

### 도박 종료 조건 (Phase 9 Kill Switch 필수)

**현재 상태 (치명적 누락)**:
- 1트레이드 손실: ✅ $10 캡 (Stage 1)
- 일일 손실: ❌ **캡 없음** → 5연속 -$10 = -$50 (계좌 50%)
- 주간 손실: ❌ **캡 없음** → 복구 욕망 무제한
- 연속 손실 중단: △ **축소만** → 계속 거래 가능
- 수수료 이상치 HALT: △ **감지만** → HALT 아님

**판정**: **도박 단계** (누적 손실 캡 없음 → 계좌가 0이 될 때까지 거래 가능)

**5개 Kill Switch (중도 기준, Phase 9 필수 구현)**:

1. **일일 손실 상한**: -$5~7 (equity 5~7%) → 당일 거래 종료
2. **주간 손실 상한**: -$15~20 (equity 15~20%) → 7일 쿨다운
3. **연속 손실 중단**: 5연패 → 당일 거래 종료 (축소 아님)
4. **거래 횟수 상한**: ✅ 5회/일 (현재 구현됨)
5. **수수료/슬리피지 이상치**: 예상 대비 50%↑ → 즉시 HALT

**도박 종료 = Phase 9 완료**:
- Testnet 검증 (Phase 8) + **Mainnet Kill Switch 5개 구현** (Phase 9)
- Phase 9 완료 전까지는 **실험** (수익 아님)
- Phase 10-13 (로그/분석/ML)은 **Phase 9 완료 후**에만 의미 있음

### 다음 단계

1. **사용자 승인**: 이 계획서 리뷰 및 DoD 6개 확인
2. **ML 계획서 완성**: Phase 10-13 최종 검토
3. **task_plan.md 병합**: ML 계획서 + Phase 9 Kill Switch 추가
4. **Phase 9 우선**: Kill Switch 구현 (도박 종료)
5. **Phase 10-13**: Phase 9 완료 후 시작 (로그 → 분석 → ML)

---

**END OF PLAN (Revision 2: DoD #1-#6 반영)**
