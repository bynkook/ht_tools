# FabriX API Memory (Compact Summary)

이 문서는 `doc/chat_apis.html`, `doc/agent_apis.html`를 매번 열지 않아도 되도록 만든 **실무 요약본**입니다.
목적은 “현재 프로젝트에서 바로 쓰는 값”만 빠르게 확인하는 것입니다.

## 1) Source & Scope

- 원본 문서:
  - `doc/chat_apis.html`
  - `doc/agent_apis.html`
- 이 문서 범위:
  - Chat API / Agent API의 필수 엔드포인트
  - 인증 헤더
  - `contents` 규칙
  - SSE parsing 규칙
- 제외:
  - 긴 예제 payload
  - 날짜별 변경 이력
  - 프로젝트 내부 구현 상세(다른 문서로 관리)

---

## 2) 공통 규칙 (Chat / Agent)

### 2.1 인증 헤더

요청 시 아래 헤더를 사용합니다.

- `x-fabrix-client`
- `x-openapi-token` (`Bearer ...` 형식)
- `x-generative-ai-user-email` (필요 시)
- `Content-Type: application/json` (JSON 요청 시)

### 2.2 `contents` 규칙

- 포맷: `[user1, ai1, user2, ai2, ..., currentUserInput]`
- 마지막 요소는 항상 현재 사용자 입력
- 프로젝트 기본 history 윈도우: `MAX_HISTORY_TURNS = 10`
- 백엔드 검증 포인트: `contents[-1]` (첫 요소 기준 검증 금지)

### 2.3 스트리밍(SSE) 규칙

- 스트림 형식: `data: {...}\n\n`
- `event_status`가 `CHUNK`인 경우만 답변 누적
- `STATUS`는 진행 상태/메타 정보로 처리

### 2.4 snake_case vs camelCase

stream 응답에서는 snake_case가 사용됩니다.

- `event_status` ↔ `eventStatus`
- `finish_reason` ↔ `finishReason`
- `filter_block_reason` ↔ `filterBlockReason`

프론트에서는 두 케이스를 모두 방어적으로 처리합니다.

---

## 3) Chat API 요약

### 3.1 Official endpoint

- `GET /openapi/chat/v1/models`
- `POST /openapi/chat/v1/messages`

참고(문서에 존재):
- `GET /openapi/chat/v1/all-models`
- `POST /openapi/chat/v1/messages-with-models`

### 3.1.1 예제 (GET)

```bash
curl -X GET "${ENDPOINT_URL}/openapi/chat/v1/models" \
  -H "x-fabrix-client: ${FABRIX_CLIENT_KEY}" \
  -H "x-openapi-token: ${OPENAPI_TOKEN}" \
  -H "x-generative-ai-user-email: ${USER_EMAIL}"
```

### 3.1.2 예제 (POST)

```bash
curl -X POST "${ENDPOINT_URL}/openapi/chat/v1/messages" \
  -H "Content-Type: application/json" \
  -H "x-fabrix-client: ${FABRIX_CLIENT_KEY}" \
  -H "x-openapi-token: ${OPENAPI_TOKEN}" \
  -H "x-generative-ai-user-email: ${USER_EMAIL}" \
  -d '{
    "modelIds": ["YOUR_MODEL_ID"],
    "contents": ["안녕하세요"],
    "isStream": true
  }'
```

### 3.2 프로젝트 내부 라우팅

- Frontend route: `/chat`
- Django API base: `/api/chat/`
- FastAPI gateway: `/models`, `/chat-messages`

### 3.3 핵심 요청 필드

- `modelIds` (또는 프로젝트 wrapper에서 model 식별자 전달)
- `contents`
- `isStream` (`true` 권장)
- 선택: `llmConfig`, `systemPrompt`

### 3.4 핵심 응답 필드 (stream)

- `content`
- `event_status` (`CHUNK`, `STATUS`)
- `finish_reason`
- `filter_block_reason`
- `status`

---

## 4) Agent API 요약

### 4.1 Official endpoint

