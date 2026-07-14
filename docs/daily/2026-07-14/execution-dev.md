# Daily Log — execution-dev
Date: 2026-07-14

## 1. Planned
- [x] 크론 실행 여부 확인 (사용자 질의)

## 2. Done (팩트만)
- 크론 실행 확인: 정상 실행됨. 단 **타임존 버그 발견·수정**:
  - 등록 시 `10 0 * * *`(00:10)로 걸었으나 시스템 TZ=Asia/Seoul → 00:10 KST = **15:10 UTC**에 실행됨 (의도한 00:10 UTC와 15h 차이)
  - 첫 실행 2026-07-13T15:10:01Z, action=no_signal (logs/tsm_shadow/runner.log)
  - 영향: shadow 신호 판정은 무해(같은 UTC일이면 참조 완결봉 동일). **live에선 종가 대비 15h 드리프트로 백테스트 패리티 파괴 → 수정 필수**
  - 수정: 프라이머리 `10 9 * * *`(09:10 KST=00:10 UTC), 재시도 `10 10 * * *`(10:10 KST=01:10 UTC). 참조본 crontab.txt 수정 후 `crontab` 재적용, live==참조본 확인
- 오늘(UTC 07-14) 신호 수동 채움 (새 슬롯이 스케줄 변경 전 지나감): **entry SHORT**
  - entry_ref=$62,311.4, stop=$67,351.0, qty=0.001 BTC, shadow (주문 미발주)
  - 교차검증: close 62311.4 < 30일전 64416.6 AND < EMA50 65110.6 → momentum_down=True ✓
  - stop=entry+2.5×ATR(2015.8)=67350.9 ✓ / risk $5.436÷dist $5039.6=0.00108→floor 0.001 ✓
  - 명목 $62.31, 실 레버리지 0.573x (cap 3x 대비 여유 — 일봉 ATR 스탑이 넓어 자연히 낮음, ADR-0015 예측대로)

### 실거래 전환 (사용자 결정 2026-07-14: G2 생략, 오늘부터 live + 트레이드 API 검증)
- 프리플라이트 (읽기전용): API 키 거래권한 O (ContractTrade Order/Position, 만료 10-13), 계좌 flat, 레버리지 5x cross
- 러너 env 확인: BYBIT_TESTNET 명시설정 → MAINNET 분기 (기본값 testnet 함정 회피 확인)
- **첫 실거래 발주** (`run_tsm_daily.py --mode live --once`, 01:43 UTC): entry SHORT 0.001 BTC
- **거래소 검증 (완료 선언 근거)**: side=Sell size=0.001 avgPrice=$62,467.8, **stopLoss=$67,351 거래소 상주 확인**, liqPrice=$74,588(스탑 위), 명목 $62.48. 최근주문 Market/Filled/stopLoss첨부 확인
  - 슬리피지: 체결 $62,467.8 vs 일봉종가 $62,311.4 = +0.25% (SHORT엔 유리 방향)
  - 트레이드 API 정상: place_order+stopLoss 동시 발주, 스탑 상주(나체포지션 리스크 해소 실증)
- 크론 shadow→live 전환 (2줄, --mode live). ADR-0015 개정 (G2 waiver 기록)

### 레버리지/마진 정합 (사용자 지시: #1 보류, #2 정책 3 isolated 유지)
- 정정: 프리플라이트 tradeMode=0을 cross로 오판 → `/v5/account/info` 조회 결과 marginMode=**ISOLATED_MARGIN**(UTA 2.0). liqPrice가 isolated 증거금 소진점과 일치 확증. **고립 이미 충족**
- 레버리지 5x→3x 설정 (set_leverage): 현 포지션 liqPrice $74,588→$82,876 원거리화(스탑 $67,351이 먼저)
- 코드: tsm_trader._ensure_leverage() 추가 — 진입 시 3x 강제(110043=성공, I/O실패 비차단). 테스트 4개(+4). 851 passed
- 버그 발견: bybit_rest_client.set_margin_mode()가 /v5/position/set-leverage로 POST(tradeMode 무시) → 마진전환 불가. ADR-0012 미작동. TSM 미사용이라 P2 후속
- #1 가드레일 자동강제: 사용자 지시로 보류

## 3. Blocked / Issue
- set_margin_mode 버그 (위) — 후속 수정 대상
- G2 평가 리플레이 스크립트 미작성 (이제 live라 실거래 로그로 대체 가능)

## 4. Decision / Change
- ADR 개정: ADR-0015에 G2 waiver + live 전환 기록 (2026-07-14)

## 5. Next Action
- 포지션 모니터링: 매일 00:10 UTC 크론이 flip 판정. 현 SHORT는 스탑 $67,351 or 모멘텀 복귀 시 청산
- P0: 가드레일($90 floor) 러너 코드 강제 + tsm_trader에 set_leverage(3x) 추가
- 첫 15건 누적 후 G3 평가 (기대값 R>0)
- $1,000 목표 처리 결정 (사용자)
