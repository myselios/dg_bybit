"""dashboard_journal.py — 매매일지 데이터 파이프라인 (테스트 호환 레이어)"""
from pathlib import Path
from src.dashboard.data_pipeline import load_journal_df, calculate_journal_stats

__all__ = ["load_journal_df", "calculate_journal_stats"]
