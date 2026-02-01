# Production 배포 가이드

**작성 일시**: 2026-01-27
**대상**: Phase 12c 완료 후 Production 실거래 시작
**전제 조건**: Mainnet Dry-Run 성공 (Phase 12b 완료)

---

## 1. 배포 전 체크리스트

### 1.1 코드 검증

```bash
# (1) 전체 테스트 통과 확인
pytest -q
# → 335 passed, 15 deselected

# (2) Force Entry 코드 0개 확인
grep -r "force_entry" src/ tests/ scripts/ | wc -l
# → 0

# (3) Debug 로깅 제거 확인
grep -r "🔍" src/ | wc -l
# → 0
```

### 1.2 환경 설정 확인

```bash
# (1) .env 파일 존재 확인
ls -la .env
# → .env 파일 있어야 함

# (2) Mainnet API 키 설정 확인
cat .env | grep BYBIT_TESTNET
# → BYBIT_TESTNET=false (Mainnet 모드)

# (3) API 키 유효성 확인 (간단한 REST 호출)
python -c "
from src.infrastructure.exchange.bybit_rest_client import BybitRestClient
import os
from dotenv import load_dotenv
load_dotenv()
client = BybitRestClient(testnet=False)
balance = client.get_wallet_balance()
print(f'✅ Mainnet API 연결 성공: {balance}')
"
```

### 1.3 초기 자금 확인

```bash
# Mainnet 계좌 잔고 확인
python scripts/check_balance.py
# → $100 이상 (최소 운영 자금)
```

---

## 2. 실행 방법

### 2.1 수동 실행 (1회성 테스트)

**용도**: 짧은 시간 동안 작동 확인 (30분 ~ 1시간)

```bash
# 가상환경 활성화
source venv/bin/activate

# Mainnet 실거래 시작 (3 거래 목표, 테스트)
python scripts/run_mainnet_dry_run.py --target-trades 3

# 또는 시간 제한 (1시간)
timeout 3600 python scripts/run_mainnet_dry_run.py --target-trades 100
```

**장점**:
- 즉시 시작 가능
- 터미널에서 직접 로그 확인

**단점**:
- 터미널 종료 시 프로세스 종료
- SSH 연결 끊김 시 중단
- 장기 운영 불가

---

### 2.2 Background 실행 (screen/tmux)

**용도**: SSH 연결과 무관하게 지속 실행 (수일 ~ 수주)

#### Option A: screen 사용

```bash
# (1) screen 세션 시작
screen -S cbgb_mainnet

# (2) 가상환경 활성화
source venv/bin/activate

# (3) Mainnet 실거래 시작 (무제한)
python scripts/run_mainnet_dry_run.py --target-trades 1000

# (4) Detach (Ctrl+A, D)
# → screen 세션 백그라운드 실행 유지

# (5) 재접속
screen -r cbgb_mainnet

# (6) 세션 종료
screen -X -S cbgb_mainnet quit
```

#### Option B: tmux 사용

```bash
# (1) tmux 세션 시작
tmux new -s cbgb_mainnet

# (2) 가상환경 활성화 + 실행
source venv/bin/activate
python scripts/run_mainnet_dry_run.py --target-trades 1000

# (3) Detach (Ctrl+B, D)

# (4) 재접속
tmux attach -t cbgb_mainnet

# (5) 세션 종료
tmux kill-session -t cbgb_mainnet
```

#### Option C: nohup (간단한 방법)

```bash
# 백그라운드 실행 + 로그 파일 저장
nohup python scripts/run_mainnet_dry_run.py --target-trades 1000 > logs/mainnet_production.log 2>&1 &

# PID 확인
echo $!
# → 12345

# 로그 모니터링
tail -f logs/mainnet_production.log

# 프로세스 종료
kill 12345
```

**장점**:
- SSH 연결 끊김에도 계속 실행
- 로그 파일로 나중에 확인 가능

**단점**:
- 서버 재부팅 시 자동 재시작 안 됨
- 수동으로 관리해야 함

---

### 2.3 systemd 서비스 (자동 시작/재시작)

**용도**: Production 환경에서 영구 실행 (자동 재시작, 부팅 시 자동 시작)

