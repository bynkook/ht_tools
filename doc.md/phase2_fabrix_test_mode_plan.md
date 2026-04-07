# Phase 2 — FabriX MCP Test Mode 설계 및 개발 계획

**적용 범위 명시**

- 이 Phase 2 계획은 **FabriX Chat 앱** 수정 계획이다.
- **FabriX Agent Chat 앱은 범위 밖** 이다.
- FabriX Agent Chat은 이미 FabriX 서버에 구현되어 있는 문서검색 MCP를 호출하는 채팅으로 간주하며, 이번 Phase 2에서 **별도의 MCP 기능 구현 또는 추가 계획이 없다.**

Phase 2는 **Phase 1에서 generic MCP host core 전환이 완료되었다는 전제 위에서**,  
외부 LLM API가 전혀 불가능한 오프라인 환경에서도 **MCP Host 자체의 연결, capability discovery, tool invocation, context assembly** 를 끝까지 검증할 수 있게 만드는 단계다.

핵심 원칙은 단순하다.

- **MCP 부분은 실제로 연결하고 실제로 호출한다**
- **외부 LLM 호출만 완전히 우회한다**
- **Normal Mode와 Test Mode는 같은 host core를 공유한다**
- **Test Mode에서 일어난 MCP 활동은 전부 system log 형태로 관찰 가능해야 한다**

즉, Phase 2의 본질은 “mock chat 앱”이 아니라,  
**실제 MCP host의 동작을 오프라인에서도 검증 가능한 운영/개발용 Test Runtime을 추가하는 것**이다.

---

## 1. High-level Architecture Diagram

### 1.1 목표 구조

```text
┌──────────────────────────────────────────────────────────────────────┐
│ React Chat UI                                                       │
│  - User / Assistant messages                                        │
│  - Inline SystemMessageBand in conversation flow                    │
│  - No header/composer status badge; system output stays in bands    │
└───────────────┬──────────────────────────────────────────────────────┘
                │ HTTP + SSE
                v
┌──────────────────────────────────────────────────────────────────────┐
│ FastAPI Gateway                                                     │
│  routers/chat.py                                                    │
│    -> ChatRuntimeFactory                                            │
│         ├─ NormalChatRuntime                                        │
│         └─ TestModeChatRuntime                                      │
│                                                                      │
│  shared:                                                             │
│    - Intent Router                                                   │
│    - MCP Host Core                                                   │
│    - Registry / Config                                               │
│    - Provider Adapters                                               │
│    - Capability Cache                                                │
│    - Context Merge                                                   │
│    - SystemEventEmitter                                              │
└───────┬───────────────────────────────┬──────────────────────────────┘
        │                               │
        │ Normal Mode                    │ Test Mode
        v                               v
┌─────────────────────┐       ┌───────────────────────────────────────┐
│ External LLM API    │       │ Deterministic Tool Planner            │
│ (FabriX/OpenAI/etc) │       │ + Scenario Loader                     │
│ real upstream call  │       │ + LLM bypass                          │
└─────────────────────┘       └───────────────────────────────────────┘
        │                               │
        └───────────────┬───────────────┘
                        v
┌──────────────────────────────────────────────────────────────────────┐
│ MCP Host Core                                                       │
│  - session lifecycle                                                │
│  - capability discovery                                             │
│  - call tool / read resource / get prompt                           │
│  - protocol event recording                                         │
│  - normalized context fragment creation                             │
└───────────────┬──────────────────────────────────────────────────────┘
                │
                v
┌──────────────────────────────────────────────────────────────────────┐
│ MCP Client Sessions                                                 │
│  - Streamable HTTP                                                  │
│  - stdio                                                            │
│  - future: SSE compatibility if Phase 1 abstraction already allows  │
└───────────────┬──────────────────────────────────────────────────────┘
                │
                v
┌──────────────────────────────────────────────────────────────────────┐
│ MCP Servers                                                         │
│  - current first provider: local fastmcp doc-search server          │
│  - future local/remote providers                                    │
└──────────────────────────────────────────────────────────────────────┘
```

### 1.2 Test Mode의 핵심 위치

Test Mode는 **MCP Host Core 아래가 아니라 위에** 위치해야 한다.

- 잘못된 방식: MCP 호출 자체를 mock 처리
- 올바른 방식: **LLM decision / LLM completion만 mock 처리**, MCP 호출은 실제 경로 사용

이 원칙이 중요한 이유는, Test Mode의 목적이 “채팅 화면만 흉내 내는 것”이 아니라  
**generic MCP host가 실제 provider와 표준 프로토콜로 상호작용하는지 검증하는 것**이기 때문이다.

### 1.3 현재 코드 기준 연결 지점

Phase 2 계획은 아래 현재 구현을 직접 대상으로 한다.

- FastAPI upstream LLM 경로: `ai_gateway/routers/chat.py`
- MCP legacy/manual path: `ai_gateway/routers/doc_search.py`
- 채팅 UI 메인: `frontend/src/features/chat/ChatPage.jsx`
- 현재 system message 렌더링: `frontend/src/features/chat/components/ChatBubble.jsx`
- 현재 수동 system message 주입: `frontend/src/hooks/useCommands.js`
- 현재 채팅 메시지 모델: `django_server/apps/fabrix_chat/models.py`

현재 상태에서 중요한 사실:

1. `chat.py` 는 현재 직접 upstream LLM 스트리밍을 수행한다.
2. `ChatPage.jsx` 는 `role === 'system'` 메시지를 `contents` 에서 제외한다.
3. `ChatBubble.jsx` 의 system message는 중앙 회색 버블 형태다.
4. Django `ChatMessage` 는 현재 `role`, `content` 만 있고 structured metadata가 없다.

Phase 2는 이 현재 상태를 전제로, **runtime strategy + system log model + inline system band UI** 로 확장한다.

---

## 2. Config & Test Mode Flag Design

### 2.1 설계 목표

Test Mode는 다음 조건을 동시에 만족해야 한다.

1. **명확하게 ON/OFF 가능**
2. **프로세스 시작 시 확정**
3. **코드 전역에서 일관된 방식으로 참조**
4. **실수로 외부 LLM 호출이 새어나가지 않도록 강한 guard 제공**
5. **필요한 경우 대화 흐름 안에서 현재 runtime 성격을 파악할 수 있어야 함**

### 2.2 권장 설정 우선순위

FabriX 현재 관례를 고려하면 **루트 `secrets.toml` 을 기본** 으로 하고,  
운영/임시 실행 편의를 위해 **환경변수 override** 를 허용하는 방식이 가장 적절하다.

우선순위:

1. 환경변수 `MCP_TEST_MODE`
2. `secrets.toml`의 `[mcp_host]` 섹션
3. 기본값 `false`

권장 이유:

- 이 저장소는 이미 민감정보/런타임 설정을 `secrets.toml` 중심으로 사용한다.
- 환경변수 override는 오프라인 테스트, CI, 임시 실행에 유리하다.

### 2.3 권장 설정 스키마

