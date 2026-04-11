# Agentic Runtime Orchestrator 설계서

> **문서 버전**: 1.2  
> **작성일**: 2026-04-11  
> **상태**: 연구 완료, 구현 대기  
> **변경 이력**:  
> - v1.2 - Celery 기술적 타당성 분석 및 asyncio 기반 구현 상세 추가  
> - v1.1 - 멀티 모델 아키텍처(Gemma 3 Router) 섹션 추가

---

## 1. 배경 및 목적

### 1.1 현재 상태 분석

현재 FabriX Chat 시스템은 **single-pass multi-MCP fan-out** 구조로 동작합니다:

```
사용자 입력 → Planner가 MCP plan 선택 → MCP 실행 → context 병합 → LLM 1회 호출
```

| Runtime | 동작 방식 | LLM 호출 |
|---------|----------|---------|
| `NormalChatRuntime` | `build_chat_resolution()` → context 병합 → `stream_chat()` | **1회** |
| `TestModeChatRuntime` | planner → tool 실행 → synthetic summary | **0회** (우회) |

### 1.2 현재 한계점

1. **1차 LLM 응답 후 추가 MCP 호출 불가**: LLM이 "더 많은 정보가 필요합니다"라고 응답해도 자동으로 추가 검색 수행 불가
2. **MCP 간 체인 불가**: MCP A의 결과를 MCP B의 입력으로 전달하는 파이프라인 없음
3. **자율적 도구 선택 불가**: LLM이 스스로 어떤 MCP 도구를 호출할지 결정하는 구조 없음

### 1.3 목표

Claude Desktop, Cursor 등의 미니멀 버전과 유사한 **agentic multi-step chat** 구현:

```
사용자 입력 → LLM 응답 → [tool call 감지] → MCP 실행 → 결과 주입 → LLM 재호출 → ... → 최종 응답
```

---

## 2. 아키텍처 비교

### 2.1 현재 아키텍처 (Single-Pass)

```
┌──────────────────────────────────────────────────────────────┐
│  User Input                                                   │
└────────────────────────┬─────────────────────────────────────┘
                         ▼
┌──────────────────────────────────────────────────────────────┐
│  SharedPlannerCore.plan()                                     │
│  → PlannerDecision(route, plans)                              │
└────────────────────────┬─────────────────────────────────────┘
                         ▼
┌──────────────────────────────────────────────────────────────┐
│  GenericMcpHost.build_chat_resolution()                       │
│  → 여러 plan 병렬 실행 → context 병합                          │
└────────────────────────┬─────────────────────────────────────┘
                         ▼
┌──────────────────────────────────────────────────────────────┐
│  FabrixUpstreamClient.stream_chat() [1회 호출]                │
│  → LLM 최종 응답                                              │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 목표 아키텍처 (Agentic Loop)

```
┌──────────────────────────────────────────────────────────────┐
│  User Input                                                   │
└────────────────────────┬─────────────────────────────────────┘
                         ▼
┌──────────────────────────────────────────────────────────────┐
│  AgenticOrchestrator                                          │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Step Loop (max_steps 제한)                             │  │
│  │  ┌─────────────────────────────────────────────────┐   │  │
│  │  │  1. LLM 호출 (with tool definitions)            │   │  │
│  │  │  2. 응답 파싱: tool_call 감지                    │   │  │
│  │  │  3. tool_call 있으면:                           │   │  │
│  │  │     → MCP 실행 → 결과 context 추가 → Step 1로   │   │  │
│  │  │  4. tool_call 없으면:                           │   │  │
│  │  │     → 최종 응답 반환                             │   │  │
│  │  └─────────────────────────────────────────────────┘   │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. 구현 패턴 분석

### 3.1 패턴 A: Client-side Orchestration

**개요**: 백엔드(ai_gateway)에서 LLM 응답을 파싱하여 tool call을 감지하고, MCP를 재호출한 후 결과를 주입하여 LLM을 다시 호출

**구현 위치**: `ai_gateway/services/mcp/runtime/agentic_runtime.py` (신규)

```python
class AgenticChatRuntime(BaseChatRuntime):
    MAX_STEPS = 10  # 무한 루프 방지

    async def stream_chat(self, runtime_input: ChatRuntimeInput) -> AsyncIterator[str]:
        messages = self._build_initial_messages(runtime_input)
        tool_definitions = await self._build_tool_definitions()
        
        for step in range(self.MAX_STEPS):
            response = await self._call_llm(messages, tool_definitions)
            
            tool_calls = self._extract_tool_calls(response)
            if not tool_calls:
                # 최종 응답
                yield self._serialize_final_response(response)
                return
            
            # tool call 실행 및 결과 추가
            for tool_call in tool_calls:
                result = await self.mcp_host.execute_tool_action(
                    action=tool_call.name,
                    arguments=tool_call.arguments,
                    provider_id=tool_call.provider,
                )
                messages.append(self._build_tool_result_message(tool_call, result))
            
            yield self._serialize_step_event(step, tool_calls)
        
        # max_steps 도달
        yield self._serialize_max_steps_warning()
```

**장점**:
- 완전한 제어권
- FabriX API 변경 없이 구현 가능
- 상세한 디버깅/로깅 가능

**단점**:
- LLM 응답 형식에 의존 (tool_call JSON 파싱 필요)
- 구현 복잡도 높음
- LLM별 tool_call 형식 차이 처리 필요

### 3.2 패턴 B: MCP Server-side Sampling (MCP 표준)

**개요**: FastMCP 2.14+의 `ctx.sample()` 기능을 활용하여 MCP 서버 내부에서 LLM을 호출하고 multi-step 작업 수행

**MCP 표준 참조**: [SEP-1577](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1577)

```python
# FastMCP 서버 내부 구현 예시
from fastmcp import FastMCP, Context

mcp = FastMCP()

def search_docs(query: str) -> str:
    """내부 문서 검색"""
    return f"검색 결과: {query}"

def read_doc(filename: str) -> str:
    """문서 읽기"""
    return f"문서 내용: {filename}"

@mcp.tool
async def research_topic(topic: str, ctx: Context) -> str:
    """주제에 대해 연구하고 종합 분석 제공"""
    result = await ctx.sample(
        messages=f"다음 주제를 연구하세요: {topic}",
        tools=[search_docs, read_doc],  # LLM이 자동으로 도구 선택
        max_tokens=2000,
    )
    return result.text
```

**장점**:
- MCP 표준 준수
- FastMCP가 agentic loop 자동 처리
- 서버측 로직 캡슐화

**단점**:
- MCP 서버에 LLM 접근 권한 필요 (sampling_handler 설정)
- 현재 fastmcp 서버 구조 변경 필요
- 클라이언트는 최종 결과만 수신 (중간 단계 불투명)

---

## 4. 멀티 모델 아키텍처 (Intent Router)

### 4.1 개요

현재 시스템은 GPT-OSS-120b 단일 모델만 사용합니다. 그러나 FabriX 서버에는 **Gemma 3** 같은 경량 모델도 있어, 이를 **의도 분류(intent classification)** 및 **도구 선택(tool routing)**에 활용할 수 있습니다.

