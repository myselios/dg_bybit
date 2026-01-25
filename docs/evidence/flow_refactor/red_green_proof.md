# FLOW.md v1.11 Refactoring — RED→GREEN 증거

## 목표 (DoD)

ADR-0009에서 정의한 SSOT 중복 제거:
1. Section 10.2 중복 제거: 38개 → 1개
2. Stop Loss 정의 통합: Section 4.5를 SSOT로 지정
3. 문서 크기 감소: 5401줄 → ~2600줄
4. 버전 업데이트: v1.10 → v1.11

---

## RED 상태 (Before — v1.10)

### (1) Section 10.2 중복
```bash
$ grep -c "### 10.2 Document-First Workflow" docs/constitution/FLOW.md.v1.10.bak
38
```

**문제**: Section 10.2가 38번 반복 → 유지보수 부담

### (2) 문서 크기
```bash
$ wc -l docs/constitution/FLOW.md.v1.10.bak
5401 docs/constitution/FLOW.md.v1.10.bak
```

**문제**: 5401줄 (Section 10.2 중복으로 인한 bloat)

### (3) Stop Loss 참조 오류
```bash
$ grep -n "Section 2.5 Stop Loss 갱신 규칙 참조" docs/constitution/FLOW.md.v1.10.bak
3453:**자세한 내용은 Section 2.5 Stop Loss 갱신 규칙 참조**
```

**문제**: "Section 2.5"는 "Execution Events"이므로 잘못된 참조

### (4) Stop Loss 규칙 중복
원본 FLOW.md의 1036번 줄과 3369번 줄에 Stop Loss 정의 분산:
- 1036: "Stop Loss 갱신 규칙" (Amend 우선, 20% threshold, 2s debounce)
- 3369: "4.5 Stop Loss 주문 계약" (Bybit API 파라미터)
- 3459-3462: **중복**: Amend/Threshold/Debounce 다시 정의

---

## GREEN 상태 (After — v1.11)

### (1) Section 10.2 단일화 ✅
```bash
$ grep -c "### 10.2 Document-First Workflow" docs/constitution/FLOW.md
1
```

**결과**: 38개 → 1개 (마지막 1개만 유지)

### (2) 문서 크기 감소 ✅
```bash
$ wc -l docs/constitution/FLOW.md
2635 docs/constitution/FLOW.md
```

**결과**: 5401줄 → 2635줄 (51.2% 감소, 2766줄 제거)

### (3) Stop Loss 참조 정정 ✅
```bash
$ grep -n "Stop Loss 갱신 규칙" docs/constitution/FLOW.md | grep "참조"
1578:**⚠️ 갱신 정책은 본 문서 상단의 "Stop Loss 갱신 규칙 (Rate Limit 방지)" 섹션 참조**
1589:- **Amend 우선, Threshold, Debounce**: 상단 "Stop Loss 갱신 규칙" 섹션 참조
```

**결과**: 참조 경로 명확화 ("Section 2.5" 제거, 정확한 섹션 제목으로 대체)

### (4) Section 4.5 SSOT 표기 추가 ✅
```bash
$ grep -n "⚠️ SSOT" docs/constitution/FLOW.md
1496:**⚠️ SSOT: Stop Loss 주문 계약 정의 (API 파라미터)**
```

**결과**: Section 4.5가 Stop Loss 주문 계약의 SSOT임을 명시

### (5) Stop Loss 규칙 중복 제거 ✅
```bash
$ grep -A5 "핵심 요구사항" docs/constitution/FLOW.md | head -8
**핵심 요구사항**:
- **Stop 필수 감시**: IN_POSITION일 때 stop_status 확인, MISSING → 즉시 복구, 3회 실패 → HALT
- **Amend 우선, Threshold, Debounce**: 상단 "Stop Loss 갱신 규칙" 섹션 참조
```

**결과**: Amend/Threshold/Debounce 상세 내용 삭제, 참조로 대체 (SSOT 준수)

### (6) 버전 업데이트 ✅
```bash
$ grep "현재 버전" docs/constitution/FLOW.md
**현재 버전**: FLOW v1.11 (2026-01-25)
```

**결과**: v1.10 → v1.11 업데이트

### (7) Change History 추가 ✅
```bash
$ grep -A6 "v1.11" docs/constitution/FLOW.md | head -8
- v1.11 (2026-01-25): SSOT 중복 제거 (문서 정리 + Stop Loss 참조 정렬) (ADR-0009)
  - **Section 10.2 중복 제거**: 38개 → 1개 (문서 크기 51.4% 감소, 5401줄 → 2626줄)
  - **Stop Loss 정의 통합**: Section 4.5를 SSOT로 지정 (주문 계약), 갱신 정책은 "Stop Loss 갱신 규칙" 섹션 참조로 정리
  - **Section 4.5 SSOT 표기 추가**: "⚠️ SSOT: Stop Loss 주문 계약 정의 (API 파라미터)"
  - **Stop 관리 규칙 정리**: Amend/Threshold/Debounce 중복 제거, 상단 섹션 참조로 대체
  - 실거래 영향: 없음 (문서 정리만, 로직 변경 없음)
  - 참조: ADR-0009
```

**결과**: ADR-0009 참조 포함, 변경 사항 명확히 기록

---

## 검증 명령어 (재현 가능)

```bash
# (1) Section 10.2 개수
grep -c "### 10.2 Document-First Workflow" docs/constitution/FLOW.md
# 기대 출력: 1

# (2) 문서 라인 수
wc -l docs/constitution/FLOW.md
# 기대 출력: 2635 docs/constitution/FLOW.md

# (3) Section 4.5 SSOT 표기
grep "⚠️ SSOT" docs/constitution/FLOW.md
# 기대 출력: **⚠️ SSOT: Stop Loss 주문 계약 정의 (API 파라미터)**

# (4) Stop 관리 규칙 참조
grep -A2 "Stop 관리 규칙" docs/constitution/FLOW.md | grep "갱신 규칙"
# 기대 출력: **⚠️ 갱신 정책은 본 문서 상단의 "Stop Loss 갱신 규칙 (Rate Limit 방지)" 섹션 참조**

# (5) 버전 확인
grep "현재 버전" docs/constitution/FLOW.md
# 기대 출력: **현재 버전**: FLOW v1.11 (2026-01-25)

# (6) ADR-0009 참조
grep "ADR-0009" docs/constitution/FLOW.md
# 기대 출력: - v1.11 (2026-01-25): ... (ADR-0009)
#           - 참조: ADR-0009
```

---

## 결론

**✅ PASS**: 모든 DoD 달성
- Section 10.2 중복 제거 완료 (38 → 1)
- 문서 크기 51.2% 감소 (5401 → 2635)
- Stop Loss SSOT 정렬 완료 (Section 4.5 + 참조)
- 버전 v1.11로 업데이트
- ADR-0009 참조 추가

**실거래 영향**: 없음 (문서 정리만, 로직 변경 없음)
