# FabriX Chat Multi-Agent 아키텍처 설계
## LexGuard MCP 통합 — 첫 번째 External Agent 구현

> **문서 목적**: FabriX Chat의 `/mcp` 문서 검색 기능을 Multi-Agent 파이프라인으로 확장하는 완전한 설계 문서.
> LexGuard MCP 통합이 첫 번째 External Agent이며, 이 설계는 향후 추가 Agent를 동일한 패턴으로 통합하기 위한 확장 아키텍처를 포함한다.

---

## 1. 배경 및 목표

### 현재 상태
- FabriX Chat은 `/mcp set <카테고리>` 활성화 시 내부 FastMCP Doc Server(포트 8002)에서 BM25 기반 RAG 검색을 수행
- `rag-search` 엔드포인트 (`doc_search.py`) 가 문서 스니펫을 가져와 `system_prompt`로 조립
- RAG 결과는 단일 소스(내부 문서 카테고리)만 활용

### 목표
- 질문이 **법령/계약서 도메인**에 해당하면, `/mcp` 활성화 여부와 무관하게 **LexGuard MCP 도구를 자동 호출**하여 법령 검색/계약서 분석 결과를 system_prompt에 병렬 주입
- 이를 기반으로 향후 **다른 External Agent(특허, 의료, 회계 등)를 최소한의 코드로 추가**할 수 있는 확장 구조 설계

---

## 2. Multi-Agent 확장 아키텍처 설계

### 2.1 핵심 추상화: Agent Interface

모든 External Agent는 다음 인터페이스를 구현해야 한다:

```python
# ai_gateway/services/agent_base.py (신규 생성)
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

@dataclass
class AgentContext:
    """Agent 실행에 필요한 모든 컨텍스트"""
    query: str                              # 사용자 원문 입력
    category: str | None = None             # /mcp set으로 설정한 카테고리명 (should_invoke 판단용)
    is_law_related: bool = False            # 법령 관련 여부 (카테고리 or 키워드 기반)
    has_real_document: bool = False         # 계약서/약관 구조 감지
    document_text: str | None = None        # 계약서 원문 (document_issue_tool용)
    legal_qa_context: str = ""              # 합성된 상황 서술 (legal_qa_tool용)
    doc_type: str | None = None             # 감지된 문서 종류
    extracted_clauses: list[str] = field(default_factory=list)

@dataclass
class AgentResult:
    """Agent 실행 결과"""
    agent_name: str
    content: str | None                     # system_prompt 섹션으로 추가될 텍스트
    used: bool = False                      # 실제 호출 여부
    priority: int = 10                      # 낮을수록 먼저 보호 (token budget)
    badge_label: str | None = None          # UI 배지 텍스트 (예: "⚖️ 법령")

class ExternalAgent(ABC):
    """모든 External Agent가 구현해야 하는 기본 인터페이스"""

    @property
    @abstractmethod
    def name(self) -> str:
        """Agent 고유 이름 (로그/배지 표시용)"""

    @property
    @abstractmethod
    def priority(self) -> int:
        """토큰 예산 소진 시 보호 우선순위 (낮을수록 먼저 보호)"""

    @abstractmethod
    def should_invoke(self, context: AgentContext, config: dict) -> bool:
        """이 Agent를 호출해야 하는지 결정"""

    @abstractmethod
    async def invoke(self, context: AgentContext, config: dict) -> AgentResult:
        """Agent를 실제 호출하고 결과 반환. 실패 시 AgentResult(used=False) 반환"""
```

### 2.2 Agent Registry (설정 기반 확장)

새 Agent 추가 시 코드 변경 없이 `secrets.toml`에 섹션만 추가:

```toml
# secrets.toml

[lexguard]
enabled = true
base_url = "https://lexguard-mcp.onrender.com/mcp"
# law_category_keywords는 lexguard_domain_keywords.json에서 관리

# 향후 추가 예시:
[patent_agent]
enabled = false
base_url = "https://patent-mcp.example.com/mcp"

[medical_agent]
enabled = false
base_url = "https://medical-mcp.example.com/mcp"
```

### 2.3 Agent 파일 레이아웃

```
ai_gateway/
├── services/
│   ├── agent_base.py              ← 추상 인터페이스 (AgentContext, AgentResult, ExternalAgent)
│   ├── lexguard_service.py        ← LexGuard Agent 구현 (첫 번째 External Agent)
│   └── (future) patent_service.py  ← 특허 Agent 추가 시
├── data/
│   ├── lexguard_domain_keywords.json  ← LexGuard 도메인 키워드 사전
│   └── (future) patent_keywords.json  ← 특허 키워드 사전
└── routers/
    └── doc_search.py              ← 오케스트레이터 (등록된 Agent 목록 관리)
```

### 2.4 Orchestrator (doc_search.py)의 확장 포인트

```python
# doc_search.py 내부 — 등록된 Agent 목록
# 새 Agent 추가 시 이 목록에만 추가하면 됨
REGISTERED_AGENTS: list[ExternalAgent] = [
    LexGuardAgent(),           # 첫 번째 Agent
    # PatentAgent(),           # 두 번째 Agent 추가 예시
    # MedicalAgent(),
]
```

---

## 3. 두 가지 실행 경로

```
[사용자 입력]
     │
     ├─ /로 시작 → 커맨드 처리 (기존 그대로)
     │
     └─ 일반 메시지 → handleSend()
           │
           ├─ [경로 A] ragEnabled=true (기존 /mcp 활성)
           │     mcpRagApi.search(query, category)
           │       → ① 내부 RAG: FastMCP Doc Server(포트 8002)
           │       → ② 등록된 Agent 중 should_invoke() = true인 것 asyncio.gather 병렬 실행
           │           (LexGuard의 경우: is_law_category(category)이면 실행)
           │       → ③ system_prompt: 내부RAG 섹션 + Agent 섹션들 병합
           │       → ④ { system_prompt, lexguard_used, ... } 반환
           │
           └─ [경로 B] ragEnabled=false (새로 추가)
                 mcpSmartAugmentApi.check(query)
                   → ① classify_query_intent(): is_law_related? has_real_document?
                   → ② 불필요하면 즉시 { system_prompt: null, agents_used: [] } 반환 (fast path)
                   → ③ 필요하면 should_invoke()=true인 Agent만 asyncio.gather
                   → ④ system_prompt 반환 (null이면 FabriX에 system_prompt 없이 호출)
           │
           └─ FabriX Chat SSE API (system_prompt 주입 — 기존 그대로)
```

---

## 4. LexGuard 서버 아키텍처 분석 및 통합 원칙

### 4.1 LexGuard 서버 전체 아키텍처

```
Client (Cursor / Claude)
  │  JSON-RPC 2.0 over SSE
  ▼
FastAPI (/mcp POST)
  │  Rate Limiting (slowapi, 60 req/min/IP)
  ▼
MCP Routes (tools/call · prompts/get · resources/read)
  │
  ▼
Services (SmartSearchService · SituationGuidanceService)
  │  asyncio.gather (병렬 멀티 API 호출)
  ▼
Repositories (Law · Precedent · Interpretation · Appeal · Constitutional …)
  │  httpx (비동기 HTTP)
  │  TTLCache (검색 결과 30분 / 실패 5분)
  │  Exponential Backoff Retry
  ▼
국가법령정보센터 DRF API (172개 엔드포인트)
```

