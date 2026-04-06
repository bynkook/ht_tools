# Phase 1 — FabriX Generic MCP Host 전환 계획 (정의 확정본)

## 1. Phase 1의 한 줄 정의

Phase 1은 **FabriX Chat을 표준적인 범용 generic MCP host 구조로 깔끔하게 전환**하는 단계다.

여기에는 반드시 두 조건이 함께 포함된다.

1. **현재 사용 중인 doc search fastmcp 서버 연동이 계속 정상 작동할 것**
2. **FabriX Chat 자체도 정상 작동할 것**

중요한 점은, 이것이 **기존 하드코딩 legacy code를 계속 안고 가는 호환 레이어 유지 계획이 아니라**,  
**표준 구조로 재구성한 뒤 legacy 구현은 최종 상태에서 과감하게 제거하는 전환 계획**이라는 점이다.

---

## 2. 목표 상태

Phase 1 완료 후 FabriX는 다음 상태여야 한다.

1. Chat backend가 특정 doc-search MCP 서버 전용 코드가 아니라 **generic MCP host core** 위에서 동작한다.
2. 현재의 로컬 `fastmcp` 문서검색 서버는 첫 번째 provider로 등록되어 작동한다.
3. 자연어 질문은 최소 **`Intent Router`(`Query Router`)** 를 거쳐 일반 채팅 또는 MCP 활용 경로로 분기될 수 있다.
4. `/mcp` 관련 기능과 일반 채팅 기능은 사용자 관점에서 정상 작동한다.
5. 현재의 하드코딩된 legacy MCP 연동 코드는 제거되거나, 더 이상 핵심 경로에 남아 있지 않다.
6. 이후 다른 provider를 추가할 때 구조를 다시 뒤집지 않아도 된다.

---

## 3. Phase 1의 방향성

### 3.1 핵심 방향

- **표준적인 generic MCP host 로 전환**
- **현재 doc-search fastmcp 연동과 일반 채팅 기능 유지**
- **legacy hardcoding 제거**
- **미래 확장 가능 구조 확보**

### 3.2 제품적 북극성

장기적으로 FabriX Chat의 방향은 **Cursor / Claude 같은 툴의 미니멀 버전**에 가깝다.

즉, 단순히 MCP 서버 하나를 붙이는 앱이 아니라:
- 여러 MCP provider를 수용하고
- 도구/리소스/프롬프트를 탐색·호출할 수 있고
- 채팅과 도구 사용이 한 구조 안에서 연결되는
작고 단단한 host 형태를 지향한다.

Phase 1은 그 최종 목표의 **첫 번째 구조 전환 단계**다.

---

## 4. 반드시 보장해야 하는 것

Phase 1은 아래를 **반드시 동시에 만족**해야 한다.

### A. doc-search fastmcp 정상 작동
- `/mcp list`
- `/mcp list <카테고리>`
- `/mcp search`
- `/mcp read`
- `/mcp set`
- `/mcp clear`
- `/mcp rag on|off|status|refresh`
- `@파일명`
- `@카테고리/파일명`
- category validation
- RAG snippet/system prompt 흐름

### B. FabriX Chat 정상 작동
- 일반 채팅 전송/응답
- 세션 생성/이동
- 기존 command flow
- MCP 미사용 일반 대화 경로

### C. 최종 코드 상태의 정리성
- 영구적인 이중 경로 유지 금지
- 임시 migration용 브리지 코드는 허용되더라도 최종 상태에서 제거
- dead code / provider-specific hardcoding / 중복 로직 제거

---

## 5. Phase 1 범위

### In Scope
- generic MCP host core 설계 및 구현
- MCP server registry / config 설계
- tools / resources / prompts discovery 및 호출 공통화
- 결과 정규화(normalization) 계층
- context fragment merge 계층
- 최소 **`Intent Router`(`Query Router`)** 설계
- 현재 `C:\Users\BgKing\mycode\fastmcp` 문서검색 서버를 첫 provider로 편입
- 현재 chat flow를 generic host 기반으로 재배선
- 기존 hardcoded MCP integration 의 **식별 → 치환 → 제거** 세부 계획 수립
- non-regression 기준 정의
- 후속 provider를 붙일 수 있는 extension point 정의