- `GET /openapi/agent-chat/v1/agents`
- `POST /openapi/agent-chat/v1/agent-messages`
- `POST /openapi/agent-chat/v1/agent-messages/file`

### 4.1.1 예제 (GET)

```bash
curl -X GET "${ENDPOINT_URL}/openapi/agent-chat/v1/agents" \
  -H "x-fabrix-client: ${FABRIX_CLIENT_KEY}" \
  -H "x-openapi-token: ${OPENAPI_TOKEN}" \
  -H "x-generative-ai-user-email: ${USER_EMAIL}"
```

### 4.1.2 예제 (POST)

```bash
curl -X POST "${ENDPOINT_URL}/openapi/agent-chat/v1/agent-messages" \
  -H "Content-Type: application/json" \
  -H "x-fabrix-client: ${FABRIX_CLIENT_KEY}" \
  -H "x-openapi-token: ${OPENAPI_TOKEN}" \
  -H "x-generative-ai-user-email: ${USER_EMAIL}" \
  -d '{
    "agentId": "YOUR_AGENT_ID",
    "contents": ["안녕하세요"],
    "isStream": true
  }'
```

### 4.1.3 예제 (POST, multipart/form-data, file)

```bash
curl -X POST "${ENDPOINT_URL}/openapi/agent-chat/v1/agent-messages/file" \
  -H "x-fabrix-client: ${FABRIX_CLIENT_KEY}" \
  -H "x-openapi-token: ${OPENAPI_TOKEN}" \
  -H "x-generative-ai-user-email: ${USER_EMAIL}" \
  -F "agentId=YOUR_AGENT_ID" \
  -F "contents=파일 내용을 요약해줘" \
  -F "isStream=true" \
  -F "file=@./sample.pdf;type=application/pdf"
```

### 4.2 프로젝트 내부 라우팅

- Frontend route: `/agent-chat`
- Django API base: `/api/agent-chat/`
- FastAPI gateway: `/agents`, `/agent-messages`

### 4.3 핵심 요청 필드

- `agentId`
- `contents`
- `isStream`
- 선택: `isRagOn`, `executeFinalAnswer`, `executeRagFinalAnswer`, `executeRagStandaloneQuery`
- 선택: `systemPromptVariables`, `llmConfig`

### 4.4 파일 첨부

- 파일 첨부 대화는 `/agent-messages/file` 사용
- multipart/form-data 형태로 `agentId`, `contents`, file 파트 조합

---

## 5) SSE 처리 실전 체크리스트

1. `data:` prefix 제거 후 JSON parse
2. `event_status ?? eventStatus`로 상태 판별
3. `CHUNK`일 때만 `content` 누적
4. `STATUS`는 누적하지 않음(로그/진행 표시)
5. `finish_reason ?? finishReason` 종료 처리
6. `filter_block_reason ?? filterBlockReason` 차단 사유 처리

---

## 6) Rate Limit / Error 기본 원칙

- 429 응답 시 `Retry-After`를 우선 반영
- 사용자 메시지는 “대기 후 재시도”로 안내
- 서버/클라이언트 모두 백오프(retry) 전략 유지

---

## 7) secrets.toml 매핑 (요약)

- Chat API 설정: `[fabrix_chat_api]`
- Agent API 설정: `[fabrix_agent_api]`
- 공통 서버 설정(예: mock): `[server]`

민감정보(API key/token)는 반드시 `secrets.toml`에만 저장하고 Git에 커밋하지 않습니다.

---

## 8) 운영 시 자주 하는 실수

- `contents` 마지막 요소가 빈 문자열인 요청
- `STATUS` 이벤트를 답변 본문에 붙여 버리는 처리
- snake_case 필드만 가정해 camelCase fallback 누락
- 429에서 `Retry-After` 무시

---

## 9) Quick links

- Chat API 원문: `doc/chat_apis.html`
- Agent API 원문: `doc/agent_apis.html`
- Canonical 개발 가이드: `.github/copilot-instructions.md`
- 프로젝트 실행/운영 요약: `README.md`

Last updated: 2026-02-18
