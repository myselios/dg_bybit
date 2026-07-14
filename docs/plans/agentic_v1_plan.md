# CBGB Agentic v1 — 구현 계획서
작성일: 2026-03-18
작성자: Claude Code

---

## 0. 현황 & 즉각 조치 필요

### 🔴 CRITICAL 버그 (현재 진입 0건 원인)

```
T_TREND = 0.4%       ← 실측 ma_slope max 0.0423% 대비 10배 높음
T_RANGE_ENTRY = 0.4% ← Range regime(abs(slope) < 0.4%) 안에서 수학적으로 달성 불가
```

**결과**: 2026-03-15 배포 이후 단 한 건의 진입 신호도 생성되지 않음

**즉시 수정 (S6 최우선)**: ThresholdCalibrator로 실제 slope 분포 기반 동적 임계값 적용

---

## 1. 아키텍처 목표

```
현재 구조 (단일 오케스트레이터):
  orchestrator.py (900줄)
    ├── 시장 분석
    ├── 신호 생성
    ├── 리스크 계산
    └── 주문 실행

목표 구조 (멀티에이전트):
  orchestrator.py (300줄 이하, 메시지 라우팅만)
    ├── MarketAnalystAgent → regime, threshold
    ├── StrategyAgent      → signal, grid
    ├── RiskAgent          → sizing, leverage, gate
    └── ReflectionAgent    → 트레이드 결과 분석
         └── HypothesisLoop → Claude API 가설 생성
              └── ShadowTrader → Paper trade 검증
                   └── ApprovalGateway → Telegram 승인
```

---

## 2. 구현 단계 (8 Stories, 우선순위 순)

### Phase A: 즉시 수정 (Week 1)

#### S6: Adaptive Threshold Engine ← **가장 먼저**
**목적**: 진입 신호 0건 버그 즉시 해결

```
src/application/threshold_calibrator.py

class ThresholdCalibrator:
    def calibrate(self, klines: List[Kline], percentile: float = 85.0) -> ThresholdConfig:
        slopes = [calculate_ma_slope(klines, i) for i in range(len(klines)-500, len(klines))]
        p85 = np.percentile([abs(s) for s in slopes], percentile)
        return ThresholdConfig(
            t_trend=p85,
            t_range_entry=p85 * 0.25,  # trend의 25% → range 진입 허용
        )
```

**signal_generator.py 변경**:
- T_TREND, T_RANGE_ENTRY 하드코딩 제거
- `generate_signal(threshold_config=ThresholdConfig(...))` 파라미터 추가

**통합**: orchestrator 시작 시 1회 + 1시간마다 asyncio.create_task(recalibrate())

#### S8: Health Scorecard
**목적**: 현재 같은 "신호 0건" 상황 즉시 감지

```
src/application/health_scorecard.py

Grade 기준:
  A: 신호발생률>5%/h, 승률>50%, 연속손실<3
  B: 신호발생률>2%/h, 승률>40%
  C: 신호발생률>0%/h
  F: 신호발생률=0% (현재 상태) → CRITICAL 알림
```

---

### Phase B: Reflection Loop (Week 2)

#### S7: Event-Driven Reflection Agent
트레이드 완료 이벤트 → 자동 원인 분석 → 가설 저장

```
logs/mainnet/reflections_2026-03-18.jsonl 형태:
{
  "trade_id": "...",
  "outcome": "loss",
  "pnl": -2.3,
  "analysis": {
    "pattern": "regime_mismatch",
    "cause": "entered LONG in ranging market",
    "hypothesis": "T_TREND too low at entry time",
    "param_delta": {"T_TREND": "+0.01%"}
  }
}
```

#### S9: Daily Strategy Review Loop
00:00 KST cron → analyze_trades.py 실행 → docs/daily/YYYY-MM-DD/auto_review.md 저장

#### S10: Human-in-the-Loop (Telegram)
주요 파라미터 변경 시 Telegram 인라인 버튼으로 승인 요청
- TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 환경변수 없으면 자동승인 폴백

---

### Phase C: Multi-Agent Structure (Week 3)

#### S11: Multi-Agent Orchestration
orchestrator.py 분리 + 에이전트 메시지 패싱

