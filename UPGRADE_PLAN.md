# 🚀 CBGB 24/7 전문 퀀트 시스템 업그레이드 계획

**목표:** 100불 → 1000불 (공격적, 5배 레버리지)
**기간:** 1개월
**운영:** 24/7 무인 운영

---

## Phase 1: 긴급 수정 (즉시)

### 1.1 Rate Limit 보호 강화 ✅ 진행 중
- [x] Tick interval 5초로 변경 (완료)
- [ ] API Retry logic (exponential backoff)
- [ ] Rate limit 감지 시 자동 대기
- [ ] API 실패 시 이전 데이터 유지

### 1.2 레버리지 5배 적용
- [ ] config/safety_limits.yaml 수정
- [ ] Stage별 레버리지: 5x 고정
- [ ] 청산 거리 재계산 (5배 = 20% 하락 시 청산)

### 1.3 공격적 파라미터 적용
- [x] 일일 손실: 5% → 15%
- [x] 거래당 손실: $10 → $25
- [x] 재진입 빈도: 0.3 ATR → 0.2 ATR (코드 적용 완료)
- [x] 익절 배수: 1.5 ATR → 1.0 ATR (코드 적용 완료)
- [x] 일일 거래: 5회 → 15회

---

## Phase 2: 안정성 개선 (1-2일)

### 2.1 에러 핸들링 강화
```python
# bybit_adapter.py
def update_market_data_with_retry(self, max_retries=3):
    for attempt in range(max_retries):
        try:
            self.update_market_data()
            return
        except RateLimitError:
            wait_time = 2 ** attempt  # 1, 2, 4초
            logger.warning(f"Rate limit, retry in {wait_time}s")
            time.sleep(wait_time)
        except Exception as e:
            logger.error(f"API error: {e}")
            if attempt == max_retries - 1:
                # 이전 데이터 유지
                logger.warning("Using cached data")
```

### 2.2 청산 방지 강화
- [ ] 청산 거리 실시간 모니터링
- [ ] 거리 15% 이하 시 경고
- [ ] 거리 10% 이하 시 강제 청산
- [ ] Stop Loss 이중 체크

### 2.3 WebSocket 안정화
- [ ] 연결 끊김 자동 재연결
- [ ] Heartbeat 모니터링
- [ ] Event 유실 감지

---

## Phase 3: 모니터링 시스템 (3-5일)

### 3.1 실시간 메트릭
```yaml
metrics:
  - 현재 포지션 & 손익
  - 청산 거리 (%)
  - API 응답 시간
  - 에러 발생 횟수
  - 일일/주간 수익률
  - 승률 & Sharpe Ratio
```

### 3.2 대시보드 개선
- [ ] 실시간 차트 (PnL, 포지션)
- [ ] 청산 위험 게이지
- [ ] API Health 상태
- [ ] 최근 거래 로그

### 3.3 알림 시스템
- [x] Telegram 기본 알림 (완료)
- [ ] 청산 위험 긴급 알림
- [ ] 일일 수익 요약
- [ ] 주간 성과 리포트

---

## Phase 4: 전략 최적화 (1주)

### 4.1 백테스트 시스템
- [ ] 과거 데이터 수집
- [ ] 파라미터 최적화
- [ ] Monte Carlo 시뮬레이션
- [ ] 리스크 분석

### 4.2 동적 파라미터
- [ ] 변동성 기반 레버리지 조정
- [ ] 시장 상황별 진입 조건
- [ ] 적응형 익절/손절

### 4.3 다중 전략
- [ ] Trend following
- [ ] Mean reversion
- [ ] Breakout
- [ ] 전략 앙상블

---

## Phase 5: 엔터프라이즈급 (2주)

### 5.1 고가용성 (HA)
- [ ] 이중화 (Primary + Backup)
- [ ] 자동 Failover
- [ ] Health check

### 5.2 확장성
- [ ] 다중 심볼 지원
- [ ] 다중 거래소
- [ ] 포트폴리오 관리

### 5.3 규제 준수
- [ ] 거래 기록 저장
- [ ] 감사 로그
- [ ] 리포팅

---

## 즉시 적용 (지금 바로)

**Priority 1 (5분):**
1. ✅ Tick interval 5초 (완료)
2. 레버리지 5배 설정
3. 공격적 파라미터 적용
4. 재시작

**Priority 2 (30분):**
1. Rate limit retry 로직
2. 청산 거리 모니터링
3. 에러 알림 강화

**Priority 3 (오늘):**
1. 대시보드 실시간 업데이트
2. 청산 위험 게이지
3. API Health 모니터링

---

## 예상 수익 시나리오 (5배 레버리지)

| 시나리오 | 일평균 수익 | 월 수익 | 최종 금액 | 확률 |
|----------|-------------|---------|-----------|------|
| **매우 성공** | +8% | +240% | $340 | 5% |
| **성공** | +5% | +150% | $250 | 20% |
| **보통** | +3% | +90% | $190 | 40% |
| **부진** | +1% | +30% | $130 | 25% |
| **실패** | -3% | -90% | $10 | 10% |

**주의:** 청산 위험 존재 (BTC -20% 하락 시)

---

## 현재 상태

- ✅ 봇 실행 중 (3시간+)
- ✅ Rate limit 수정됨
- ✅ 모니터링 활성화
- ⏳ 5배 레버리지 대기 중
- ⏳ 공격적 파라미터 대기 중

---

**다음 단계:** 동건님 최종 승인 → 즉시 적용 → 재시작
