# Daily Log — TDD-Guide
Date: 2026-03-18

## 1. Planned (아침 기준)
- [x] S6 ThresholdCalibrator TDD-RED 단계 실행
- [x] tests/unit/test_threshold_calibrator.py 작성 (8개 테스트)
- [x] RED 확인 (모든 테스트 실패)

## 2. Done (팩트만, 파일/함수/커맨드 단위)
- `tests/unit/test_threshold_calibrator.py` 생성 — 8개 테스트 함수
  - test_calibrate_returns_threshold_config
  - test_calibrate_p85_below_hardcoded_0_4
  - test_calibrate_t_range_entry_is_quarter_of_t_trend
  - test_calibrate_minimum_clamp
  - test_calibrate_insufficient_klines_raises
  - test_signal_generator_uses_threshold_config
  - test_signal_generator_enters_with_calibrated_low_threshold
  - test_threshold_config_immutable
- `pytest -q tests/unit/test_threshold_calibrator.py -v` → 8 failed (ModuleNotFoundError)
- 기존 테스트 영향 없음 확인: 419 passed (telegram 3건은 기존 실패)

## 3. Blocked / Issue
- (없음)

## 4. Decision / Change
- ADR 필요 여부: NO
- ThresholdConfig: t_range_entry = t_trend * 0.25 비율 결정
- 최솟값 클램프: t_trend >= 0.005%

## 5. Next Action (내일)
- GREEN 단계: src/application/threshold_calibrator.py 구현
- signal_generator.py에 threshold_config 파라미터 추가 (generate_signal)
- determine_regime()도 threshold_config 사용하도록 변경
