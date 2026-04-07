# Phase 3 — FabriX Multi-MCP Provider 확장 계획 (Part 1 초안)

**적용 범위 명시**

- 이 Phase 3 계획은 **FabriX Chat 앱** 수정 계획이다.
- **FabriX Agent Chat 앱은 범위 밖** 이다.
- FabriX Agent Chat은 이미 FabriX 서버에 구현되어 있는 문서검색 MCP를 호출하는 채팅으로 간주하며, 이번 Phase 3에서 **별도의 MCP 기능 구현 또는 추가 계획이 없다.**

**이 문서의 현재 범위**

- 이번 문서는 **운영모드 / Test Mode 모두에서 multi-MCP provider 를 고려한 확장 계획**만 먼저 정리한다.
- 나머지 세부 기능 계획, 세부 UI/운영 정책, 개별 provider 온보딩 시나리오는 **다음 작성 단계에서 추가**한다.
- 따라서 이 문서는 긴 Phase 1 / Phase 2 문서의 뒤를 잇는 **Phase 3 Part 1 companion 초안**으로 본다.

---

## 1. Phase 3의 한 줄 정의

Phase 3은 **Phase 1에서 만든 generic MCP host core** 와 **Phase 2에서 만든 runtime strategy / Test Mode 구조**를 기반으로,  
FabriX Chat이 **운영모드와 Test Mode 모두에서 여러 MCP provider를 구조적으로 수용**할 수 있게 확장하는 단계다.

중요한 점은, 이것이 단순히 provider 개수를 늘리는 작업이 아니라:

1. **host core를 다시 뒤집지 않고**
2. **provider-specific 임시 분기를 chat core에 재도입하지 않으며**
3. **Normal/Test 두 모드가 같은 multi-provider host core를 공유**

하도록 만드는 구조 확장이라는 점이다.

---

## 2. Phase 3가 필요한 이유

Phase 1의 핵심 성과는 다음이었다.

- FabriX Chat을 특정 doc-search 전용 하드코딩 경로에서 분리하고
- generic MCP host core / provider adapter / registry / intent router 구조로 전환하고
- `/mcp` 와 `@파일명` 을 **host core 위의 UX adapter** 로 재배치한 것이다.

Phase 2의 핵심 성과는 다음이었다.

- Normal Mode와 Test Mode를 **runtime strategy** 로 분리하고
- **외부 LLM 호출만 우회**하면서도 MCP 연결/호출은 실제 경로를 유지하고
- system log / persistence / inline band UI를 도입해 오프라인 검증 경로를 확보한 것이다.

이제 Phase 3에서는 다음 질문에 답해야 한다.

1. provider가 하나가 아니라 여러 개일 때도 **같은 host core** 로 운영 가능한가?
2. Normal/Test 모두에서 provider 선택, capability inventory, tool invocation, context merge가 **일관되게 유지**되는가?
3. 첫 provider(`internal_docs`) 기준으로 굳어진 가정이 있다면, 그것을 어디까지 일반화해야 하는가?

---

## 3. Phase 3의 목표 상태

Phase 3 완료 후 FabriX Chat은 아래 상태여야 한다.

1. **여러 MCP provider를 registry/config 수준에서 등록**할 수 있다.
2. 각 provider는 local / remote / transport 종류 차이와 관계없이 **공통 host contract** 아래에서 다뤄진다.
3. Normal Mode와 Test Mode는 **동일한 multi-provider host core** 를 공유한다.
4. Test Mode는 여전히 **실제 provider 연결/호출을 사용**하고, 외부 LLM completion만 우회한다.
5. `/mcp` 같은 수동 경로와 자연어 기반 경로가 모두 **같은 multi-provider abstraction** 위에서 동작한다.
6. provider-specific tool 이름, 응답 shape, 정책 차이는 **adapter / normalizer / provider policy 층** 으로 국소화된다.
7. provider가 늘어나도 chat router / UI / persistence model을 다시 뒤집지 않아도 된다.

---

## 4. 이번 Part 1에서 명확히 고정할 방향

이번 문서에서는 아래 방향만 먼저 고정한다.

### 4.1 운영모드 / Test Mode 공통 원칙

