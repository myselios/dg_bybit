Docker 이미지를 리빌드하고 봇을 재배포한다.

순서:
1. `pytest -q` — 테스트 통과 확인 (실패 시 중단)
2. `docker build --no-cache -f docker/Dockerfile.base --target production -t cbgb:production .`
3. `docker compose build --no-cache bot`
4. `docker compose up -d bot`
5. 30초 대기 후 `docker ps` + `docker logs cbgb-bot --tail 10` — 상태 확인
6. healthy 확인 후 완료 보고

**주의**: 반드시 사용자 확인 후 실행. 라이브 트레이딩 중단 위험.
