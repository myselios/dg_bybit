# 🤖 CBGB 봇 모니터링 & 관리 가이드

## 📊 현재 상태

### 실행 중인 서비스
- **cbgb-bot** - 트레이딩 봇 (24/7)
- **cbgb-dashboard** - 대시보드 (http://localhost:8501)
- **cbgb-analysis** - 분석 서비스
- **monitor.sh** - 에러 감시 & 자동 재시작 (PID: 60331)

### 위치
```
/Users/ria_home/.openclaw/workspace/dg_bybit/
```

---

## 🔍 모니터링

### 1. 실시간 로그 확인
```bash
cd ~/.openclaw/workspace/dg_bybit

# 봇 로그
docker logs -f cbgb-bot

# 대시보드 로그
docker logs -f cbgb-dashboard

# 분석 로그
docker logs -f cbgb-analysis

# 모니터 로그
tail -f monitor.log
```

### 2. 상태 확인
```bash
# 컨테이너 상태
docker-compose ps

# 모니터 프로세스 확인
ps aux | grep monitor.sh
```

### 3. 대시보드 접속
브라우저에서: http://localhost:8501

---

## 🚨 자동 알림

**텔레그램으로 자동 알림:**
- ❌ 컨테이너 다운 → 자동 재시작 시도
- 🚨 ERROR/EXCEPTION 로그 발견
- ⚠️ 청산 위험 감지
- 🛑 Stop Loss 실행

---

## 🔧 수동 관리

### 컨테이너 재시작
```bash
cd ~/.openclaw/workspace/dg_bybit

# 모든 컨테이너
docker-compose restart

# 특정 컨테이너만
docker-compose restart cbgb-bot
docker-compose restart cbgb-dashboard
docker-compose restart cbgb-analysis
```

### 컨테이너 중지/시작
```bash
# 중지
docker-compose down

# 시작
docker-compose up -d
```

### 로그 삭제
```bash
# 모든 로그 삭제
docker-compose down -v

# 다시 시작
docker-compose up -d
```

---

## 🔄 코드 수정 & 재배포

### 자동 재배포 (추천!)
```bash
cd ~/.openclaw/workspace/dg_bybit
./redeploy.sh
```

**자동 진행:**
1. Git pull (최신 코드 받기)
2. Docker 이미지 재빌드
3. 컨테이너 재시작
4. 텔레그램 알림

### 수동 재배포
```bash
cd ~/.openclaw/workspace/dg_bybit

# 1. Git pull
git pull origin main

# 2. Base 이미지 재빌드
docker build -t cbgb:production -f docker/Dockerfile.base .

# 3. 서비스 재빌드
docker-compose build

# 4. 재시작
docker-compose down
docker-compose up -d
```

---

## 🛑 모니터 관리

### 모니터 중지
```bash
# PID 확인
ps aux | grep monitor.sh

# 종료
kill 60331  # PID 번호 사용
```

### 모니터 재시작
```bash
cd ~/.openclaw/workspace/dg_bybit
nohup ./monitor.sh > monitor.nohup.log 2>&1 &
```

---

## 📝 로그 파일 위치

```
~/.openclaw/workspace/dg_bybit/
├── monitor.log         # 모니터 로그
├── monitor.nohup.log   # 모니터 백그라운드 로그
└── logs/              # Docker volume (컨테이너 로그)
```

---

## ⚡ 빠른 명령어

```bash
# 현재 디렉토리로 이동
cd ~/.openclaw/workspace/dg_bybit

# 상태 확인
docker-compose ps

# 봇 로그 확인 (최근 50줄)
docker logs cbgb-bot --tail 50

# 재시작
docker-compose restart cbgb-bot

# 재배포
./redeploy.sh

# 대시보드 열기
open http://localhost:8501
```

---

## 🆘 문제 해결

### 컨테이너가 계속 죽는 경우
```bash
# 로그 확인
docker logs cbgb-bot

# .env 파일 확인
cat .env

# 완전 재시작
docker-compose down
docker system prune -f
docker-compose up -d
```

### API 에러
```bash
# .env 파일의 API 키 확인
cat .env | grep API

# Testnet/Mainnet 모드 확인
cat .env | grep TESTNET
```

### 포트 충돌 (8501)
```bash
# 포트 사용 확인
lsof -i :8501

# 프로세스 종료
kill -9 <PID>
```

---

## 📞 연락처

**텔레그램:** 맹수 구찌 (id: 2128418205)

모든 에러/알림은 자동으로 텔레그램으로 전송됩니다!
