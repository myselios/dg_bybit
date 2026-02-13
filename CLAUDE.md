# CLAUDE.md — CBGB 운영 계약서
Last Updated: 2026-02-13

## 0) 세션 시작 (매 세션 필수, 예외 없음)

```
1. TASKS.md 읽기           → 현재 할 일 파악
2. 전날 작업일지 읽기       → docs/daily/YYYY-MM-DD/ 최신 파일
3. 봇 상태 확인            → docker ps + docker logs cbgb-bot --tail 5
4. 오늘 작업일지 생성       → docs/daily/YYYY-MM-DD/execution-dev.md (TEMPLATE.md 기반)
5. 작업일지 Section 1 작성  → 오늘 할 일 계획 (TASKS.md 기반)
```

**이 5단계를 건너뛰고 코드 작업을 시작하면 안 된다.**

---

## 1) 프로젝트 개요

**CBGB** — Bybit BTCUSDT Linear Futures 트레이딩 봇 ($100→$1,000)

- 청산 = 실패. Martingale 금지.
- 정책 수치는 코드가 아니라 SSOT 문서에서만 정의.

---

## 2) 응답 규칙

- 한국어 응답. 코드 식별자는 영어(PEP8). 커밋 메시지는 영어.
- 팩트 우선. 추측 금지. 아부 금지.
- 비판 우선: 문제 → 원인 → 방치 시 결과 → 개선 방향.

---

## 3) SSOT 문서 (3개, 충돌 시 이것이 우선)

1. `docs/constitution/FLOW.md` — 상태 전환, 실행 순서
2. `docs/specs/account_builder_policy.md` — 정책 수치, 게이트
3. `docs/plans/task_plan.md` — Phase 이력, Evidence

**현재 태스크 SSOT**: `TASKS.md` (프로젝트 루트)

---

## 4) 작업 흐름

```
테스트 먼저 → RED 확인 → 최소 구현 → GREEN → 리팩토링 → pytest -q
```

- FLOW.md 수정 시 ADR 필수 (예외 없음)
- 정의/단위/스키마 변경 시 ADR 필수
- 코드 먼저 → 문서 나중 금지

---

## 5) 작업 완료 시

1. `pytest -q` 통과 확인
2. `TASKS.md` 업데이트 (완료 체크 + 날짜)
3. 작업일지 Section 2(Done) 작성 — 파일명/함수명/커맨드 단위로 팩트만
4. 작업일지 Section 5(Next Action) 작성

---

## 6) 개발 커맨드

```bash
source venv/bin/activate
pip install -e ".[dev]"        # 최초/pyproject.toml 변경 시
pytest -q                      # 전체 테스트
pytest -q tests/unit/파일.py -v  # 단일 파일
ruff check src/ && mypy src/   # 린트/타입
```

---

## 7) 작업일지 규칙

- 위치: `docs/daily/YYYY-MM-DD/execution-dev.md`
- 템플릿: `docs/daily/TEMPLATE.md`
- 감정 표현 금지. "검토함", "고민함" 금지.
- 파일명/함수명/커맨드 결과 필수.
- Blocked는 24시간 방치 금지.

---

## 8) 금지 사항 (코드)

- `assert True`, `pass # TODO`, `raise NotImplementedError` 테스트 금지
- tests/에서 domain 타입 재정의 금지 (Position, State 등)
- `sys.path.insert` 금지
- transition() 외부에 상태 전이 로직 금지
