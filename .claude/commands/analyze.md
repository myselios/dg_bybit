트레이드 분석 파이프라인을 실행한다.

1. `docker exec cbgb-analysis python /app/scripts/analyze_trades.py` 또는
   `source venv/bin/activate && python scripts/analyze_trades.py`
2. 결과 분석:
   - 총 트레이드 수, 승률
   - 평균 PnL, 누적 PnL
   - R:R 실측값 vs 설정값 (2.14:1)
   - 최대 드로다운
   - 슬리피지/수수료 분석
3. 정책(account_builder_policy.md) 대비 성과 평가
4. 파라미터 조정 필요 여부 판단
