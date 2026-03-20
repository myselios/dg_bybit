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


def load_journal_df(log_dir: Path) -> pd.DataFrame:
    """trades_*.jsonl 파일들을 읽어 DataFrame 반환.

    Args:
        log_dir: trades_*.jsonl 파일이 있는 디렉토리 경로,
                 또는 단일 .jsonl 파일 경로

    Returns:
        pd.DataFrame with columns: direction, entry_price, exit_price,
        qty_btc, realized_pnl_usd, fee_usd, hold_minutes, market_regime,
        exit_time, order_id, side
    """
    all_trades = []

    # 단일 파일 경로인 경우
    if log_dir.is_file():
        files = [log_dir]
    else:
        files = sorted(log_dir.glob("trades_*.jsonl"))

    for f in files:
        with open(f) as fp:
            for line in fp:
                line = line.strip()
                if line:
                    try:
                        all_trades.append(json.loads(line))
                    except Exception:
                        pass

    if not all_trades:
        return pd.DataFrame(columns=[
            "order_id", "direction", "side", "entry_price", "exit_price",
            "qty_btc", "realized_pnl_usd", "fee_usd", "hold_minutes",
            "market_regime", "exit_time"
        ])

    df = pd.DataFrame(all_trades)

    # hold_minutes: hold_seconds / 60 (None 유지)
    if "hold_seconds" in df.columns:
        df["hold_minutes"] = df["hold_seconds"].apply(
            lambda x: x / 60 if x is not None and not pd.isna(x) else None
        )
    else:
        df["hold_minutes"] = None

    return df


def calculate_journal_stats(df: pd.DataFrame) -> dict:
    """DataFrame에서 요약 통계 계산.

    Returns:
        dict with keys: win_rate, avg_pnl, max_loss, total_trades, total_pnl
    """
    if df.empty or "realized_pnl_usd" not in df.columns:
        return {
            "win_rate": 0.0,
            "avg_pnl": 0.0,
            "max_loss": 0.0,
            "total_trades": 0,
            "total_pnl": 0.0,
        }

    pnl = df["realized_pnl_usd"].dropna()
    wins = (pnl > 0).sum()
    total = len(pnl)

    return {
        "win_rate": wins / total if total > 0 else 0.0,
        "avg_pnl": float(pnl.mean()) if total > 0 else 0.0,
        "max_loss": float(pnl.min()) if total > 0 else 0.0,
        "total_trades": int(total),
        "total_pnl": float(pnl.sum()),
    }


def load_all_trades(log_dir: str) -> pd.DataFrame:
    """
    지정 디렉토리의 모든 trades_*.jsonl 파일을 로드하여 DataFrame 반환.

    - entry_time null → NaN으로 처리 (crash 없음)
    - hold_seconds null → NaN으로 처리
    - exit_time float → datetime 변환 없이 raw float 유지 (하류에서 변환)
    - 파일이 없으면 빈 DataFrame 반환

    Args:
        log_dir: 로그 디렉토리 경로 (str)

    Returns:
        pd.DataFrame: 모든 트레이드 레코드 (정렬: exit_time asc)
    """
    log_path = Path(log_dir)
    if not log_path.exists():
        return pd.DataFrame()

    files = sorted(log_path.glob("trades_*.jsonl"))
    if not files:
        return pd.DataFrame()

    all_rows: list = []
    for f in files:
        with open(f, encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    all_rows.append(row)
                except json.JSONDecodeError:
                    pass

    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)

    # null 처리: entry_time, hold_seconds → NaN
    for col in ("entry_time", "hold_seconds", "exit_time"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            df[col] = float("nan")

    # realized_pnl_usd null → 0
    if "realized_pnl_usd" in df.columns:
        df["realized_pnl_usd"] = pd.to_numeric(df["realized_pnl_usd"], errors="coerce").fillna(0.0)

    # exit_time 기준 정렬 (NaT 뒤로)
    df = df.sort_values("exit_time", na_position="last").reset_index(drop=True)

    return df


def get_summary_stats(df: pd.DataFrame) -> dict:
    """
    요약 통계 반환.

    Args:
        df: load_all_trades() 또는 load_journal_df() 로 로드한 DataFrame

    Returns:
        dict with:
            - total_trades: int
            - win_rate: float (0.0~1.0)
            - total_pnl: float
            - avg_win: float (승리 트레이드 평균 PnL)
            - avg_loss: float (손실 트레이드 평균 PnL, 음수)
            - rr_ratio: float (avg_win / abs(avg_loss), 0 if no losses)
            - max_drawdown: float (최대 드로다운 USD, 0 이하)
    """
    empty: dict = {
        "total_trades": 0,
        "win_rate": 0.0,
        "total_pnl": 0.0,
        "avg_win": 0.0,
        "avg_loss": 0.0,
        "rr_ratio": 0.0,
        "max_drawdown": 0.0,
    }

    pnl_col = None
    for candidate in ("realized_pnl_usd", "pnl"):
        if candidate in df.columns:
            pnl_col = candidate
            break

    if df.empty or pnl_col is None:
        return empty

    pnl = df[pnl_col].dropna()
    total = len(pnl)
    if total == 0:
        return empty

    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]

    avg_win = float(wins.mean()) if not wins.empty else 0.0
    avg_loss = float(losses.mean()) if not losses.empty else 0.0
    rr_ratio = avg_win / abs(avg_loss) if avg_loss != 0 else 0.0

    # max drawdown 계산
    cum_pnl = pnl.cumsum()
    running_max = cum_pnl.cummax()
    drawdown = cum_pnl - running_max
    max_drawdown = float(drawdown.min()) if not drawdown.empty else 0.0

    return {
        "total_trades": int(total),
        "win_rate": float((pnl > 0).sum()) / total,
        "total_pnl": float(pnl.sum()),
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "rr_ratio": rr_ratio,
        "max_drawdown": max_drawdown,
    }


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