### Out of Scope
- LexGuard 실제 통합
- LexGuard용 질의 라우팅 정책
- 완성형 multi-provider orchestration engine
- 고도화된 domain classifier / planner
- 완성형 mini Cursor/Claude 제품화
- 전면적인 UI 재설계

---

## 6. 첫 번째 provider — 로컬 `fastmcp` 문서검색 서버

Phase 1의 첫 provider는 **현재 운영 중인 로컬 `fastmcp` 문서검색 서버**다.

### 6.1 서버 정보
- 위치: `C:\Users\BgKing\mycode\fastmcp`
- 실행: `run_server.bat`
- 기본 MCP 주소: `http://127.0.0.1:8002/mcp`
- 설정: `.env`
  - `DOCS_DIR`
  - `MCP_HOST`
  - `MCP_PORT`

### 6.2 현재 노출 capability

#### Tools
- `list_categories`
- `list_categories_detail`
- `list_docs_detail`
- `search_docs`
- `search_docs_rag`
- `read_doc`

#### Resources
- `docs://categories`
- `docs://{category}/list`

### 6.3 현재 FabriX 결합 지점
- `ai_gateway/routers/doc_search.py`
- `frontend/src/hooks/useCommands.js`
- `/mcp-command`
- `/mcp-command/validate-category`
- `/mcp-command/rag-search`

Phase 1의 목적은 이 결합을 그대로 유지하는 것이 아니라,  
**이 기능 표면은 유지하되 내부 구현을 generic host 구조로 완전히 갈아끼우는 것**이다.

---

## 7. 범용 MCP host 표준과 FabriX 정책 계층의 경계

### 7.1 일반적인 generic MCP host가 담당하는 것
- provider 연결
- transport/session 관리
- capability discovery
- tool/resource/prompt invocation
- 기본 에러 처리
- provider registry와 adapter

### 7.2 FabriX 정책 계층이 담당하는 것
- 어떤 질의를 어느 provider로 보낼지 판단
- snippet만 넣을지 전체 문서를 넣을지 판단
- 여러 provider를 순차/병렬 호출할지 판단
- 어떤 결과를 어떤 형태로 LLM context에 합칠지 판단

즉, **MCP host core와 FabriX orchestration policy는 분리**되어야 한다.

Phase 1은 orchestration engine 완성이 아니라,  
**그 정책을 나중에 얹을 수 있는 clean host foundation** 까지 만드는 단계다.

### 7.3 Phase 1에 포함할 최소 질의 판별기

Phase 1에는 최소 형태의 **`Intent Router`** 를 포함한다. 설명할 때는 **`Query Router`** 라고 병기해도 된다.

역할은 단순하다.

1. 사용자의 자연어 질문을 본다.
2. 이 질문을 **일반 채팅으로 바로 보낼지**
3. **로컬 doc-search MCP를 먼저 사용할지**
4. 혹은 **사용자가 이미 `/mcp` 나 `@파일명` 으로 명시적 수동 지시를 했는지**
를 판별한다.

Phase 1의 Intent Router는 **최소형** 으로 둔다.

- 포함: 일반 채팅 vs 로컬 문서검색 MCP 분기
- 포함: 슬래시 커맨드/멘션이 있으면 manual override 우선
- 포함: 향후 외부 provider 추가를 위한 분기 지점 확보
- 제외: 고급 planner, 다단계 multi-provider 자동 orchestration

즉, **Phase 1은 generic host 전환 + 최소 Intent Router** 까지이고, 고도화된 자동 판단 엔진은 이후 단계의 일이다.

---

## 8. `/mcp` 슬래시 커맨드와 `@파일명` 문법의 위치

이 항목도 Phase 1 정의에 포함해야 한다.

### 8.1 결론

현재의 아래 문서검색 기능:

- `/mcp list`
- `/mcp list <카테고리>`
- `/mcp search`
- `/mcp read`
- `/mcp set`
- `/mcp clear`
- `/mcp rag on|off|status|refresh`
- `@파일명`
- `@카테고리/파일명`

