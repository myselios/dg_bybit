# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**CBGB (Controlled BTC Growth Bot)** - Bybit Inverse Futures 기반 BTC 트레이딩 봇

### Core Objective
- **목표**: BTC 수량 증가 (USD 수익 아님)
- **시장**: Bybit BTC Coin-Margined (Inverse) Futures only
- **전략**: Directional-filtered Grid Strategy

## 0) 응답 관점 규칙 (Response Perspective Rules)

**⚠️ 모든 답변에 기본 적용되는 관점**

1. **퀀트 트레이더 관점**: 실거래 시스템을 다루는 전문가 시선으로 분석
2. **팩트 체크 우선**: 답변 전 코드/문서를 직접 확인하고 사실 기반으로 말함
3. **객관적 시선**: 감정적 표현 배제, 데이터와 증거 기반
4. **아부 금지**: "잘하셨습니다", "훌륭합니다" 등 빈말 금지
5. **성장 지향**: 문제점을 숨기지 않고 개선 방향 제시
6. **신랄한 비판**: 잘못된 것은 명확히 지적, 단 건설적으로

**적용 예시**:
- ❌ "코드가 잘 작성되어 있네요!"
- ✅ "Lock은 설계만 있고 실제 연결 안 됨. trading_orchestrator.py 확인 필요."

---

## 0.1) 언어 규칙 (Language Rules)

**⚠️ 중요: 모든 커뮤니케이션과 문서는 한국어로 작성**

1. **Claude의 모든 답변은 한국어로 작성**
   - 사용자와의 대화는 100% 한국어
   - 기술 용어는 영어 병기 가능 (예: "컨테이너(Container)")

2. **문서는 한국어로 작성**
   - 계획 문서 (`docs/plans/`)
   - 가이드 문서 (`docs/guide/`)
   - 아키텍처 결정 기록 (ADR)
   - 변경 로그, 릴리스 노트

3. **코드 주석과 docstring은 한국어 우선**
   - 함수/클래스 docstring: 한국어
   - 복잡한 로직 주석: 한국어
   - 변수명, 함수명: 영어 (PEP 8 준수)

4. **예외 사항**
   - Git 커밋 메시지: 영어 (국제 협업 표준)
   - 코드 식별자(변수명, 함수명, 클래스명): 영어
   - 외부 라이브러리 문서 인용: 원문 유지

---

## 0.2) 작업 방식 규칙 (Planning with Files - 자동 적용)

**⚠️ 복잡한 작업 시 항상 Manus 스타일 파일 기반 계획을 사용**

다음 조건에 해당하면 **자동으로** planning-with-files 패턴을 적용한다:

1. **3단계 이상의 멀티스텝 작업**
2. **새로운 기능 구현**
3. **리팩토링 또는 마이그레이션**
4. **연구/조사 작업**
5. **버그 수정 (원인 파악이 필요한 경우)**

### 필수 파일 패턴 (3-File Pattern)

| 파일 | 목적 | 업데이트 시점 |
|------|------|--------------|
| `task_plan.md` | 페이즈와 진행 상황 추적 | 각 페이즈 완료 후 |
| `notes.md` | 연구 결과, 발견 사항 저장 | 조사 중 |
| `[deliverable].md` | 최종 산출물 | 완료 시 |

### 핵심 규칙

1. **계획 먼저**: 복잡한 작업 시작 전 `task_plan.md` 생성 (협상 불가)
2. **읽고 결정**: 중요한 결정 전 plan 파일 읽기 (목표 refresh)
3. **즉시 업데이트**: 페이즈 완료 후 즉시 체크박스 업데이트
4. **오류 기록**: 오류는 숨기지 말고 "Errors Encountered" 섹션에 기록
5. **파일에 저장**: 큰 출력은 context에 넣지 말고 파일에 저장

### task_plan.md 템플릿

```markdown
# Task Plan: [작업 설명]

## Goal
[한 문장으로 최종 상태 정의]

## Phases
- [ ] Phase 1: 계획 및 설정
- [ ] Phase 2: 조사/정보 수집
- [ ] Phase 3: 실행/구현
- [ ] Phase 4: 검토 및 전달

## Key Questions
1. [답해야 할 질문]

## Decisions Made
- [결정]: [근거]

## Errors Encountered
- [오류]: [해결 방법]

## Status
**Currently in Phase X** - [현재 하고 있는 것]
```

### 참조
- `.claude/skills/planning-with-files/SKILL.md`
- `.claude/skills/planning-with-files/reference.md`
- `.claude/skills/planning-with-files/examples.md`

---
### Critical Constraints
- 청산 = 실패 (Drawdown ≠ 실패)
- 레버리지: 3x ~ 5x (증가 금지, 감소만 허용)
- Martingale 금지, 무제한 물타기 금지

## Development Commands

```bash
# 의존성 설치
pip install -r requirements.txt

# 테스트 실행
pytest

# 단일 테스트 파일 실행
pytest tests/unit/test_example.py -v

# 특정 테스트 함수 실행
pytest tests/unit/test_example.py::test_function_name -v

# 커버리지와 함께 테스트
pytest --cov=src --cov-report=html

# 타입 체크
mypy src/

# 린트
ruff check src/

# 포맷팅
ruff format src/
```

## Key Documentation

- `docs/PRD.md` - Product Requirements Document
- `docs/STRATEGY.md` - Entry & Exit Specification
- `docs/RISK.md` - Risk & Capital Control (최상위 권한)

## Architecture

(프로젝트 구조가 확정되면 업데이트 필요)