```python
# AgentMessage 프로토콜
@dataclass(frozen=True)
class AgentMessage:
    from_agent: str
    to_agent: str
    msg_type: str   # "regime_update" | "signal" | "size_request" | "reflection" | etc.
    payload: dict
    timestamp: float
```

**구현 순서**:
1. 에이전트 인터페이스 정의 (BaseAgent Protocol)
2. 각 에이전트 구현 (로직은 기존 모듈 위임)
3. orchestrator 경량화 (메시지 라우터로 전환)
4. 기존 테스트 모두 green 확인

---

### Phase D: Autonomous Loop (Week 4)

#### S12: Autonomous Hypothesis Loop (Claude API)
```python
# 가설 생성 프롬프트 구조
prompt = f"""
최근 {N}개 트레이드 분석:
- 승률: {win_rate:.1%}
- 평균 PnL: ${avg_pnl:.2f}
- 현재 T_TREND: {current_t_trend:.4f}%

개선 가설을 JSON으로 제시하세요:
{{
  "hypothesis": "...",
  "param_changes": {{"T_TREND": 0.015, "T_RANGE_ENTRY": 0.004}},
  "expected_improvement": "승률 5% 향상 예상",
  "confidence": 0.7
}}
"""
```

#### S13: Shadow Trading Mode
실제 시장 데이터 수신 + 가상 주문 실행 + 실제 주문 없음
Shadow 24h 성과 ≥ 현재 → S10 승인 요청 → 실제 파라미터 교체

---

## 3. 파일 구조 (신규 생성)

```
src/application/
  threshold_calibrator.py     ← S6 (즉시)
  health_scorecard.py         ← S8
  shadow_trader.py            ← S13
  hypothesis_loop.py          ← S12
  agents/
    __init__.py
    base_agent.py             ← Protocol 정의
    market_analyst_agent.py   ← S11
    strategy_agent.py         ← S11
    risk_agent.py             ← S11
    reflection_agent.py       ← S7
    daily_review_agent.py     ← S9
    approval_gateway.py       ← S10

logs/mainnet/
  reflections_*.jsonl         ← ReflectionAgent 출력
  hypotheses_*.jsonl          ← HypothesisLoop 출력
  shadow_results_*.jsonl      ← ShadowTrader 출력
```

---

## 4. 환경변수 추가 (신규)

```bash
# .env에 추가 필요
ANTHROPIC_API_KEY=sk-ant-...   # S12 Hypothesis Loop
TELEGRAM_BOT_TOKEN=...         # S10 승인 UI (선택)
TELEGRAM_CHAT_ID=...           # S10 승인 UI (선택)
SHADOW_DURATION_HOURS=24       # S13 Shadow 기간 (기본 24h)
HYPOTHESIS_MIN_TRADES=10       # S12 최소 트레이드 수
```

---

## 5. 실행 계획 (시작 순서)

```
즉시 → S6 (진입 버그 수정) → 배포 → 매수 재개 확인
Week 1 → S8 (Health Scorecard)
Week 2 → S7 → S9 → S10 (Reflection + Review + Telegram)
Week 3 → S11 (Multi-Agent 구조)
Week 4 → S12 → S13 (Hypothesis Loop + Shadow)
```

**S6는 오늘 배포 필수** — 현재 봇은 구조적으로 진입 불가 상태.

---

## 6. 리스크 & 완화 전략

| 리스크 | 심각도 | 완화 |
|--------|--------|------|
| Calibrator가 너무 낮은 T_TREND 생성 → 과잉 진입 | HIGH | 최소값 clamp 적용 (T_TREND >= 0.005%) |
| Claude API 호출 실패 | MEDIUM | 실패 시 현재 파라미터 유지 |
| Telegram 미응답 → 파라미터 무한 대기 | MEDIUM | 30분 타임아웃 → 자동 거부 |
| Shadow mode가 Live보다 느린 시장 반영 | LOW | WebSocket 동일 스트림 사용 |
| orchestrator 분리 중 기존 테스트 깨짐 | HIGH | 에이전트마다 단계적 분리, Green 유지 |