은 **MCP 표준 그 자체가 아니라, FabriX가 MCP 기능을 노출하기 위해 만든 앱 고유 UX 계층**이다.

즉:
- **MCP 표준**: provider 연결, capability discovery, tool/resource/prompt invocation
- **FabriX UX**: slash command, mention 문법, operator-facing manual override

### 8.2 이것이 “표준과 다르다”는 뜻인가?

엄밀히 말하면 **표준 자체는 아니다.**

하지만 이것이 잘못된 것은 아니다.

왜냐하면 generic MCP host는 보통:
- UI가 전혀 없거나
- tool browser / inspector 형태이거나
- 모델이 내부적으로 tool을 호출하게 두는 구조
를 가지며,

`/mcp ...` 같은 슬래시 커맨드는 **앱이 사용자를 위해 추가한 명시적 제어 인터페이스** 로 볼 수 있기 때문이다.

따라서 현재 방식은:
- **초기 구현을 쉽게 만들기 위한 실용적 UX**
- **power-user/debug/operator control surface**
로는 타당하다.

다만 이것이 **host core의 구조를 정의하는 기준** 이 되어서는 안 된다.

### 8.2.1 슬래시 커맨드를 제거하면 보통 무엇으로 대체하는가?

generic MCP host에서 더 표준적인 기본 경로는 보통 다음과 같다.

1. **자연어 기반 요청**
2. **Intent Router / Query Router**
3. **MCP host core**
4. **LLM 응답 생성**

즉, 슬래시 커맨드의 대체물은 보통 **자연어 + Intent Router + MCP host core** 조합이다.

Phase 1에서는 이 기본 경로를 도입하되, 기존 `/mcp` 와 `@파일명` 은 **manual override UX** 로 유지한다.

### 8.3 Phase 1에서의 해석

Phase 1은 다음처럼 해석해야 한다.

1. `/mcp` 와 `@파일명` 은 **유지해야 하는 사용자-facing 기능 계약** 이다.
2. 그러나 generic MCP host core 는 이 슬래시 커맨드에 종속되지 않아야 한다.
3. 기본 경로는 **자연어 → Intent Router → MCP host core** 가 되어야 한다.
4. 즉, slash command 계층은 **host core 위에 얹힌 하나의 UX adapter** 여야 한다.
5. 향후 mini Cursor/Claude 방향으로 가더라도, `/mcp` 는
   - 유지될 수는 있지만
   - 필수 주 경로가 아니라
   - 명시적 제어 / 디버깅 / power-user 용 인터페이스
   로 재정의될 가능성이 크다.

### 8.4 Phase 1 설계 원칙

따라서 Phase 1에서는 아래를 원칙으로 한다.

1. **기존 `/mcp` UX는 유지한다.**
2. **하지만 `/mcp` UX를 generic host core와 분리한다.**
3. **chat core 는 최소 Intent Router를 통해 slash command 없이도 generic MCP provider를 사용할 수 있는 구조** 로 설계한다.
4. **`/mcp` 와 `@파일명` 은 host capability를 수동으로 제어하는 UX adapter** 로 위치시킨다.

이렇게 해야 나중에:
- 자연어 기반 자동 tool selection
- provider routing
- multi-provider orchestration
- Cursor/Claude형 미니멀 UX
를 얹을 때 host core를 다시 뒤집지 않아도 된다.

---

## 9. 목표 아키텍처

예상 backend 구조:

```text
ai_gateway/
  services/
    mcp/
      registry.py
      client_adapter.py
      capability_cache.py
      result_normalizer.py
      context_merge.py
      tool_selection.py
      providers/
        internal_docs.py
```

핵심 원칙:

1. `internal_docs.py` 는 현재 fastmcp 서버를 감싸는 **첫 provider adapter**
2. Chat flow는 더 이상 특정 tool 이름과 MCP endpoint를 직접 하드코딩하지 않음
3. provider-specific 로직은 provider adapter 내부로 국소화
4. 최종 LLM 입력 직전에는 normalized context fragment 로만 다룸
5. 자연어 기반 경로는 `Intent Router` 를 통해 provider 사용 여부를 먼저 판별

---

## 10. legacy code 처리 원칙

