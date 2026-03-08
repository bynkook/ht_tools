# AGENTS.md - ht_fools readme

This document provides essential context for AI coding agents working on the FabriX project.

## Quick Reference

| Command | Description |
|---------|-------------|
| `setup_project.bat` | Initial setup (venv + dependencies) |
| `run_project.bat` | Start all services (development mode) |
| `service_project.bat` | Start all services (production/network mode) |
| `reset_create_admin.bat` | Reset DB and create admin user |
| `migrate_db.bat` | Run migrations with backup (server-safe) |

## Build Commands

### Frontend (React + Vite)
```bash
cd frontend
npm install              # Install dependencies
npm run dev              # Development server (port 5173)
npm run build            # Production build
npm run lint             # ESLint check
npm run preview          # Preview production build
```

### Backend - Django (port 8000)
```bash
.venv\Scripts\activate
cd django_server
python manage.py makemigrations <app_name>   # Create migration
python manage.py migrate                     # Apply migrations
python manage.py runserver                   # Development server
python manage.py test                        # Run Django tests
```

### Backend - FastAPI (port 8001)
```bash
.venv\Scripts\activate
uvicorn ai_gateway.main:app --host 127.0.0.1 --port 8001 --reload
```

## Test Commands

```bash
# Python tests (pytest)
pytest test/test_contents_validation.py -v                    # Run specific test file
pytest test/test_contents_validation.py::TestContentsValidation::test_01_single_valid_element -v  # Single test
pytest test/ -v                                               # Run all tests

# Frontend tests (if configured)
cd frontend && npm run test
```

## Architecture

```
Browser
  |
  v
React (5173) ----+--> Django (8000)   : Auth, History, DB, Data Explorer API
                 +--> FastAPI (8001)  : AI proxy, SSE streaming, image processing
```

### Port Map
- `5173`: Vite frontend
- `8000`: Django + DRF (REST API)
- `8001`: FastAPI gateway (SSE streaming)

### Key Directories
- `django_server/apps/`: Django applications
  - `authentication/`: Login/signup/JWT
  - `fabrix_chat/`: Model-based chat sessions
  - `fabrix_agent_chat/`: Agent-based chat sessions
  - `data_explorer/`: Data exploration + DuckDB
  - `image_inspector/`: Image comparison logic
  - `user_settings/`: User preferences
  - `core/`: Shared utilities
- `frontend/src/`: React application
  - `api/djangoApi.js`: Django API client
  - `api/fastapiApi.js`: FastAPI API client
  - `features/`: Feature-based components
- `ai_gateway/`: FastAPI application
  - `routers/`: API endpoints
  - `services/`: Business logic (rate limiter, image processor)

## Code Style Guidelines

### dos batch file(.bat)

1. add 'chcp 65001 > nul' after '@echo off'
2. file encoding is 'utf-8' without BOM.
3. always use 'REM' to add non-code comments. never use '::'.

### Python (Django/FastAPI)

**Imports ordering:**
1. Standard library
2. Third-party (django, fastapi, rest_framework, etc.)
3. Local imports

```python
# Standard library
import logging
from pathlib import Path

# Third-party
from django.db import transaction
from rest_framework import viewsets, status, permissions
from fastapi import APIRouter, HTTPException

# Local
from .models import ChatSession
from .serializers import ChatSessionSerializer
```

**Naming conventions:**
- Classes: PascalCase (`ChatSessionViewSet`)
- Functions/methods: snake_case (`get_queryset`, `perform_create`)
- Variables: snake_case (`current_session_id`)
- Constants: UPPER_SNAKE_CASE (`MAX_HISTORY_TURNS`)
- Private helpers: prefix with underscore (`_get_file_metadata_helper`)

**Error handling:**
- Use DRF `Response` with appropriate status codes
- Log errors with `logging.getLogger(__name__)`
- Return JSON error objects with `error` key

```python
logger = logging.getLogger(__name__)

# Good
try:
    response.raise_for_status()
    return Response(data, status=status.HTTP_200_OK)
except httpx.HTTPStatusError as e:
    logger.error(f"HTTP error: {e.response.status_code}")
    return Response({'error': str(e)}, status=e.response.status_code)
```

**Django ORM:**
- Always use `select_related` / `prefetch_related` to avoid N+1 queries
- Use `transaction.atomic()` for multi-step operations