- provider 수가 늘어나도 **runtime 차이는 오직 “누가 tool decision을 하느냐 / 외부 LLM completion을 호출하느냐”** 에만 남겨야 한다.
- provider registry, session lifecycle, capability discovery, tool/resource/prompt invocation, result normalization, context merge는 **두 모드가 공유**해야 한다.
- Test Mode라고 해서 **provider 호출 자체를 mock 처리하면 안 된다.**
- 운영모드에서만 가능한 특수 path, Test Mode에서만 가능한 특수 provider path를 따로 만들면 안 된다.

### 4.2 multi-provider 구조의 기본 방향

- provider는 `internal_docs` 하나만 고정 전제하지 않는다.
- 각 provider는 최소한 아래 식별자를 가져야 한다.
  - `provider_id`
  - `display_name`
  - `transport_type`
  - `origin_type` (local / remote / builtin 등)
  - `enabled`
  - `policy flags`
- host core는 “현재 provider가 누구인가”를 알아야 하지만,  
  **개별 provider의 세부 tool 이름과 응답 특수성은 직접 알지 않도록** 유지해야 한다.

### 4.3 자연어 경로 / 수동 경로 공존 방향

- `/mcp` 는 계속 **manual override / debugging / power-user UX** 로 남길 수 있다.
- 그러나 host core는 `/mcp` 명령 체계에 종속되면 안 된다.
- 기본 경로는 계속 **자연어 → intent/provider selection → host core → LLM/Test runtime** 구조를 유지한다.
- `@파일명` 류의 기존 UX 계약이 provider 개수 증가 때문에 깨져서는 안 된다.

### 4.4 공용 질문 의도 판별 계층 통합

- 현재 상태에서 **운영 모드의 자연어 라우팅**과 **Test Mode의 deterministic planner** 는 서로 다른 코드 파일/규칙으로 존재한다.
- 이 분리는 Phase 2까지는 허용되었지만, Phase 3의 multi-provider 확장에서는 **구조적 위험요소**로 간주해야 한다.
- 법률/판례 검색 MCP 같은 신규 provider가 추가되면,  
  같은 사용자 질문이 운영 모드와 Test Mode에서 서로 다른 provider/action으로 분류되는 문제가 생기기 쉽다.
- 따라서 Phase 3에서는 **공용 질문 의도 판별 계층(shared intent planner / provider-selection layer)** 을 도입해야 한다.
- 이 공용 계층은 최소한 아래 책임을 가져야 한다.
  - 자연어 질의의 의도 분류
  - provider 선택
  - provider 내부 action 선택
  - manual `/mcp` / `@파일명` 같은 UX adapter와의 경계 유지
- 운영 모드와 Test Mode는 이 공용 계층을 공유하되,  
  **차이는 “누가 tool decision을 최종 집행하고 외부 LLM completion을 호출하느냐”** 에만 남겨야 한다.

---

## 5. Phase 1, 2에서 특히 지키려고 했던 개발 원칙 정리

이 항목은 Phase 3에서 **절대 깨뜨리면 안 되는 원칙 목록**이다.

### 5.1 계층/구조 원칙

1. **generic host core 와 FabriX UX adapter 를 분리한다**
   - `/mcp`, `@파일명`, chat UI, system band는 host core 그 자체가 아니다.
   - UI/명령 체계는 host capability를 드러내는 adapter여야 한다.

2. **provider-specific logic 는 provider adapter 내부로 국소화한다**
   - tool 이름
   - 입력 인자 shape 차이
   - 응답 shape 차이
   - provider별 validation/policy
   는 chat core나 router에 퍼지면 안 된다.

3. **Normal Mode / Test Mode 는 같은 host core 를 공유한다**
   - Test Mode는 host 아래가 아니라 host 위 runtime strategy 층이다.
   - mock은 LLM decision / completion까지만 허용한다.

4. **legacy 구현을 영구 compatibility shim 으로 남기지 않는다**
   - 사용자 계약은 유지하되
   - 내부 구현은 새 구조로 완전히 cutover 해야 한다.

### 5.2 데이터/계약 원칙

1. **tool/resource/prompt 결과는 정규화 후 사용한다**
   - provider raw 결과를 chat layer가 직접 소비하지 않는다.