### 4.2 ht_tools 통합의 핵심 원칙 — "LexGuard는 블랙박스"

아키텍처 분석에서 도출된 가장 중요한 설계 원칙:

**LexGuard가 이미 내부적으로 처리하는 것** → 우리가 중복 구현하면 안 됨:

| LexGuard 내부 기능 | 위치 | 우리가 할 필요 없는 것 |
|---|---|---|
| 법령/판례/해석/행정심판 **병렬 검색** | Services → asyncio.gather | 개별 저장소 호출 |
| **TTLCache** 30분 / 실패 5분 | Repositories | LexGuard 응답 별도 캐싱 |
| **Exponential Backoff Retry** | Repositories | LexGuard 호출 재시도 로직 |
| **도메인 감지** (`detect_legal_domain`) | SmartSearchService | 법률 도메인 분류 (내부에서 함) |
| **쿼리 정규화** (`normalize_query_for_search`) | SmartSearchService | 검색 쿼리 전처리 |

**우리(ht_tools)가 담당해야 하는 것**:

| 우리 역할 | 이유 |
|---|---|
| **게이트키핑**: `is_law_related` / `has_contract` 판단 | 불필요한 LexGuard 호출 방지 (60 req/min/IP 공유 제한) |
| **도구 선택**: `legal_qa_tool` vs `document_issue_tool` vs 둘 다 | LexGuard가 제공하지 않는 규칙 기반 분기 |
| **입력 포매팅**: 올바른 형식으로 각 도구에 전달 | 도구별 요구 입력 형식이 다름 |
| **우리 레벨 asyncio.gather**: 두 도구 **동시** 호출 | 경로 A/B에서 두 도구 병렬화 (LexGuard 내부 병렬화와 다른 레벨) |
| **그레이스풀 디그레이드**: 전체 실패 시 내부 RAG만으로 계속 | 네트워크 장애, Render cold start, 429 초과 |
| **결과 병합 + 토큰 예산 관리** | system_prompt 조립 및 길이 조절 |

### 4.3 transport 및 클라이언트 연결

- **LexGuard transport**: JSON-RPC 2.0 over SSE (`/mcp POST`)
- **기존 `fastmcp.Client`**: `async with Client(url) as client: await client.call_tool(...)` 패턴이 **그대로 적용됨**
- 내부 FastMCP Doc Server(포트 8002) 호출 코드와 동일한 패턴 사용 가능

```python
# 기존 내부 Doc Server 호출 (doc_search.py)
async with Client("http://127.0.0.1:8002/mcp") as client:
    result = await client.call_tool("search_docs", {...})

# LexGuard 원격 서버 호출 — 동일 패턴
async with Client("https://lexguard-mcp.onrender.com/mcp") as client:
    result = await client.call_tool("legal_qa_tool", {"query": "..."})
```

### 4.4 Rate Limit 전략 (60 req/min/IP)

- 60 req/min은 우리 서버 IP 기준 (멀티 사용자 공유)
- **우리 게이트키핑이 핵심 방어**: `is_law_related=False`이면 LexGuard를 아예 호출하지 않음
- 429 수신 시: `{"system_prompt": null, "agents_used": [], "error": "rate_limit"}` graceful degrade
- 우리 FastAPI에서 재시도 로직 불필요 (LexGuard 내부 backoff는 외부 법령 API용)

### 4.5 TTLCache 활용

- 동일 질문 30분 이내 재호출 → LexGuard 서버가 캐시 응답 (빠름)
- **우리 측 별도 캐싱 불필요** → 구현 복잡도 감소
- 단, Render free tier의 **cold start**(10~30초)는 캐시 무효화됨
  - cold start 대응: `timeout=30` 설정 + 실패 시 graceful degrade

### 4.6 MCP Routes 활용 범위

LexGuard가 노출하는 세 가지 MCP 라우트:

| MCP 라우트 | 우리 사용 여부 | 이유 |
|---|---|---|
| `tools/call` | ✅ **사용** | `legal_qa_tool`, `document_issue_tool` 직접 호출 |
| `prompts/get` | ⚠️ **참고용** | 입력 포맷 가이드로 활용. 프롬프트 자체는 FabriX LLM 호출이 추가되어 비효율 |
| `resources/read` | ❌ **미사용** | 정적 법령 리소스 — 현재 통합 범위 외 (Phase 2 고려) |

**`prompts/get` 활용 방법**: 구현 전 LexGuard에 `client.list_prompts()`를 한 번 호출하여 어떤 프롬프트 템플릿이 있는지 확인. 이를 바탕으로 `legal_qa_tool` 입력 포맷을 최적화.

---

## 5. LexGuard MCP 도구 상세 분석

### 5.1 소스코드 검증 완료
출처: https://github.com/SeoNaRu/lexguard-mcp (README + situation_guidance_service.py + smart_search_service.py)

### 5.2 MCP 클라이언트의 도구 선택 메커니즘

Cursor, Claude Desktop 같은 MCP 클라이언트는 이렇게 동작한다:

```
1. MCP 서버 tools/list 조회 → 도구 이름 + description + input_schema 수신
2. 사용자 메시지 + 도구 목록 → LLM에 전달
3. LLM이 "이 질문에는 어떤 도구?" 판단 → tool_call 발행
4. 클라이언트가 선택된 도구 실행 → 결과를 다시 LLM에 전달
```

**ht_tools에서의 도전**: ht_tools는 MCP 서버에 직접 `fastmcp.Client`로 tool_call을 하기 때문에, **LLM 없이 규칙 기반으로 도구 선택 로직을 구현**해야 한다. 이것이 `classify_query_intent()`의 역할이다.

### 5.3 공식 README에서 확인된 도구 선택 기준

| 도구 | 설계 의도 | 올바른 사용 시점 |
|---|---|---|
| `legal_qa_tool` | **"모든 법률 질문의 단일 진입점"** — 범용 법률 QA | 일반 법령 질문, 판례 검색 |
| `document_issue_tool` | 계약서/약관 **붙여넣기** 전용 분석 | 사용자가 계약서 원문을 붙여넣었을 때 |
| `law_article_tool` | 특정 법령명+조문번호 정밀 조회 | "근로기준법 제50조 알려줘" 같은 경우 |

**도구 선택 결정 로직**:

```
[일반 법령 질문, 문서 없음]
  → legal_qa_tool만 호출
  예: "퇴직금 지급 기한이 법령상 며칠인지?"

[계약서 원문 붙여넣기, 질문 없음]
  → document_issue_tool만 호출
  이유: 내부에서 이미 관련 법령 자동 검색 수행
  예: [임대차계약서 전문 붙여넣기]

[계약서 + 법령 질문 혼합]
  → 두 도구 asyncio.gather 병렬 호출 (우리 레벨)
  예: "이 하도급계약서 제5조, 하도급법 위반인지?"

[법령 무관]
  → 두 도구 모두 호출하지 않음 (fast path)

[특정 조문 번호 질문 - 현재 범위 외]
  → law_article_tool (Phase 2 이후 고려)
  예: "근로기준법 제50조 내용 알려줘"
```

### 5.4 `document_issue_tool` — 계약서/약관 법적 이슈 분석

**내부 서비스**: `SituationGuidanceService.document_issue_analysis(document_text)`

