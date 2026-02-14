# ADR-0014: Stage 1 max_loss_usd_cap $3 → $10

**날짜**: 2026-02-13
**상태**: 수락됨
**영향 받는 문서**: account_builder_policy.md (v2.4)
**작성자**: Claude + selios

---

## 컨텍스트

Stage 1 ($100-$300 equity)에서 per-trade loss cap이 $3로 설정되어 있었다.

**문제점**:
1. $3 예산으로는 ATR*0.7 SL 거리에서 최소 주문 단위(0.001 BTC = 1 contract)밖에 못 넣음
2. Grid entry 2-3단계 진입 불가 → R:R 2.14:1 전략의 이론적 이점을 실현할 수 없음
3. BTC 가격 $65,000+ 에서 0.001 BTC ≈ $65, SL 3% → 손실 $1.95. $3 캡은 사실상 무의미
4. 수익 스케일링이 사실상 불가능 → $100→$1,000 목표 달성 시간 과도

**Evidence**: 8건 실거래에서 max realized loss = $0.11 (SL hit 1건). $3 한도가 바인딩된 적 없음.

---

## 결정

Stage 1 `max_loss_usd_cap`을 $3 → $10으로 상향한다.

- **실제 공식**: `max_loss_usdt = min(equity * 10%, $10)`
  - equity $100: min($10, $10) = $10
  - equity $200: min($20, $10) = $10
- **Grid 진입 여유**: $10 예산 → 최대 3-5 contracts (ATR*0.3 간격 기준)
- **R:R 유지**: TP=ATR*1.5, SL=ATR*0.7 → R:R 2.14:1 불변

---

## 대안

### 대안 1: $5로 절충
- equity $100 기준 5% risk per trade
- Grid 2단계까지 가능하나 3단계 불가
- **거부 이유**: 여전히 수익 스케일링 부족. equity $150 넘어야 실질적 변화.

### 대안 2: 현행 $3 유지
- 보수적 접근, 청산 리스크 최소
- **거부 이유**: 전략 에지를 활용할 수 없어 기회비용이 청산 리스크보다 큼.
  실거래 8건 중 max loss $0.11. $3 한도가 불필요하게 제약적.

### 대안 3: 비율만 적용 ($cap 제거)
- `max_loss = equity * 10%` (하드캡 없음)
- equity $300: $30 risk → 과도
- **거부 이유**: Stage 1에서 $30 손실은 30% drawdown. 하드캡 필요.

---

## 결과

### 긍정적 영향
- [x] Grid 전략 충분한 진입 여유 확보
- [x] 수익 스케일링 가능 (연간 목표 달성 가속)
- [x] 실제 시장에서 SL hit 시 $2-5 수준 → $10 한도 내 충분한 여유

### 부정적 영향 / Trade-off
- [x] 단일 트레이드 최대 손실 $3 → $10 (3.3배 증가)
- [x] 연속 3패 시 최대 $30 손실 (equity 30%) → daily loss cap 5%와 함께 관리

### 변경이 필요한 코드/문서
- [x] `docs/specs/account_builder_policy.md` — v2.4 Stage 1 max_loss_usd_cap 수정
- [x] `src/cbgb/config.py` 또는 safety_limits.yaml — 설정값 반영
- [x] Dashboard Risk & Config 탭 — Per-Trade Loss Cap 표시 업데이트 필요

---

## 실거래 영향 분석

### 리스크 변화
- **청산 리스크**: 미미하게 증가 (Equity $100 기준 최악 $10 = 10%, 청산과는 거리 멀음)
- **손실 한도**: $3 → $10 (하지만 daily 5% + weekly 12.5% 가드레일 유지)
- **Emergency 대응**: 불변 (HALT/COOLDOWN 로직 변경 없음)

### 백워드 호환성
- [x] 기존 포지션 영향 없음 (sizing은 다음 진입부터 적용)

### 롤백 가능성
- [x] 쉽게 롤백 가능 (config 값 $3으로 복원)

---

## 참고 자료

- Policy: `docs/specs/account_builder_policy.md` v2.4
- 실거래 데이터: `logs/mainnet/trades_2026-02-12.jsonl`, `trades_2026-02-13.jsonl`
- R:R 분석: TP=ATR*1.5 / SL=ATR*0.7 = 2.14:1