```toml
[mcp_host]
test_mode = true
test_mode_verbose_json = true
test_mode_scenario_path = "ai_gateway/services/mcp/test_mode/scenarios/default.json"
test_mode_discovery_on_startup = true
test_mode_store_system_logs = true
test_mode_max_payload_chars = 4000
test_mode_visible_band_limit = 20
test_mode_redact_headers = true
test_mode_allow_remote_mcp = true
```

환경변수 예시:

```powershell
$env:MCP_TEST_MODE = "true"
$env:MCP_TEST_MODE_SCENARIO_PATH = "C:\Users\BgKing\mycode\ht_tools_mcphost\ai_gateway\services\mcp\test_mode\scenarios\offline-docs.json"
```

### 2.4 플래그 상세 정의

| Key | 타입 | 기본값 | 역할 |
|---|---:|---:|---|
| `test_mode` | bool | `false` | Test Mode 전체 토글 |
| `test_mode_verbose_json` | bool | `true` | JSON-RPC payload/raw result 상세 출력 |
| `test_mode_scenario_path` | str | `default.json` | deterministic planner 시나리오 파일 |
| `test_mode_discovery_on_startup` | bool | `true` | 앱 시작 시 provider capability discovery 수행 |
| `test_mode_store_system_logs` | bool | `true` | system log persistence 여부 |
| `test_mode_max_payload_chars` | int | `4000` | UI/DB에 저장할 raw payload 길이 상한 |
| `test_mode_visible_band_limit` | int | `20` | request당 화면에 표시할 visible system band 상한 |
| `test_mode_redact_headers` | bool | `true` | auth/token 헤더 마스킹 |
| `test_mode_allow_remote_mcp` | bool | `true` | remote MCP 연결 허용 여부 |

### 2.5 설정 적용 위치

Phase 2에서는 설정 로딩을 라우터 내부에서 반복하지 말고,  
**Phase 1 generic MCP host config 계층에서 단일 settings 객체** 로 통합해야 한다.

권장 위치:

- `ai_gateway/services/mcp/config.py`
- `ai_gateway/main.py` startup 시 settings 로드
- `request.app.state.mcp_settings` 또는 singleton settings provider 사용

### 2.6 UI 노출 방식

Phase 2 UI는 용어와 표면을 단순하게 유지한다.

1. **badge**: header나 입력창 근처의 작은 상태 표시. Phase 2에서는 사용하지 않는다.
2. **strip**: 대화창 상단의 가로 상태줄. Phase 2에서는 사용하지 않는다.
3. **panel**: 대화 흐름 바깥의 별도 펼침 영역. Phase 2에서는 사용하지 않는다.
4. **band**: 대화 흐름 안의 full-width system message. Phase 2의 유일한 대화형 시스템 출력 표면이다.

따라서:

- 기존 입력창 바로 위 왼쪽의 MCP 상태 badge는 **완전 제거**
- Test Mode 활성 사실이 필요하면 별도 badge나 입력창 안내가 아니라 **system message band** 로 출력
- `runtime_status` 전용 UI surface나 별도 status endpoint는 Phase 2 계획에 두지 않는다

### 2.7 왜 세션 단위 토글이 아니라 프로세스 단위 토글인가

Phase 2에서는 **프로세스 단위 토글** 이 더 안전하다.

이유:

1. 오프라인 개발 환경 제약이 프로세스 전체에 적용된다.
2. 같은 런타임에서 일부 세션만 실제 upstream, 일부 세션만 test mode로 섞으면 디버깅이 복잡해진다.
3. 실수로 외부 호출이 살아남을 위험이 커진다.

따라서 기본 원칙은:

- **앱 시작 시 mode를 고정**
- 변경하려면 **프로세스 재시작**

---

## 3. Normal Mode vs Test Mode Core Flow (step-by-step 비교 테이블)

### 3.1 전체 비교

| 단계 | Normal Mode | Test Mode |
|---|---|---|
| 1. 사용자 입력 | 일반 채팅 입력 수신 | 동일 |
| 2. 세션/메시지 저장 | user message 저장 | 동일 |
| 3. Intent Router | 일반 채팅 vs MCP 사용 판단 | 동일 |
| 4. Provider 선택 | 실제 provider 선정 | 동일 |
| 5. Capability discovery | 필요 시 실제 discovery | 동일, 단 log를 더 자세히 남김 |
| 6. Tool decision | 외부 LLM 또는 향후 planner가 결정 | deterministic planner / scenario rules가 결정 |
| 7. MCP 호출 | 실제 MCP 서버 호출 | 동일 |
| 8. 응답 정규화 | normalized fragments 생성 | 동일 |
| 9. Context merge | LLM 입력용 aggregated context 구성 | 동일 |
| 10. LLM completion | 외부 upstream 호출 | **호출 금지**, bypass |
| 11. UI 출력 | assistant 응답 + 운영 system logs | system logs + optional synthetic assistant summary |
| 12. 로그 저장 | 필요 최소 system logs | 상세 system logs 저장 가능 |

### 3.2 상세 흐름

#### Normal Mode

1. 사용자가 메시지를 전송한다.
2. 프런트엔드는 user message를 세션에 저장한다.
3. FastAPI `chat` 라우터는 runtime factory를 통해 `NormalChatRuntime` 을 선택한다.
4. `NormalChatRuntime` 은 Phase 1 host core를 통해 provider registry / capability cache / context merge를 사용한다.
5. 필요 시 MCP tool/resource/prompt 호출이 일어난다.
6. assembled context가 준비되면 external LLM API를 호출한다.
7. upstream SSE를 프런트엔드에 전달한다.
8. 프런트엔드는 assistant 메시지를 렌더링하고 저장한다.
9. 운영상 필요한 system logs 는 대화 흐름 안의 **inline system band** 로 남긴다.

#### Test Mode

1. 사용자가 메시지를 전송한다.
2. 프런트엔드는 user message를 세션에 저장한다.
3. FastAPI `chat` 라우터는 runtime factory를 통해 `TestModeChatRuntime` 을 선택한다.
4. Test runtime은 **외부 LLM payload를 만들지 않는다**.
5. 먼저 연결 대상 MCP server 상태를 확인한다.
6. capability discovery를 수행하고 결과를 structured system log로 기록한다.
7. deterministic planner 또는 scenario loader가 “어떤 tool을 어떤 순서로 호출할지” 결정한다.
8. MCP host core를 통해 실제 tool/resource/prompt 호출을 수행한다.
9. 각 JSON-RPC request/response를 system log로 기록한다.
10. context merge 결과를 system log로 기록한다.
    - 이때 `Context aggregated` raw에는 **건수 요약만이 아니라, 실제 upstream LLM 호출에 사용되었을 최종 assembled context(system prompt)** 가 디버그용으로 보여져야 한다.
11. 실제 LLM 호출 없이 종료한다.
12. 필요 시 `assistant` 자리에 “LLM bypassed in MCP_TEST_MODE” 요약 메시지를 남긴다.

### 3.3 Phase 2의 중요한 설계 결정

Test Mode에서도 아래는 반드시 Normal Mode와 동일해야 한다.