```python
# 검증된 내부 코드 (lexguard-mcp/situation_guidance_service.py)
def build_document_analysis(self, situation: str):
    has_clause_pattern = bool(re.search(r"제\s*\d+\s*조", situation))
    if not any(k in situation for k in ["계약서", "약관", "임대인", "임차인"]) \
       and not has_clause_pattern:
        return None  # ← 계약서 구조 없으면 None 반환, 도구 무효화
    # 조항 추출: re.compile(r'(제\s*\d+\s*조[^\n]*)')
    # 조항별 법적 이슈 감지 → 관련 법령 자동 검색 (내부 처리)
```

**공식 지원 문서 타입**:
- `labor` — 근로계약서 / 용역계약서
- `lease` — 임대차 계약서
- `terms` — 이용약관

> ⚠️ **건설공사 계약서는 공식 지원 타입에 없음** (건설공사, 도급계약 등 미포함).
> 단, `제N조` 패턴이 있으면 조항 추출 regex가 동작하므로 부분적으로 작동 가능.
> 실제 사용 전 건설공사계약서로 테스트 필요. 작동하지 않으면 `legal_qa_tool`만 사용.

**핵심 제약사항**:
- `제N조` 패턴 또는 `["계약서", "약관", "임대인", "임차인"]` 키워드 중 하나 이상 필요
- 입력이 실제 계약서/약관 FULL TEXT가 아니면 내부에서 None 반환 → 빈 결과
- **이 도구는 자체적으로 관련 법령 검색을 수행** → 계약서가 있을 때 단독으로 충분

### 5.5 `legal_qa_tool` — 범용 법령·판례·해석 종합 검색

**내부 서비스**: `SmartSearchService.comprehensive_search_v2(query)`

```python
# 검증된 내부 코드 (lexguard-mcp/smart_search_service.py)
LEGAL_DOMAIN_KEYWORDS = {
    "노동": [...], "세금": [...], "부동산": [...], "소비자": [...], ...
}

def comprehensive_search_v2(self, situation: str):
    domains = self.detect_legal_domain(situation)      # 법적 영역 자동 감지
    terms = self.extract_key_terms(situation)          # 핵심 용어 추출
    query = self.normalize_query_for_search(situation, domains, terms)  # 검색 정규화
    # asyncio.gather: 법령 조문 + 판례 + 법령 해석 + 행정심판 병렬 검색 (172개 엔드포인트)
```

**핵심 특성**:
- 단순 키워드가 아닌 **상황 서술(situation description)**을 입력받아 내부에서 도메인 감지
- `legal_qa_tool`에는 "질문만 분리"하지 않고 **문서 컨텍스트 + 사용자 의도를 합성**하여 전달
- 잘못된 입력: 문서 원문에서 질문 부분만 분리 (컨텍스트 손실로 도메인 감지 실패 가능)
- **`legal_qa_tool`을 호출하면 LexGuard가 내부적으로 법령/판례/해석/행정심판을 모두 병렬 검색** → 우리가 개별 저장소를 다시 병렬화할 필요 없음

### 5.6 `law_article_tool` — 특정 법령 조문 직접 조회 (향후 확장)

**내부 서비스**: `LawDetailRepository.get_law(law_name, article_number, ...)`
- 특정 법령명 + 조문 번호가 명확히 알려진 경우에만 유용
- 현재 구현 범위 외 (Phase 2 이후 고려)

---

## 6. 질의 재작성 전략 (핵심 설계)

두 도구는 완전히 다른 **입력 형식**이 요구된다.

### 6.1 `document_issue_tool` 입력 구성

```
호출 조건: has_real_document = True 일 때만

소스 우선순위:
  1. 경로 A (RAG active, @파일명 지정): RAG에서 가져온 전체 파일 내용 (최대 14000자)
  2. 경로 A (RAG active, 일반 검색): 상위 RAG 스니펫들을 결합한 텍스트
  3. 경로 B (스마트 감지): 사용자가 채팅창에 붙여넣은 계약서 본문
     (classify_query_intent()에서 감지: len>500 AND 계약서 구조 패턴)

전달 내용:
  - 계약서/약관 원문 그대로
  - 사용자의 메타 질문("검토해줘", "어떻게 생각해?") 제거
  - 조항 구조 (제N조) 반드시 보존
```

### 6.2 `legal_qa_tool` 입력 구성 — 상황 서술 합성

```python
# 시나리오 1: 문서 + 질문 혼합
# User: "이 계약서 제5조가 법을 위반하나요? [계약서 내용]"
legal_qa_context = f"{사용자 질문}\n관련 문서: {doc_type}, 핵심 조항: {', '.join(extracted_clauses[:3])}"
# 예: "이 계약서 제5조가 법을 위반하나요?\n관련 문서: 임대차계약서, 핵심 조항: 제5조(보증금반환), 제7조(해지)"

# 시나리오 2: 문서만 붙여넣기 (질문 없음)
# User: "[계약서 내용만 붙여넣기]"
legal_qa_context = f"다음 {doc_type} 문서의 법적 이슈를 분석해주세요. 핵심 조항: {', '.join(extracted_clauses[:3])}"
# 예: "다음 근로계약서 문서의 법적 이슈를 분석해주세요. 핵심 조항: 제3조(임금), 제6조(근로시간)"

# 시나리오 3: 법령 질문만 (문서 없음)
# User: "퇴직금 지급 기한이 법령상 며칠인가요?"
legal_qa_context = 사용자 원문 그대로  # 재작성 불필요

# 시나리오 4: 법령 무관
# → legal_qa_tool 호출 안 함
```

### 6.3 `classify_query_intent()` 반환 구조

```python
@dataclass
class QueryIntentResult:
    is_law_related: bool           # law_intent_keywords 포함 여부
    has_real_document: bool        # clause_patterns 또는 도메인 키워드+len>500
    document_text: str | None      # 계약서 원문 (document_issue_tool용)
    legal_qa_context: str          # 합성된 상황 서술 (legal_qa_tool용)
    doc_type: str | None           # "임대차계약서", "건설공사계약서" 등
    extracted_clauses: list[str]   # ["제N조 ..." 조항명 목록]
```

---

## 7. JSON 키워드 사전 — 확장 가능한 도메인 감지

### 7.1 파일 위치 및 목적

`ai_gateway/.agentConfig/lexguard_domain_keywords.json`

**목적**: LexGuard의 하드코딩된 `["계약서", "약관", "임대인", "임차인"]`을 확장하여 건설공사 등 다양한 도메인 감지. 코드 수정 없이 JSON 파일 편집으로 도메인 추가 가능.

### 6.2 JSON 구조

