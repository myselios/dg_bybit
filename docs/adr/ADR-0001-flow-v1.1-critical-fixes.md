# ADR-0001: FLOW v1.1 치명적 구멍 6가지 수정

**날짜**: 2026-01-18
**상태**: 수락됨
**영향 받는 문서**: FLOW.md v1.0 → v1.1
**작성자**: System Review

---

## 컨텍스트

FLOW.md v1.0 초안을 실거래 관점에서 검토한 결과, **6가지 치명적 구멍**이 발견되었습니다.

이 구멍들은 모두 **실거래 사고**로 직결될 수 있는 문제들입니다.

### 문제 1: 상태 수 불일치
- "5가지 상태"라고 명시했으나 실제로는 6개 나열
- 구현자가 문서 신뢰도를 의심하게 만드는 기본적 오류

### 문제 2: Tick 주기 고정
- "1초마다 실행"을 고정값으로 명시
- Bybit rate limit (120 req/min) 무시
- API 호출 제한 없음 → rate limit 초과 → 시스템 차단

### 문제 3: Execution Events 소스 불명확
- WS vs REST 우선순위 없음
- 부분체결/취소/ADL 등 이벤트 처리 규칙 부재
- REST 폴링으로 상태 확정 시 불일치 발생

### 문제 4: Long/Short 공식 미분기
- Long만 예시로 제시, Short는 암시만
- Stop price 정의가 방향별로 다름 (Long: -d, Short: +d)
- Short 구현 시 손실 계산 오류 가능성

### 문제 5: Leverage와 Loss Budget 관계 모호
- Leverage를 sizing에 넣으면 안 되는 이유 명시 부족
- 구현자가 혼동하여 `contracts × leverage` 같은 오류 가능

### 문제 6: Fee Rate API 실패 시 대응 없음
- API 조회만 명시, fallback 정책 없음
- API 장애 시 시스템 정지 or 잘못된 수수료 사용

---

## 결정

6가지 구멍을 모두 수정하여 FLOW v1.1로 업데이트합니다.

### 수정 1: 상태 수 정정
```markdown
- 변경 전: "5가지 상태"
- 변경 후: "6가지 상태"
```

### 수정 2: Tick 주기 동적화 + Rate Limit 보호
```markdown
추가:
- 목표 1초, 실제 0.5~2초 동적 조정
- 1 Tick당 REST API 최대 3회 제한
- WebSocket 우선, REST는 fallback
- Rate limit 근접 시 Tick 주기 자동 증가
```

### 수정 3: Execution Events 소스 우선순위 명시
```markdown
신규 Section 2.5 추가:
- Event Source: WS > REST
- Event Types: FILL/PARTIAL_FILL/CANCEL/REJECT/LIQUIDATION/ADL
- State Confirmation: Event-driven 필수, REST 폴링 금지
- Fallback: WS 실패 시만 REST (5분 timeout)
```

### 수정 4: Direction별 공식 분기
```markdown
Section 3.2, 3.3 수정:
- Stop Price: Long (entry × (1-d)), Short (entry × (1+d))
- Loss Formula: Long/Short 분리
- Sizing Formula: Long/Short 분리
```

### 수정 5: Leverage 독립성 명시
```markdown
신규 Section 3.5 추가:
- 원칙: Stop-loss 손실은 레버리지와 무관
- 이유: PnL 계산에 leverage 없음
- 올바른 사용: Loss Sizing (leverage 없음), Margin Check (leverage 사용)
- 금지: contracts = f(leverage) in loss budget
```

### 수정 6: Fee Rate Fallback 정책
```markdown
Section 6 확장:
- Fallback 우선순위: API → Cache (1h) → Config Default
- API 실패 시 HALT 금지
- Inverse category 명시 필수
```

---

## 대안

### 대안 1: 구멍을 그대로 두고 구현 중 해결
- **거부 이유**: 헌법(FLOW.md)의 신뢰도 상실, 구현자마다 다른 해석

### 대안 2: FLOW.md를 더 간략하게 작성
- **거부 이유**: 실거래에서 "간략함"은 "애매함"과 동일, 사고 확률 증가

---

## 결과

### 긍정적 영향
- [x] Rate limit 사고 방지
- [x] Execution event 불일치 방지
- [x] Long/Short 구현 오류 방지
- [x] Leverage 오용 방지
- [x] Fee API 장애 대응 가능
- [x] 문서 신뢰도 회복

### 부정적 영향 / Trade-off
- [x] 문서 길이 증가 (600줄 → 800줄)
- [x] 구현 복잡도 약간 증가 (WS 구현 필수)

### 변경이 필요한 코드/문서
- [x] FLOW.md v1.0 → v1.1
- [ ] task_plan.md: Phase 1에 "WebSocket implementation" 추가 필요
- [ ] src/exchange/: WebSocket adapter 구현 필요
- [ ] src/sizing/: Direction별 분기 구현 필요

---

## 실거래 영향 분석

### 리스크 변화
- **청산 리스크**: 감소 (Leverage 독립성 명시)
- **손실 한도**: 불변 (계산 정확도만 증가)
- **Emergency 대응**: 개선 (WS로 실시간 감지)

### 백워드 호환성
- [x] 기존 포지션 영향 없음 (아직 구현 전)
- [x] 기존 설정 마이그레이션 불필요
- [x] v1.0은 초안이므로 완전 교체 가능

### 롤백 가능성
- [x] 쉽게 롤백 가능 (Git revert)
- [ ] 데이터 마이그레이션 불필요
- [ ] 롤백 불필요 (v1.0은 미구현)

---

## 참고 자료

- Bybit WebSocket API: https://bybit-exchange.github.io/docs/v5/websocket/intro
- Bybit Rate Limit: https://bybit-exchange.github.io/docs/v5/rate-limit
- User Review: 2026-01-18 실거래 관점 리뷰
