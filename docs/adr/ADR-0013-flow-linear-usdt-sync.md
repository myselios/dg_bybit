# ADR-0013: FLOW.md Inverse → Linear USDT 동기화

**날짜**: 2026-02-08
**상태**: 수락됨
**영향 받는 문서**: FLOW.md (Section 2, 3, 4.3, 6, 7, 7.5, 9, Changelog)
**작성자**: Chief Architect (Team Lead)
**선행 ADR**: ADR-0002 (Inverse to Linear USDT Migration)

---

## 컨텍스트

ADR-0002에서 Bybit Inverse Futures → Linear USDT 마이그레이션을 결정하고, **코드**는 Phase 14a에서 완전 전환 완료했다 (411 tests passed, `src/` 내 BTCUSD 잔존 0건).

그러나 **FLOW.md (헌법)** 는 여전히 Inverse 기준으로 작성되어 있다:
- Section 3 전체: "Bybit Inverse Futures 특성" (BTC-Denominated)
- Section 6.2: Inverse Fee 공식 (`fee_btc = contracts × fee_rate / price`)
- Section 7: Sizing에 `equity_btc`, `max_loss_btc` 사용
- Section 7.5: `equity_btc` 파라미터, "Bybit Inverse Futures 청산가"
- Section 9: `pnl_btc` 변수명
- Changelog v1.4: "Inverse 1 contract = 1 USD notional"

**문제**:
- 코드는 Linear USDT인데 FLOW.md는 Inverse → **SSOT 불일치 (헌법 ≠ 구현)**
- 새 개발자/Agent가 FLOW.md를 읽으면 Inverse 기준으로 구현할 위험
- 감사(QA) 시 "문서와 코드가 다르다"는 판정이 반복됨

**잔존 항목 수**: FLOW.md 내 Inverse 참조 **28건+** (grep 결과)

---

## 결정

FLOW.md의 모든 Inverse 참조를 **Linear USDT** 기준으로 교체한다.

### 변경 대상 (Section별)

| Section | 현재 (Inverse) | 변경 (Linear USDT) |
|---------|----------------|---------------------|
| **2** (Tick Flow) | `equity_btc, margin, upnl` | `equity_usdt, margin_usdt, upnl_usdt` |
| **3** (제목) | "Bybit Inverse Futures 특성" | "Bybit Linear USDT Futures 특성" |
| **3.1** | BTC-Denominated, Balance/Margin/Fee/PnL: BTC | USDT-Denominated, Balance/Margin/Fee/PnL: USDT |
| **3.2** | Inverse PnL Formula `contracts × (1/entry - 1/exit)` | Linear PnL Formula `qty × (exit - entry)` |
| **3.3-3.6** | `equity_btc`, `max_loss_btc`, `contracts / entry_price` | `equity_usdt`, `max_loss_usdt`, `qty × price` |
| **4.3** | `category="inverse"` 금지 언급 (유지) | 유지 (금지 규칙이므로 그대로) |
| **6.1** | `category="inverse"`, `symbol="BTCUSD"` | `category="linear"`, `symbol="BTCUSDT"` |
| **6.2** | `fee_btc = (contracts × fee_rate) / price` | `fee_usdt = qty × price × fee_rate` |
| **7** | `equity_btc × 0.8`, `required_margin_btc` | `equity_usdt × 0.8`, `required_margin_usdt` |
| **7.5** | `equity_btc` 파라미터, "Bybit Inverse Futures 청산가" | `equity_usdt`, "Bybit Linear USDT 청산가" |
| **9** | `pnl_btc` | `pnl` (단위 중립) |
| **Changelog** | "Inverse 1 contract = 1 USD notional" | 참고 기록 유지 (역사적 맥락) |

### 변경하지 않는 항목

- **Section 4.3 금지 규칙**: `category="inverse"` 금지는 **금지 규칙**이므로 그대로 유지
- **Changelog 과거 버전**: 역사적 기록이므로 수정하지 않음 (v1.4 설명 등)
- **ADR-0002 참조**: ADR 본문은 수정하지 않음

### Linear USDT 핵심 공식 (교체 대상)

**PnL**:
```
Long PnL  = qty × (exit_price - entry_price)
Short PnL = qty × (entry_price - exit_price)
```

**Fee**:
```
fee_usdt = qty × price × fee_rate
```

**Sizing**:
```
qty = max_loss_usdt / (price × stop_distance_pct)
```

**Margin**:
```
required_margin_usdt = qty × price / leverage
```

**Liquidation Distance** (근사):
```
LONG:  liq_price ≈ entry × leverage / (leverage + 1)
SHORT: liq_price ≈ entry × leverage / (leverage - 1)
liq_distance = abs(entry - liq_price) / entry
```
(Inverse/Linear 모두 동일한 근사식)

---

## 대안

### 대안 1: Inverse 내용을 주석/참고로 보존
- FLOW.md에 "Historical Note: Inverse에서는 이렇게 했다" 추가
- 장점: 마이그레이션 이력 보존
- 단점: 문서 길이 증가, 혼란 유발
- **거부 이유**: Changelog에 이미 v1.4 기록 존재, 추가 보존 불필요

### 대안 2: Section 3을 통째로 삭제하고 새로 작성
- 장점: 깨끗한 문서
- 단점: git history에서 diff 추적 불가
- **거부 이유**: 기존 구조 유지하면서 내용만 교체하는 것이 추적성이 좋음

---

## 결과

### 긍정적 영향
- [x] SSOT 일치: 코드 ↔ 문서 ↔ 테스트 모두 Linear USDT
- [x] 신규 개발자 혼란 제거
- [x] QA AC-5 (Inverse 잔존) PASS 가능
- [x] Agent 팀 운영 시 FLOW.md 기반 올바른 구현 보장

### 부정적 영향 / Trade-off
- [x] FLOW.md 대량 수정 (28건+) → 리뷰 부담
- [x] Changelog에 v2.0 업데이트 기록 필요

### 변경이 필요한 코드/문서
- [x] FLOW.md Section 2, 3, 3.1, 3.2, 3.3-3.6, 6.1, 6.2, 7, 7.5, 9 수정
- [ ] FLOW.md Changelog에 v2.0 기록 추가
- [ ] task_plan.md Evidence 업데이트

---

## 실거래 영향 분석

### 리스크 변화
- **청산 리스크**: 불변 (코드는 이미 Linear USDT)
- **손실 한도**: 불변 (문서만 동기화)
- **Emergency 대응**: 불변

### 백워드 호환성
- [x] 기존 포지션 영향 없음 (문서 변경만)
- [x] 코드 변경 없음 (이미 완료)

### 롤백 가능성
- [x] 쉽게 롤백 가능 (git revert)

---

## 참고 자료

- ADR-0002: Inverse to Linear USDT Migration (코드 마이그레이션 결정)
- Phase 14a Inverse 잔존 코드 감사 결과: CRITICAL 3, HIGH 4, MEDIUM 8+ 수정 완료
- pytest 검증: 411 passed (2026-02-08)