```json
{
  "_comment": "법령/계약서 도메인 키워드 사전. 코드 수정 없이 이 파일만 편집하여 도메인 확장 가능.",

  "law_intent_keywords": [
    "법령", "법률", "조항", "조문", "판례", "계약서", "약관", "근로계약", "임대차",
    "해고", "위반", "위법", "손해배상", "위약금", "법원", "소송", "분쟁",
    "시행령", "시행규칙", "고시", "지침", "처벌", "벌칙", "과태료", "행정처분",
    "하도급법", "건설업법", "계약해지", "지체상금", "하자보수", "공사대금",
    "개인정보보호법", "근로기준법"
  ],

  "_comment_law_intent": "위 키워드가 일반 질문에 등장하면 legal_qa_tool을 호출한다. 범용 업무 용어(건설공사 단독, 계획, 예산 등)는 포함하지 않는다.",

  "document_domains": {
    "construction": {
      "description": "건설공사 도메인",
      "keywords": [
        "건설공사", "공사계약", "도급계약", "하도급계약", "수급인", "발주자",
        "시공사", "원도급", "하도급", "설계변경", "준공", "공사대금",
        "하자보수", "공사감리", "감독관", "계약금액", "공사기간",
        "착공", "준공검사", "하자담보", "실비정산", "물가변동"
      ],
      "doc_types": ["건설공사계약서", "하도급계약서", "도급계약서", "공사도급계약"]
    },
    "employment": {
      "description": "근로/노동 도메인",
      "keywords": [
        "근로계약", "임금", "해고", "퇴직금", "취업규칙",
        "근로시간", "연장근무", "야간근무", "휴일근무", "4대보험",
        "연차휴가", "출산휴가", "육아휴직", "최저임금"
      ],
      "doc_types": ["근로계약서", "노동계약서", "고용계약서"]
    },
    "rental": {
      "description": "임대차 도메인",
      "keywords": [
        "임대인", "임차인", "보증금", "월세", "전세", "전대",
        "임대료", "명도", "계약갱신", "갱신요구권", "임대차"
      ],
      "doc_types": ["임대차계약서", "전세계약서", "임대계약서"]
    },
    "general": {
      "description": "일반 계약 도메인",
      "keywords": [
        "계약서", "약관", "이용약관", "당사자",
        "갑은", "을은", "병은", "계약당사자", "서약서", "각서"
      ],
      "doc_types": ["계약서", "약관", "이용약관", "동의서", "각서"]
    }
  },

  "_comment_document_domains": "document_domains 키워드 + len>500이면 has_real_document=True로 판정. 매칭된 도메인의 doc_types에서 doc_type 결정.",

  "clause_patterns": [
    "제\\s*\\d+\\s*조",
    "[갑을병정][\\s은는이가]"
  ],

  "_comment_clause_patterns": "이 regex 패턴 중 하나라도 매칭되면 즉시 has_real_document=True. 글자수 제한 없음."
}
```

### 6.3 두 키워드 목록의 역할 구분 (중요)

| 목록 | 역할 | 감지 시 행동 | 예시 |
|---|---|---|---|
| `law_intent_keywords` | 법령 **의도** 감지 | `legal_qa_tool` 호출 | "퇴직금 지급 법령상 기한?" |
| `document_domains.*.keywords` + `len>500` | 계약서 **문서** 감지 | `document_issue_tool` 호출 | [계약서 본문 붙여넣기] |
| `clause_patterns` | 조항 **구조** 감지 | `has_real_document=True` | "제1조, 제2조..." |

**`law_intent_keywords` 설계 원칙**:
- ✅ 포함: 법령 고유 용어 (법령, 위반, 소송, 판례, 지체상금, 하도급법 등)
- ❌ 제외: 범용 업무 용어 (건설공사 단독, 계획, 예산, 일정 등)
- 이유: 범용 용어가 있으면 일반 업무 질문에도 LexGuard가 불필요하게 호출됨

---

## 7. 토큰 로드밸런싱

### 7.1 기존 RAG budget 구조

```python
# _decide_prompt_budget() 현재 반환값:
# compact_hint: max_total_chars = 6000
# expand_hint:  max_total_chars = 12000
# default:      max_total_chars = 9000
```

### 7.2 LexGuard 추가 후 budget 조정 전략

**사전 고정 예산 없음** → `asyncio.gather` 완료 후 실제 응답 크기 기반 priority truncation:

```python
LEXGUARD_SOFT_CEILING = 8000  # LexGuard 결과 합산 소프트 상한 (조정 가능)

# 1. asyncio.gather → doc_issue_text, legal_qa_text 수신
# 2. if len(doc_issue_text) + len(legal_qa_text) > LEXGUARD_SOFT_CEILING:
#      Priority 1 보호: document_issue_tool 결과 유지 (PRIMARY)
#      Priority 2 감축: legal_qa_tool 결과 먼저 truncate (SECONDARY)
#      legal_qa_budget = max(0, LEXGUARD_SOFT_CEILING - len(doc_issue_text))
#      legal_qa_text = legal_qa_text[:legal_qa_budget]  # 단락 경계 기준
# 3. actual_lexguard = len(doc_issue_text) + len(legal_qa_text)
# 4. RAG budget 동적 조정:
#      rag_budget = max(2000, original_rag_budget - actual_lexguard)
#      # _select_prompt_snippets(max_total_chars=rag_budget) 재호출
```

**동작 특성**:
- LexGuard 응답이 짧으면 → RAG가 풀 예산 가져감
- LexGuard 응답이 길면 → RAG 예산 자동 압축
- `document_issue_tool` 결과는 최대한 보호 (계약서 분석이 핵심)
- `legal_qa_tool` 결과가 먼저 잘림

### 7.3 system_prompt 3섹션 병합 구조

```
당신은 사내 문서 기반 질문 답변 어시스턴트입니다.
아래 참고 자료를 바탕으로 사용자의 질문에 답하세요.

=== 사내 문서 ({category}) ===

{내부 RAG 스니펫들}

==================

=== 계약서·문서 법적 이슈 분석 (LexGuard) ===

{document_issue_tool 결과}

==================

=== 관련 법령·판례 검색 결과 (LexGuard) ===

{legal_qa_tool 결과}

==================
```

---

## 8. 구현 파일 목록 및 변경 사항

### 8.1 신규 생성 파일

| 파일 | 역할 |
|------|------|
| `ai_gateway/services/agent_base.py` | Multi-Agent 추상 인터페이스 (`AgentContext`, `AgentResult`, `ExternalAgent`) |
| `ai_gateway/services/lexguard_service.py` | LexGuard Agent 구현 (첫 번째 External Agent) |
| `ai_gateway/.agentConfig/lexguard_domain_keywords.json` | 도메인 키워드 사전 (건설공사 등 포함) |

### 8.2 수정 파일

| 파일 | 변경 내용 |
|------|-----------|
| `secrets.toml` | `[lexguard]` 섹션 추가 |
| `ai_gateway/routers/doc_search.py` | `rag_search` 엔드포인트 확장 (경로 A) + `smart_augment` 신규 (경로 B) + `REGISTERED_AGENTS` 목록 추가 |
| `frontend/src/api/fastapiApi.js` | `mcpSmartAugmentApi` export 추가 |
| `frontend/src/features/chat/ChatPage.jsx` | handleSend에 smart-augment 호출 + LexGuard 배지 |

---

## 9. `lexguard_service.py` 상세 설계