```python
# Good
queryset = ChatSession.objects.filter(user=request.user).prefetch_related('messages')

# Multi-step save
@transaction.atomic
def messages(self, request, pk=None):
    session = self.get_object()
    serializer.save(session=session)
    session.save()  # Update timestamp
```

**FastAPI specifics:**
- Use shared HTTP client: `request.app.state.http_client`
- NEVER create new `httpx.AsyncClient()` per request
- SSE responses: `StreamingResponse(generator, media_type="text/event-stream")`

### JavaScript/React (Frontend)

**Imports ordering:**
1. React and React ecosystem
2. Third-party libraries
3. Local components/APIs

```javascript
import React, { useState, useEffect, useCallback } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { fetchEventSource } from '@microsoft/fetch-event-source';
import { Bot, Sparkles } from 'lucide-react';

import ChatBubble from './components/ChatBubble';
import { modelChatApi } from '../../api/djangoApi';
```

**Naming conventions:**
- Components: PascalCase (`ChatPage`, `ChatBubble`)
- Functions: camelCase (`handleSend`, `updateLastMessage`)
- Constants: UPPER_SNAKE_CASE (`MAX_HISTORY_TURNS`)
- Refs: suffix with `Ref` (`messagesEndRef`, `abortControllerRef`)

**API Layer:**
- Django endpoints → `djangoApi.js`
- FastAPI endpoints → `fastapiApi.js`
- Never mix in same component for different purposes

```javascript
// Django API - for CRUD, auth, sessions
import { modelChatApi } from '../../api/djangoApi';
await modelChatApi.createSession(modelId, title);

// FastAPI API - for streaming, file processing
import { getFastApiUrl } from '../../api/axiosConfig';
await fetchEventSource(getFastApiUrl('/chat-messages'), { ... });
```

**SSE Handling:**
- Server returns snake_case fields: `event_status`, `finish_reason`
- Handle both cases defensively:
```javascript
const eventStatus = parsed.event_status ?? parsed.eventStatus;
const finishReason = parsed.finish_reason ?? parsed.finishReason;
```

**Error Display:**
- Use top red banner with `AlertCircle` icon
- Pattern:
```javascript
{error && (
  <div className="bg-red-50 text-red-600 px-4 py-3 flex items-center gap-2">
    <AlertCircle size={16} />
    {error}
  </div>
)}
```

## Non-Negotiable Rules

## Safety & Root Cause Principles

### 안전성 검토 원칙 (Safety Assessment)

코드 작성 전 Plan 수립 단계에서 작업의 안전성을 반드시 평가한다.

**High Risk로 분류하여 신중하게 접근해야 하는 작업:**
- 기능 추가/변경, 아키텍처 변경 등 대규모 코드 변경
- 엔드 유저의 사용자 경험 또는 품질을 저하시킬 오류 발생 가능성이 높은 작업
- 예측하기 어려운 버그 발생 가능성이 높은 복잡한 작업

**High Risk 작업 대응 방식:**
- 작업 전 위험 요소를 명시적으로 나열하고 사용자에게 알린다
- 변경 범위를 최소화(Minimal Diff)하여 영향 범위를 좁힌다
- 한 번에 큰 변경보다 단계적·점진적 변경을 우선한다
- 불확실한 경우 코드 작성 전에 사용자에게 확인을 요청한다

### Root Cause 탐색 원칙 (Root Cause Analysis)

오류 수정 시 증상 제거가 아닌 근본 원인을 먼저 탐색한다.

- 오류의 근본 원인(Root Cause)을 파악한 후 수정 방향을 결정한다
- Temporary fix(임시 우회, 예외 무시, 하드코딩 방어 등)는 가급적 사용하지 않는다
- Temporary fix가 불가피한 경우, 반드시 `# TODO: temporary fix - <이유>` 주석을 남긴다
- 동일 오류가 다른 경로에서도 재현될 수 있는지 확인하고 함께 수정한다

### Security
- **NEVER** commit API keys, tokens, or secrets
- Secrets go in root `secrets.toml` only (gitignored)
- SQL queries must be SELECT-only with validation

### API Layer Separation
- Django endpoints: `djangoClient` / `djangoApi.js`
- FastAPI endpoints: `fastApiClient` / `fastapiApi.js`
- Do NOT mix responsibilities

