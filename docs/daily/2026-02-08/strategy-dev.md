# Daily Log — Strategy Engine Developer
Date: 2026-02-08

## 1. Planned (아침 기준)
- [x] sizing.py Linear USDT 공식 검증
- [x] fee_verification.py Inverse 수식 검증
- [x] metrics_tracker.py 단위 검증

## 2. Done (팩트만)
- fee_verification.py: Inverse 수식 전체 재작성 → Linear USDT (`fee = qty × price × fee_rate`)
  - `estimate_fee_usd(contracts, fee_rate)` → `estimate_fee_usdt(qty, price, fee_rate)`
  - `verify_fee_post_trade`: BTC→USD 변환 제거, USDT 직접 비교
- metrics_tracker.py: `pnl_btc` → `pnl` 네이밍 정리 (replace_all)
- liquidation_gate.py: `equity_btc` → `equity_usdt` 네이밍 정리
- 테스트 3개 파일 동기화 수정

## 3. Blocked / Issue
- 없음

## 4. Decision / Change
- ADR 필요 여부: NO

## 5. Next Action
- Signal/Sizing Output Contract 정의
- Grid spacing 공식 Linear USDT 검증