```python
# ai_gateway/services/lexguard_service.py

import json
import re
import logging
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from .agent_base import ExternalAgent, AgentContext, AgentResult

if TYPE_CHECKING:
    from fastmcp import Client

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
KEYWORDS_FILE = DATA_DIR / "lexguard_domain_keywords.json"
LEXGUARD_SOFT_CEILING = 8000

@lru_cache(maxsize=1)
def _load_domain_keywords() -> dict:
    """도메인 키워드 사전 1회 로드 (앱 재시작 전까지 캐시)"""
    with open(KEYWORDS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def classify_query_intent(query: str) -> dict:
    """
    쿼리에서 법령 의도와 계약서 문서 존재 여부를 감지한다.

    Returns:
        {
            "is_law_related": bool,         # law_intent_keywords 포함 여부
            "has_real_document": bool,       # clause_patterns OR 도메인 키워드+len>500
            "document_text": str | None,     # 계약서 원문 (document_issue_tool용)
            "legal_qa_context": str,         # 합성된 상황 서술 (legal_qa_tool용)
            "doc_type": str | None,          # 감지된 문서 종류
            "extracted_clauses": list[str],  # 조항명 목록
        }
    """
    kw = _load_domain_keywords()
    law_keywords = kw.get("law_intent_keywords", [])
    doc_domains = kw.get("document_domains", {})
    clause_patterns = [re.compile(p) for p in kw.get("clause_patterns", [])]

    # 1. 법령 의도 감지
    is_law_related = any(kw_item in query for kw_item in law_keywords)

    # 2. 계약서 구조 감지 (clause_patterns)
    has_clause_pattern = any(p.search(query) for p in clause_patterns)

    # 3. 도메인 키워드 + 길이 감지
    matched_domain = None
    matched_doc_type = None
    for domain_name, domain_info in doc_domains.items():
        if any(k in query for k in domain_info.get("keywords", [])):
            matched_domain = domain_name
            doc_types = domain_info.get("doc_types", [])
            matched_doc_type = doc_types[0] if doc_types else None
            break

    has_keyword_doc = bool(matched_domain) and len(query) > 500
    has_real_document = has_clause_pattern or has_keyword_doc

    # 4. 조항 추출
    extracted_clauses = re.findall(r"제\s*\d+\s*조[^\n]*", query)[:5]

    # 5. 문서 텍스트 분리 (질문과 문서 분리 시도)
    # 단순 휴리스틱: 첫 문장이 짧고 질문형이면 질문으로 간주
    document_text = None
    clean_query = query
    if has_real_document:
        lines = query.strip().split("\n")
        if len(lines) > 3:
            first_line = lines[0].strip()
            # 첫 줄이 질문형 (짧고 ? 포함 또는 100자 미만)이면 분리
            if len(first_line) < 100 and (first_line.endswith("?") or "?" in first_line or "요" in first_line[-5:]):
                clean_query = first_line
                document_text = "\n".join(lines[1:]).strip()
            else:
                document_text = query
                clean_query = ""

    # 6. legal_qa_context 합성
    if has_real_document and document_text and extracted_clauses:
        doc_type_label = matched_doc_type or "계약서"
        if clean_query:
            legal_qa_context = f"{clean_query}\n관련 문서: {doc_type_label}, 핵심 조항: {', '.join(extracted_clauses[:3])}"
        else:
            legal_qa_context = f"다음 {doc_type_label} 문서의 법적 이슈를 분석해주세요. 핵심 조항: {', '.join(extracted_clauses[:3])}"
    else:
        legal_qa_context = clean_query or query

    return {
        "is_law_related": is_law_related,
        "has_real_document": has_real_document,
        "document_text": document_text,
        "legal_qa_context": legal_qa_context,
        "doc_type": matched_doc_type,
        "extracted_clauses": extracted_clauses,
    }


class LexGuardAgent(ExternalAgent):
    """LexGuard MCP 법령 검색/계약서 분석 Agent"""

    @property
    def name(self) -> str:
        return "lexguard"

    @property
    def priority(self) -> int:
        return 1  # 낮을수록 먼저 보호 (document_issue가 priority=1, legal_qa가 priority=2)

    def should_invoke(self, context: AgentContext, config: dict) -> bool:
        """LexGuard 호출 여부 결정"""
        if not config.get("enabled", False):
            return False
        return context.is_law_related or context.has_real_document

    async def invoke(self, context: AgentContext, config: dict) -> AgentResult:
        """LexGuard MCP 도구 호출 (document_issue + legal_qa 병렬)"""
        from fastmcp import Client
        import asyncio

        base_url = config.get("base_url", "https://lexguard-mcp.onrender.com/mcp")

        try:
            async with Client(base_url) as client:
                tasks = []
                if context.has_real_document and context.document_text:
                    tasks.append(("doc_issue", _call_document_issue_tool(client, context.document_text)))
                if context.is_law_related:
                    tasks.append(("legal_qa", _call_legal_qa_tool(client, context.legal_qa_context)))

                if not tasks:
                    return AgentResult(agent_name=self.name, content=None, used=False)

                results = await asyncio.gather(*[t[1] for t in tasks], return_exceptions=True)

                doc_issue_text = ""
                legal_qa_text = ""
                for (task_name, _), result in zip(tasks, results):
                    if isinstance(result, Exception):
                        logger.warning("LexGuard %s 실패: %s", task_name, result)
                    elif task_name == "doc_issue":
                        doc_issue_text = result or ""
                    elif task_name == "legal_qa":
                        legal_qa_text = result or ""

                # Priority truncation
                combined = len(doc_issue_text) + len(legal_qa_text)
                if combined > LEXGUARD_SOFT_CEILING:
                    legal_qa_budget = max(0, LEXGUARD_SOFT_CEILING - len(doc_issue_text))
                    legal_qa_text = legal_qa_text[:legal_qa_budget]

                # 섹션 조립
                sections = []
                if doc_issue_text:
                    sections.append(f"=== 계약서·문서 법적 이슈 분석 (LexGuard) ===\n\n{doc_issue_text}")
                if legal_qa_text:
                    sections.append(f"=== 관련 법령·판례 검색 결과 (LexGuard) ===\n\n{legal_qa_text}")

                if not sections:
                    return AgentResult(agent_name=self.name, content=None, used=False)

                content = "\n\n==================\n\n".join(sections)
                return AgentResult(
                    agent_name=self.name,
                    content=content,
                    used=True,
                    priority=self.priority,
                    badge_label="⚖️ 법령",
                )

        except Exception as e:
            logger.warning("LexGuard Agent 전체 실패 (graceful degrade): %s", e)
            return AgentResult(agent_name=self.name, content=None, used=False)


async def _call_document_issue_tool(client, document_text: str, max_clauses: int = 3) -> str:
    """document_issue_tool 호출 — 계약서 원문 분석"""
    result = await client.call_tool("document_issue_tool", {"document_text": document_text})
    if result.data is not None:
        return str(result.data)
    return "\n".join(c.text for c in result.content if hasattr(c, "text"))


async def _call_legal_qa_tool(client, legal_qa_context: str, max_results: int = 3) -> str:
    """legal_qa_tool 호출 — 법령/판례 종합 검색"""
    result = await client.call_tool("legal_qa_tool", {"query": legal_qa_context})
    if result.data is not None:
        return str(result.data)
    return "\n".join(c.text for c in result.content if hasattr(c, "text"))
```

---

## 10. `doc_search.py` 수정 상세

### 10.1 경로 A: `rag_search` 엔드포인트 확장