```
┌──────────────────────────────────────────────────────────────────────┐
│  User Input                                                           │
└─────────────────────────┬────────────────────────────────────────────┘
                          ▼
┌──────────────────────────────────────────────────────────────────────┐
│  [Small Model Router] Gemma 3                                         │
│  • 사용자 의도 분류 (일반대화/문서검색/코드분석/...)                    │
│  • 필요한 MCP provider/tool 결정                                       │
│  • 빠른 응답, 낮은 비용                                                │
└─────────────────────────┬────────────────────────────────────────────┘
                          ▼
┌──────────────────────────────────────────────────────────────────────┐
│  [MCP Tool Execution] 선택된 도구들 병렬 실행                          │
│  • 문서 검색, RAG, 코드 분석 등                                        │
└─────────────────────────┬────────────────────────────────────────────┘
                          ▼
┌──────────────────────────────────────────────────────────────────────┐
│  [Main Model] GPT-OSS-120b                                            │
│  • MCP 결과를 context로 활용                                           │
│  • 최종 응답 생성 (높은 품질)                                          │
└──────────────────────────────────────────────────────────────────────┘
```

### 4.2 기존 인프라 활용 가능성

현재 코드베이스 분석 결과, 멀티 모델 지원이 **이미 가능**합니다:

```python
# ai_gateway/routers/chat.py - 이미 model list API 존재
@router.get("/models")
async def get_models(request: Request, page: int = 1, limit: int = 50):
    """FabriX에서 사용 가능한 LLM Model 목록을 조회"""
    ...

# ai_gateway/services/mcp/runtime/upstream.py - model_ids 배열 지원
async def stream_chat(
    self,
    *,
    model_ids: list[str],  # 이미 리스트로 모델 전달 가능
    contents: list[str],
    ...
):
    payload = {
        "modelIds": model_ids,  # FabriX API에 여러 모델 전달 가능
        ...
    }
```

### 4.3 Small Model Router 설계

```python
from dataclasses import dataclass
from typing import Literal

@dataclass
class RoutingDecision:
    """Small model의 라우팅 결정"""
    intent: Literal[
        "general_chat",       # 일반 대화 - MCP 불필요
        "document_search",    # 문서 검색 - internal_docs provider
        "code_analysis",      # 코드 분석 - (미래 provider)
        "multi_tool",         # 복합 작업 - 여러 provider 필요
    ]
    providers: list[str]      # 활성화할 MCP provider IDs
    tools: list[str]          # 호출할 특정 도구들 (선택적)
    reasoning: str            # 라우팅 근거 (디버깅용)
    confidence: float         # 신뢰도 (0.0~1.0)


class SmallModelRouter:
    """경량 모델을 사용한 의도 분류 및 도구 선택"""
    
    SMALL_MODEL_ID = "gemma-3-8b"  # 또는 동적으로 모델 목록에서 선택
    
    def __init__(
        self,
        upstream_client: FabrixUpstreamClient,
        available_providers: list[str],
    ):
        self.upstream = upstream_client
        self.available_providers = available_providers
    
    async def route(self, user_message: str, history: list[str]) -> RoutingDecision:
        """사용자 메시지를 분석하여 라우팅 결정"""
        
        routing_prompt = self._build_routing_prompt(user_message, history)
        
        # Small model 호출 (non-streaming, 빠른 응답)
        response = await self._call_small_model(routing_prompt)
        
        return self._parse_routing_response(response)
    
    def _build_routing_prompt(self, user_message: str, history: list[str]) -> str:
        return f"""당신은 사용자 의도를 분류하고 필요한 도구를 선택하는 라우터입니다.

사용 가능한 MCP providers: {self.available_providers}

사용자 메시지: {user_message}

다음 JSON 형식으로 응답하세요:
{{
    "intent": "general_chat | document_search | code_analysis | multi_tool",
    "providers": ["provider_id1", "provider_id2"],
    "tools": ["specific_tool_name"],
    "reasoning": "라우팅 근거 설명",
    "confidence": 0.95
}}"""
    
    async def _call_small_model(self, prompt: str) -> str:
        """Small model 호출 (non-streaming)"""
        response_text = ""
        async for chunk in self.upstream.stream_chat(
            model_ids=[self.SMALL_MODEL_ID],
            contents=[prompt],
            is_stream=False,  # 빠른 응답을 위해 non-streaming
            llm_config={"max_tokens": 200, "temperature": 0.1},
        ):
            response_text += chunk
        return response_text
```

### 4.4 Agentic Orchestrator 통합

```python
class AgenticOrchestrator:
    """멀티 모델 기반 Agentic Orchestrator"""
    
    def __init__(
        self,
        mcp_host: GenericMcpHost,
        upstream_client: FabrixUpstreamClient,
        main_model_id: str = "gpt-oss-120b",
        router_model_id: str = "gemma-3-8b",
        use_router: bool = True,  # 라우터 사용 여부
    ):
        self.mcp_host = mcp_host
        self.upstream = upstream_client
        self.main_model = main_model_id
        self.router_model = router_model_id
        self.use_router = use_router
        
        if use_router:
            self.router = SmallModelRouter(
                upstream_client=upstream_client,
                available_providers=self._get_provider_ids(),
            )
    
    async def run(self, user_message: str, history: list[str]) -> AsyncIterator[str]:
        """Agentic loop with multi-model routing"""
        
        # Step 1: Small model로 의도 분류 및 도구 선택
        if self.use_router:
            yield self._emit_event("routing_start", {"model": self.router_model})
            
            routing = await self.router.route(user_message, history)
            
            yield self._emit_event("routing_complete", {
                "intent": routing.intent,
                "providers": routing.providers,
                "confidence": routing.confidence,
            })
            
            # 일반 대화면 MCP 스킵
            if routing.intent == "general_chat" and routing.confidence > 0.9:
                yield self._emit_event("skip_mcp", {"reason": "general_chat"})
                async for chunk in self._call_main_model(user_message, history, None):
                    yield chunk
                return
            
            # MCP 실행 대상 결정
            target_providers = routing.providers
        else:
            target_providers = None  # 기존 planner 사용
        
        # Step 2: MCP 도구 실행
        mcp_context = await self._execute_mcp(user_message, target_providers)
        
        # Step 3: Main model로 최종 응답
        async for chunk in self._call_main_model(user_message, history, mcp_context):
            yield chunk
```

### 4.5 모델 목록 동적 로딩

사용자가 Router 모델을 선택할 수 있도록 설정 UI 지원:

```python
# ai_gateway/services/mcp/config.py 확장
@dataclass
class AgenticConfig:
    """Agentic runtime 설정"""
    enabled: bool = False
    max_steps: int = 10
    timeout_seconds: float = 120.0
    
    # 멀티 모델 설정
    use_router: bool = True
    router_model_id: str | None = None  # None이면 자동 선택
    router_model_pattern: str = r"gemma|phi|qwen.*small"  # 자동 선택 패턴
    main_model_id: str | None = None  # None이면 프론트엔드 선택 사용


async def select_router_model(request: Request) -> str:
    """사용 가능한 모델 중 router에 적합한 모델 자동 선택"""
    import re
    
    models_response = await request.app.state.http_client.get(
        f"{get_fabrix_chat_config()[1]}/models",
        headers=get_fabrix_chat_headers(),
    )
    models = models_response.json().get("data", [])
    
    # 경량 모델 패턴 매칭
    pattern = re.compile(r"gemma|phi|qwen.*small|llama.*8b", re.IGNORECASE)
    for model in models:
        if pattern.search(model.get("id", "")):
            return model["id"]
    
    # fallback: 첫 번째 모델
    return models[0]["id"] if models else "gpt-oss-120b"
```

### 4.6 장점 및 고려사항

| 측면 | 장점 | 고려사항 |
|------|------|----------|
| **비용** | Router 호출 비용 << Main model | 추가 API 호출 오버헤드 |
| **속도** | Small model 응답 빠름 (~100ms) | 총 latency 증가 가능 |
| **정확도** | 명확한 의도는 높은 정확도 | 모호한 의도는 Main model로 fallback 필요 |
| **유연성** | 도구 선택 로직 분리 | 프롬프트 튜닝 필요 |

