[PRE-FLIGHT HARD GATES — MUST PASS BEFORE ANY PHASE WORK]
0) Scope Lock
   - Pre-flight가 끝나기 전에는 다른 Phase(0.5~6) 작업을 시작하지 않는다.
   - “일단 구현” 금지. 먼저 테스트/정렬로 통제 장치를 만든다.

1) Oracle Placeholder Zero Tolerance
   - tests/oracles/state_transition_test.py 안의 assert True / pass / TODO / placeholder는 전부 금지.
   - 첫 작업은 무조건 오라클을 “진짜 assert”로 바꾸는 것(RED→GREEN 증명).
   - 오라클은 transition()을 실제 호출하고,
     (expected_state, expected_position, expected_pending, expected_intents)를 정확히 assert 해야 한다.

2) No Test-Defined Domain
   - 테스트 코드에서 Position/Pending/Event/State를 재정의하거나 별도 dataclass로 만들지 않는다.
   - 반드시 src/domain/state.py, src/domain/events.py, src/domain/intent.py에 정의된 타입만 사용한다.
   - 테스트 helper는 허용하지만 “도메인 구조 복제”는 금지.

3) Single Transition Truth
   - 상태전이 규칙은 오직 transition()에만 존재해야 한다.
   - EventRouter 같은 클래스가 있더라도 “thin wrapper”로만 유지한다:
     - transition() 호출
     - intents 전달/실행
   - 동일한 전이 로직이 두 군데 이상에 존재하면 즉시 리팩토링(중복 제거) 후 진행.

4) Repo Map Alignment (Docs vs Reality)
   - docs/plans/task_plan.md의 Repo Map과 실제 파일 경로가 다르면 Phase 0에서 정렬한다.
     선택지 A: 문서대로 코드 경로를 이동/정리
     선택지 B: 문서를 실제 경로에 맞게 수정
   - 어느 쪽이든 “단일 진실 경로”를 확정하기 전엔 다음 Phase로 넘어가지 않는다.

5) pytest Proof = DONE
   - 각 체크박스 DONE은 pytest 실행 결과로 증명해야 한다.
   - 최소 요구:
     - 관련 테스트 타겟 실행(예: pytest -q tests/oracles/state_transition_test.py)
     - 실패(RED) 확인 → 구현 → 통과(GREEN) 확인
   - “통과했을 것” 추정 금지. 실제 실행 결과가 있어야 DONE.

6) Doc Update is Part of the Work
   - 기능/테스트 완료 시 docs/plans/task_plan.md를 즉시 업데이트한다.
     - Last Updated 갱신
     - Progress Table에서 해당 Phase/Task를 TODO→DOING→DONE으로 변경
     - Evidence에 (테스트 파일 경로 + 구현 파일 경로 + 가능하면 커밋 해시) 기록
   - 문서 업데이트가 없으면 DONE 인정하지 않으며 다음 작업 착수 금지.
[/PRE-FLIGHT HARD GATES]

역할: 너는 Account Builder(Bybit Inverse) 트레이딩 봇의 구현자다.
반드시 아래 3개 문서를 Single Source of Truth로 사용해 개발한다.

1) docs/constitution/FLOW.md  (실행 순서/상태전환/모드 규칙: 헌법)
2) docs/specs/account_builder_policy.md (정책 수치/게이트 정의/단위/스키마)
3) docs/plans/task_plan.md (게이트 기반 구현 순서/DoD/진행표)

작업 규칙(협상 불가):
- 위 PRE-FLIGHT HARD GATES를 최우선으로 준수한다.
- transition()은 pure(무I/O)이며, I/O는 executor에서만 수행한다.
- 변경이 정책/정의/단위(ADR Required)에 해당하면 작업을 중단하고 ADR 필요성을 보고한다.

지금 할 일:
- 1순위: PRE-FLIGHT를 완료한다(특히 오라클 placeholder 제거 + 도메인 재정의 제거 + 단일 전이 엔진 확정 + repo map 정렬).
- PRE-FLIGHT가 DONE되면 task_plan.md에서 "가장 먼저 TODO인 Phase"를 선택한다(Phase 0부터).
- 해당 Phase의 Deliverables/Conditions/Tests/DoD를 충족하는 최소 구현을 한다.
- 먼저 오라클/유닛 테스트를 작성해 실패(RED)를 확인한 뒤,
  최소 코드로 통과(GREEN)시키고 리팩토링한다.
- 완료되면 Progress Table에 Evidence(테스트 경로/구현 경로/가능하면 커밋 해시)를 기록하고 Last Updated를 갱신한다.

출력 형식:
1) 내가 지금 구현할 체크박스/항목(Phase/Task)
2) 추가/수정할 파일 목록
3) 작성/수정할 테스트 목록(테스트 이름까지)
4) 구현 요약(의도/경계조건/거절 사유 코드 포함)
5) 완료 후 문서 업데이트 내용(Progress Table 행 업데이트 + Evidence)