- registry에서 provider 선택하는 방식
- transport/session 수명 관리
- capability discovery 결과 처리
- tool/resource/prompt 결과 정규화
- context merge 규칙

즉, 달라지는 것은 오직:

1. **누가 tool decision을 하느냐**
2. **external LLM completion을 호출하느냐**

뿐이다.

---

## 4. Test Mode 구현 상세 계획

### 4.1 핵심 구현 원칙

Phase 2는 기존 라우터에 `if test_mode:` 를 흩뿌리는 방식으로 구현하면 안 된다.

권장 방식은 **runtime strategy + event hooks + shared host core** 다.

핵심 구조:

- `BaseChatRuntime`
- `NormalChatRuntime`
- `TestModeChatRuntime`
- `ChatRuntimeFactory`
- `DeterministicToolPlanner`
- `ScenarioLoader`
- `SystemEventEmitter`
- `ProtocolRecorder`

### 4.2 어디에 로직을 넣을 것인가

#### A. Runtime 선택

위치:

- `ai_gateway/routers/chat.py` 는 직접 upstream 호출을 하지 않고
- `ChatRuntimeFactory` 로부터 runtime을 받아 실행하는 구조로 바꾼다.

이유:

- 현재 `chat.py` 에는 upstream rate limiting, payload 구성, SSE 전달이 한데 섞여 있다.
- Phase 2는 여기에 “테스트 시 외부 LLM 우회”를 넣어야 하므로, runtime 분리가 필수다.

#### B. Test Mode 전용 로직

위치:

- `ai_gateway/services/mcp/test_mode/`

여기에 둘 것:

- scenario loading
- deterministic planner
- protocol logging helper
- synthetic assistant summary builder
- system event schema

#### C. 공통 MCP 동작

위치:

- `ai_gateway/services/mcp/` 공통 계층

여기에 둘 것:

- registry
- provider adapter
- capability cache
- client session management
- result normalizer
- context merge

### 4.3 LLM API 호출 interception 방법

가장 중요한 결정은 **라우터 레벨에서 upstream 호출 코드를 분리**하는 것이다.

권장 구조:

1. `chat.py` 는 request validation만 수행
2. 이후 `runtime.stream_chat(req, request)` 호출
3. `NormalChatRuntime` 만 upstream client를 사용
4. `TestModeChatRuntime` 는 upstream client를 전혀 사용하지 않음

이 방식의 장점:

- “실수로 외부 LLM API를 호출하는 버그”를 구조적으로 줄인다.
- 테스트와 운영의 분기 지점이 하나로 고정된다.
- 향후 agent chat에도 같은 runtime strategy를 재사용할 수 있다.

### 4.4 Deterministic Simulation Logic

Test Mode의 planner는 **간단하고 결정적이어야** 한다.

권장 우선순위:

1. **Scenario JSON 매칭**
2. **Keyword rule 매칭**
3. **Fallback no-tool path**

예시:

- “안전밸브 점검 기준” → `internal_docs.search_docs_rag`
- “카테고리 보여줘” → `internal_docs.list_categories_detail`
- `@파일명` 포함 → `read_doc`
- `/mcp ...` 포함 → manual override 우선
- 어떤 매칭도 없으면 → MCP 미사용, “No tool selected in test mode” 로그 출력

중요한 점:

- Test Mode planner는 LLM을 대체하는 것이지, 고급 reasoning engine이 아니다.
- 따라서 **작고 예측 가능하게 유지** 해야 한다.

### 4.5 JSON-RPC 요청/응답 기록 방법

요구사항상 Test Mode는 실제 MCP 요청/응답을 system log로 보여줘야 한다.

권장 방식:

1. 공식 Python SDK를 사용해 session/transport를 유지한다.
2. SDK 아래를 직접 구현하지 않는다.
3. 대신 **session wrapper 또는 adapter boundary** 에서 아래 이벤트를 기록한다.

기록 대상:

- `initialize`
- capability listing (`tools`, `resources`, `prompts`)
- `call_tool`
- resource read / prompt get
- 오류 응답

로그 레벨:

- `INFO`: 연결 성공, discovery 완료, tool 선택
- `DEBUG`: JSON-RPC payload/raw response
- `WARN`: provider timeout, malformed response, capability missing
- `ERROR`: transport 연결 실패, tool call 실패

권장 저장 형식:

```json
{
  "request_id": "turn-20260407-0001",
  "provider": "internal_docs",
  "phase": "tool_call",
  "direction": "outbound",
  "rpc_method": "tools/call",
  "payload": { "...": "..." },
  "timestamp": "2026-04-07T05:00:00Z"
}
```

### 4.6 System Message 주입 방법

현재 `ChatPage.jsx` 와 `ChatBubble.jsx` 는 `role: 'system'` 을 중앙 회색 버블로 렌더링한다.  
Phase 2에서는 이를 **inline system message band stream** 으로 재정의해야 한다.

권장 방식:

#### Backend SSE event 종류

- `system_log`
- `assistant_delta`
- `assistant_final`
- `stream_end`

예시:

```json
{
  "event_type": "system_log",
  "level": "info",
  "channel": "mcp_test",
  "request_id": "turn-20260407-0001",
  "content": "Simulating LLM tool decision...",
  "meta": {
    "provider": "internal_docs",
    "phase": "planning"
  }
}
```

#### Frontend 수신 방식

1. SSE 수신기에서 `event_type` 을 해석한다.
2. `system_log` 는 일반 assistant bubble에 넣지 않는다.
3. `messages` 배열 내 structured system message로 넣고, `SystemMessageBand` 로 렌더링한다.
4. `assistant_delta` 는 assistant bubble을 업데이트한다.

### 4.7 Framework-agnostic UI interface

React 기준 구현을 하되, 인터페이스 자체는 프레임워크 비종속적으로 설계한다.

권장 이벤트 모델:

```json
{
  "kind": "system_log",
  "level": "debug",
  "scope": "mcp",
  "title": "Tool call",
  "content": "Calling search_docs_rag",
  "raw": { "...": "..." },
  "request_id": "turn-20260407-0001"
}
```

즉, UI는 “system log event list” 인터페이스만 알면 되고,  
그것이 React든 Tauri든 Electron이든 동일하게 consume 가능해야 한다.

### 4.8 mark3labs/mcphost hooks 패턴 반영

Phase 2는 `mcphost` 의 hooks 철학을 차용하는 것이 좋다.

FabriX용 권장 훅:

- `OnUserPromptReceived`
- `OnProviderConnectStart`
- `OnProviderConnectEnd`
- `OnCapabilityDiscoveryStart`
- `OnCapabilityDiscoveryEnd`
- `OnToolDecision`
- `OnBeforeToolCall`
- `OnAfterToolCall`
- `OnContextAggregated`
- `OnLlmBypassed`
- `OnRuntimeFinished`

장점:

- Test Mode 뿐 아니라 Normal Mode 운영 로그도 같은 인터페이스로 남길 수 있다.
- 나중에 LexGuard 같은 provider를 붙여도 로깅 구조를 재사용할 수 있다.
- UI logger, file logger, test assertion 모두 같은 event stream을 볼 수 있다.