### 4.7 Fallback 전략

```python
class SmallModelRouter:
    CONFIDENCE_THRESHOLD = 0.7
    
    async def route_with_fallback(
        self,
        user_message: str,
        history: list[str],
    ) -> RoutingDecision:
        """신뢰도 낮으면 기존 SharedPlannerCore fallback"""
        
        decision = await self.route(user_message, history)
        
        if decision.confidence < self.CONFIDENCE_THRESHOLD:
            # 기존 planner 사용
            logger.info(
                "Router confidence %.2f < threshold, falling back to SharedPlanner",
                decision.confidence,
            )
            return RoutingDecision(
                intent="fallback",
                providers=[],  # planner가 결정
                tools=[],
                reasoning="Low confidence, using SharedPlannerCore",
                confidence=0.0,
            )
        
        return decision
```

---

## 5. Celery vs asyncio 기술적 비교

### 5.1 Celery 도입 기술적 타당성 분석

#### 5.1.1 현재 아키텍처 의존성 분석

| 구성요소 | 의존 객체 | Celery 호환성 | 난이도 |
|---------|----------|--------------|--------|
| **FabrixUpstreamClient** | `request.app.state.http_client` | ❌ **불가** - Celery worker에서 Request 객체 접근 불가 | 🔴 높음 |
| **GenericMcpHost** | `McpSettings` (앱 시작 시 로드) | ⚠️ **중간** - 별도 로드 가능하나 재설계 필요 | 🟡 중간 |
| **doc_converter** | `http_client` 파라미터 전달 | ⚠️ **중간** - 별도 httpx 클라이언트 생성 필요 | 🟡 중간 |
| **Chat SSE 스트리밍** | `AsyncIterator` + `StreamingResponse` | ❌ **불가** - Celery는 실시간 스트리밍 미지원 | 🔴 높음 |
| **asyncio.Lock** | 단일 프로세스 내 직렬화 | ⚠️ **중간** - Redis 분산 Lock으로 대체 필요 | 🟡 중간 |

#### 5.1.2 핵심 Blocking 이슈

**1. httpx.AsyncClient 의존성 (난이도: 🔴 높음)**
```python
# 현재 코드 - FastAPI Request에 바인딩
async with self._request.app.state.http_client.stream(...) as response:
    async for line in response.aiter_lines():
        yield f"data: {json.dumps(data)}\n\n"
```
- Celery task는 별도 프로세스 → `request.app.state` 접근 불가
- **해결 비용**: 모든 upstream 호출 코드 리팩토링 (약 10개 파일, 500+ LOC)
- **부작용**: 연결 풀 공유 불가 → 성능 저하

**2. SSE 실시간 스트리밍 (난이도: 🔴 심각)**
```python
# 현재 코드 - Generator 기반 스트리밍
async def stream_chat(...) -> AsyncIterator[str]:
    async for line in response.aiter_lines():
        yield f"data: {json.dumps(data)}\n\n"
```
- Celery는 **작업 완료 후 결과 반환** 모델 → 토큰 단위 스트리밍 불가
- **해결 비용**: WebSocket + Redis Pub/Sub 별도 구축 필요 (1~2주 추가 공수)
- **복잡도**: 기존 SSE 프론트엔드 전면 재작성

**3. async/await와 Celery 혼용 (난이도: 🟡 중간)**
```python
# 현재 - 전체가 async 기반
async def build_chat_resolution(...):
    resolution = await self.mcp_host.build_chat_resolution(...)
```
- Celery task는 기본 동기 실행
- `asyncio.run()` 래퍼 사용 시 이벤트 루프 충돌 위험
- **해결 비용**: `celery[gevent]` 설정 또는 sync 래퍼 추가

#### 5.1.3 Agentic Loop에 Celery 적합성

| 요구사항 | Celery 적합성 | 이유 |
|---------|--------------|------|
| LLM 응답 실시간 스트리밍 | ❌ **부적합** | 작업 완료까지 결과 수신 불가 |
| Multi-step 상태 관리 | ⚠️ 부분적 | chain/chord 가능하나 복잡 |
| Tool 실행 병렬화 | ✅ 적합 | `group()`으로 병렬 실행 가능 |
| 재시도/복구 | ✅ 적합 | 내장 retry 메커니즘 |
| GPU 작업 직렬화 | ✅ 적합 | 단일 worker concurrency=1 |

#### 5.1.4 Celery 결론

> **Celery 도입은 현재 코드베이스에서 기술적으로 타당하지 않음**

**이유**:
1. Chat 앱 핵심 기능인 **SSE 스트리밍과 호환 불가**
2. `httpx.AsyncClient` 의존성 제거에 **대규모 리팩토링 필요** (2~3주)
3. Agentic loop의 **실시간 step 진행 상황 전달 불가**

**적합한 사용처** (선택적 도입 가능):
- ✅ Doc Uploader 변환 작업 (이미 BackgroundTasks 사용 중)
- ✅ Data Explorer DuckDB 리빌드 (이미 threading 사용 중)
- ❌ Chat 스트리밍 (부적합)
- ❌ Agentic Orchestrator (부적합)

---

### 5.2 asyncio 기반 구현 (권장 방안)

#### 5.2.1 설계 원칙

현재 코드베이스의 async 인프라를 그대로 활용하여 Agentic Orchestrator를 구현합니다:

1. **기존 패턴 유지**: `StreamingResponse` + `AsyncIterator` SSE 스트리밍
2. **httpx 클라이언트 재활용**: `request.app.state.http_client` 공유
3. **MCP Host 통합**: 기존 `GenericMcpHost.execute_tool_action()` 활용
4. **점진적 마이그레이션**: `NormalChatRuntime` 확장 후 독립 클래스 분리

#### 5.2.2 아키텍처 다이어그램

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  FastAPI (uvicorn)                                                          │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  /chat-messages/stream Endpoint                                       │  │
│  │  └─ StreamingResponse(agentic_runtime.stream_chat())                  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                          │                                   │
│                                          ▼                                   │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  AgenticChatRuntime (신규)                                             │  │
│  │  ┌─────────────────────────────────────────────────────────────────┐  │  │
│  │  │  async def stream_chat() -> AsyncIterator[str]:                 │  │  │
│  │  │      for step in range(MAX_STEPS):                              │  │  │
│  │  │          response = await self._call_llm_async()                │  │  │
│  │  │          tool_calls = self._extract_tool_calls(response)        │  │  │
│  │  │          if not tool_calls:                                     │  │  │
│  │  │              yield final_response                               │  │  │
│  │  │              return                                             │  │  │
│  │  │          results = await asyncio.gather(*[                      │  │  │
│  │  │              self._execute_tool_async(tc) for tc in tool_calls  │  │  │
│  │  │          ])                                                     │  │  │
│  │  │          messages.extend(tool_results)                          │  │  │
│  │  │          yield step_progress_event                              │  │  │
│  │  └─────────────────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                          │                              │                    │
│                          ▼                              ▼                    │
│  ┌───────────────────────────────┐   ┌───────────────────────────────────┐  │
│  │  FabrixUpstreamClient         │   │  GenericMcpHost                   │  │
│  │  • stream_chat() (기존)        │   │  • execute_tool_action() (기존)   │  │
│  │  • httpx.AsyncClient 재활용    │   │  • FastMCP Client 통합            │  │
│  └───────────────────────────────┘   └───────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 5.2.3 핵심 구현 클래스

