# FabriX용 LexGuard MCP Workflow 통합 가이드

## 문서 목적

이 문서는 FabriX가 `lexguard-mcp` 서버를 **외부 MCP provider**로 통합할 때,
무엇을 **upstream contract**로 받아들이고 무엇을 **FabriX host 책임**으로 구현해야 하는지 정리한 실무 문서다.

이 문서의 초점은 “LexGuard tool이 어떻게 동작하는가” 자체보다,
**FabriX가 그 동작을 어떤 경계(boundary)와 책임 분리 위에서 통합해야 하는가**에 있다.

다루는 핵심 질문은 다음과 같다.

1. `document_issue_tool`을 포함한 LexGuard workflow를 FabriX가 새로 설계해야 하는가?
2. upstream `lexguard-mcp`가 이미 정의한 tool-calling semantics를 FabriX가 따라야 하는가?
3. 현재 FabriX 구현은 이 원칙과 얼마나 정합적인가?

이 문서의 결론은 명확하다.

- **LexGuard tool semantics, 응답 의미, 작성 지시문, 중간 결과의 역할은 upstream이 이미 정의하고 있다.**
- FabriX는 이를 다시 설계하는 것이 아니라, **MCP Host/Client로서 activation, chaining, context injection, final LLM synthesis**를 담당해야 한다.
- 즉, **LexGuard는 법률 도메인 MCP server**, **FabriX는 이를 조합하는 host/orchestrator**로 동작해야 한다.

---

## 1. 최상위 판단

### 1-1. FabriX가 LexGuard workflow를 새로 정의해야 하는가?

기본 판단은 **아니다**.

이미 upstream에는 다음 수준의 정의가 들어 있다.

- 어떤 tool이 어떤 목적에 쓰이는지
- 각 tool이 어떤 입력을 받는지
- 어떤 형식의 응답을 내는지
- downstream LLM이 어떤 형식으로 최종 답변을 작성해야 하는지

주요 근거 파일:

- `lexguard-mcp/src/routes/mcp_routes.py`
  - `tools/list`에서 각 tool의 `description`, `inputSchema`, `outputSchema`를 공개한다.
  - 이 description에는 단순 설명이 아니라 **답변 형식, 금지사항, 사용 목적**이 포함되어 있다.
- `lexguard-mcp/src/utils/document_issue_prompts.py`
  - `document_issue_tool` 결과를 받은 downstream LLM이 어떤 구조로 답해야 하는지 정의한다.
  - 출력 라벨, 위험도, 총평, 디스클레이머까지 규정한다.
- upstream PR #3
  - `fix: remove top-level allOf/anyOf from inputSchema for Claude API compatibility`
  - 이는 upstream이 실제로 **Claude API / tool calling 환경을 의식해 schema를 조정**하고 있다는 증거다.

즉 upstream `lexguard-mcp`는 단순 “법률 데이터 반환 서버”가 아니라,
**AI tool-calling client가 사용하기 쉬운 방향으로 이미 설계된 MCP server**라고 보는 것이 맞다.

### 1-2. FabriX의 책임은 어디까지인가?

FabriX는 MCP 관점에서 다음 역할을 갖는다.

- **Host**: 전체 대화 orchestration 주체
- **Client**: LexGuard MCP server와 연결해 `tools/list`, `tools/call` 수행
- **LLM runtime owner**: tool 결과를 받아 최종 사용자 응답을 생성하는 모델 호출 주체

따라서 FabriX의 책임은 다음으로 정리된다.

1. 어떤 사용자 질의에서 어떤 LexGuard tool을 호출할지 결정
2. 필요 시 복수 tool 또는 내부 문서 검색과 tool chain 구성
3. tool 결과를 **중간 context**로 LLM에 전달
4. 최종 사용자 응답은 LLM이 작성하도록 orchestration

이 역할 분리는 MCP 공식 개념과도 일치한다.

---

## 2. 공식 MCP 관점에서의 해석