### 4.9 Dive의 system message 패턴 반영

`Dive` 에서 차용할 포인트는 “도구/서버 활동을 사용자 메시지와 다른 층위로 보이게 한다”는 점이다.

FabriX에 맞는 반영 방식:

- 사용자/assistant 대화는 conversational bubble 유지
- 시스템 활동은 **full-width inline system band** 로 분리
- 필요 시 raw payload는 collapse/expand
- tool enable/disable, provider connect, auth issue 같은 운영성 정보도 같은 inline system message 규약으로 통합

### 4.10 메시지 persistence 계획

Test Mode에서 system logs를 세션 기록에 남기려면 현재 모델이 부족하다.

권장 방안:

1. `django_server/apps/fabrix_chat/models.py` 의 `ChatMessage` 에 `metadata = models.JSONField(default=dict, blank=True)` 추가
2. `role='system'` + `metadata.kind='system_log'` 로 구조화

예시 metadata:

```json
{
  "kind": "system_log",
  "level": "debug",
  "channel": "mcp_test",
  "request_id": "turn-20260407-0001",
  "phase": "tool_call",
  "provider": "internal_docs"
}
```

저장 전략:

- user turn 동안 system log를 프런트에서 버퍼링
- turn 종료 시 batch 저장
- `buildContentsArray()` 에서는 여전히 `role === 'system'` 제외

이렇게 해야:

- 시스템 로그는 history/debug에는 남고
- 실제 LLM `contents` 는 오염되지 않는다

### 4.11 권장 개발 순서

1. **Phase 1 host core가 안정화되었는지 확인**
2. `chat.py` 를 runtime strategy 구조로 분리
3. config/test flag 계층 추가
4. system event schema + emitter 추가
5. deterministic planner + scenario loader 추가
6. protocol recorder 추가
7. `SystemMessageBand` UI 추가
8. message metadata/persistence 추가
9. non-regression + offline validation

### 4.12 Phase 2 완료 기준

아래가 충족되면 Phase 2 완료다.

1. `MCP_TEST_MODE=true` 에서 외부 LLM API 호출이 발생하지 않는다.
2. MCP server 연결, discovery, tool call, context merge가 실제 경로로 수행된다.
3. 모든 중요한 MCP 활동이 system logger UI에 표시된다.
4. Normal/Test runtime 분기가 strategy 계층으로 정리된다.
5. system logs가 conversational context에 섞이지 않는다.
6. stdio + streamable HTTP provider를 같은 host core로 검증할 수 있다.

---

## 5. 추천 Code Structure (폴더 레이아웃 + 핵심 파일/클래스)

### 5.1 언어 선택

Phase 2의 핵심 구현 언어는 **Python** 이 더 적합하다.

이유:

1. 현재 MCP host backend 중심이 `ai_gateway` Python 계층이다.
2. 현재 upstream LLM interception 지점도 `ai_gateway/routers/chat.py` 다.
3. 공식 **`modelcontextprotocol/python-sdk`** 가 client/session/transport 관점에서 매우 강한 참조점이다.
4. Test Mode의 핵심은 “MCP host runtime 분리”이지 프런트엔드 프레임워크 변경이 아니다.

즉, **핵심 동작은 Python**, **UI 렌더링은 기존 React** 로 가는 것이 가장 안전하다.

### 5.2 권장 폴더 구조

```text
ai_gateway/
  routers/
    chat.py
  services/
    mcp/
      config.py
      registry.py
      client_adapter.py
      capability_cache.py
      result_normalizer.py
      context_merge.py
      event_schema.py
      event_emitter.py
      runtime/
        base.py
        factory.py
        normal_runtime.py
        test_mode_runtime.py
      test_mode/
        planner.py
        scenario_loader.py
        protocol_recorder.py
        synthetic_assistant.py
        scenarios/
          default.json
          docs_lookup.json
frontend/
  src/
    features/
      chat/
        ChatPage.jsx
        components/
          ChatBubble.jsx
          SystemMessageBand.jsx
          SystemMessageMeta.jsx
          SystemMessageRaw.jsx
        utils/
          systemLogFormatter.js
          sseEventNormalizer.js
django_server/
  apps/
    fabrix_chat/
      models.py
      serializers.py
      views.py
doc.md/
  phase1_fabrix_generic_mcp_host_plan.md
  phase2_fabrix_test_mode_plan.md
```

### 5.3 핵심 클래스 책임

| 파일 | 책임 |
|---|---|
| `runtime/factory.py` | 현재 mode에 맞는 runtime 선택 |
| `runtime/normal_runtime.py` | 기존 upstream LLM 경로 담당 |
| `runtime/test_mode_runtime.py` | external LLM bypass + deterministic planning |
| `test_mode/planner.py` | 사용자 질의 -> tool plan 결정 |
| `test_mode/scenario_loader.py` | JSON 기반 시나리오 로딩 |
| `test_mode/protocol_recorder.py` | JSON-RPC 요청/응답 구조 기록 |
| `event_emitter.py` | system log event 통일 인터페이스 |
| `SystemMessageBand.jsx` | full-width inline system log/message 렌더링 |
| `systemLogFormatter.js` | event -> human-readable line formatting |

### 5.4 기존 파일 변경 포인트

#### Backend

- `ai_gateway/routers/chat.py`
  - 직접 upstream 호출 코드를 runtime strategy 호출로 치환
- `ai_gateway/main.py`
  - runtime settings/bootstrap 추가
- `django_server/apps/fabrix_chat/models.py`
  - `metadata` JSONField 추가
- 필요 시 `django_server/apps/fabrix_chat/views.py`
  - system log batch save 지원

#### Frontend

- `frontend/src/features/chat/ChatPage.jsx`
  - SSE event_type 해석, system log buffering/persistence
- `frontend/src/features/chat/components/ChatBubble.jsx`
  - legacy system bubble 축소 또는 fallback 역할로 전환
- `frontend/src/hooks/useCommands.js`
  - 수동 `/mcp` 결과도 새 inline system message 규약으로 연결

---

## 6. Sample Code Snippets (선택한 언어로 핵심 모듈 3~4개 제공 – Test Mode 핵심 포함)

아래 코드는 구현 방향을 고정하기 위한 **설계용 sample snippet** 이다.  
실제 프로젝트 반영 시에는 기존 설정/타입/에러 처리 패턴에 맞춰 조정한다.

### 6.1 Settings 모델