```python
# ai_gateway/services/mcp/runtime/agentic_runtime.py

from dataclasses import dataclass, field
from typing import AsyncIterator, Any
import asyncio
import json
import re
import time

from .base_runtime import BaseChatRuntime, ChatRuntimeInput
from .upstream import FabrixUpstreamClient
from ..host import GenericMcpHost


@dataclass
class ToolCall:
    """LLM이 요청한 도구 호출"""
    id: str
    name: str
    arguments: dict[str, Any]
    provider: str | None = None


@dataclass
class AgenticConfig:
    """Agentic runtime 설정"""
    max_steps: int = 10
    max_tool_calls_per_step: int = 5
    max_tokens_per_step: int = 4000
    step_timeout_seconds: float = 30.0
    total_timeout_seconds: float = 120.0
    allowed_tools: set[str] | None = None  # None = 모두 허용


@dataclass
class AgenticState:
    """Agentic loop 실행 상태"""
    step: int = 0
    total_tool_calls: int = 0
    total_tokens: int = 0
    start_time: float = field(default_factory=time.time)
    messages: list[dict] = field(default_factory=list)


class AgenticChatRuntime(BaseChatRuntime):
    """asyncio 기반 Agentic Chat Runtime"""
    
    # JSON tool call 패턴
    JSON_TOOL_PATTERN = re.compile(
        r'```(?:json)?\s*(\{[^`]+\})\s*```|'
        r'<tool_call>\s*(\{.+?\})\s*</tool_call>',
        re.DOTALL
    )
    
    def __init__(
        self,
        upstream_client: FabrixUpstreamClient,
        mcp_host: GenericMcpHost,
        config: AgenticConfig | None = None,
    ):
        self.upstream = upstream_client
        self.mcp_host = mcp_host
        self.config = config or AgenticConfig()
    
    async def stream_chat(
        self,
        runtime_input: ChatRuntimeInput,
    ) -> AsyncIterator[str]:
        """Agentic loop 실행 - SSE 이벤트 스트림 반환"""
        
        state = AgenticState()
        state.messages = self._build_initial_messages(runtime_input)
        tool_definitions = await self._build_tool_definitions()
        
        try:
            async with asyncio.timeout(self.config.total_timeout_seconds):
                async for event in self._run_agentic_loop(state, tool_definitions):
                    yield event
        except asyncio.TimeoutError:
            yield self._emit_event("timeout", {
                "elapsed": time.time() - state.start_time,
                "limit": self.config.total_timeout_seconds,
            })
    
    async def _run_agentic_loop(
        self,
        state: AgenticState,
        tool_definitions: list[dict],
    ) -> AsyncIterator[str]:
        """핵심 Agentic loop"""
        
        for step in range(self.config.max_steps):
            state.step = step
            yield self._emit_event("step_start", {"step": step})
            
            # Step 1: LLM 호출
            response_content = await self._call_llm_async(
                state.messages,
                tool_definitions,
            )
            state.total_tokens += self._estimate_tokens(response_content)
            
            # Step 2: Tool call 감지
            tool_calls = self._extract_tool_calls(response_content)
            
            if not tool_calls:
                # 최종 응답 - 스트리밍으로 전달
                async for chunk in self._stream_final_response(response_content):
                    yield chunk
                yield self._emit_event("complete", {
                    "steps": step + 1,
                    "tool_calls": state.total_tool_calls,
                })
                return
            
            # 안전성 검사
            if len(tool_calls) > self.config.max_tool_calls_per_step:
                tool_calls = tool_calls[:self.config.max_tool_calls_per_step]
                yield self._emit_event("warning", {
                    "type": "tool_call_limit",
                    "limit": self.config.max_tool_calls_per_step,
                })
            
            # Step 3: Tool 병렬 실행
            yield self._emit_event("tools_start", {
                "count": len(tool_calls),
                "tools": [tc.name for tc in tool_calls],
            })
            
            results = await self._execute_tools_parallel(tool_calls)
            state.total_tool_calls += len(tool_calls)
            
            # Step 4: 결과를 메시지에 추가
            for tc, result in zip(tool_calls, results):
                state.messages.append(self._build_tool_result_message(tc, result))
                yield self._emit_event("tool_result", {
                    "tool": tc.name,
                    "success": result.get("success", True),
                    "preview": str(result.get("content", ""))[:200],
                })
        
        # max_steps 도달
        yield self._emit_event("max_steps", {
            "limit": self.config.max_steps,
            "tool_calls": state.total_tool_calls,
        })
    
    async def _call_llm_async(
        self,
        messages: list[dict],
        tool_definitions: list[dict],
    ) -> str:
        """LLM 호출 (non-streaming)"""
        
        # tool definitions를 system prompt에 포함
        system_with_tools = self._build_system_prompt_with_tools(
            messages[0].get("content", ""),
            tool_definitions,
        )
        
        contents = [m["content"] for m in messages if m["role"] == "user"]
        
        response_text = ""
        async for chunk in self.upstream.stream_chat(
            model_ids=self.upstream.default_model_ids,
            contents=contents,
            history_messages=messages[1:],  # system 제외
            system_prompt=system_with_tools,
            llm_config={"max_tokens": self.config.max_tokens_per_step},
        ):
            response_text += chunk
        
        return response_text
    
    def _extract_tool_calls(self, response_text: str) -> list[ToolCall]:
        """LLM 응답에서 tool call 추출"""
        
        tool_calls = []
        
        for match in self.JSON_TOOL_PATTERN.finditer(response_text):
            json_str = match.group(1) or match.group(2)
            try:
                data = json.loads(json_str)
                name = data.get("name") or data.get("tool") or data.get("function")
                if name:
                    # 허용된 도구인지 검사
                    if self.config.allowed_tools and name not in self.config.allowed_tools:
                        continue
                    
                    tool_calls.append(ToolCall(
                        id=data.get("id", f"tc_{len(tool_calls)}"),
                        name=name,
                        arguments=data.get("arguments", data.get("params", {})),
                        provider=data.get("provider"),
                    ))
            except json.JSONDecodeError:
                continue
        
        return tool_calls
    
    async def _execute_tools_parallel(
        self,
        tool_calls: list[ToolCall],
    ) -> list[dict]:
        """여러 tool을 asyncio.gather로 병렬 실행"""
        
        tasks = [
            self._execute_single_tool(tc)
            for tc in tool_calls
        ]
        
        return await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _execute_single_tool(self, tool_call: ToolCall) -> dict:
        """단일 tool 실행"""
        
        try:
            async with asyncio.timeout(self.config.step_timeout_seconds):
                # provider_tool 형식 파싱 (예: "internal_docs_search_docs")
                if "_" in tool_call.name and not tool_call.provider:
                    parts = tool_call.name.split("_", 1)
                    provider_id = parts[0]
                    action = parts[1] if len(parts) > 1 else tool_call.name
                else:
                    provider_id = tool_call.provider or "internal_docs"
                    action = tool_call.name
                
                result = await self.mcp_host.execute_tool_action(
                    action=action,
                    arguments=tool_call.arguments,
                    provider_id=provider_id,
                )
                
                return {
                    "success": True,
                    "content": result,
                    "tool_call_id": tool_call.id,
                }
        
        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": f"Tool '{tool_call.name}' timed out ({self.config.step_timeout_seconds}s)",
                "tool_call_id": tool_call.id,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "tool_call_id": tool_call.id,
            }
    
    async def _build_tool_definitions(self) -> list[dict]:
        """MCP 도구를 LLM이 이해할 수 있는 형식으로 변환"""
        
        definitions = []
        
        for provider_config in self.mcp_host.settings.enabled_provider_configs():
            try:
                capabilities = await self.mcp_host.discover_provider_capabilities(
                    provider_id=provider_config.provider_id
                )
                
                for tool in capabilities.get("tools", []):
                    definitions.append({
                        "type": "function",
                        "function": {
                            "name": f"{provider_config.provider_id}_{tool['name']}",
                            "description": tool.get("description", ""),
                            "parameters": tool.get("inputSchema", {"type": "object"}),
                        },
                    })
            except Exception:
                continue
        
        return definitions
    
    def _build_system_prompt_with_tools(
        self,
        base_system: str,
        tool_definitions: list[dict],
    ) -> str:
        """System prompt에 tool 사용 지침 추가"""
        
        tools_json = json.dumps(tool_definitions, ensure_ascii=False, indent=2)
        
        return f"""{base_system}

## 사용 가능한 도구

다음 도구들을 사용할 수 있습니다. 도구를 사용하려면 JSON 코드 블록으로 응답하세요:

```json
{{"name": "도구이름", "arguments": {{"param1": "value1"}}}}
```

### 도구 목록
{tools_json}

## 도구 사용 지침
1. 정보가 필요할 때만 도구를 호출하세요
2. 한 번에 필요한 모든 도구를 호출하세요 (병렬 실행됩니다)
3. 도구 결과를 받으면 사용자에게 종합하여 답변하세요
4. 도구 없이 답변 가능하면 도구를 호출하지 마세요"""
    
    def _build_initial_messages(self, runtime_input: ChatRuntimeInput) -> list[dict]:
        """초기 메시지 구성"""
        
        messages = []
        
        if runtime_input.system_prompt:
            messages.append({
                "role": "system",
                "content": runtime_input.system_prompt,
            })
        
        # 히스토리 추가
        for msg in runtime_input.history_messages or []:
            messages.append(msg)
        
        # 현재 사용자 메시지
        messages.append({
            "role": "user",
            "content": runtime_input.user_message,
        })
        
        # MCP 사전 context가 있으면 추가
        if runtime_input.mcp_context:
            messages.append({
                "role": "system",
                "content": f"[참고 자료]\n{runtime_input.mcp_context}",
            })
        
        return messages
    
    def _build_tool_result_message(
        self,
        tool_call: ToolCall,
        result: dict,
    ) -> dict:
        """Tool 결과를 메시지 형식으로 변환"""
        
        if result.get("success"):
            content = f"[도구 결과: {tool_call.name}]\n{result.get('content', '')}"
        else:
            content = f"[도구 오류: {tool_call.name}]\n{result.get('error', 'Unknown error')}"
        
        return {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "name": tool_call.name,
            "content": content,
        }
    
    async def _stream_final_response(self, content: str) -> AsyncIterator[str]:
        """최종 응답 스트리밍"""
        
        # Tool call JSON 블록 제거
        clean_content = self.JSON_TOOL_PATTERN.sub("", content).strip()
        
        # 청크 단위로 스트리밍 (사용자 경험 향상)
        chunk_size = 50
        for i in range(0, len(clean_content), chunk_size):
            yield self._emit_event("assistant_chunk", {
                "content": clean_content[i:i + chunk_size],
            })
            await asyncio.sleep(0.01)  # 자연스러운 스트리밍 효과
        
        yield self._emit_event("assistant_final", {"content": clean_content})
    
    def _emit_event(self, event_type: str, data: dict) -> str:
        """SSE 이벤트 직렬화"""
        
        event = {"event_type": event_type, **data}
        return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    
    def _estimate_tokens(self, text: str) -> int:
        """토큰 수 추정 (대략 4자당 1토큰)"""
        return len(text) // 4
```

#### 5.2.4 FastAPI 라우터 상세 구현

##### 5.2.4.1 Request/Response 모델

```python
# ai_gateway/routers/agentic_chat.py (신규 라우터)

from typing import Optional, List, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class AgenticMcpContext(BaseModel):
    """Agentic chat용 MCP 컨텍스트"""
    model_config = ConfigDict(populate_by_name=True)
    
    active_category: Optional[str] = Field(default=None, alias="activeCategory")
    rag_enabled: bool = Field(default=False, alias="ragEnabled")
    provider_id: Optional[str] = Field(default=None, alias="providerId")


class AgenticChatRequest(BaseModel):
    """Agentic chat API 요청 모델"""
    model_config = ConfigDict(populate_by_name=True)
    
    # 모델 설정
    model_ids: List[str] = Field(default_factory=list, alias="modelIds")
    router_model_id: Optional[str] = Field(
        default=None,
        alias="routerModelId",
        description="의도 분류용 경량 모델 ID (None이면 자동 선택)"
    )
    
    # 메시지
    contents: List[str] = Field(..., min_length=1)
    system_prompt: Optional[str] = Field(default=None, alias="systemPrompt")
    
    # Agentic 설정
    max_steps: int = Field(default=10, ge=1, le=20)
    step_timeout: float = Field(default=30.0, ge=5.0, le=60.0, alias="stepTimeout")
    total_timeout: float = Field(default=120.0, ge=30.0, le=300.0, alias="totalTimeout")
    allowed_tools: Optional[List[str]] = Field(default=None, alias="allowedTools")
    
    # MCP 컨텍스트
    mcp_context: Optional[AgenticMcpContext] = Field(default=None, alias="mcpContext")
    
    # 스트리밍 옵션
    include_thinking: bool = Field(
        default=False,
        alias="includeThinking",
        description="LLM 사고 과정 이벤트 포함 여부"
    )
    
    @field_validator("contents")
    @classmethod
    def validate_contents(cls, v):
        if not v or not v[-1].strip():
            raise ValueError("마지막 메시지는 비어있을 수 없습니다")
        return v


class AgenticStepEvent(BaseModel):
    """SSE 이벤트 응답 모델"""
    event_type: Literal[
        "step_start",
        "tools_start",
        "tool_result",
        "assistant_chunk",
        "assistant_final",
        "complete",
        "max_steps",
        "timeout",
        "warning",
        "error",
    ]
    step: Optional[int] = None
    count: Optional[int] = None
    tools: Optional[List[str]] = None
    tool: Optional[str] = None
    success: Optional[bool] = None
    preview: Optional[str] = None
    content: Optional[str] = None
    elapsed: Optional[float] = None
    limit: Optional[int] = None
    error: Optional[str] = None
```

##### 5.2.4.2 라우터 엔드포인트

```python
# ai_gateway/routers/agentic_chat.py (계속)

import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..dependencies import verify_token
from ..services.mcp.runtime.agentic_runtime import (
    AgenticChatRuntime,
    AgenticConfig,
)
from ..services.mcp.runtime.upstream import FabrixUpstreamClient
from ..services.mcp.runtime import ChatRuntimeInput, McpContextInput

router = APIRouter(prefix="/agentic-chat", tags=["Agentic Chat"])
logger = logging.getLogger(__name__)


@router.post(
    "/stream",
    dependencies=[Depends(verify_token)],
    summary="Agentic multi-step chat 스트리밍",
    description="""
    LLM이 자율적으로 MCP 도구를 호출하고 결과를 취합하여 최종 응답을 생성합니다.
    
    **SSE 이벤트 타입:**
    - `step_start`: 새 step 시작
    - `tools_start`: tool 병렬 실행 시작
    - `tool_result`: 개별 tool 실행 결과
    - `assistant_chunk`: 최종 응답 청크
    - `assistant_final`: 최종 응답 완료
    - `complete`: 전체 완료
    - `max_steps`: max_steps 도달 경고
    - `timeout`: 타임아웃
    - `error`: 오류
    """,
    response_class=StreamingResponse,
)
async def stream_agentic_chat(
    req: AgenticChatRequest,
    request: Request,
):
    """Agentic multi-step chat 스트리밍 엔드포인트"""
    
    # 모델 ID 검증 (test mode가 아닌 경우)
    mcp_settings = request.app.state.mcp_settings
    if not mcp_settings.host.test_mode:
        normalized_model_ids = [m for m in req.model_ids if m and m.strip()]
        if not normalized_model_ids:
            raise HTTPException(
                status_code=400,
                detail="modelIds is required in production mode"
            )
    else:
        normalized_model_ids = req.model_ids
    
    # Agentic 설정 구성
    config = AgenticConfig(
        max_steps=req.max_steps,
        step_timeout_seconds=req.step_timeout,
        total_timeout_seconds=req.total_timeout,
        allowed_tools=set(req.allowed_tools) if req.allowed_tools else None,
    )
    
    # MCP 컨텍스트 변환
    mcp_context_input = None
    if req.mcp_context:
        mcp_context_input = McpContextInput(
            active_category=req.mcp_context.active_category,
            rag_enabled=req.mcp_context.rag_enabled,
            provider_id=req.mcp_context.provider_id,
        )
    
    # Runtime 생성
    try:
        runtime = AgenticChatRuntime(
            upstream_client=FabrixUpstreamClient(request),
            mcp_host=request.app.state.mcp_host,
            config=config,
            router_model_id=req.router_model_id,
        )
    except Exception as e:
        logger.error(f"[AGENTIC] Runtime creation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create agentic runtime: {str(e)}"
        )
    
    # Runtime input 구성
    runtime_input = ChatRuntimeInput(
        model_ids=normalized_model_ids,
        contents=req.contents,
        is_stream=True,
        system_prompt=req.system_prompt,
        mcp_context=mcp_context_input,
    )
    
    # 스트리밍 응답
    try:
        event_stream = await runtime.stream_chat(runtime_input)
        
        return StreamingResponse(
            event_stream,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # nginx 버퍼링 비활성화
                "X-Content-Type-Options": "nosniff",
            },
        )
    except Exception as e:
        logger.error(f"[AGENTIC] Stream failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Agentic chat stream failed: {str(e)}"
        )