공식 MCP 문서의 핵심 원칙은 다음과 같다.

- tool은 **model-controlled capability**이다.
- host/client는 tool을 호출하지만,
- **tool result 자체가 최종 사용자 답변은 아니다.**
- 일반적인 흐름은 tool result를 모델에 다시 전달하고, 모델이 이를 해석해 답변을 작성하는 구조다.

이 원칙을 LexGuard 통합에 적용하면 다음과 같다.

- LexGuard의 structured result는 **최종 답변 원문**이 아니라 **법률 근거 context**로 다뤄야 한다.
- upstream이 함께 주는 instruction text / response policy는 **LLM 작성 지시문**으로 유지해야 한다.
- FabriX는 raw tool result를 그대로 사용자에게 노출하는 것이 아니라,
  **LLM이 해석 가능한 형태로 유지·주입**하는 host 역할을 수행해야 한다.

현재 FabriX 구현 방향은 이 원칙과 대체로 맞다.

---

## 3. upstream authoritative source는 어디인가?

### 3-1. MCP route와 tool exposure의 기준점

**기준 파일**
- `lexguard-mcp/src/routes/mcp_routes.py`

**이 파일이 담당하는 역할**
- `/mcp` GET/POST endpoint 제공
- JSON-RPC `initialize`, `tools/list`, `tools/call`, `prompts/get` 처리
- tool schema / description / output contract 공개
- 각 tool 요청을 실제 service/repository로 라우팅
- `format_mcp_response(...)`를 거쳐 MCP 표준 응답 생성

FabriX 관점에서 이 파일은 다음 의미를 가진다.

- 어떤 tool이 server에 공식 노출되는지 확인하는 기준
- tool description을 통해 upstream intended usage를 확인하는 기준
- tool 응답이 어떤 MCP shape로 나오는지 확인하는 기준

즉, **LexGuard tool usage contract의 1차 기준점**은 이 파일이다.

### 3-2. `document_issue_tool`의 실제 설계 의도

**기준 파일**
- `lexguard-mcp/src/utils/document_issue_prompts.py`

**이 파일이 담당하는 역할**
- `document_issue_tool` 결과를 받은 downstream LLM의 출력 형식 정의
- 문서 유형별 review instruction / addon 정의
- 출력 라벨, 위험도, 총평, 디스클레이머 규칙 정의

이 파일을 기준으로 보면 `document_issue_tool`은 단순 분석기라기보다,
**문서 분석 결과 + LLM 작성 지시문을 함께 제공하는 tool**로 이해하는 것이 맞다.

따라서 FabriX는 `document_issue_tool`를 다음처럼 다뤄야 한다.

- “이 tool 하나가 최종 완성 보고서를 바로 반환해야 한다”로 해석하지 않는다.
- “이 tool이 준 분석 패키지와 작성 지시문을 바탕으로 LLM이 최종 보고서를 쓰게 한다”로 해석한다.

이 해석은 upstream maintainer 답변과도 일치하고,
현재 observed payload 구조와도 부합한다.

### 3-3. 실제 tool execution은 upstream 내부에서 끝난다

**관련 파일**
- `lexguard-mcp/src/routes/mcp_routes.py`
- `lexguard-mcp/src/services/smart_search_service.py`
- `lexguard-mcp/src/services/situation_guidance_service.py`
- `lexguard-mcp/src/repositories/law_detail.py`

여기서 중요한 점은,
FabriX가 LexGuard 내부 구현을 다시 복제할 필요가 없다는 것이다.

FabriX는:

- tool 내부 검색 로직을 재구현하지 않고
- upstream tool contract를 따라 호출하고
- 결과를 적절한 host context로 가공·주입하면 된다.

즉, **upstream 내부 구현은 server의 책임**이고,
FabriX는 그 결과를 orchestration layer에서 활용하는 쪽에 집중해야 한다.

---

## 4. PR #3가 FabriX 통합에 주는 의미

**PR**
- `https://github.com/SeoNaRu/lexguard-mcp/pull/3`