```python
from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class McpHostSettings:
    test_mode: bool
    verbose_json: bool
    scenario_path: Path
    discovery_on_startup: bool
    store_system_logs: bool
    max_payload_chars: int
    redact_headers: bool


def _parse_bool(value: str | bool | None, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_mcp_host_settings(secrets: dict, base_dir: Path) -> McpHostSettings:
    host = secrets.get("mcp_host", {})

    # why this decision was made for Test Mode:
    # env override lets developers force offline mode without editing secrets.toml.
    test_mode = _parse_bool(os.getenv("MCP_TEST_MODE"), _parse_bool(host.get("test_mode"), False))

    scenario_value = os.getenv(
        "MCP_TEST_MODE_SCENARIO_PATH",
        host.get("test_mode_scenario_path", "ai_gateway/services/mcp/test_mode/scenarios/default.json"),
    )

    return McpHostSettings(
        test_mode=test_mode,
        verbose_json=_parse_bool(os.getenv("MCP_TEST_MODE_VERBOSE_JSON"), _parse_bool(host.get("test_mode_verbose_json"), True)),
        scenario_path=(base_dir / scenario_value).resolve(),
        discovery_on_startup=_parse_bool(host.get("test_mode_discovery_on_startup"), True),
        store_system_logs=_parse_bool(host.get("test_mode_store_system_logs"), True),
        max_payload_chars=int(host.get("test_mode_max_payload_chars", 4000)),
        redact_headers=_parse_bool(host.get("test_mode_redact_headers"), True),
    )
```

### 6.2 Runtime Factory

```python
from .normal_runtime import NormalChatRuntime
from .test_mode_runtime import TestModeChatRuntime


class ChatRuntimeFactory:
    def __init__(self, settings, host_core, event_emitter):
        self._settings = settings
        self._host_core = host_core
        self._event_emitter = event_emitter

    def create(self):
        if self._settings.test_mode:
            # why this decision was made for Test Mode:
            # keep the mode switch in one place so upstream calls cannot leak from scattered if-statements.
            return TestModeChatRuntime(self._settings, self._host_core, self._event_emitter)
        return NormalChatRuntime(self._settings, self._host_core, self._event_emitter)
```

### 6.3 Deterministic Planner

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class ToolPlan:
    provider: str
    action: str
    params: dict


class DeterministicToolPlanner:
    def __init__(self, scenario_loader):
        self._scenario_loader = scenario_loader

    def plan(self, user_text: str, active_category: str | None = None) -> list[ToolPlan]:
        scenario = self._scenario_loader.match(user_text)
        if scenario is not None:
            return scenario.to_tool_plans(active_category=active_category)

        text = user_text.strip().lower()
        if "카테고리" in text and "문서" in text:
            return [ToolPlan("internal_docs", "list_categories_detail", {})]
        if "안전밸브" in text or "점검 기준" in text:
            params = {"query": user_text, "max_results": 5}
            if active_category:
                params["category"] = active_category
            return [ToolPlan("internal_docs", "search_docs_rag", params)]
        return []
```

### 6.4 Test Mode Runtime 골격

```python
import json


class TestModeChatRuntime:
    def __init__(self, settings, host_core, event_emitter, planner=None):
        self._settings = settings
        self._host_core = host_core
        self._event_emitter = event_emitter
        self._planner = planner

    async def stream_chat(self, req, request_id: str):
        await self._event_emitter.info(
            request_id=request_id,
            title="Runtime selected",
            content="MCP_TEST_MODE is enabled. External LLM call will be bypassed.",
            phase="runtime",
        )

        await self._event_emitter.info(
            request_id=request_id,
            title="Planner",
            content="Simulating LLM tool decision...",
            phase="planning",
        )

        plans = self._planner.plan(req.contents[-1])
        if not plans:
            await self._event_emitter.info(
                request_id=request_id,
                title="Planner",
                content="No tool selected in test mode.",
                phase="planning",
            )
            yield self._sse("assistant_final", {
                "content": "[MCP-TEST] LLM 호출을 생략했습니다. 선택된 MCP tool이 없습니다."
            })
            return

        fragments = []
        for plan in plans:
            await self._event_emitter.debug(
                request_id=request_id,
                title="JSON-RPC Request",
                content=f"{plan.provider}.{plan.action}",
                phase="tool_call",
                raw={"params": plan.params},
            )

            result = await self._host_core.call_tool(
                provider_name=plan.provider,
                tool_name=plan.action,
                arguments=plan.params,
            )
            fragments.append(result.normalized_fragment)

            await self._event_emitter.debug(
                request_id=request_id,
                title="JSON-RPC Response",
                content=f"{plan.provider}.{plan.action} completed",
                phase="tool_call",
                raw=result.raw_result,
            )

        aggregated = self._host_core.merge_fragments(fragments)
        await self._event_emitter.info(
            request_id=request_id,
            title="Aggregated context",
            content="Final context prepared for hypothetical LLM input.",
            phase="context_merge",
            raw=aggregated,
        )

        # why this decision was made for Test Mode:
        # return a small assistant summary so the chat UX still completes a turn without calling upstream.
        yield self._sse("assistant_final", {
            "content": "[MCP-TEST] 외부 LLM 호출 없이 MCP 결과를 수집했습니다."
        })

    def _sse(self, event_type: str, payload: dict) -> str:
        return f"data: {json.dumps({'event_type': event_type, **payload}, ensure_ascii=False)}\n\n"