```python
# rag_search() 함수 내부 수정점:

# --- 기존 끝부분 (system_prompt 조립 완료 이후) ---
# 추가할 코드:

# [Multi-Agent 주입] 등록된 Agent 실행
from .services.agent_base import AgentContext
from .services.lexguard_service import LexGuardAgent, classify_query_intent, is_law_category

REGISTERED_AGENTS = [LexGuardAgent()]  # 파일 상단에 정의

lexguard_config = _get_lexguard_config()  # secrets.toml [lexguard] 로드

# category가 법령 카테고리에 속하는 경우에만 경로 A에서 LexGuard 실행
# is_law_category()는 lexguard_domain_keywords.json의 law_category_keywords 기준으로 판단
agent_context = None
agents_used = []

if body.category and is_law_category(body.category):
    intent = classify_query_intent(body.query)
    # 경로 A에서는 RAG 스니펫을 document_text로도 활용
    doc_text = intent.get("document_text") or "\n".join(s["snippet"] for s in selected_snippets)
    agent_context = AgentContext(
        query=body.query,
        category=body.category,
        is_law_related=is_law_category(body.category) or intent.get("is_law_related", False),
        has_real_document=intent.get("has_real_document") or bool(body.filename_filter),
        document_text=doc_text if (intent.get("has_real_document") or body.filename_filter) else None,
        legal_qa_context=intent.get("legal_qa_context", body.query),
        doc_type=intent.get("doc_type"),
        extracted_clauses=intent.get("extracted_clauses", []),
    )

if agent_context:
    agent_results = await asyncio.gather(*[
        agent.invoke(agent_context, lexguard_config)
        for agent in REGISTERED_AGENTS
        if agent.should_invoke(agent_context, lexguard_config)
    ], return_exceptions=True)

    # Agent 결과를 system_prompt에 추가 (RAG budget 동적 조정)
    for agent_result in agent_results:
        if isinstance(agent_result, Exception):
            logger.warning("Agent 실패: %s", agent_result)
            continue
        if agent_result.used and agent_result.content:
            agents_used.append(agent_result.agent_name)
            # RAG budget 재조정
            actual_agent_chars = len(agent_result.content)
            rag_budget = max(2000, budget.get("max_total_chars", 9000) - actual_agent_chars)
            # system_prompt 섹션 추가
            system_prompt += f"\n\n{agent_result.content}\n\n=================="

# 반환값에 agents_used 추가
return {
    ...existing fields...,
    "lexguard_used": "lexguard" in agents_used,
    "agents_used": agents_used,
}
```

### 10.2 경로 B: `smart_augment` 신규 엔드포인트

```python
class SmartAugmentRequest(BaseModel):
    query: str

@router.post("/smart-augment", dependencies=[Depends(verify_token)])
async def smart_augment(body: SmartAugmentRequest):
    """
    [POST] /mcp-command/smart-augment

    /mcp 비활성 상태에서 법령/계약서 관련 질문을 자동 감지하여 LexGuard를 호출.
    법령 관련 없으면 즉시 null 반환 (fast path, FabriX 호출 지연 없음).

    Returns:
        { "system_prompt": str | None, "lexguard_used": bool, "agents_used": list[str] }
    """
    from .services.lexguard_service import LexGuardAgent, classify_query_intent

    intent = classify_query_intent(body.query)

    # Fast path: 법령 관련 없음
    if not intent["is_law_related"] and not intent["has_real_document"]:
        return {"system_prompt": None, "lexguard_used": False, "agents_used": []}

    lexguard_config = _get_lexguard_config()
    agent_context = AgentContext(
        query=body.query,
        is_law_related=intent["is_law_related"],
        has_real_document=intent["has_real_document"],
        document_text=intent["document_text"],
        legal_qa_context=intent["legal_qa_context"],
        doc_type=intent["doc_type"],
        extracted_clauses=intent["extracted_clauses"],
    )

    agents_used = []
    system_prompt_sections = []

    for agent in REGISTERED_AGENTS:
        if not agent.should_invoke(agent_context, lexguard_config):
            continue
        try:
            result = await agent.invoke(agent_context, lexguard_config)
            if result.used and result.content:
                agents_used.append(result.agent_name)
                system_prompt_sections.append(result.content)
        except Exception as e:
            logger.warning("smart_augment Agent 실패 (graceful degrade): %s", e)

    if not system_prompt_sections:
        return {"system_prompt": None, "lexguard_used": False, "agents_used": []}

    system_prompt = (
        "당신은 법령 및 계약서 검토 어시스턴트입니다.\n"
        "아래 법령 검색 결과를 참고하여 사용자의 질문에 답하세요.\n\n"
        + "\n\n==================\n\n".join(system_prompt_sections)
    )

    return {
        "system_prompt": system_prompt,
        "lexguard_used": "lexguard" in agents_used,
        "agents_used": agents_used,
    }
```

---

## 11. Frontend 변경

### 11.1 `fastapiApi.js` 추가

```javascript
// 경로 B: /mcp 비활성 시 자동 법령 감지
export const mcpSmartAugmentApi = {
  check: (query) => fastApiClient.post('/mcp-command/smart-augment', { query }),
};
```

### 11.2 `ChatPage.jsx` handleSend 수정

```javascript
// RAG 비활성 구간 (ragEnabled=false) 에 추가:
let systemPrompt = null;
let lexguardUsed = false;

if (!ragEnabled) {
  try {
    // Path B: 3초 timeout — cold start로 인한 지연으로 사용자 경험 저하 방지
    const augResult = await Promise.race([
      mcpSmartAugmentApi.check(text),
      new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), 3000))
    ]);
    if (augResult?.data?.system_prompt) {
      systemPrompt = augResult.data.system_prompt;
      lexguardUsed = augResult.data.lexguard_used;
    }
  } catch (e) {
    // timeout(3s 초과) 또는 실패 → graceful degrade (LexGuard 없이 FabriX 호출)
    if (e.message !== 'timeout') console.warn('smart-augment 실패 (무시됨):', e);
  }
}

// 배지 표시 (기존 RAG 배지 옆에 추가)
// {lexguardUsed && <span className="badge">⚖️ 법령</span>}
```

---

## 12. UX 품질 확보 전략

### 12.1 Path B 지연 문제 — 3초 Timeout (최우선)

**위험**: `smart_augment` 호출이 FabriX SSE 호출보다 **순차적으로 먼저** 실행됨.
LexGuard가 Render 무료 서버에서 cold start하면 10~30초 지연 → 사용자가 아무 응답도 없이 30초 대기.

**대응**: 프론트엔드에서 **3초 하드 timeout**:

```javascript
// ChatPage.jsx: 3초 timeout 패턴
const augResult = await Promise.race([
  mcpSmartAugmentApi.check(text),
  new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), 3000))
]).catch(() => null);  // timeout 또는 오류 모두 null로 graceful degrade
```

- 3초 내 응답 → LexGuard 결과 주입 (캐시 히트 응답은 보통 0.5~2초)
- 3초 초과 → LexGuard 없이 FabriX 바로 호출 (사용자는 3초 추가 대기만 경험)
- cold start 중이더라도 최악 3초 추가 지연으로 제한

Path A(경로 A, 명시적 `/mcp set 법령`)는 사용자가 RAG 검색을 선택했으므로 5초 timeout으로 관대하게 설정.

### 12.2 False Positive 방지 — 엄격한 키워드 정책

**위험**: "계약서 작성 일정 논의", "위반 사항 체크리스트 정리" 같은 일반 업무 대화에서 LexGuard 불필요 호출.

**대응**: `law_intent_keywords`는 **법령 고유 용어만** 포함.