@router.get(
    "/config",
    dependencies=[Depends(verify_token)],
    summary="Agentic runtime 설정 조회",
)
async def get_agentic_config(request: Request):
    """현재 agentic runtime 설정 반환"""
    
    mcp_settings = request.app.state.mcp_settings
    
    return {
        "enabled": getattr(mcp_settings.host, "agentic_enabled", False),
        "defaults": {
            "max_steps": 10,
            "step_timeout": 30.0,
            "total_timeout": 120.0,
        },
        "limits": {
            "max_steps": {"min": 1, "max": 20},
            "step_timeout": {"min": 5.0, "max": 60.0},
            "total_timeout": {"min": 30.0, "max": 300.0},
        },
        "available_tools": await _get_available_tools(request),
    }


@router.get(
    "/router-models",
    dependencies=[Depends(verify_token)],
    summary="Router 모델 후보 목록 조회",
)
async def get_router_models(request: Request):
    """의도 분류에 사용할 수 있는 경량 모델 목록"""
    
    import re
    from ..services.mcp.runtime.upstream import (
        get_fabrix_chat_config,
        get_fabrix_chat_headers,
    )
    
    _, fabrix_chat_url = get_fabrix_chat_config()
    headers = get_fabrix_chat_headers()
    
    try:
        response = await request.app.state.http_client.get(
            f"{fabrix_chat_url}/models",
            headers=headers,
            params={"page": 1, "limit": 100},
        )
        response.raise_for_status()
        models = response.json().get("data", [])
    except Exception as e:
        logger.error(f"[AGENTIC] Failed to fetch models: {e}")
        return {"router_models": [], "error": str(e)}
    
    # 경량 모델 패턴 (Gemma, Phi, Qwen-small, Llama-8B 등)
    router_pattern = re.compile(
        r"gemma|phi|qwen.*small|llama.*8b|mistral.*7b",
        re.IGNORECASE
    )
    
    router_models = []
    for model in models:
        model_id = model.get("id", "")
        if router_pattern.search(model_id):
            router_models.append({
                "id": model_id,
                "name": model.get("name", model_id),
                "recommended": "gemma" in model_id.lower(),
            })
    
    return {
        "router_models": router_models,
        "default": router_models[0]["id"] if router_models else None,
    }