#### (1) systemd 서비스 파일 생성

```bash
sudo nano /etc/systemd/system/cbgb-mainnet.service
```

**내용**:
```ini
[Unit]
Description=CBGB Mainnet Trading Bot
After=network.target

[Service]
Type=simple
User=selios
WorkingDirectory=/home/selios/dg_bybit
Environment="PATH=/home/selios/dg_bybit/venv/bin:/usr/bin"
ExecStart=/home/selios/dg_bybit/venv/bin/python scripts/run_mainnet_dry_run.py --target-trades 10000
Restart=on-failure
RestartSec=10
StandardOutput=append:/home/selios/dg_bybit/logs/mainnet_production.log
StandardError=append:/home/selios/dg_bybit/logs/mainnet_production_error.log

[Install]
WantedBy=multi-user.target
```

#### (2) 서비스 활성화 및 시작

```bash
# 서비스 파일 리로드
sudo systemctl daemon-reload

# 서비스 활성화 (부팅 시 자동 시작)
sudo systemctl enable cbgb-mainnet

# 서비스 시작
sudo systemctl start cbgb-mainnet

# 상태 확인
sudo systemctl status cbgb-mainnet

# 로그 확인
sudo journalctl -u cbgb-mainnet -f
# 또는
tail -f logs/mainnet_production.log
```

#### (3) 서비스 관리 명령어

```bash
# 중지
sudo systemctl stop cbgb-mainnet

# 재시작
sudo systemctl restart cbgb-mainnet

# 비활성화 (부팅 시 자동 시작 중지)
sudo systemctl disable cbgb-mainnet

# 서비스 제거
sudo systemctl stop cbgb-mainnet
sudo systemctl disable cbgb-mainnet
sudo rm /etc/systemd/system/cbgb-mainnet.service
sudo systemctl daemon-reload
```

**장점**:
- 서버 재부팅 시 자동 재시작
- Crash 시 자동 재시작 (Restart=on-failure)
- systemd 통합 (표준 리눅스 관리)

**단점**:
- 초기 설정 복잡
- sudo 권한 필요

---

### 2.4 Docker 컨테이너 (격리 + 이식성)

**용도**: 다른 환경에서도 동일하게 실행 (로컬 → 클라우드 이전 등)

#### (1) Dockerfile 생성

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 코드 복사
COPY . .

# 가상환경 없이 직접 실행
CMD ["python", "scripts/run_mainnet_dry_run.py", "--target-trades", "10000"]
```

#### (2) Docker 이미지 빌드 및 실행

```bash
# 이미지 빌드
docker build -t cbgb-mainnet .

# 컨테이너 실행 (.env 파일 마운트)
docker run -d \
  --name cbgb-mainnet \
  --env-file .env \
  -v $(pwd)/logs:/app/logs \
  cbgb-mainnet

# 로그 확인
docker logs -f cbgb-mainnet

# 컨테이너 중지
docker stop cbgb-mainnet

# 컨테이너 제거
docker rm cbgb-mainnet
```

**장점**:
- 환경 격리 (의존성 충돌 없음)
- 이식성 (어디서나 동일하게 실행)
- docker-compose로 다중 인스턴스 관리 가능

**단점**:
- Docker 설정 필요
- 리소스 오버헤드 (경미)

---

## 3. 스케줄링 전략

### 3.1 24/7 운영 (권장)

**방법**: systemd 서비스 또는 screen/tmux

**장점**:
- Grid 전략 특성상 가격 변동 시 즉시 대응
- Entry 기회 놓치지 않음

**단점**:
- 서버 비용 (항상 켜져 있어야 함)
- 모니터링 필요

### 3.2 시간대별 운영 (선택)

**방법**: cron으로 특정 시간에만 실행

**예시**: 변동성 높은 시간대만 운영 (UTC 00:00-08:00, 한국 시간 09:00-17:00)

```bash
# crontab 편집
crontab -e
```

**내용**:
```cron
# 매일 09:00 시작 (한국 시간)
0 9 * * * cd /home/selios/dg_bybit && source venv/bin/activate && python scripts/run_mainnet_dry_run.py --target-trades 50 > logs/cron_$(date +\%Y\%m\%d).log 2>&1