2. **system message 는 LLM `contents` 를 오염시키지 않는다**
   - system log는 persistence/display 용이지, upstream LLM 입력용 대화 내용이 아니다.

3. **settings ownership 은 단일 소스로 유지한다**
   - 요청 단위에서 settings를 흩뿌리거나 fallback 로딩을 남기지 않는다.

4. **system event / metadata schema 는 구조적으로 검증 가능해야 한다**
   - frontend 임시 shape와 backend 저장 shape가 따로 놀면 안 된다.

### 5.3 품질 원칙

1. **증상 패치보다 root cause 수정**
2. **실제 provider를 직접 검증한 뒤 FabriX 쪽을 의심**
3. **높은 위험도의 구조 변경은 작은 단계로 나눠 검증**
4. **단일 provider 가정이 숨어 있는 곳은 조용히 늘리지 말고 구조적으로 분리**

---

## 6. Phase 1, 2에서 난이도가 높았던 부분 정리

Phase 3에서 다시 가장 위험해질 가능성이 높은 부분들이다.

### 6.1 host core 오염 없이 provider 확장하기

가장 어려웠던 점은 **provider-specific 현실을 수용하면서도 host core를 generic 하게 유지하는 것**이었다.

- 현재 provider 하나만 보면 쉬워 보이지만,
- 실제로는 tool 이름, category validation, RAG 결과 shape, manual command 결과 formatting 같은 지점에서
  provider-specific 가정이 host/core/router 쪽으로 새어나가기 쉽다.

Phase 3는 이 문제를 **한 provider의 하드코딩을 둘 이상으로 늘리는 방식**으로 풀면 안 된다.  
그렇게 하면 구조는 바로 다시 망가진다.

### 6.2 Test Mode를 “mock chat”이 아니라 “real MCP verification runtime”으로 유지하기

Phase 2에서 어려웠던 점은 Test Mode가 편의상 mock 구현으로 무너지는 것을 막는 일이었다.

- provider 연결
- capability discovery
- tool invocation
- context assembly

는 실제 경로를 유지해야 하고,  
달라지는 것은 오직 **tool decision / LLM completion** 뿐이라는 점을 계속 지켜야 했다.

Phase 3에서도 multi-provider Test Mode가 이 원칙을 깨면 안 된다.

### 6.3 runtime layering 과 zero-upstream 보장

Phase 2에서 upstream LLM 호출 경로를 runtime 바깥/전용 client로 분리한 이유는,  
Test Mode에서 실수로 외부 upstream 호출이 새어나가는 구조를 막기 위해서였다.

Phase 3에서도 provider routing 이나 orchestration 이 runtime 계층을 흐리게 만들면,

- Test Mode에서 upstream이 다시 섞이거나
- provider 선택 로직이 router/UI로 분산되거나
- mode 분기가 host core 안으로 침투하는

문제가 재발할 수 있다.

또한 현재처럼 **운영 모드와 Test Mode가 서로 다른 질문 의도 판별 파일**을 유지한 채 multi-provider를 추가하면,

- 신규 provider 온보딩 때 규칙을 두 군데에 중복 반영해야 하고
- 한쪽만 수정되어 mode별 판정 불일치가 생기고
- Test Mode가 운영 구조를 검증하는 역할 자체가 약해지는

문제가 발생한다.

### 6.4 system log / persistence / UI surface 의 일관성 유지

Phase 2에서 난이도가 높았던 또 하나의 지점은 system log를

- backend event schema
- SSE payload
- frontend message normalization
- Django persistence metadata

사이에서 **하나의 계약**으로 유지하는 일이었다.

Phase 3에서 provider가 여러 개가 되면

- provider 식별자
- provider별 title/phase/tool 정보
- partial success / partial failure
- 여러 provider 결과의 band 표현 방식

이 더 복잡해진다.

즉, multi-provider는 단순 registry 문제가 아니라 **event contract 문제**이기도 하다.

### 6.5 사용자 계약 유지하면서 내부 구조 바꾸기

Phase 1, 2 모두에서 어려웠던 점은

- `/mcp`
- `@파일명`
- 일반 채팅
- session history
- persistence

같은 사용자-facing 계약을 깨지 않으면서 내부 구조를 교체하는 일이었다.

