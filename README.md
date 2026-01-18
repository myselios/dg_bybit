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

## 아키텍처 (v2)

이 프로젝트는 **클린 아키텍처 + 퀀트 실무 원칙**을 엄격히 준수합니다.

### 핵심 원칙
1. **State Machine 도메인 중심**: 모든 레이어의 행동 허가 제어
2. **EV 2단계 검증**: Pre-filter (빠름) + Full Validator (무거움)
3. **Trading Engine 추상화**: Backtest/Live 동일 구조
4. **Feature Engine 분리**: 지표 계산과 조건 판단 분리

### 문서 구조

#### 헌법 (최상위)
- **[docs/base/BASE_ARCHITECTURE.md](docs/base/BASE_ARCHITECTURE.md)**: 구조적 헌법
- **[docs/base/INTERFACES.md](docs/base/INTERFACES.md)**: 컴포넌트 계약

#### 필수 보완 문서
- **[docs/base/DECISION_LOG.md](docs/base/DECISION_LOG.md)**: 결정 기록 시스템
- **[docs/base/TIME_CONTEXT.md](docs/base/TIME_CONTEXT.md)**: 시간 기반 제약
- **[docs/base/EXECUTION_EVENTS.md](docs/base/EXECUTION_EVENTS.md)**: 실행 이벤트 처리
- **[docs/base/EXPANSION_POLICY.md](docs/base/EXPANSION_POLICY.md)**: Expansion 재검증

#### 기능 명세서
- **[docs/base/PRD.md](docs/base/PRD.md)**: 목표 및 제약 정의
- **[docs/base/EV_FRAMEWORK.md](docs/base/EV_FRAMEWORK.md)**: EV 검증 기준
- **[docs/base/STATE_MACHINE.md](docs/base/STATE_MACHINE.md)**: 상태 흐름
- **[docs/base/STRATEGY.md](docs/base/STRATEGY.md)**: 진입 조건
- **[docs/base/RISK.md](docs/base/RISK.md)**: 리스크 정책
- **[docs/base/POSITION_MODEL.md](docs/base/POSITION_MODEL.md)**: 사이징 로직
- **[docs/base/EXECUTION_MODEL.md](docs/base/EXECUTION_MODEL.md)**: 체결 처리

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

현재: **Phase 0 - 문서 완성 단계**

### 완료
- ✅ BASE_ARCHITECTURE v2 (클린 아키텍처 + 퀀트 실무)
- ✅ INTERFACES v2 (9개 컴포넌트 Protocol)
- ✅ 4개 필수 보완 문서
- ✅ 8개 기능 명세서

### 다음 단계
- [ ] Phase 0: 인터페이스 정의 (`src/core/interfaces.py`)
- [ ] Phase 1: 도메인 코어 구현
- [ ] Phase 2: 정책 레이어 구현
- [ ] Phase 3: 인프라 레이어 구현
- [ ] Phase 4: 통합 및 백테스트

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