# 매일 17:00 종료 (kill script)
0 17 * * * pkill -f "run_mainnet_dry_run.py"
```

**장점**:
- 서버 비용 절감
- 특정 시간대 집중 운영

**단점**:
- 24시간 기회 놓침
- Grid 전략 특성상 비효율적 (가격은 24시간 움직임)

---

## 4. 모니터링

### 4.1 로그 모니터링

```bash
# 실시간 로그 확인 (systemd)
sudo journalctl -u cbgb-mainnet -f

# 실시간 로그 확인 (파일)
tail -f logs/mainnet_production.log

# 에러만 확인
grep "ERROR" logs/mainnet_production.log

# HALT 이벤트 확인
grep "HALT" logs/mainnet_production.log
```

### 4.2 Telegram 알림

**자동 알림 (이미 구현됨)**:
- Entry/Exit 거래
- HALT 발생 (Session Risk, Emergency)
- Daily Summary

**설정 확인**:
```bash
cat .env | grep TELEGRAM
# → TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 확인
```

### 4.3 거래 로그 확인

```bash
# 오늘 거래 수 확인
wc -l logs/mainnet_dry_run/trades_$(date +%Y-%m-%d).jsonl

# 최근 10개 거래 확인
tail -10 logs/mainnet_dry_run/trades_$(date +%Y-%m-%d).jsonl | jq .

# Total PnL 계산 (jq 필요)
cat logs/mainnet_dry_run/trades_*.jsonl | jq -s 'map(.pnl) | add'
```

### 4.4 Health Check Script

**scripts/health_check.py** (새로 작성 권장):
```python
#!/usr/bin/env python3
"""Health check script for production monitoring"""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

def check_process_running():
    """봇 프로세스 실행 중인지 확인"""
    result = os.system("pgrep -f 'run_mainnet_dry_run.py' > /dev/null")
    return result == 0

def check_recent_log():
    """최근 1분 이내 로그 있는지 확인"""
    log_file = Path("logs/mainnet_production.log")
    if not log_file.exists():
        return False

    mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
    return datetime.now() - mtime < timedelta(minutes=1)

def check_halt_status():
    """HALT 상태 확인"""
    result = os.system("tail -100 logs/mainnet_production.log | grep -q 'State.HALT'")
    return result == 0  # True면 HALT 상태 (위험)

if __name__ == "__main__":
    checks = {
        "Process Running": check_process_running(),
        "Recent Log": check_recent_log(),
        "HALT Status": not check_halt_status()  # HALT 없어야 정상
    }

    all_ok = all(checks.values())

    for name, status in checks.items():
        symbol = "✅" if status else "❌"
        print(f"{symbol} {name}: {'OK' if status else 'FAIL'}")

    sys.exit(0 if all_ok else 1)
```

**cron으로 5분마다 Health Check**:
```cron
*/5 * * * * cd /home/selios/dg_bybit && python scripts/health_check.py || echo "⚠️ CBGB Health Check FAIL" | mail -s "CBGB Alert" your-email@example.com
```

---

## 5. 안전 정지 및 재시작

### 5.1 안전 정지 (Graceful Shutdown)

**방법 1: Ctrl+C (터미널 실행 중)**
- Ctrl+C 누르면 현재 tick 완료 후 종료 (구현 필요)

**방법 2: systemd**
```bash
sudo systemctl stop cbgb-mainnet
# → systemd가 SIGTERM 전송, 프로세스가 정상 종료
```

**방법 3: kill signal**
```bash
# PID 확인
ps aux | grep run_mainnet_dry_run.py

# Graceful shutdown (SIGTERM)
kill -15 <PID>

# 강제 종료 (최후의 수단, SIGKILL)
kill -9 <PID>
```

### 5.2 긴급 정지 (Emergency Stop)

**상황**: HALT 상태 발생, 즉시 거래 중단 필요

```bash
# (1) 프로세스 즉시 종료
pkill -9 -f "run_mainnet_dry_run.py"

# (2) Bybit 계좌 확인 (수동)
python -c "
from src.infrastructure.exchange.bybit_rest_client import BybitRestClient
client = BybitRestClient(testnet=False)
position = client.get_position('BTCUSDT')
print(f'Current Position: {position}')
"