**핵심 변경**
- 일부 tool의 input schema에서 top-level `allOf` / `anyOf` 제거
- 이유: **Claude API compatibility**

이 PR이 중요한 이유는 다음과 같다.

1. upstream이 실제 사용 client로 Claude 계열 tool calling을 의식하고 있다.
2. schema를 “이론적으로 더 엄격하게” 유지하는 것보다,
   **실제 tool-calling client와의 호환성**을 우선하고 있다.
3. 일부 validation은 schema보다 tool description과 service-layer validation에 의존한다.

FabriX에 대한 실무적 의미:

- upstream contract를 볼 때 `inputSchema`만 보면 부족하다.
- 반드시 함께 봐야 하는 것:
  - `tools/list.description`
  - prompt/instruction 파일
  - 실제 observed payload
  - maintainer PR/issue 설명

즉 FabriX 문서와 구현도 **schema-only 사고방식**으로 가면 안 된다.

---

## 5. 현재 FabriX 구현과의 대응 관계

### 5-1. provider 연결 레이어

**파일**
- `ai_gateway/services/mcp/providers/lexguard.py`

**현재 역할**
- `fastmcp.Client`로 LexGuard MCP server 연결
- `call_tool`, `call_tool_dict`, `health_check` 제공
- FabriX 내부 provider adapter 역할 수행

이 레이어는 현재 thin adapter로 유지되고 있고,
역할 분리도 적절하다.

즉 이 레이어는 **tool semantics를 해석하는 곳이 아니라 transport/adapter 레이어**로 유지하는 것이 맞다.

### 5-2. tool activation / planning 레이어

**파일**
- `ai_gateway/services/mcp/shared_planner/rules/lexguard.default.json`
- `ai_gateway/services/mcp/shared_planner/core.py`

**현재 역할**
- 어떤 사용자 질의가 어떤 LexGuard tool로 가야 하는지 결정

현재 rule 예시:

- 계약서/약관 + 분석 intent → `document_issue_tool`
- 법령명 + 제N조 패턴 → `law_article_tool`
- 신구법/연혁 → `law_comparison_tool`
- 그 외 일반 법률 질문 → `legal_qa_tool`

이 구조는 upstream tool 분리와 대체로 잘 맞는다.

다만 FabriX는 다음 원칙을 유지해야 한다.

- activation rule은 FabriX가 소유한다.
- 하지만 rule semantics는 upstream `tools/list.description`과 충돌하면 안 된다.
- 즉 **FabriX가 tool을 고르는 방식은 host 책임**이지만,
  **tool 의미 자체는 upstream 정의를 따라야 한다.**

### 5-3. result normalization / context injection 레이어

**파일**
- `ai_gateway/services/mcp/result_normalizer.py`
- `ai_gateway/services/mcp/rag_context.py`
- `ai_gateway/services/mcp/host.py`

**현재 핵심 동작**
FabriX는 LexGuard 결과를 바로 최종 출력하지 않고 다음 순서로 다룬다.

1. `structured_content`를 dict로 보존
2. `content[]` 안의 instruction text를 별도로 추출
3. `render_legal_context_system_prompt()`로 LLM 주입용 prompt 생성
4. 최종 답변은 LLM이 작성

이건 FabriX가 반드시 유지해야 하는 핵심 구현 원칙이다.

특히 `result_normalizer.py`가 중요한 이유는,
LexGuard MCP 결과가 단순 JSON만이 아니라:

- instruction text block
- structured content block

의 2층 구조를 가질 수 있기 때문이다.

FabriX가 instruction text를 버리면,
upstream이 의도한 답변 형식·작성 제약을 잃게 된다.

따라서 FabriX는 **structured result와 instruction text를 함께 유지**해야 한다.

### 5-4. 내부 문서 검색과 `document_issue_tool` chaining

**파일**
- `ai_gateway/services/mcp/shared_planner/result_chaining.py`
- `ai_gateway/services/mcp/mcp_plan_executor.py`

