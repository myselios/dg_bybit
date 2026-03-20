"""
src/application/indicators/volume.py

거래량 확인 (Volume Confirmation) 유틸리티.
외부 라이브러리 없이 stdlib만 사용.
"""


def is_volume_confirmed(volumes: list[float], period: int = 20) -> bool:
    """
    현재 거래량이 과거 평균보다 높은지 확인.

    Args:
        volumes: 거래량 리스트. volumes[-1]이 현재 거래량.
        period: 비교 기준 평균 기간 (기본 20)

    Returns:
        True: volumes[-1] > 과거 period개 평균
        False: 그 외 또는 데이터 부족
    """
    # 현재 거래량 포함하여 최소 period+1개 필요
    if len(volumes) < period + 1:
        return False

    current = volumes[-1]
    # 현재 거래량 제외한 직전 period개 평균
    historical = volumes[-(period + 1):-1]
    avg = sum(historical) / period

    return current > avg