```

여기서 `aggregated` 는 단순한 file/snippet 개수 요약이 아니라,  
**Normal Mode에서 upstream으로 전달되었을 최종 조립 context와 그 provenance를 확인할 수 있는 payload** 여야 한다.

---

## 7. Best Practices & Edge Cases (MCP spec 준수 + 보안 + maintainability)

### 7.1 반드시 지킬 베스트 프랙티스

1. **같은 host core를 써라**
   - Test Mode라고 해서 별도의 mock host를 만들지 않는다.

2. **공식 SDK를 우선 사용하라**
   - transport/session/message lifecycle은 직접 재구현하지 않는다.

3. **protocol log와 business log를 분리하라**
   - “tool 선택”과 “JSON-RPC raw envelope”는 구분해서 저장한다.

4. **system log는 context에 넣지 마라**
   - UI에는 보여도 `contents`에는 포함하지 않는다.

5. **raw payload는 길이 제한을 둬라**
   - 긴 payload를 그대로 UI/DB에 넣지 말고 truncate + raw copy option 제공

6. **header/token은 항상 redact 하라**
   - remote MCP headers나 auth 값은 UI에 평문 노출 금지

7. **Normal/Test 공용 event schema를 써라**
   - Test Mode 전용 임시 문자열 포맷을 만들지 않는다.

### 7.2 MCP spec 관점의 주의점

- Initialize / capability negotiation 흐름을 우회하지 말 것
- capability cache가 있어도 Test Mode에서 최초 연결 검증은 실제로 수행할 것
- tool/resource/prompt 경계를 섞지 말 것
- stdio transport는 프로세스 시작 실패/종료 코드를 명확히 surface 할 것
- streamable HTTP transport는 상태코드, timeout, 인증 실패를 system log에 드러낼 것

### 7.3 보안/운영상 edge cases

#### A. provider down

증상:
- local fastmcp 미기동
- remote MCP timeout

대응:
- turn 시작 직후 `provider_connect_failed` system log 출력
- planner는 동일 turn 내 추가 tool call 시도 중단
- assistant summary에는 “provider unavailable”를 명시

#### B. capability drift

증상:
- 예전에는 있던 tool이 새 릴리즈에서 사라짐

대응:
- startup discovery snapshot과 turn-time discovery 결과가 다르면 warning log 출력
- cache invalidate 후 재조회

#### C. malformed JSON-RPC response

대응:
- raw body 일부를 debug log로 남김
- normalized fragment 생성 실패 시 turn 종료
- context merge에 부분 성공 결과를 넣을지 여부는 provider adapter 정책으로 고정

#### D. no tool selected

대응:
- 이것도 정상 case로 취급
- “No tool selected in test mode” log 출력
- synthetic assistant summary 반환

#### E. system log 폭증

대응:
- payload char limit
- raw collapse 기본값
- batch persistence
- request_id별 grouping
- **동일 event fingerprint 기준 dedupe/throttle**
- **반복 횟수는 새 band를 계속 만들지 않고 기존 band의 repeat count로 병합**
- **억제(suppressed)된 로그 개수는 별도 summary band 또는 summary line으로 반드시 표시**
- **request 단위 visible band 상한 / raw bytes 상한 설정**
- **같은 source에서 짧은 시간 안에 임계치를 넘기면 raw payload 수집을 중단하고 summary만 남김**

### 7.4 유지보수성 관점의 중요한 결정

Phase 2는 결국 나중에 다음 기능들의 기반이 될 수 있다.

- script mode
- regression replay
- provider conformance testing
- MCP integration smoke test
- future local LLM offline mode

따라서 Test Mode 구현은 **임시 디버그 코드** 가 아니라,  
**호스트 품질 보증 인프라의 첫 번째 버전** 으로 취급하는 것이 맞다.

### 7.5 권장 테스트 범위

1. config flag parsing
2. runtime factory selection
3. deterministic planner matching
4. provider connection + discovery
5. tool call logging shape
6. context merge snapshot
7. zero external LLM call guarantee
8. frontend system log rendering
9. system logs excluded from `contents`
10. persistence on/off behavior

---

## 8. 시스템 메시지 채팅창 화면 출력 UI/UX design

### 8.1 용어 정의와 현재 문제

- **badge**: header나 입력창 근처의 작은 상태 표시. Phase 2에서는 사용하지 않는다.
- **strip**: 대화창 상단에 붙는 가로 상태줄. Phase 2에서는 사용하지 않는다.
- **panel**: 대화 흐름 바깥의 별도 펼침 영역. Phase 2에서는 사용하지 않는다.
- **band**: 대화 흐름 안의 full-width system message. Phase 2에서는 이것만 사용한다.

현재 `ChatBubble.jsx` 의 system message는 중앙 회색 버블이라  
**연결 상태 / discovery / JSON-RPC payload / aggregated context** 를 표현하기에 부족하다.

반대로 panel로 빼면 `/mcp list <카테고리>` 처럼  
**사용자가 실제로 읽어야 하는 시스템 메시지** 가 숨겨진다.

### 8.2 목표 UI

Phase 2에서는 system message를 **대화 메인 플로우 안의 full-width inline system band** 로 렌더링한다.

핵심 개념:

- system message는 대화 흐름 안에 존재한다
- 하지만 user/assistant 버블과는 **명확히 다른 시각 언어** 를 가진다
- 내용형 시스템 메시지(`/mcp list`, `/mcp read`, test mode logs, provider warnings)는 **숨기지 않고 바로 보인다**
- system message는 `role='system'` 이므로 여전히 **LLM `contents` 에는 포함되지 않는다**
- raw JSON 같은 긴 내용은 **각 band 내부에서만 접기/펼치기** 한다

즉, 방향은:

- inline system band 중심 UI**

로 바꾼다.

### 8.2.1 왜 inline band가 더 적합한가

1. `/mcp list` 결과처럼 사용자가 즉시 읽어야 하는 정보가 숨겨지지 않는다.
2. 일반 사용자는 “패널을 열어야만 보이는 시스템 출력”을 강요받지 않는다.
3. system message가 대화의 흐름 속 어디에서 발생했는지 시간순으로 자연스럽게 이해할 수 있다.
4. 여전히 `role='system'` 으로 관리하므로 LLM 대화 컨텍스트는 오염되지 않는다.
5. 개발자용 상세 정보도 각 band 내부에서 접기/펼치면 충분하다.

### 8.2.2 system message의 두 종류

UI 설계를 위해 system message를 두 종류로 나눈다.

#### A. Content-bearing system message

사용자가 실제 내용을 읽어야 하는 메시지다.

예:

- `/mcp list <카테고리>` 결과
- `/mcp read` 결과 요약 또는 문서 내용
- category validation 결과
- memory 명령 결과
- Test Mode의 aggregated context 요약

이 메시지는 **항상 full-width band 본문을 펼친 상태로 렌더링** 한다.

#### B. Operational system message

진행 상태/디버그/프로토콜 로그 중심 메시지다.

예:

- provider connected
- capability discovery completed
- Simulating LLM tool decision...
- JSON-RPC request/response summary
- warning/error runtime event

이 메시지도 기본적으로 inline band로 렌더링하되:

- 짧은 summary는 바로 보이고
- raw payload / verbose detail만 band 내부에서 접기/펼치기 한다.

### 8.2.3 Header strip / Composer badge 제거 정책

Phase 2는 대화형 시스템 출력을 **band 하나로만** 처리한다.

결론:

1. **`/chat` 대화 화면에서는 header/top strip을 두지 않는다.**
2. **입력창 바로 위 왼쪽의 MCP 상태 badge도 완전 제거한다.**
3. 대화형 warning/error/runtime/test-mode 안내는 **inline system band** 로만 표시한다.
4. 전역 앱 오류는 system band가 아니라, 아래 8.2.4의 **app-shell / page-local 정책** 으로 처리한다.

즉, Phase 2는:

- header badge 없음
- composer badge 없음
- top strip 없음
- panel 없음
- **system band 단일 체계 사용**

으로 정리한다.

### 8.2.4 전역 앱 오류 알림 정책

여기서 말하는 “전역 앱 오류”는 chat turn 안에서 발생한 system/runtime 정보와 다르다.  
예를 들면:

- React render crash
- app bootstrap 실패
- route chunk load 실패
- auth/session 만료로 인해 앱 전체 사용이 불가능해지는 경우
- 특정 non-chat 페이지 자체가 데이터를 로드하지 못하는 경우

이런 경우까지 system band로 처리하면 오히려 책임 범위가 섞인다.  
따라서 **Phase 2는 global top header strip을 부활시키지 않고**, 아래처럼 **scope별로 고정 처리** 한다.

#### A. App-shell fatal error

대상:

- React render crash
- lazy chunk load 실패
- route-level fatal exception

처리:

1. `App.jsx` 의 `ErrorBoundary` 를 **정식 app-wide fatal surface** 로 사용한다.
2. 이 경우는 chat system band로 우회하지 않는다.
3. full-page blocking fallback 화면을 사용한다.
4. 사용자가 취할 수 있는 액션은 `reload` 또는 `login으로 이동` 같은 복구 동작만 제공한다.

#### B. Auth / session 전역 오류

대상:

- 인증 토큰 만료
- 전역 401/403으로 현재 앱 세션을 유지할 수 없는 경우

처리:

1. chat header strip이나 system band에 남겨두지 않는다.
2. 세션을 정리하고 로그인 화면으로 이동한다.
3. 로그인 화면 또는 auth 전용 페이지에서 **page-local error message** 로 이유를 명시한다.

#### C. Non-chat page local error

대상:

- settings 저장 실패
- data explorer fetch 실패
- uploader validation 실패

처리:

1. 해당 feature/page 내부의 **local inline error block** 으로 표시한다.
2. global top header strip은 사용하지 않는다.
3. chat system band도 사용하지 않는다.

#### D. FabriX Chat conversation runtime error

대상:

- MCP provider warning
- tool call 실패
- discovery mismatch
- test mode planning/runtime 로그

처리:

1. `role='system'` 기반 **inline system band** 로 표시한다.
2. header strip, toast, global banner는 사용하지 않는다.

최종 결정:

1. **전역 top header 오류/경고 줄은 삭제한다.**
2. **전역 toast/notification center를 Phase 2에서 도입하지 않는다.**
3. 오류 표면은 scope별로 고정한다:
   - app-shell fatal -> ErrorBoundary full-page fallback
   - auth/session 전역 오류 -> login/auth page-local message
   - non-chat page 오류 -> 해당 page local inline error
   - chat runtime 오류 -> inline system band

### 8.3 권장 레이아웃

```text