**현재 구현**
FabriX는 이미 다음 흐름을 지원한다.

1. `search_docs_rag`
2. 필요 시 `read_doc` 동적 삽입 (`full_read_mode`)
3. `document_issue_tool`에 `document_text` 주입

이 설계는 FabriX host 기능 관점에서 매우 적절하다.

왜냐하면 upstream `document_issue_tool`는 `document_text`를 필요로 하고,
FabriX는 사내 문서 검색을 통해 그 입력을 만들어 줄 수 있기 때문이다.

여기서 책임 분리는 다음처럼 정리해야 한다.

- upstream LexGuard 책임:
  - 문서 텍스트를 받아 법률 분석 수행
  - 분석 결과와 작성 지시문 반환
- FabriX 책임:
  - 어떤 문서를 읽을지 결정
  - snippet이 아니라 full text를 넘길지 결정
  - search → read → analyze chain을 구성

즉, 이 부분은 **FabriX가 구현해야 할 host-side orchestration의 대표 사례**다.

---

## 6. FabriX가 새로 설계하면 안 되는 것

다음 항목은 FabriX가 임의로 재정의하면 안 된다.

1. `document_issue_tool` 응답 의미를 upstream과 다르게 재해석하는 것
2. upstream instruction text를 버리고 FabriX가 별도 답변 형식을 강제하는 것
3. LexGuard structured result를 host 쪽에서 과도하게 요약·변형해 의미를 잃는 것
4. upstream tool semantics와 충돌하는 pseudo-workflow를 만드는 것

실무적으로는 다음처럼 이해하면 된다.

- **tool 의미는 upstream 소유**
- **tool 선택과 연결은 FabriX 소유**

이 경계를 어기면,
direct test와 chat runtime의 해석이 어긋나고 유지보수가 어려워진다.

---

## 7. FabriX가 직접 책임져야 하는 것

FabriX가 설계·유지해야 하는 핵심 항목은 다음이다.

1. tool activation rules
2. multi-step plan ordering
3. doc search ↔ legal tool chaining
4. transport/API failure filtering
5. tool-level failure의 LLM context 유입 차단
6. instruction text + structured result 동시 유지
7. 최종 chat UX와 system prompt merge 정책

즉, FabriX는 LexGuard를 “대체 구현”하는 것이 아니라,
**LexGuard를 안전하게 사용할 수 있게 만드는 host orchestration layer**를 책임진다.

---

## 8. tool별 FabriX 해석 원칙

### 8-1. `legal_qa_tool`

**FabriX에서의 위치**
- 일반 법률 질문의 기본 진입점
- broad legal intent에 대한 1차 도구

**통합 원칙**
- 결과는 최종 답변이 아니라 **법적 근거의 실마리**로 취급한다.
- FabriX는 raw structured result를 LLM context로 넘기고,
  최종 답변은 LLM이 작성하게 한다.

**직접 테스트로 확인된 pass 조건**
- `success=True`, `results`가 dict 타입으로 존재함.
- `has_legal_basis=False`, `missing_reason=NO_MATCH` 인 sparse/no-result 응답도 정상 contract 범주다.

### 8-2. `law_article_tool`

**FabriX에서의 위치**
- 법령명 + 특정 조문번호가 명시된 정밀 조회 도구
- 일반 QA보다는 조문 근거 조회 도구

**통합 원칙**
- specificity가 높은 질의에서만 발화한다. 법령명과 조문번호가 모두 명시된 경우에만 activation한다.
- `legal_qa_tool` 후속 근거 보강 chain으로도 사용할 수 있다.
- provider retrieval 실패는 host workflow 실패와 분리해 관리한다. 상세는 아래 참조.

**직접 테스트로 확인된 pass 조건**
- `content`가 존재하고 `"조문 내용을 찾을 수 없습니다."`를 포함하지 않음.
- `raw_data`가 채워져 있어도 위 조건을 만족하지 않으면 FAIL이다.