Phase 3에서도 가장 위험한 실수는  
**multi-provider 지원을 이유로 기존 manual override UX나 일반 채팅 흐름을 깨는 것**이다.

---

## 7. Phase 3에서 먼저 설계해야 할 핵심 질문

이번 Part 1에서 답을 확정하지는 않지만, 구현 전 반드시 구조적으로 정리해야 할 질문들이다.

1. provider selection 책임은 어디에 둘 것인가?
   - intent router 확장?
   - provider router 신설?
   - runtime planner 내부?
   - 아니면 **운영/Test 공용 shared intent planner 계층** 으로 승격할 것인가?

2. 한 turn에서 여러 provider를 허용할 것인가?
   - 단일 provider 선택만 먼저 할지
   - 순차/병렬 multi-provider 호출까지 열지

3. capability inventory는 provider별로 어떻게 캐시할 것인가?

4. provider failure isolation은 어디에서 할 것인가?
   - adapter
   - registry/session manager
   - orchestration layer

5. Test Mode planner는 provider/action을 어떻게 고를 것인가?
   - scenario file 기반
   - keyword rule 기반
   - provider capability 기반

6. context merge는 provider별 fragment provenance를 어떻게 유지할 것인가?

---

## 8. Phase 3의 구현 순서 초안 (Part 1 기준)

위험을 최소화하려면 아래 순서가 바람직하다.

1. **현재 단일-provider 가정 위치 전수조사**
   - `internal_docs` 고정 참조
   - tool 이름 고정 참조
   - category/document 전용 가정

2. **provider identity / config model 확장**
   - registry가 여러 provider 정의를 다룰 수 있게 모델 정리

3. **provider adapter contract 재점검**
   - provider 공통 contract와 provider policy 경계를 분리

4. **provider selection 계층 도입**
   - 자연어 경로와 manual 경로 모두가 같은 selection 구조를 사용하게 정리
   - 운영 모드 `intent_router.py` 와 Test Mode `test_mode/planner.py` 의 분리 상태를 해소하고
     공용 질문 의도 판별 계층으로 통합

5. **Normal Mode multi-provider 경로 확장**
   - context merge / routing / failure isolation 정리

6. **Test Mode multi-provider planner 확장**
   - 같은 host core를 사용하면서 provider/action 선택만 별도 결정

7. **system event / persistence schema 확장**
   - multi-provider provenance / partial failure / aggregated summary 대응

8. **직접 provider validation + end-to-end 검증**
   - 각 provider 자체 검증
   - FabriX integration 검증
   - Normal/Test parity 검증

---

## 9. Phase 3에서 특히 금지할 구현 방식

1. provider가 늘어난다고 해서 `if provider == ...` 분기를 chat router에 늘리는 방식
2. Test Mode 전용 mock provider를 host core 아래에 끼워 넣는 방식
3. manual `/mcp` 와 자연어 경로가 서로 다른 provider 호출 코드를 가지는 방식
4. provider-specific result formatting을 UI가 직접 아는 방식
5. multi-provider 지원을 이유로 system message를 다시 top strip / badge / panel 로 흩뜨리는 방식
6. “일단 internal_docs 하나 더 복사” 식의 확장

---

## 10. 현재 시점의 잠정 결론

Phase 3의 본질은 **provider 개수 증가**가 아니라,  
**Phase 1의 generic host 원칙과 Phase 2의 runtime/test-mode 원칙을 깨지 않으면서 multi-provider 구조를 도입하는 것**이다.

따라서 Phase 3는 다음 문장으로 기억하면 된다.

> **여러 provider를 지원하되, host core는 더 generic 해지고, Normal/Test parity는 더 강해져야 하며, provider-specific 복잡성은 더 바깥 계층으로 밀어내야 한다.**

---

## 11. 다음 작성 단계에서 이어서 정리할 것

이번 Part 1 이후 다음 문서 개정에서 보강할 항목:

1. provider selection 세부 설계안 비교
2. multi-provider orchestration 허용 범위
3. `/mcp` UX의 provider 지정 문법
4. provider별 capability inventory/cache 정책
5. event schema 확장안
6. persistence / history / UI 세부 규약
 7. 운영 모드 / Test Mode 공용 질문 의도 판별기 통합 설계
 8. 검증 체크리스트와 테스트 전략