| 포함 기준 | 제외 기준 |
|---|---|
| 법령 맥락에서만 쓰이는 용어 | 범용 업무 용어 |
| 판례, 시행령, 시행규칙, 위약금, 지체상금, 하도급법 | 계약서(단독), 위반(단독), 건설공사(단독) |
| 행정처분, 과태료, 소송, 가처분, 강제집행 | 계획, 일정, 예산, 검토(단독) |

목표: 일반 업무 대화의 **5% 미만**에서 트리거. 법령 진짜 질문의 **90% 이상** 감지.
운영 중 false positive 높으면 → keywords.json에서 해당 단어 제거 (코드 변경 없음).

### 12.3 사용자 투명성 — ⚖️ 배지

사용자가 예상치 못한 법령 내용이 응답에 포함됐을 때 "왜 이런 결과가?" 혼란 방지.

- **경로 A**: 기존 RAG 배지(`📄 파일명`) 옆에 `⚖️ 법령` 소형 배지 추가
- **경로 B**: 어시스턴트 버블 헤더 영역에 `⚖️ 법령 참고` 소형 배지

LexGuard가 graceful degrade(미호출 또는 실패)되면 배지 없음 → 사용자에게 별도 오류 메시지 불필요.

### 12.4 응답 품질 보증

**LexGuard 결과가 부실한 경우**: system_prompt에 "참고 자료" 형태로만 주입.
FabriX LLM이 최종 판단하므로 부실한 결과는 LLM이 자체적으로 보완하거나 낮은 비중으로 활용.

**건설공사 도메인 테스트 정책**:
- `document_issue_tool`의 공식 지원 타입은 `labor`, `lease`, `terms`만
- 건설공사 계약서는 `제N조` 패턴이 있으면 부분적으로 작동할 수 있으나 미검증
- **초기 배포 시**: 건설공사 도메인에서 `document_issue_tool` 비활성, `legal_qa_tool`만 호출
- **검증 후**: 실제 건설계약서로 테스트 통과 시 건설 도메인 활성화

### 12.5 Path B 활성화 기본값

`secrets.toml`에서 `enabled = true`로 기본 활성화, 단 키워드 목록을 엄격하게 유지.
전체 비활성화가 필요하면 `[lexguard] enabled = false`로 즉시 적용 (재배포 불필요).

향후 Phase 2: 사용자 프로파일 설정에서 개인별 "법령 자동 검색" 토글 UI 추가 가능.

---

## 13. `secrets.toml` 추가 설정

```toml
[lexguard]
enabled = true
base_url = "https://lexguard-mcp.onrender.com/mcp"
# 법령 카테고리 키워드는 ai_gateway/.agentConfig/lexguard_domain_keywords.json의
# law_category_keywords 키로 관리. secrets.toml에서는 enabled/base_url만 관리.
```

> **설계 변경 (v2)**: `law_categories` 목록이 `secrets.toml`에서 제거됨.
> 카테고리 키워드는 `lexguard_domain_keywords.json`의 `law_category_keywords`로 단일 관리.
> 매칭은 **키워드 포함(substring, 대소문자 무관)** 방식 — "건설법령"은 `"법령"` 키워드로 자동 커버.

---

## 13. 구현 Todo 목록

| # | ID | 제목 | 선행 의존성 |
|---|------|------|------------|
| 1 | `secrets-config` | `secrets.toml`에 `[lexguard]` 섹션 추가 | — |
| 2 | `keywords-json` | `ai_gateway/.agentConfig/lexguard_domain_keywords.json` 생성 | — |
| 3 | `agent-base` | `ai_gateway/services/agent_base.py` 생성 (추상 인터페이스) | — |
| 4 | `lexguard-service` | `ai_gateway/services/lexguard_service.py` 생성 | 1, 2, 3 |
| 5 | `rag-search-patch` | `doc_search.py` `rag_search` 엔드포인트 확장 (경로 A) | 4 |
| 6 | `smart-augment-ep` | `doc_search.py` `smart_augment` 엔드포인트 추가 (경로 B) | 4 |
| 7 | `frontend-api` | `fastapiApi.js` `mcpSmartAugmentApi` 추가 | 6 |
| 8 | `frontend-chat` | `ChatPage.jsx` handleSend 수정 + 배지 | 7 |
| 9 | `secrets-docs` | 문서 업데이트 | 1 |

---

## 14. 예외 처리 및 Graceful Degrade

| 상황 | 처리 방법 |
|------|-----------|
| LexGuard Render 서버 cold start (Path A) | `asyncio.timeout(5)` 설정, 실패 시 graceful degrade |
| LexGuard Render 서버 cold start (Path B) | 프론트엔드 3초 timeout → null로 처리 후 FabriX 바로 호출 |
| `document_issue_tool` 실패 | `legal_qa_tool`만으로 계속, 로그만 기록 |
| `legal_qa_tool` 실패 | `document_issue_tool`만으로 계속, 로그만 기록 |
| LexGuard 전체 실패 | 내부 RAG만으로 계속 (기존 동작과 동일) |
| RAG 결과 없음 | `document_issue_tool` 생략, `legal_qa_tool`만 실행 |
| 경로 B fast path | 법령 키워드 없으면 즉시 `null` 반환 (FabriX 지연 없음) |
| 경로 B false positive | law_intent_keywords에서 해당 단어 제거 (코드 변경 불필요) |

---

## 15. 향후 확장 가이드 (새 Agent 추가 방법)

### 15.1 두 가지 확장 시나리오

#### 시나리오 A: 기존 Agent(LexGuard)가 인식하는 카테고리명 추가

**조건**: 이미 LexGuard가 활성화된 상태에서 새로운 카테고리명을 인식시키고 싶을 때.

**작업**: `ai_gateway/.agentConfig/lexguard_domain_keywords.json`의 `law_category_keywords`에 키워드 추가만.  
코드 변경 없음. 서버 재시작 필요 (`@lru_cache` 때문).

```json
"law_category_keywords": ["법령", "법률", "law", "legal", "특수법령"]
```

> ⚠️ **주의**: "건설법령", "건설공사법령"처럼 기존 키워드의 substring으로 이미 커버되는 경우는 추가 불필요.  
> `"법령"` 키워드가 있으면 `"X법령"` 형태는 전부 자동 매칭된다.

---

#### 시나리오 B: 완전히 새로운 도메인 Agent 추가 (예: 특허 검색)

**필요한 작업 4가지** (코드 변경 포함):

**1. 키워드 사전** — `ai_gateway/.agentConfig/patent_keywords.json` 생성

```json
{
  "patent_category_keywords": ["특허", "IP", "patent", "지식재산"],

  "_comment": "아래부터는 classify_query_intent() 상당의 의도 감지 키워드",

  "intent_keywords": ["출원", "등록", "침해", "무효심판", "선행기술", "명세서"],

  "clause_patterns": []
}
```

**2. Agent 구현** — `ai_gateway/services/patent_service.py` 생성