**직접 테스트 및 소스 조사로 확인된 provider 동작 사실**

다음 사실은 직접 테스트와 소스 조사를 통해 확인된 것이다.

1. **확인된 실패 패턴**: `건축법 제3조`, `건축법 제3조제1항제2호다목` 케이스에서
   `content="조문 내용을 찾을 수 없습니다."` 와 함께 `raw_data`에 `법령 → 기본정보`(메타데이터)만
   반환되는 실패가 직접 테스트에서 재현되었다 (초기 6/8 통과).

2. **소스 확인된 원인**: provider `law_detail.py`가 `eflawjosub` 응답의 최상위 `법령` 컨테이너를
   unwrap하지 않고, `법령 → 조문정보 → 조문단위` 경로로 내려가지 않았다.
   조문 본문은 해당 경로에 존재할 수 있으며, `raw_data`가 메타데이터만 보여도 실제 조문 내용이
   그 경로에 있을 수 있다.

3. **로컬 수정 결과**: `law` target JSON fallback으로 `법령 → 조문정보 → 조문단위` 경로를
   추가한 후 직접 테스트 **8/8 통과** 달성.

4. **host 주의사항**: `raw_data` 존재 여부로 조문 조회 성공을 판단하면 안 된다.
   반드시 `content` 필드로 실패 sentinel(`"조문 내용을 찾을 수 없습니다."`)을 확인해야 한다.
   이 실패는 provider-level retrieval 문제이며 host orchestration 오류가 아니다.
   host는 이 sentinel을 LLM context에 그대로 주입하지 않아야 한다.

### 8-3. `law_comparison_tool`

**FabriX에서의 위치**
- 신구법, 연혁, 3단 비교 전용 도구

**통합 원칙**
- 일반 법률 QA의 대체 도구로 사용하지 않는다.
- 비교 intent가 명확할 때만 activation한다.
- 결과는 비교 데이터 context로 LLM에 넘긴다.

**직접 테스트로 확인된 pass 조건**
- `error` 없음, `law_name` 존재, `comparison` 비어있지 않음. 비교 intent가 명확한 질의에서만 유효하다.

### 8-4. `document_issue_tool`

**FabriX에서의 위치**
- 문서 분석용 핵심 도구
- 최종 답변 생성기가 아니라 **중간 분석 패키지 provider**

**통합 원칙**
- `document_text` 확보가 가장 중요하다.
- tool 단독 응답을 곧바로 사용자 출력으로 쓰지 않는다.
- `response_policy`, `instruction_text`, `document_analysis`, `citations`, `retry_plan`을 모두 고려해 LLM이 최종 답변을 작성하도록 한다.

**직접 테스트로 확인된 pass 조건**
- `analysis_success=True`, `detected=True`. issues 목록만 있고 citations 없는 경우도 PASS다.
  `missing_reason`이 `API_ERROR`로 시작하면 FAIL이다.

즉 FabriX는 `document_issue_tool`를 "완결 보고서 API"로 다루지 않고,
**문서 분석 + 근거 초안 + 작성 규칙 제공 도구**로 다루는 것이 맞다.

---

## 9. FabriX 구현 원칙

### 9-1. Host boundary 원칙

FabriX는 LexGuard에 대해 다음 경계를 유지해야 한다.

- **LexGuard server가 tool semantics를 정의한다.**
- **FabriX host가 plan / chaining / context merge를 정의한다.**
- **최종 answer rendering은 FabriX의 LLM runtime이 담당한다.**

이 세 층을 섞지 않는 것이 통합 품질과 유지보수성의 핵심이다.

### 9-2. Context injection 원칙

LexGuard 결과를 LLM에 전달할 때는 다음을 유지한다.

- structured result 유지
- instruction text 유지
- transport/API failure는 필터링
- tool-level failure는 normal mode에서 기본적으로 context 제외

현재 `render_legal_context_system_prompt()` 방향은 이 원칙과 맞다.

### 9-3. Chaining 원칙