async def _get_available_tools(request: Request) -> list[dict]:
    """사용 가능한 MCP 도구 목록"""
    
    mcp_host = request.app.state.mcp_host
    tools = []
    
    for provider_config in mcp_host.settings.enabled_provider_configs():
        try:
            capabilities = await mcp_host.discover_provider_capabilities(
                provider_id=provider_config.provider_id
            )
            for tool in capabilities.get("tools", []):
                tools.append({
                    "name": f"{provider_config.provider_id}_{tool['name']}",
                    "provider": provider_config.provider_id,
                    "description": tool.get("description", ""),
                })
        except Exception:
            continue
    
    return tools
```

##### 5.2.4.3 라우터 등록

```python
# ai_gateway/main.py 수정

from .routers import agentic_chat

# 기존 라우터 등록 부분에 추가
app.include_router(
    agentic_chat.router,
    prefix="/api/v1",
    dependencies=[],  # 개별 엔드포인트에서 verify_token 적용
)
```

##### 5.2.4.4 에러 핸들링 미들웨어

```python
# ai_gateway/middleware/agentic_error_handler.py (신규)

import json
import logging
from typing import Callable
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import StreamingResponse

logger = logging.getLogger(__name__)


class AgenticErrorMiddleware(BaseHTTPMiddleware):
    """Agentic chat 스트리밍 에러를 SSE 이벤트로 변환"""
    
    async def dispatch(self, request: Request, call_next: Callable):
        # agentic-chat 경로가 아니면 통과
        if "/agentic-chat/" not in request.url.path:
            return await call_next(request)
        
        try:
            response = await call_next(request)
            return response
        
        except Exception as e:
            logger.error(f"[AGENTIC] Unhandled error: {e}", exc_info=True)
            
            # SSE 에러 이벤트 생성
            async def error_stream():
                error_event = {
                    "event_type": "error",
                    "error": str(e),
                    "recoverable": False,
                }
                yield f"data: {json.dumps(error_event)}\n\n"
            
            return StreamingResponse(
                error_stream(),
                media_type="text/event-stream",
                status_code=500,
                headers={
                    "X-Accel-Buffering": "no",
                    "X-Error-Type": type(e).__name__,
                },
            )
```

##### 5.2.4.5 Rate Limiting 통합

```python
# ai_gateway/routers/agentic_chat.py 확장

from ..services.rate_limiter_v2 import rate_limiter, RateLimitExceeded


@router.post("/stream", dependencies=[Depends(verify_token)])
async def stream_agentic_chat(req: AgenticChatRequest, request: Request):
    # Rate limit 체크 (agentic은 더 제한적)
    try:
        rate_limiter.check_limit(
            endpoint="agentic_chat",
            weight=3,  # 일반 chat 대비 3배 가중치
        )
    except RateLimitExceeded as e:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Rate limit exceeded for agentic chat",
                "retry_after": e.retry_after,
                "limit": e.limit,
            },
            headers={"Retry-After": str(e.retry_after)},
        )
    
    # ... 기존 로직 ...
