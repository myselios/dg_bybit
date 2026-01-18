# CBGB (Controlled BTC Growth Bot)

**Account Builder Trading System** - Bybit Inverse Futures 기반 BTC 트레이딩 봇

## 프로젝트 개요

CBGB는 작은 시드로 시작해 계좌의 절대 규모를 "점프"시키는 것을 목표로 하는 Account Builder 시스템입니다.

### 핵심 목표
- 시작 자본: 100 USD
- 목표: 계좌 규모 10배 확대
- 전략: Directional-filtered Grid Strategy
- 시장: Bybit BTC Coin-Margined (Inverse) Futures

### 핵심 철학
- 청산 = 실패 (Drawdown ≠ 실패)
- +300% R-multiple 필수
- Tail Profit 구조
- 낮은 승률 허용, 극단적 비대칭 수익

## 아키텍처 (v2.1)

이 프로젝트는 **클린 아키텍처 + 퀀트 실무 원칙**을 엄격히 준수합니다.

### 핵심 원칙
1. **State Machine 도메인 중심**: 모든 레이어의 행동 허가 제어
2. **EV 2단계 검증**: Pre-filter (빠름) + Full Validator (무거움)
3. **Trading Engine 추상화**: Backtest/Live 동일 구조
4. **Feature Engine 분리**: 지표 계산과 조건 판단 분리
5. **동적 적응**: 시장 환경에 따른 임계값 조정
6. **학습 시스템**: Hindsight 기반 결정 평가 및 개선

### 문서 구조 (Single Source of Truth)

이 프로젝트는 3개의 SSOT(Single Source of Truth) 문서로 운영됩니다:

#### 헌법 (불변 규칙)
- **[docs/constitution/FLOW.md](docs/constitution/FLOW.md)**: 실행 순서, 상태 전환, 모드 규칙

#### 정책 (튜닝 가능 규칙)
- **[docs/specs/account_builder_policy.md](docs/specs/account_builder_policy.md)**: 정책 수치, 게이트 정의, 단위, 스키마

#### 구현 계획 (Gate 기반 체크리스트)
- **[docs/plans/task_plan.md](docs/plans/task_plan.md)**: Gate 기반 구현 순서, DoD, 진행표

## 개발 명령어

```bash
# 의존성 설치
pip install -r requirements.txt

# 테스트 실행
pytest

# 특정 테스트
pytest tests/unit/test_example.py -v

# 커버리지
pytest --cov=src --cov-report=html

# 타입 체크
mypy src/

# 린트
ruff check src/

# 포맷팅
ruff format src/
```

## 구현 상태

현재: **v2.1 - 문서 완성 + 학습/적응 구조 추가**

### 완료 (Documentation)
- ✅ BASE_ARCHITECTURE v2 (클린 아키텍처 + 퀀트 실무)
- ✅ INTERFACES v2 (9개 컴포넌트 Protocol)
- ✅ 4개 필수 보완 문서 (DECISION_LOG, TIME_CONTEXT, EXECUTION_EVENTS, EXPANSION_POLICY)
- ✅ 8개 기능 명세서
- ✅ v2.1: 학습 능력 추가
  - DecisionOutcome (사후 평가)
  - 동적 EV 임계값 (변동성/실적/DD 기반)
  - Marginal EV 계산 (Expansion)
  - State 전환 테이블 (9×9 완전 매핑)
  - Risk Priority 재정렬 (P0/P1/P2)

### 다음 단계 (Implementation)
- [ ] P0: 청산 방지 시스템 (Liquidation Monitor, Risk Manager, Emergency Exit)
- [ ] P1: 핵심 기능 (State Machine, EV Validator, Strategy, Decision Log)
- [ ] P2: 최적화 (동적 임계값, DecisionOutcome 학습, 성능 개선)

## 라이선스

이 프로젝트는 개인 학습 및 연구 목적으로 개발되었습니다.

## 주의사항

⚠️ **실거래 경고**:
- 이 시스템은 Account Builder로 설계되었습니다
- 높은 리스크, 낮은 승률을 전제로 합니다
- 실거래 시 자본 손실 위험이 있습니다
- 충분한 백테스트 및 Paper Trading 검증 후 사용하세요

## 개발자

- 설계 및 문서: Claude Code + Quant Domain Expert Review
- 구현: (진행 중)