FabriX에서 권장되는 chain은 다음과 같다.

1. **일반 법률 질문**
   - user query → `legal_qa_tool` → LLM answer

2. **특정 조문 질문**
   - user query → `law_article_tool` → LLM answer

3. **외부 입력 문서 분석**
   - document text 입력 → `document_issue_tool` → LLM answer

4. **사내 문서 검색 기반 분석**
   - query → `search_docs_rag` → `read_doc` → `document_issue_tool` → LLM answer

5. **향후 강화형 후속 chain**
   - `document_issue_tool` 결과의 `retry_plan.suggested_queries` 또는 `document_analysis`를 바탕으로
   - 추가 `legal_qa_tool` / `law_article_tool` 호출
   - 이후 최종 answer synthesis

5번은 아직 FabriX에 완전히 구현되어 있지 않아도,
**향후 host 고도화 방향**으로 문서화할 가치가 있다.

---

## 10. 현재 구현과의 정합성 평가

### 10-1. 이미 잘 맞는 부분

1. FabriX가 LexGuard를 외부 MCP provider로 다루고 있음
2. planner rule로 tool activation을 분리하고 있음
3. structured result를 보존하고 있음
4. instruction text를 별도로 추출하고 있음
5. 최종 답변을 LLM이 생성하도록 설계되어 있음
6. `search_docs_rag -> read_doc -> document_issue_tool` chaining이 이미 존재함

### 10-2. 보강이 필요한 부분

1. upstream `tools/list.description` / `document_issue_prompts.py`와 FabriX rule 간 drift 감시 필요
2. `document_issue_tool -> legal_qa_tool / law_article_tool` 후속 강화 chain 필요 여부를 제품 요구사항으로 분리 필요
3. direct test contract와 chat orchestration workflow 분리는 §8에 기술되어 있다. tool별 pass 조건과 host 주의사항은 §8 각 subsection을 기준으로 한다.
4. upstream output schema와 실제 observed payload 차이는 host 설계 문제와 분리해 기록해야 함

---

## 11. 최종 결론

FabriX가 LexGuard 통합에서 따라야 할 핵심 원칙은 다음과 같이 정리할 수 있다.

> **LexGuard는 upstream이 이미 정의한 AI-friendly MCP legal tool server이고, FabriX는 그 결과를 조합해 최종 답변을 만드는 host/orchestrator로 동작해야 한다.**

실무적으로는 다음처럼 이해하면 된다.

- `document_issue_tool`을 포함한 tool workflow를 FabriX가 처음부터 새로 발명할 필요는 없다.
- authoritative source는 우선적으로 upstream이다.
  - `src/routes/mcp_routes.py`
  - `src/utils/document_issue_prompts.py`
  - 각 service / repository 구현
- FabriX는 그 위에서 다음을 구현한다.
  - activation
  - chaining
  - failure filtering
  - context injection
  - final LLM synthesis

이 역할 분리를 유지해야 FabriX의 MCP host 기능이 upstream과 충돌하지 않고,
실제 제품 목적에 맞는 통합 품질을 유지할 수 있다.

---

## 12. 실무 액션 아이템

### 단기
1. LexGuard integration 관련 내부 판단은 이 문서를 기준으로 맞춘다.
2. direct test 결과 해석 시 “tool contract”와 “orchestration contract”를 분리한다.
3. `document_issue_tool`을 final answer generator로 가정하지 않는다.

### 중기
1. `document_issue_tool -> legal_qa_tool / law_article_tool` 후속 강화 chain 필요 여부를 제품 요구사항으로 확정한다.
2. upstream tool descriptions / prompts 변경 시 FabriX rule drift 점검 절차를 만든다.
3. MCP Inspector 기준 capability / response shape 검증 절차를 추가한다.

### 장기
1. LexGuard provider integration regression 문서/테스트 체계를 정리한다.
2. host-side multi-tool legal orchestration 정책을 별도 문서로 정식화한다.
3. provider-specific prompt merge 정책을 정교화한다.