```

##### 5.2.4.6 OpenAPI 스키마 확장

```python
# ai_gateway/routers/agentic_chat.py - 라우터 정의 부분

from fastapi import APIRouter

router = APIRouter(
    prefix="/agentic-chat",
    tags=["Agentic Chat"],
    responses={
        400: {"description": "잘못된 요청 (빈 메시지, 잘못된 설정값)"},
        401: {"description": "인증 실패"},
        429: {"description": "Rate limit 초과"},
        500: {"description": "서버 내부 오류"},
        504: {"description": "타임아웃"},
    },
)
```

#### 5.2.5 프론트엔드 통합

```javascript
// frontend/src/hooks/useAgenticChat.js

import { useState, useCallback } from 'react';

export function useAgenticChat() {
    const [steps, setSteps] = useState([]);
    const [isThinking, setIsThinking] = useState(false);
    const [currentTool, setCurrentTool] = useState(null);
    
    const sendAgenticMessage = useCallback(async (message, options = {}) => {
        setIsThinking(true);
        setSteps([]);
        
        const response = await fetch('/api/v1/chat-messages/stream-agentic', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                contents: [message],
                ...options,
            }),
        });
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let finalContent = '';
        
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n\n');
            buffer = lines.pop() || '';
            
            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                
                try {
                    const event = JSON.parse(line.slice(6));
                    
                    switch (event.event_type) {
                        case 'step_start':
                            setSteps(prev => [...prev, {
                                step: event.step,
                                status: 'running',
                                tools: [],
                            }]);
                            break;
                        
                        case 'tools_start':
                            setCurrentTool(event.tools[0]);
                            setSteps(prev => {
                                const updated = [...prev];
                                const last = updated[updated.length - 1];
                                if (last) {
                                    last.tools = event.tools.map(t => ({
                                        name: t,
                                        status: 'running',
                                    }));
                                }
                                return updated;
                            });
                            break;
                        
                        case 'tool_result':
                            setSteps(prev => {
                                const updated = [...prev];
                                const last = updated[updated.length - 1];
                                if (last) {
                                    const tool = last.tools.find(t => t.name === event.tool);
                                    if (tool) {
                                        tool.status = event.success ? 'done' : 'error';
                                        tool.preview = event.preview;
                                    }
                                }
                                return updated;
                            });
                            setCurrentTool(null);
                            break;
                        
                        case 'assistant_chunk':
                            finalContent += event.content;
                            break;
                        
                        case 'assistant_final':
                            finalContent = event.content;
                            break;
                        
                        case 'complete':
                            setSteps(prev => {
                                const updated = [...prev];
                                const last = updated[updated.length - 1];
                                if (last) last.status = 'complete';
                                return updated;
                            });
                            break;
                        
                        case 'timeout':
                        case 'max_steps':
                            setSteps(prev => {
                                const updated = [...prev];
                                const last = updated[updated.length - 1];
                                if (last) last.status = 'warning';
                                return updated;
                            });
                            break;
                    }
                } catch (e) {
                    console.error('Event parse error:', e);
                }
            }
        }
        
        setIsThinking(false);
        return finalContent;
    }, []);
    
    return {
        sendAgenticMessage,
        steps,
        isThinking,
        currentTool,
    };
}
```

#### 5.2.6 StepIndicator 컴포넌트

```jsx
// frontend/src/components/StepIndicator.jsx

import { Box, Flex, Text, Badge, Spinner, VStack, HStack } from '@chakra-ui/react';
import { CheckIcon, WarningIcon, TimeIcon } from '@chakra-ui/icons';

const statusConfig = {
    running: { color: 'blue', icon: Spinner },
    complete: { color: 'green', icon: CheckIcon },
    warning: { color: 'orange', icon: WarningIcon },
    error: { color: 'red', icon: WarningIcon },
};

export function StepIndicator({ steps, currentTool }) {
    if (!steps.length) return null;
    
    return (
        <VStack align="stretch" spacing={2} p={3} bg="gray.50" borderRadius="md">
            <Text fontSize="sm" fontWeight="bold" color="gray.600">
                🤖 Agentic 처리 중...
            </Text>
            
            {steps.map((step, idx) => (
                <Box key={idx} pl={4} borderLeft="2px" borderColor="blue.200">
                    <HStack spacing={2}>
                        <Badge colorScheme={statusConfig[step.status]?.color || 'gray'}>
                            Step {step.step + 1}
                        </Badge>
                        {step.status === 'running' && <Spinner size="xs" />}
                        {step.status === 'complete' && <CheckIcon color="green.500" boxSize={3} />}
                    </HStack>
                    
                    {step.tools?.length > 0 && (
                        <VStack align="stretch" spacing={1} mt={1} pl={2}>
                            {step.tools.map((tool, tidx) => (
                                <HStack key={tidx} fontSize="xs">
                                    <Text color="gray.500">🔧 {tool.name}</Text>
                                    {tool.status === 'running' && <Spinner size="xs" />}
                                    {tool.status === 'done' && <CheckIcon color="green.400" boxSize={2} />}
                                    {tool.status === 'error' && <WarningIcon color="red.400" boxSize={2} />}
                                </HStack>
                            ))}
                        </VStack>
                    )}
                </Box>
            ))}
        </VStack>
    );
}
```

#### 5.2.7 장점 요약

| 측면 | asyncio 기반 구현 | Celery 기반 구현 |
|------|------------------|-----------------|
| **구현 복잡도** | 🟢 낮음 (기존 패턴 활용) | 🔴 높음 (전면 재설계) |
| **SSE 스트리밍** | ✅ 자연스럽게 지원 | ❌ WebSocket 별도 구축 |
| **httpx 클라이언트** | ✅ 기존 재활용 | ❌ 재구성 필요 |
| **실시간 진행률** | ✅ step별 이벤트 | ⚠️ Redis Pub/Sub 필요 |
| **디버깅** | 🟢 단일 프로세스 | 🔴 분산 디버깅 |
| **마이그레이션 비용** | 1~2주 | 3~4주 |

---

## 6. 권장 구현 전략

### 6.1 단계적 접근법 (asyncio + Multi-Model)

**Phase 1: asyncio 기반 Agentic Runtime 구현** (1~2주)
- `AgenticChatRuntime` 클래스 신설 (Section 5.2.3 참조)
- 기존 `FabrixUpstreamClient`, `GenericMcpHost` 재활용
- `/stream-agentic` 엔드포인트 추가

**Phase 2: Small Model Router 통합** (1주)
- Gemma 3 등 경량 모델로 의도 분류
- confidence threshold 기반 fallback
- 도구 선택 로직 분리로 main model 비용 절감

**Phase 3: 프론트엔드 UI 통합** (1주)
- `useAgenticChat` 훅 구현
- `StepIndicator` 컴포넌트 추가
- 기존 Chat UI와 통합

**Phase 4: FastMCP Sampling 통합** (장기/선택)
- MCP 서버에 sampling_handler 설정
- 서버측 agentic 워크플로우 구현
- 고급 자동화 시나리오 지원

### 6.2 구현 우선순위

| 우선순위 | 작업 | 복잡도 | 효과 |
|---------|------|--------|------|
| 1 | `AgenticChatRuntime` 클래스 구현 | 중간 | 핵심 기능 |
| 2 | Tool call 감지 로직 (`_extract_tool_calls`) | 낮음 | 필수 |
| 3 | SSE 이벤트 스트림 설계 | 낮음 | UX |
| 4 | `SmallModelRouter` 통합 (Gemma 3) | 중간 | 비용 절감 |
| 5 | 프론트엔드 `useAgenticChat` 훅 | 중간 | 완성도 |
| 6 | FastMCP sampling 통합 | 높음 | MCP 표준 준수 |

---

## 7. SSE 이벤트 스트림 설계

Agentic runtime은 다음 이벤트 타입을 스트리밍:

```typescript
// 프론트엔드 타입 정의
interface AgenticEvent {
  event_type: 
    | "step_start"      // 새 step 시작
    | "tools_start"     // tool 실행 시작 (병렬)
    | "tool_result"     // 개별 tool 실행 결과
    | "assistant_chunk" // 최종 응답 청크
    | "assistant_final" // 최종 응답 완료
    | "complete"        // 전체 완료
    | "max_steps"       // max_steps 도달 경고
    | "timeout"         // 타임아웃
    | "warning"         // 경고 (tool call 제한 등)
    | "error";          // 오류