User bubble

╔════════════════ SYSTEM ═════════════════════╗
║ /mcp list 배관기준                          ║
║                                             ║
║ 1. valve-checklist.md                       ║
║ 2. pressure-standard.md                     ║
║ 3. safety-guide.md                          ║
║                                             ║
║ [copy]                                      ║
╚═════════════════════════════════════════════╝

Assistant bubble

╔══════════════ MCP-TEST / DEBUG ═════════════╗
║ Simulating LLM tool decision...             ║
║ Provider: internal_docs                     ║
║ Tool: search_docs_rag                       ║
║ [show raw]                                  ║
╚═════════════════════════════════════════════╝
```

### 8.3.1 레이아웃 원칙

1. system band는 **대화 영역 전체 폭** 을 가로지른다.
2. user/assistant bubble처럼 좌우 정렬하지 않는다.
3. 위아래에 **회색 실선(gray thin line)** 구분선을 둔다.
4. 배경은 연한 회색/슬레이트 계열로 하되, 대화 버블과 구분되는 평평한(flat) 스타일을 사용한다.
5. Markdown 렌더링을 지원한다(table 출력 가능).
6. 텍스트는 강제로 수평 중앙정렬하지 않는다.


### 8.3.2 긴 출력 처리 규칙

긴 시스템 메시지는 band 자체를 숨기지 않고, **band 내부의 상세 부분만** 접는다.

정확한 규칙:

1. 제목/요약 1~3줄은 항상 펼쳐 보인다.
2. raw JSON / 긴 목록 / 전문 텍스트는 `Show more` 로 접을 수 있다.
3. `/mcp list` 결과처럼 핵심이 “목록 그 자체”인 경우는 기본 펼침 상태로 둔다.
4. `search_docs_rag` raw payload 같은 디버그성 세부정보는 기본 접힘 상태로 둔다.

즉, 접힘의 단위는 **패널 전체가 아니라 각 system band 내부의 detail section** 이다.

### 8.3.3 WARN/ERROR 표시 규칙

WARN/ERROR는 **별도 header surface 없이** system band로만 표시한다.

권장 규칙:

1. 새로운 WARN/ERROR가 발생하면 해당 시점에 full-width system band를 즉시 추가한다.
2. band 라벨, border, accent color로 심각도를 명확히 드러낸다.
3. active conversation 중 새 WARN/ERROR가 발생하면 일반 새 메시지처럼 해당 위치가 자연스럽게 보이도록 스크롤 흐름에 포함한다.
4. 과거 WARN/ERROR를 다시 확인하는 방식도 별도 header indicator가 아니라 **대화 히스토리 내 band 재탐색** 이다.

### 8.4 시각 규칙

| 요소 | 권장 스타일 |
|---|---|
| System band 폭 | 대화 메인창 전체 폭 |
| 구분선 | 회색 이중 실선 또는 두꺼운 상/하단 룰 |
| 배경 | 밝은 회색/슬레이트 |
| 제목행 | 작은 대문자 라벨 + 아이콘/상태 |
| 본문 | markdown 렌더링 |
| raw detail | band 내부 collapsible section |
| INFO | 회색/청회색 |
| DEBUG | 옅은 회색 |
| WARN | 황색 포인트 |
| ERROR | 적색 포인트 |

### 8.4.1 band 타입별 라벨 예시

- `SYSTEM`
- `MCP`
- `MCP-TEST`
- `WARNING`
- `ERROR`
- `COMMAND RESULT`

라벨은 메시지 종류를 구분하기 위한 것으로,  
UI를 지나치게 화려하게 만들지 않도록 짧고 일관되게 유지한다.

### 8.4.2 header 디자인과의 관계

중요:

1. **기존 Chat Header의 내부 레이아웃은 Phase 2 범위에서 재설계하지 않는다.**
2. header 내부에 badge나 strip을 추가하지 않는다.
3. 입력창 근처에도 MCP 상태 badge를 두지 않는다.
4. system message의 표시 위치는 header/composer가 아니라 **대화 흐름 내부** 다.
5. 따라서 header/composer와 system message UI는 역할이 분리된다.
6. app-wide fatal error surface가 필요할 때는 header가 아니라 `App.jsx` 의 ErrorBoundary fallback이 담당한다.

### 8.5 대화형 시스템 메시지 공통 적용 원칙

이 inline system band UI는 **test mode 전용이 아니라 chat conversation 공통 system message renderer** 여야 한다.

즉:

- Test Mode: 상세 MCP 활동 로그
- Normal Mode: `/mcp` 수동 명령 결과, provider warning, runtime info

를 모두 같은 구조로 보여준다.

이렇게 해야:

- mode마다 UI가 달라지지 않고
- 사용자가 system message를 읽는 법을 한 번만 익히면 되며
- 수동 명령 결과와 테스트 로그가 같은 규약으로 정리된다

### 8.6 프런트엔드 구현 포인트

1. `SystemMessageBand.jsx` 추가
2. `SystemMessageMeta.jsx` 추가
3. `SystemMessageRaw.jsx` 추가
4. `messages` 배열 내 structured system message를 band로 렌더링
5. `ChatPage.jsx` 에서 SSE `system_log` 를 `role='system'` 항목으로 축적
6. 현재 `ChatBubble.jsx` 의 중앙 system bubble은 제거하거나 `SystemMessageBand` 로 대체
7. `/mcp` 와 memory 명령도 같은 `system_log` 포맷으로 정규화

### 8.6.1 기존 top strip 및 composer MCP badge 제거 계획

이 부분은 **실수 방지를 위해 명시적으로 삭제 대상으로 관리** 한다.

정확한 원칙:

1. 기존 top strip은 **유지하지 않는다.**
2. 기존 입력창 바로 위 왼쪽 MCP 상태 badge도 **유지하지 않는다.**
3. 단순 hide 처리나 CSS 비노출로 남겨두지 않는다.
4. 상태 저장 state, props, context, reducer, SSE mapping, dismiss timer, 스타일 규칙까지 **legacy 경로 전체를 제거** 한다.
5. top strip이나 composer badge에 연결되어 있던 system output producer가 있다면 모두 `system_log` -> `role='system'` -> `SystemMessageBand` 경로로 이관한다.
6. 이관 후에는 strip/badge 경로에 system status를 보내는 코드가 남지 않아야 한다.

구현 체크리스트:

1. top strip 렌더링 컴포넌트 삭제
2. composer MCP badge 렌더링 컴포넌트 삭제
3. 관련 CSS/className/style 삭제
4. 관련 state/store/selector/props 삭제
5. auto-dismiss/open/close, badge on/off 같은 strip/badge 전용 제어 로직 삭제
6. 관련 테스트/스냅샷이 있다면 inline system band 기준으로 갱신
7. 최종적으로 “대화형 system output은 오직 system band로만 보인다”는 조건을 확인
8. app-shell fatal error 처리는 strip/badge가 아니라 ErrorBoundary fallback 경로만 남도록 확인

### 8.6.2 반복 로그/무한 생성 제어 대책

system band로 통합하더라도, 같은 warning/error/log가 반복 생성되면 UI와 persistence가 다시 오염될 수 있다.  
따라서 Phase 2 계획에는 아래 제어를 포함한다.

핵심 원칙:

1. **같은 이벤트를 무한히 새 band로 추가하지 않는다.**
2. 사용자에게 중요한 사실은 숨기지 않되, 반복 출력은 **병합(coalescing)** 한다.
3. 억제된 로그가 있으면 그 사실 자체는 **가시적으로 남긴다.**

권장 제어 방식:

1. `severity + phase + provider + tool + normalized content + request_id` 기준으로 event fingerprint를 만든다.
2. 짧은 sliding window 안에서 같은 fingerprint가 반복되면 **새 band를 만들지 않고 기존 band의 repeat count** 를 증가시킨다.
3. repeat count 예시:
   - `WARNING`
   - `Provider timeout detected`
   - `Repeated 12 times in 5s`
4. raw payload는 첫 번째 또는 최근 1건만 유지하고, 반복본 전체를 계속 붙이지 않는다.
5. request당 visible system band 수에 상한을 둔다. 기본값은 **20**으로 두고, 이 상한은 평상시 로그를 자주 자르기 위한 값이 아니라 **비정상적인 flooding으로 브라우저가 마비되는 상황을 막는 차단장치** 로 사용한다.
6. request당 raw payload 누적 bytes에도 상한을 둔다.
7. 임계치 초과 시에는 `Additional 37 repeated warning logs were collapsed.` 같은 **summary band** 를 남긴다.
8. 같은 source가 runaway 상태가 되면 raw payload 수집은 중단하고 summary만 계속 업데이트한다.
9. persistence도 같은 규칙으로 병합 저장하여 DB row가 폭증하지 않게 한다.

### 8.7 UX 세부 규칙

#### 기본 동작

1. system message가 생성되면 **즉시 대화 흐름 안에 새 band가 추가** 된다.
2. 사용자는 별도 상단 surface 조작 없이 메시지를 읽을 수 있다.
3. 최신 system message는 일반 대화 메시지처럼 스크롤 흐름에 따라 바로 보인다.

#### `/mcp list` 같은 목록형 결과

1. 기본 펼침
2. markdown list 렌더링
3. 파일 수가 많아도 우선 목록 자체를 보여준다
4. 필요 시 band 내부에 “접기/더 보기”를 둔다

#### JSON-RPC raw payload

1. summary는 기본 표시
2. raw payload는 기본 접힘
3. `show raw` / `hide raw` 토글은 각 band 내부에 둔다

#### WARN/ERROR 발생 시 동작

1. 해당 시점에 WARN/ERROR system band를 즉시 추가한다.
2. band 라벨과 border/accent 색으로 심각도를 명확히 드러낸다.
3. 별도 상단 latest-error indicator는 두지 않는다.

#### 반복 로그 발생 시 동작

1. 같은 fingerprint의 WARN/ERROR/system log가 짧은 시간 안에 반복되면 새 band를 계속 추가하지 않는다.
2. 기존 band의 repeat count 또는 summary line을 갱신한다.
3. suppression이 발생하면 `collapsed`, `suppressed`, `repeated N times` 같은 문구로 사용자에게 명시한다.
4. raw payload는 band 내부에 1건만 유지하거나 최근본으로 교체한다.

#### 사용자가 직접 조작하는 규칙

1. `show raw` 클릭 -> 현재 band의 raw detail 펼침
2. `hide raw` 클릭 -> 현재 band의 raw detail 접기
3. `copy` 클릭 -> 현재 band 본문 또는 raw JSON 복사

#### 읽기 우선순위

사용자가 화면을 위에서 아래로 읽을 때 다음 순서로 이해되도록 한다.

1. **System band 제목/라벨**: 이 메시지가 무엇인가
2. **System band 본문**: 어떤 정보가 전달되는가
3. **Assistant Bubble**: 사용자 관점의 최종 응답이 무엇인가

### 8.7.1 권장 컴포넌트 조합

```text
ChatPage
  ├─ ChatHeader
  ├─ MessageList
  │    ├─ UserBubble
  │    ├─ AssistantBubble
  │    └─ SystemMessageBand
  │         ├─ SystemMessageMeta
  │         └─ SystemMessageRaw
  └─ InputBox
