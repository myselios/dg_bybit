"""
src/dashboard/data_pipeline.py

Phase 14a (Dashboard): JSONL 로그 → DataFrame 변환 파이프라인

DoD:
- JSONL 파일 로드 (logs/*.log)
- TradeLogV1 스키마 파싱
- DataFrame 변환 (필수 컬럼 검증)
- 에러 핸들링 (빈 파일, 잘못된 JSON)
"""

from pathlib import Path
from typing import List
import json
import pandas as pd
from src.infrastructure.logging.trade_logger_v1 import TradeLogV1


def load_log_files(log_dir: Path) -> List[Path]:
    """
    logs/ 디렉토리에서 *.log 및 *.jsonl 파일 목록 로드

    Args:
        log_dir: 로그 파일 디렉토리 경로

    Returns:
        List[Path]: .log 및 .jsonl 파일 경로 리스트 (수정 시간 역순)

    Raises:
        FileNotFoundError: 디렉토리가 존재하지 않으면
    """
    if not log_dir.exists():
        raise FileNotFoundError(f"Log directory not found: {log_dir}")

    # trades_*.jsonl 파일만 로드 (일반 텍스트 .log 제외)
    log_files = list(log_dir.glob("trades_*.jsonl"))
    log_files = sorted(log_files, key=lambda f: f.stat().st_mtime, reverse=True)
    return log_files


def parse_jsonl(file_path: Path) -> List[TradeLogV1]:
    """
    JSONL 파일을 TradeLogV1 객체 리스트로 파싱

    Args:
        file_path: JSONL 파일 경로

    Returns:
        List[TradeLogV1]: 파싱된 TradeLogV1 객체 리스트

    Note:
        - 빈 파일은 빈 리스트 반환
        - 잘못된 JSON 라인은 스킵 (로그 경고만)
    """
    logs: List[TradeLogV1] = []

    if not file_path.exists():
        raise FileNotFoundError(f"Log file not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue  # 빈 라인 스킵

            try:
                data = json.loads(line)
                # 구 스키마 호환: 누락 필드에 기본값 추가
                data.setdefault("side", "")
                data.setdefault("direction", "")
                data.setdefault("qty_btc", 0.001)
                data.setdefault("entry_price", 0.0)
                data.setdefault("exit_price", 0.0)
                data.setdefault("realized_pnl_usd", 0.0)
                data.setdefault("fee_usd", 0.0)
                log = TradeLogV1(**data)
                logs.append(log)
            except json.JSONDecodeError as e:
                # 잘못된 JSON 라인 스킵 (경고만)
                print(f"Warning: Invalid JSON at {file_path}:{line_num} - {e}")
                continue
            except TypeError as e:
                # TradeLogV1 스키마 불일치 스킵
                print(f"Warning: Schema mismatch at {file_path}:{line_num} - {e}")
                continue

    return logs


def to_dataframe(logs: List[TradeLogV1]) -> pd.DataFrame:
    """
    TradeLogV1 리스트를 DataFrame으로 변환

    Args:
        logs: TradeLogV1 객체 리스트

    Returns:
        pd.DataFrame: 변환된 DataFrame (필수 컬럼 포함)

    Note:
        DataFrame 컬럼:
        - order_id, fills, slippage_usd, latency_*
        - funding_rate, mark_price, index_price, market_regime
        - schema_version, config_hash, git_commit
    """
    if not logs:
        # 빈 리스트는 빈 DataFrame 반환
        return pd.DataFrame()

    # TradeLogV1 → dict 변환
    records = []
    for log in logs:
        record = {
            "order_id": log.order_id,
            "fills": log.fills,
            "slippage_usd": log.slippage_usd,
            "latency_rest_ms": log.latency_rest_ms,
            "latency_ws_ms": log.latency_ws_ms,
            "latency_total_ms": log.latency_total_ms,
            "funding_rate": log.funding_rate,
            "mark_price": log.mark_price,
            "index_price": log.index_price,
            "orderbook_snapshot": log.orderbook_snapshot,
            "market_regime": log.market_regime,
            "schema_version": log.schema_version,
            "config_hash": log.config_hash,
            "git_commit": log.git_commit,
            "exchange_server_time_offset_ms": log.exchange_server_time_offset_ms,
            "side": log.side,
            "direction": log.direction,
            "qty_btc": log.qty_btc,
            "entry_price": log.entry_price,
            "exit_price": log.exit_price,
            "realized_pnl_usd": log.realized_pnl_usd,
            "fee_usd": log.fee_usd,
            "pnl": log.realized_pnl_usd,
        }
        records.append(record)

    df = pd.DataFrame(records)
    return df