이 항목이 이번 정의에서 가장 중요하다.

### 9.1 버릴 것
- doc-search 전용 하드코딩 흐름
- 특정 MCP 서버를 전제로 한 직접 호출 코드
- generic host 도입 후에도 남는 중복/임시 경로
- 영구 compatibility shim

### 9.2 남길 것
- 사용자-facing 동작 계약
- 필요한 API path 자체
- 현재 정상 동작의 기능적 결과

즉, **버리는 것은 legacy implementation 이고, 유지하는 것은 사용자 계약과 기능 결과**다.

### 9.3 legacy 제거/치환 세부 스탭

#### Step 1. legacy surface audit
- 현재 hardcoded MCP 경로를 파일/책임 단위로 식별
- 직접 `fastmcp.Client` 호출 지점 식별
- provider-specific tool 이름/응답 가공/카테고리 검증 하드코딩 지점 식별
- chat flow 내부의 provider 결합 지점 식별

#### Step 2. contract freeze
- 사용자-facing 기능 계약을 문서화
- `/mcp-command*`, `/mcp`, `@파일명`, RAG 결과 형식을 고정
- 치환 중에도 깨지면 안 되는 동작을 테스트 체크리스트로 고정

#### Step 3. target replacement mapping
- legacy 책임을 새 generic host 구조의 어느 컴포넌트로 옮길지 매핑
  - registry
  - adapter
  - provider adapter (`internal_docs`)
  - normalizer
  - context merge

#### Step 4. call-site cutover
- chat/doc-search 호출 경로를 새 generic host core 로 전환
- 기존 기능은 유지하되 내부 구현만 새 구조를 통하도록 변경

#### Step 5. dead path removal
- 더 이상 사용하지 않는 direct client path 제거
- 중복 helper 제거
- provider-specific branching 이 chat core 에 남지 않도록 제거
- 영구 compatibility shim 제거

#### Step 6. post-removal verification
- legacy 제거 후에도 `/mcp` 기능 정상 작동 확인
- 일반 채팅 기능 정상 작동 확인
- 운영 설정과 장애 시 동작 확인

---

## 11. 권장 개발 순서

현재 문서의 개발 순서는 큰 방향은 맞지만, **위험성과 난이도를 더 낮추려면 자동 경로보다 수동 경로를 먼저 옮기고, 회귀 기준을 더 앞당기는 순서**가 더 안전하다.

### 11.1 왜 순서를 바꾸는가

1. **회귀 기준은 구현 전에 고정하는 편이 안전하다.**
   - 나중에 확인하면 “원래 동작” 기준이 흔들릴 수 있다.

2. **manual override 경로가 자연어 자동 경로보다 훨씬 단순하다.**
   - `/mcp`, `@파일명` 은 사용자의 의도가 이미 명시돼 있다.
   - `Intent Router` 는 분류/오판 리스크가 추가된다.

3. **legacy 제거는 항상 마지막이어야 한다.**
   - 새 core + provider + manual path + 자연어 path 가 모두 안정화된 뒤 제거해야 rollback 위험이 낮다.

### Step 1. 현재 계약 동결
- `/mcp-command*` 요청/응답 형식 정리
- `/mcp` 관련 사용자-facing 동작 정리
- `@파일명` / RAG / category validation 동작 정리
- `/mcp` 와 `@파일명` 을 **host core가 아니라 UX adapter contract** 로 정리

### Step 2. current system inventory + legacy audit
- fastmcp provider inventory 작성
- tools/resources 입력/출력 정리
- `search_docs_rag` structured result 정리
- current coupling point 정리
- hardcoded direct call / provider-specific branching / 중복 helper 식별

### Step 3. non-regression baseline 먼저 정의
- 문서검색 기능 체크리스트 확정
- 일반 채팅 기능 체크리스트 확정
- 치환 전 기준 동작을 명확히 기록

### Step 4. target generic host 설계
- registry
- adapter
- normalizer
- context merge
- provider extension point
- slash command UX adapter 경계 정의

### Step 5. generic MCP host core 구현
- generic MCP host core 추가
- fastmcp를 `internal_docs` provider로 연결
- provider 단위에서 isolated parity 확인