```python
from functools import lru_cache
from pathlib import Path
import json
from .agent_base import AgentContext, AgentResult, ExternalAgent

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

@lru_cache(maxsize=1)
def _load_patent_keywords() -> dict:
    with open(DATA_DIR / "patent_keywords.json", encoding="utf-8") as f:
        return json.load(f)

def is_patent_category(category_name: str | None) -> bool:
    """카테고리명에 특허 키워드가 포함되면 True (대소문자 무관, substring 매칭)"""
    if not category_name:
        return False
    kw = _load_patent_keywords()
    lower_name = category_name.lower()
    return any(k.lower() in lower_name for k in kw.get("patent_category_keywords", []))

class PatentAgent(ExternalAgent):

    @property
    def name(self) -> str:
        return "patent"

    @property
    def priority(self) -> int:
        return 2  # LexGuard(1)보다 낮은 우선순위

    def should_invoke(self, context: AgentContext, config: dict) -> bool:
        if not config.get("enabled", False):
            return False
        # Path A: /mcp set으로 특허 카테고리 명시 설정
        if context.category and is_patent_category(context.category):
            return True
        # Path B: 쿼리에 특허 의도 키워드 포함
        kw = _load_patent_keywords()
        return any(k in context.query for k in kw.get("intent_keywords", []))

    async def invoke(self, context: AgentContext, config: dict) -> AgentResult:
        # 특허 MCP 서버 호출 구현
        ...
```

**3. 등록** — `ai_gateway/routers/doc_search.py`의 `REGISTERED_AGENTS`에 1줄 추가

```python
from ..services.patent_service import PatentAgent

REGISTERED_AGENTS: list[ExternalAgent] = [
    LexGuardAgent(),
    PatentAgent(),   # ← 이 1줄만 추가
]
```

**4. 설정** — `secrets.toml`에 섹션 추가

```toml
[patent_agent]
enabled = true
base_url = "https://patent-mcp.example.com/mcp"
```

**Frontend 변경**: `fastapiApi.js`와 `ChatPage.jsx` 변경 없음. 배지 표시를 원하면 `AgentResult.badge_label`만 설정하면 자동 표시됨.

---

### 15.2 설계 원칙 요약

```
각 Agent는 자신의 활성화 조건을 자체 소유한다 (should_invoke).
Router(doc_search.py)는 should_invoke()를 호출할 뿐, Agent별 로직을 모른다.
카테고리 키워드는 각 Agent의 JSON 사전에 있고 substring 매칭을 사용한다.
```

| 작업 범위 | 변경 대상 | 코드 변경 필요 |
|-----------|----------|----------------|
| 기존 Agent 카테고리 키워드 추가 | JSON 파일만 | ❌ 없음 |
| 완전히 새로운 Agent 추가 | JSON + service.py + REGISTERED_AGENTS + secrets.toml | ✅ 최소 (보일러플레이트) |

---

## 16. UX 시스템 메시지 출력 설계 (사용자 경험 + 개발자 디버깅)

### 16.1 목적

- **사용자**: 어떤 문서가 참조됐는지, LexGuard가 활성화됐는지 투명하게 인지
- **개발자**: RAG 검색 결과 및 Agent 활성화 상태 실시간 확인 (별도 로그 조회 없이)

### 16.2 경로 A (RAG 활성) 시스템 메시지

`rag_search` API 응답에 `searched_files: list[str]` 필드 추가.

프론트엔드: RAG 검색 완료 직후 시스템 메시지 버블로 출력:

```
🔍 검색 완료: 건설법령 카테고리 | 3개 문서 참조
    • 건설공사표준도급계약서.pdf
    • 하도급법 시행령.docx
    • 공사계약일반조건.pdf
⚖️ LexGuard 법령 검색 결과 포함됨      ← lexguard_used=true일 때만 추가
```

### 16.3 경로 B (smart-augment 활성) 시스템 메시지

`smart_augment` 응답에 `activated_tools: list[str]` 필드 추가.
(예: `["legal_qa_tool"]`, `["legal_qa_tool", "document_issue_tool"]`)

프론트엔드: LexGuard 활성화 시 시스템 메시지 버블로 출력:

```
⚖️ 법령 관련 질문 감지 — LexGuard 자동 검색 활성화
    검색 도구: legal_qa_tool
    (법령·판례 검색 결과가 답변에 포함되었습니다)
```

fast path(`system_prompt=null`)이면 시스템 메시지 없음 (사용자에게 비표시).

### 16.4 구현 패턴

```javascript
// ChatPage.jsx: 기존 system command log 패턴 재사용
// 경로 A: rag_search 완료 후
if (ragResult?.searched_files?.length > 0) {
  const fileList = ragResult.searched_files.map(f => `  • ${f}`).join('\n');
  const lexguardLine = ragResult.lexguard_used ? '\n⚖️ LexGuard 법령 검색 결과 포함됨' : '';
  addSystemMessage(`🔍 검색 완료: ${activeCategory} | ${ragResult.searched_files.length}개 문서 참조\n${fileList}${lexguardLine}`);
}

// 경로 B: smart-augment 활성 시
if (augResult?.data?.lexguard_used) {
  const tools = augResult.data.activated_tools?.join(', ') || 'legal_qa_tool';
  addSystemMessage(`⚖️ 법령 관련 질문 감지 — LexGuard 자동 검색 활성화\n    검색 도구: ${tools}`);
}
```

**구현 규칙** (기존 가이드와 동일):
- live session UI 상태로만 표시 (**DB 저장 금지**)
- 히스토리 재로드 시 복원 안 됨
- 시스템 메시지 버블 폭: **85%** (기존 적용 수치)
- `role: 'system'`으로 저장하여 LLM `contents` 구성에서 자동 제외

### 16.5 Backend API 응답 필드 추가

`rag_search` 응답에 추가:
```python
{
    ...,
    "searched_files": [s["filename"] for s in selected_snippets],  # 참조된 파일명 목록
    "lexguard_used": bool,
    "agents_used": list[str],
}
```

`smart_augment` 응답에 추가:
```python
{
    ...,
    "activated_tools": list[str],  # 실제 호출된 도구 목록
    "lexguard_used": bool,
}
```

---

## 17. 테스트 시나리오

### 17.1 경로 A 테스트 (RAG 활성)
1. `/mcp set 건설법령` → 건설공사 관련 문서 검색
2. "하도급 계약서 작성 시 지체상금 조항 법령 준수 여부" 입력
3. 기대: 내부 RAG 스니펫 + LexGuard 법령 검색 결과 함께 반환
4. **기대 시스템 메시지**: `🔍 검색 완료: 건설법령 | N개 문서 참조` + `⚖️ LexGuard 법령 검색 결과 포함됨`

### 17.2 경로 B 테스트 (RAG 비활성)
1. `/mcp` 없이 일반 대화 모드
2. "퇴직금 지급 기한이 법령상 며칠인지 알려줘" 입력
3. 기대: smart-augment가 `legal_qa_tool` 자동 호출, 법령 답변 주입
4. **기대 시스템 메시지**: `⚖️ 법령 관련 질문 감지 — LexGuard 자동 검색 활성화`

### 17.3 계약서 붙여넣기 테스트
1. 건설공사계약서 원문 (제1조~제10조 포함) 채팅창에 붙여넣기
2. 기대: `document_issue_tool` 호출, 조항별 법적 이슈 분석 반환

### 17.4 Fast Path 테스트 (시스템 메시지 없음)
1. "내일 회의 일정 알려줘" 등 비법령 질문
2. 기대: smart-augment 즉시 null 반환, LexGuard 미호출, **시스템 메시지 없음**

### 17.5 Graceful Degrade 테스트
1. `secrets.toml`에서 `base_url`을 잘못된 주소로 변경
2. 기대: LexGuard 실패 로그 + 내부 RAG 결과만으로 정상 응답, **배지/시스템 메시지 없음**