### Frontend API Runtime Rules
- Base URL is built dynamically from `window.location.protocol` + `window.location.hostname` (port only differs)
- Auth token storage is `sessionStorage` (`authToken`)
- Both `djangoClient` and `fastApiClient` inject `Authorization: Token <token>` via request interceptors

### Gateway Prefixes (Prefix + Role)
- `/health`: health check and liveness
- `/chat-messages`: model chat streaming gateway + model list/rate-limit status
- `/agent-messages`: agent chat streaming gateway + agent list/file upload/rate-limit status
- `/image-compare`: image compare processing + preview

### HTTP Client (FastAPI)
- ALWAYS use shared client: `request.app.state.http_client`
- NEVER create `httpx.AsyncClient()` per request

### Database
- SQLite in WAL mode
- N+1 prevention with `select_related`/`prefetch_related`

### UI Consistency
- Sidebar header format: `[Icon][Title][Home][Shrink]`
- Error display: top red banner with `AlertCircle`

## Conversation Context Format (Chat APIs)

The `contents` array format for FabriX APIs:
```
[user1, ai1, user2, ai2, ..., currentUserInput]
```
- Last element is ALWAYS current user input
- Default history limit: `MAX_HISTORY_TURNS = 5` (10 messages)
- Backend validates based on `contents[-1]`
- **Before API send, exclude `role: 'system'` messages** (including `/memory list` output) to prevent context pollution

## Rate Limiting (FastAPI)

- Implementation: `ai_gateway/services/rate_limiter_v2.py`
- Default limits: `100 RPM`, `1,000,000 TPM`
- Limiter scope: `global_shared` (shared FabriX account protection)
- Soft/Hard control:
  - Soft throttle starts around 80% load (`soft_throttle_delay`, server-led slowdown)
  - Hard limit returns HTTP 429
- 429 handling:
  - Prioritize `Retry-After` for retry timing
  - Response includes `Retry-After` and `X-RateLimit-*` metadata headers
- Operational status endpoints:
  - `GET /chat-messages/rate-limit-status`
  - `GET /agent-messages/rate-limit-status`
- Operating assumption (Windows): single-process / single-worker baseline

## Mock Mode

Controlled by `secrets.toml`:
```toml
[server]
mock_mode = true   # Returns mock SSE responses
mock_mode = false  # Real FabriX API calls
```

Note:
- Current implementation applies mock streaming behavior to chat streaming paths.
- Non-streaming APIs (for example image preview/process and dataset APIs) follow their normal backend flow.

## Data Explorer Specifics

- Visualization: Graphic Walker (native React)
- SQL transpile: Official `gw-dsl-parser` ONLY
- Computation: DuckDB server-side mode
- SQL: SELECT-only, forbidden patterns validated
- Errors: Sanitize in production (no stack traces)
- Projection model: keep full source in `raw_main_table`, recreate `main_table` as selected-columns projection
- Cache rebuild flow: cache status -> rebuild start -> rebuild status polling
- Frontend 429 behavior: `throttledUntilRef` blocks extra calls until `Retry-After` expires
- Frontend loading split: Data Explorer shell renders first; Graphic Walker chart engine is lazy-loaded when the first dataset/preset chart is actually needed
- Initial empty-state guidance is only for first entry; dataset/preset reloads must use a dedicated dataset-loading UI instead of reusing the empty-state message

### Current limitation (Data Explorer)
- This guide keeps endpoint depth at `prefix + role`; detailed request/response field specs are intentionally excluded.

## Image Inspector Specifics

- FastAPI handles heavy processing with endpoint roles under `/image-compare` (`/process`: compare, `/preview`: crop preview)
- Concurrency control uses `asyncio.Semaphore(5)` (separate from chat global rate limiter)
- One compare call returns `file1_base64`, `file2_base64`, `overlay_base64`; mode switching is frontend-only view logic
- Frontend cache key includes pages, diff settings, CAD settings, quality settings, and crop rect

### Current limitation (Image Inspector)
- Page-count mismatch warning UI is not currently implemented; page navigation is clamped per file page range.

## Reference Documents

For detailed implementation:
- `.github/copilot-instructions.md` - Canonical development guide
- `README.md` - General overview
- `GEMINI.md` - Extended documentation
- `doc.md/` - Feature-specific docs

Last updated: 2026-03-08 (Gateway/API 규칙 동기화, Data Explorer/Image Inspector current limitation 명시)