  step?: number;
  count?: number;           // tools_start에서 tool 개수
  tools?: string[];         // tools_start에서 tool 이름 목록
  tool?: string;            // tool_result에서 tool 이름
  success?: boolean;        // tool_result 성공 여부
  preview?: string;         // tool_result 미리보기 (200자)
  content?: string;         // assistant_chunk/final 내용
  elapsed?: number;         // timeout에서 경과 시간
  limit?: number;           // timeout/max_steps에서 제한값
}
```

> **참고**: 상세 구현은 Section 5.2.3의 `AgenticChatRuntime._emit_event()` 메서드 참조

---

## 8. 안전성 고려사항

### 8.1 무한 루프 방지

```python
MAX_STEPS = 10
MAX_TOOL_CALLS_PER_STEP = 5
MAX_TOTAL_TOKENS = 100000

class SafetyGuard:
    def __init__(self):
        self.step_count = 0
        self.total_tool_calls = 0
        self.total_tokens = 0
    
    def check_step_limit(self) -> bool:
        self.step_count += 1
        return self.step_count <= MAX_STEPS
    
    def check_tool_call_limit(self, calls: int) -> bool:
        if calls > MAX_TOOL_CALLS_PER_STEP:
            return False
        self.total_tool_calls += calls
        return True
    
    def check_token_limit(self, tokens: int) -> bool:
        self.total_tokens += tokens
        return self.total_tokens <= MAX_TOTAL_TOKENS
```

### 8.2 비용 제어

```python
@dataclass
class AgenticConfig:
    max_steps: int = 10
    max_tokens_per_step: int = 4000
    allowed_tools: set[str] | None = None  # None = 모든 도구 허용
    timeout_seconds: float = 120.0
    
    def is_tool_allowed(self, tool_name: str) -> bool:
        if self.allowed_tools is None:
            return True
        return tool_name in self.allowed_tools
```

---

## 9. 테스트 계획

### 9.1 단위 테스트

```python
# test_agentic_runtime.py
import pytest

class TestToolCallExtraction:
    def test_extract_json_block(self):
        response = '''Here's what I'll do:
        ```json
        {"name": "search_docs", "arguments": {"query": "test"}}
        ```
        '''
        calls = extract_tool_calls(response)
        assert len(calls) == 1
        assert calls[0].name == "search_docs"
    
    def test_extract_multiple_calls(self):
        response = '''
        <tool_call>{"name": "search_docs", "arguments": {"query": "a"}}</tool_call>
        <tool_call>{"name": "read_doc", "arguments": {"filename": "b"}}</tool_call>
        '''
        calls = extract_tool_calls(response)
        assert len(calls) == 2

class TestAgenticLoop:
    @pytest.mark.asyncio
    async def test_stops_on_final_response(self):
        # LLM이 tool call 없이 응답하면 즉시 종료
        ...
    
    @pytest.mark.asyncio
    async def test_max_steps_limit(self):
        # max_steps 도달 시 경고와 함께 종료
        ...
```

### 9.2 통합 테스트

```python
# test_agentic_integration.py
@pytest.mark.asyncio
async def test_multi_step_document_research():
    """문서 검색 → 읽기 → 요약의 multi-step 시나리오"""
    orchestrator = AgenticOrchestrator(...)
    
    events = []
    async for event in orchestrator.run("회의록 폴더에서 최근 회의 내용을 찾아 요약해줘"):
        events.append(event)
    
    # 검증: search_docs → read_doc → 최종 요약
    tool_events = [e for e in events if e["event_type"] == "tool_call"]
    assert any("search" in e["tool_name"] for e in tool_events)
    assert any("read" in e["tool_name"] for e in tool_events)
    
    final = [e for e in events if e["event_type"] == "assistant_final"]
    assert len(final) == 1
```

---

## 10. 마일스톤 (asyncio 기반)

| Phase | 기간 | 목표 | 산출물 |
|-------|------|------|--------|
| **Phase 1** | 1주 | `AgenticChatRuntime` 핵심 구현 | Section 5.2.3 클래스 전체 |
| **Phase 2** | 0.5주 | `/stream-agentic` 엔드포인트 | Section 5.2.4 라우터 통합 |
| **Phase 3** | 1주 | 프론트엔드 `useAgenticChat` 훅 | Section 5.2.5~5.2.6 |
| **Phase 4** | 1주 | Small Model Router 통합 | Section 4.3~4.4 (선택) |
| **Phase 5** | 0.5주 | 테스트 및 안정화 | Section 9 테스트 |

**총 예상 기간**: 4주 (Phase 4 포함 시)

---

## 11. 참고 자료

### 11.1 MCP 표준 문서
- [MCP Architecture](https://modelcontextprotocol.io/docs/concepts/architecture)
- [SEP-1577: Tool Use in Sampling](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1577)

### 11.2 FastMCP 문서
- [FastMCP Client](https://gofastmcp.com/clients/client)
- [FastMCP Sampling](https://gofastmcp.com/servers/sampling)
- [FastMCP Tool Use](https://gofastmcp.com/servers/sampling#tool-use)

### 11.3 현재 코드베이스
- `ai_gateway/services/mcp/runtime/normal_runtime.py` - 현재 single-pass 구현
- `ai_gateway/services/mcp/runtime/test_mode_runtime.py` - test mode 구현 (LLM 우회)
- `ai_gateway/services/mcp/runtime/upstream.py` - FabriX upstream 클라이언트 (model_ids 지원)
- `ai_gateway/services/mcp/host.py` - MCP host 및 tool 실행
- `ai_gateway/routers/chat.py` - `/models` 엔드포인트 (모델 목록 조회)

---

## 부록: 용어 정의

| 용어 | 정의 |
|------|------|
| **Agentic Loop** | LLM이 tool을 호출하고 결과를 받아 다시 응답하는 반복 구조 |
| **Tool Call** | LLM이 외부 도구 실행을 요청하는 JSON 구조 |
| **Sampling** | MCP 표준에서 서버가 클라이언트의 LLM에 텍스트 생성을 요청하는 기능 |
| **Single-Pass** | LLM을 1회만 호출하는 현재 구조 |
| **Multi-Step** | LLM을 여러 번 호출하며 중간 결과를 축적하는 구조 |
| **Step** | Agentic loop의 1회 반복 (LLM 호출 → tool 실행 → 결과 주입) |
| **Router Model** | 의도 분류 및 도구 선택에 사용되는 경량 모델 (예: Gemma 3) |
| **Main Model** | 최종 응답 생성에 사용되는 대형 모델 (예: GPT-OSS-120b) |
| **Intent Classification** | 사용자 질의의 의도(일반대화/문서검색/코드분석 등)를 분류하는 작업 |
| **Confidence Threshold** | Router 결정의 신뢰도 임계값, 이하면 fallback |