```

### 8.8 Phase 2 UI 완료 기준

1. `/mcp list`, `/mcp read`, Test Mode 로그가 **숨겨지지 않고 대화 흐름에서 바로 읽힌다.**
2. system message가 user/assistant bubble과 시각적으로 명확히 구분된다.
3. system message는 대화 플로우 안에 있지만 `contents` 에는 포함되지 않는다.
4. raw payload 같은 긴 내용은 각 band 내부에서만 접고 펼칠 수 있다.
5. Normal Mode와 Test Mode 모두 같은 system message rendering 규약을 사용한다.
6. user/assistant 대화 가독성을 해치지 않는다.
7. header 내부에 별도의 WARN/ERROR 표시 surface를 만들지 않는다.
8. 동일 warning/error가 반복되어도 system band가 무한 증식하지 않는다.
9. app-wide/global 오류를 이유로 chat header strip이 다시 도입되지 않는다.

---

이 문서는 **Phase 2 계획 문서 작성 완료본**이다.

- 현재는 **구현을 시작하지 않는다.**
- 이 문서는 Phase 1 이후 오프라인 MCP 검증을 가능하게 하는 Test Mode의 구조적 설계 기준이다.
- 구현 시에는 반드시 **공식 MCP spec / official SDK / `mcphost` / `Dive` / Inspector** 기준을 먼저 확인한 뒤 진행한다.