### Step 6. 기존 manual MCP UX cutover
- `/mcp` 와 `@파일명` 경로를 새 generic host core 위로 먼저 옮김
- slash command 처리 계층이 host core를 직접 정의하지 않도록 분리
- 즉, **manual override path를 먼저 안정화**

### Step 7. minimal Intent Router 도입
- 자연어 질문을 일반 채팅 / 로컬 문서검색 MCP / manual override 로 분기
- `/mcp` 와 `@파일명` 이 있으면 manual override 우선
- 향후 외부 provider 라우팅을 위한 최소 확장 지점 확보

### Step 8. main chat flow cutover
- 자연어 기반 기본 경로가 `Intent Router` 를 거치도록 정리
- 일반 채팅과 MCP 채팅 경로가 함께 정상 작동하도록 정리
- context merge를 최종 chat flow에 연결

### Step 9. legacy 제거/치환 실행
- legacy audit 결과를 기준으로 파일별 제거 순서를 확정
- old hardcoded path 제거
- dead code 제거
- 중복 로직 제거
- 최종 코드 상태에 permanent shim 이 남지 않도록 정리

### Step 10. final non-regression 확인
- doc-search 기능 회귀 없음
- 일반 채팅 회귀 없음
- 설정/운영 방식 정리

---

## 12. non-regression 체크리스트

### 문서검색 기능
- `/mcp list`
- `/mcp list <카테고리>`
- `/mcp search`
- `/mcp read`
- `/mcp set`
- `/mcp clear`
- `/mcp rag on|off|status|refresh`
- `@파일명`
- `@카테고리/파일명`
- RAG no-result
- provider down 상황

### 일반 채팅 기능
- 일반 채팅 전송/응답
- 세션 생성/전환
- 기존 command flow
- MCP 미사용 경로

---

## 13. 예상 영향 파일

### Backend
- `ai_gateway/main.py`
- `ai_gateway/routers/doc_search.py`
- `ai_gateway/services/mcp/*`
- `secrets.toml`

### Frontend
- `frontend/src/api/fastapiApi.js`
- `frontend/src/hooks/useCommands.js`
- 필요 시 Chat 관련 feature 파일

### 문서
- `doc.md/phase1_fabrix_generic_mcp_host_plan.md`

---

## 14. Phase 1 완료 기준

다음이 충족되면 Phase 1 완료다.

1. FabriX Chat이 generic MCP host 구조 위에서 동작한다.
2. 현재 fastmcp 문서검색 서버는 첫 provider로 정상 작동한다.
3. 자연어 질문이 최소 `Intent Router` 를 통해 일반 채팅 또는 MCP 활용 경로로 분기될 수 있다.
4. 기존 `/mcp` 기능과 일반 채팅 기능이 정상 작동한다.
5. legacy hardcoded MCP integration code 가 핵심 경로에서 제거된다.
6. `/mcp` 와 `@파일명` 은 유지되더라도 host core가 아니라 **분리된 UX adapter 계층** 으로 정리된다.
7. 후속 provider를 위한 clean extension point 가 준비된다.

---

## 15. 최종 판단

Phase 1의 본질은 **“작동 중인 legacy integration을 감싸는 것”이 아니라,  
FabriX Chat을 표준적인 generic MCP host 로 깔끔하게 전환하고, 그 결과로 기존 doc-search와 chat이 정상 작동하게 만드는 것**이다.

즉, 이번 단계는:

- **기능 유지**
- **구조 전환**
- **최소 Intent Router 도입**
- **legacy 제거**
- **slash command를 core가 아닌 UX 계층으로 재배치**
- **미래 mini Cursor/Claude 방향을 위한 기반 확보**

의 단계로 정의한다.

---

## 16. 현재 문서 상태

이 문서는 **Phase 1 계획 문서 작성 완료본**이다.

- 현재는 **코드 수정/구현을 시작하지 않는다.**
- 사용자가 문서를 추가 검토한 뒤 구현 착수 여부를 결정한다.
- 따라서 지금 단계의 산출물은 **계획 문서의 확정** 이고, 실행은 보류 상태다.