# (3) 포지션 있으면 수동 청산
# Bybit Web UI 또는 REST API로 수동 청산
```

### 5.3 재시작

```bash
# systemd 사용 시
sudo systemctl restart cbgb-mainnet

# screen 사용 시
screen -r cbgb_mainnet
# Ctrl+C로 종료
python scripts/run_mainnet_dry_run.py --target-trades 1000
# Ctrl+A, D로 detach

# nohup 사용 시
pkill -f "run_mainnet_dry_run.py"
nohup python scripts/run_mainnet_dry_run.py --target-trades 1000 > logs/mainnet_production.log 2>&1 &
```

---

## 6. 추천 Production 설정

### 6.1 초기 운영 (Phase 12c 직후, 1-2주)

**목적**: Production 환경 안정성 검증

**설정**:
- **실행 방법**: screen + nohup (간단함)
- **목표 거래**: 100-200 거래
- **모니터링**: Telegram + 로그 수동 확인 (1일 1회)
- **Health Check**: 수동 (1일 1-2회)

**커맨드**:
```bash
screen -S cbgb_mainnet
source venv/bin/activate
nohup python scripts/run_mainnet_dry_run.py --target-trades 200 > logs/mainnet_production.log 2>&1 &
# Ctrl+A, D
```

### 6.2 안정 운영 (1-2주 후, 장기)

**목적**: 24/7 무인 운영

**설정**:
- **실행 방법**: systemd 서비스 (자동 재시작)
- **목표 거래**: 무제한 (--target-trades 10000 이상)
- **모니터링**: Telegram + Health Check (cron 5분마다)
- **알림**: HALT 발생 시 즉시 알림 (Telegram + Email)

**설정 파일**: `/etc/systemd/system/cbgb-mainnet.service` (위 2.3 참조)

---

## 7. 트러블슈팅

### 7.1 봇이 거래를 하지 않음

**원인**:
- Grid spacing 조건 미충족 (가격이 Grid 범위 내)
- Entry Gates 차단 (COOLDOWN, max_trades_per_day 등)
- HALT 상태

**확인**:
```bash
# (1) 현재 State 확인
tail -50 logs/mainnet_production.log | grep "State\."

# (2) Grid spacing 확인
tail -50 logs/mainnet_production.log | grep "grid_spacing"

# (3) Entry blocked 이유 확인
tail -50 logs/mainnet_production.log | grep "entry_blocked"
```

### 7.2 HALT 발생

**원인**:
- Session Risk (Daily/Weekly Loss Cap 초과)
- Emergency (Balance 0, Latency 5s 초과 등)

**대응**:
```bash
# (1) HALT 이유 확인
grep "HALT" logs/mainnet_production.log | tail -5

# (2) Session Risk 초과 시 → 다음날까지 대기
# (3) Emergency 시 → 원인 해결 후 재시작
```

### 7.3 WebSocket 연결 끊김

**증상**: "WS connection lost" 로그 반복

**대응**:
```bash
# (1) 네트워크 확인
ping api.bybit.com

# (2) 봇 재시작
sudo systemctl restart cbgb-mainnet

# (3) 지속되면 Bybit API 상태 확인
# https://bybit-exchange.github.io/docs/v5/ws/connect
```

---

## 8. Production 체크리스트

**배포 전**:
- [ ] pytest 335 passed
- [ ] Force Entry 0개
- [ ] Debug 로깅 0개
- [ ] .env Mainnet 모드 확인
- [ ] API 키 유효성 확인
- [ ] 초기 자금 $100 이상

**실행 설정**:
- [ ] 실행 방법 선택 (screen/systemd/docker)
- [ ] 로그 디렉토리 생성 (`mkdir -p logs/mainnet_dry_run`)
- [ ] Telegram 설정 확인

**모니터링**:
- [ ] Telegram 알림 동작 확인
- [ ] Health Check 설정 (선택)
- [ ] 로그 모니터링 방법 확인

**안전망**:
- [ ] 긴급 정지 방법 숙지
- [ ] Bybit Web UI 접근 가능 확인
- [ ] 수동 청산 방법 숙지

---

**End of Production Deployment Guide**
