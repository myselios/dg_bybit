---
description: 세션 간 태스크 연속성. 모든 파일에 적용.
globs:
  - "**/*"
---

# Task Continuity (세션 간 작업 연속성)

## 세션 시작 시 (CLAUDE.md Section 0 실행)

1. `TASKS.md` 읽기 → 미완료 태스크 중 unblocked 확인
2. `docs/daily/` 최신 날짜 폴더의 작업일지 읽기 → Section 5(Next Action) 확인
3. `docker ps` + `docker logs cbgb-bot --tail 5` → 봇 상태 확인
4. 오늘 작업일지 생성 → `docs/daily/YYYY-MM-DD/execution-dev.md`
5. 작업일지 Section 1(Planned) 작성 → TASKS.md 기반 오늘 계획

## 세션 종료 시

1. `TASKS.md` 업데이트 (완료 [x] + 날짜, 새 태스크 추가)
2. 작업일지 Section 2(Done) — 팩트만 (파일명/함수명/커맨드)
3. 작업일지 Section 5(Next Action) — 다음 세션이 이어받을 내용
4. git commit (사용자 요청 시)

## 우선순위

P0(즉시) → P1(단기) → P2(중기) → P3(장기)
blocked_by가 해소된 태스크만 진행.
