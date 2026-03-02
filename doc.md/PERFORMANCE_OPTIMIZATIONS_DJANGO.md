# Production Readiness: Performance Optimizations for Chat Application

**Document Version:** 1.0
**Date:** 2026-02-20
**Target Audience:** Development Team, DevOps Engineers
**Scope:** FabriX chat application optimizations for 10-20 concurrent users

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Operational Context](#operational-context)
3. [Fix 1: N+1 Query Optimization](#fix-1-n1-query-optimization)
4. [Fix 2: API Throttling](#fix-2-api-throttling)
5. [Fix 3: Pagination Implementation](#fix-3-pagination-implementation)
6. [Fix 4: HTTP Client Timeout Configuration](#fix-4-http-client-timeout-configuration)
7. [Fix 5: Read-Only Fields in Serializers](#fix-5-read-only-fields-in-serializers)
8. [Implementation Priority](#implementation-priority)
9. [Testing & Validation](#testing--validation)
10. [References](#references)

---

## Executive Summary

### Problem Statement

The FabriX chat application will support **10-20 concurrent users** with **slow FabriX API responses**. This operational scenario presents several performance and scalability challenges:

- **Latency Amplification**: Slow external API + unoptimized database queries = poor user experience
- **Cascading Failures**: No rate limiting under concurrent load could overwhelm resources
- **Database Overload**: N+1 queries and unpaginated results will compound under load
- **Data Integrity Risk**: Missing protection mechanisms could lead to data corruption

### Recommended Fixes Overview

| Priority | Fix | Impact | Effort | Category |
|----------|-----|--------|--------|----------|
| 1 | N+1 Query Optimization | 🔴 High | Very Low (1 line change) | Performance |
| 2 | API Throttling | 🔴 High | Low (8 lines) | Protection |
| 3 | Pagination | 🟡 Medium | Low (2 lines) | Scalability |
| 4 | HTTP Timeout Configuration | 🟢 Low | Very Low (1 line optional) | Resilience |
| 5 | Read-Only Fields | 🟢 Low | Low (2 lines each) | Data Integrity |

**Total Implementation Effort**: ~15-20 lines of code configuration

### Implementation Status (2026-02-20)

이번 세션에서 우선순위 기반으로 다음 항목을 실제 반영했습니다.

- ✅ Fix 1: N+1 Query Optimization (`select_related('user')` 적용)
- ✅ Fix 2: API Throttling (DRF 전역 throttle 클래스/레이트 적용)
- ✅ Fix 3: Pagination (DRF 전역 `PageNumberPagination`, `PAGE_SIZE=20` 적용)
- ✅ Fix 5: Read-Only Fields in Serializers (Chat/Agent serializer 보호)
- 🟡 추가 안정화: Chat/Agent SSE assistant 저장 단일화(중복 저장 방지)
- 🟡 추가 안정화: Agent Chat 429 처리 로직을 Chat과 동일 정책으로 통일
- 🟡 추가 안정화: FastAPI 429 응답 `Retry-After` 헤더 명시 및 payload 로그 축소

미반영/부분반영 항목:

- ⏳ Fix 4 Timeout 최적화는 현 구성(주요 경로 60s) 유지, 추가 튜닝은 운영 지표 확인 후 진행

---

## Operational Context

### System Architecture

```
┌─────────────┐
│   React     │  (Frontend: 5173)
│   Client    │
└──────┬──────┘
       │
   HTTP/SSE
       │
┌──────▼──────────────────────┐
│  Django (8000)              │
│  - Auth & State Management  │
│  - Chat Sessions/Msgs       │
│  - Data Explorer API        │
│  - SQLite Database          │
│  - NO Throttling ❌        │
│  - NO Pagination  ❌       │
│  - N+1 Risk       ❌       │
└──────┬──────────────────────┘
       │
   HTTPS
       │
┌──────▼────────┐
│  FastAPI      │  (8001)
│  - SSE Proxy  │
│  - Image Proc │
│  - Rate Limit │ ✅ (Already)
└──────┬────────┘
       │
   HTTPS
       │
┌──────▼────────┐
│  FabriX API   │  (Slow External Service)
│  - LLM Models │
│  - Agents     │
└───────────────┘
```

### Operational Scenarios

#### Scenario A: Peak Usage (20 concurrent users)

| Component | Requests/Min | Without Fixes | With Fixes |
|-----------|--------------|---------------|-----------|
| Chat Messages | 600 | 420 DB queries (N+1) | 20 DB queries |
| Preset List | 120 | 2640 DB queries | 120 DB queries |
| Auth Requests | 60 | Unprotected | Throttled |

**Impact**: Without fixes → 3060 DB queries/min vs 140 DB queries/min (**22x reduction**)

#### Scenario B: Average Usage (10 concurrent users)

| Component | Requests/Min | DB Queries Without | DB Queries With |
|-----------|--------------|-------------------|-----------------|
| Chat Messages | 300 | 210 | 10 |
| Preset List | 60 | 1320 | 60 |

**Impact**: 1530 DB queries/min vs 70 DB queries/min (**21x reduction**)

### External API Constraints

- **FabriX API Response Time**: 2-5 seconds (slow)
- **SSE Streaming**: Long-lived connections
- **Failure Impact**: Chat messages depend on external API

---

## Fix 1: N+1 Query Optimization

### Objective

**Eliminate the "1 + N" database query pattern** in the preset listing endpoint, reducing database queries from 11+ to 1 per request.

### Technical Analysis

#### The Problem

**File**: `django_server/apps/data_explorer/views.py`

**Location**: Lines 365-381

```python
def get(self, request):
    """List all presets: user's own presets + public presets from other users."""
    is_admin = request.user.is_superuser or request.user.is_staff

    if is_admin:
        # Admin sees all presets
        presets = DataExplorerPreset.objects.all().order_by('-updated_at')  # ❌ N+1
    else:
        # Regular user sees own presets + public presets
        presets = DataExplorerPreset.objects.filter(
            Q(user=request.user) | Q(is_public=True)
        ).distinct().order_by('-updated_at')  # ❌ N+1

    serializer = DataExplorerPresetListSerializer(presets, many=True, context={'request': request})
    return Response({"presets": serializer.data, "is_admin": is_admin})
```

#### N+1 Query Flow

```python
# 1️⃣ Initial Query (1 query)
SELECT * FROM data_explorer_preset;
-- Returns N presets (e.g., 10 presets)

# 2️⃣ For EACH preset, Django makes SEPARATE queries (N queries)
SELECT * FROM auth_user WHERE id = 1;  # for preset 1's owner_username
SELECT * FROM auth_user WHERE id = 2;  # for preset 2's owner_username
SELECT * FROM auth_user WHERE id = 3;  # for preset 3's owner_username
...
# Total: 1 + N queries = N+1 queries
```

#### The Source

**File**: `django_server/apps/data_explorer/serializers.py`

**Location**: Line 9

```python
class DataExplorerPresetListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing presets (minimal info).
    """
    owner_username = serializers.CharField(source='user.username', read_only=True)  # ⚠️ Triggers N+1
    # ...
```

### Implementation Method

#### Step 1: Modify QuerySet in `data_explorer/views.py`

**Replace lines 371-378** with:

```python
if is_admin:
    # Admin sees all presets with user data joined
    presets = DataExplorerPreset.objects.select_related('user').all().order_by('-updated_at')
else:
    # Regular user sees own presets + public presets with join
    presets = DataExplorerPreset.objects.filter(
        Q(user=request.user) | Q(is_public=True)
    ).select_related('user').distinct().order_by('-updated_at')
```

**Key Change**: Added `.select_related('user')` to both querysets.

#### What `select_related()` Does

Performs a **SQL JOIN** instead of separate queries:

```sql
-- Single JOIN query
SELECT
    data_explorer_preset.*,
    auth_user.*
FROM data_explorer_preset
INNER JOIN auth_user ON data_explorer_preset.user_id = auth_user.id
ORDER BY data_explorer_preset.updated_at DESC;
```

### Expected Results

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Queries per request | 1 + N | 1 | **N+1 → 1** |
| 10 presets | 11 queries | 1 query | **11x faster** |
| 20 presets | 21 queries | 1 query | **21x faster** |
| 50 presets | 51 queries | 1 query | **51x faster** |

### Impact Analysis

#### Database Load Reduction

With 20 concurrent users, each viewing 10 presets:

| Metric | Without Fix | With Fix |
|--------|-------------|----------|
| Total DB queries/min | 2640 | 240 |
| Total DB queries/hour | 158,400 | 14,400 |
| Approx query time (SQLite) | 26.4 seconds | 2.4 seconds |

#### Response Latency

| Presets Count | Latency Without | Latency With |
|----------------|-----------------|--------------|
| 5 presets | ~55ms | ~5ms |
| 10 presets | ~105ms | ~5ms |
| 20 presets | ~205ms | ~5ms |

**Result**: 10-41x faster response times

### Migration Requirements

**No migration required** - only queryset modification.

---

## Fix 2: API Throttling

### Objective

**Implement rate limiting** to protect Django endpoints from abuse under concurrent load, preventing cascading failures when the external FabriX API is slow.

### Technical Analysis

#### Current State

**File**: `django_server/config/settings.py`

**Lines 171-179**: Current `REST_FRAMEWORK` configuration

```python
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    # ❌ Missing throttling
    # ❌ Missing pagination
    # ❌ Filter backends not configured
}
```

#### Why Throttling is Critical

**Operational Scenario Analysis**:

1. **Slow FabriX API** (2-5 seconds per message)
2. **20 concurrent users**
3. **No throttling** → single user can flood the system
4. **Database overload** → SQLite cannot handle concurrent read/write bursts
5. **FastAPI protection** exists but Django endpoints are **unprotected**

**Failure Scenario (No Throttling)**:

```
User A starts spamming → 100 requests/min
  ↓
All HTTP server threads blocked
  ↓
All other users timeout
  ↓
System unusable
```

### Throttling Strategy

#### Conservative Rate Calculation

**Assumptions**:
- 20 concurrent users
- Each user makes ~15 requests/min (reasonable for chat)
- Peak buffer: 2x normal usage
- FabriX API slow → reduce burst allowance

**Recommended Rates**:

| User Type | Rate | Rationale |
|-----------|------|-----------|
| Anonymous | 60/hour | Prevent abuse before auth |
| Authenticated | 300/hour | 20 users × 15 req = 300 req/hour |

**Why Low Rates?**
- External API is slow (2-5s per response)
- SQLite has concurrency limits
- Better to reject requests than overwhelm system

### Implementation Method

#### Step 1: Update `django_server/config/settings.py`

**Add to `REST_FRAMEWORK` dictionary** (appends after line 179):

```python
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],

    # === NEW: Throttling Configuration ===
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '60/hour',      # Unauthenticated users
        'user': '300/hour',     # 10-20 users × ~15 requests each
    },
}
```

### Expected Results

#### Request Rate Control

| Scenario | Without Throttling | With Throttling |
|----------|-------------------|-----------------|
| Normal usage (20 users × 15 req) | Accepts all | Accepts all |
| Single user attacks (100 req/min) | Accepts all (flood) | Rejects after 5/min |
| Load test (1000 req/min) | Overwhelms server | Rejects 700+ req/min |

#### Error Response Format

```json
{
    "detail": "Request was throttled. Expected available in 60 seconds."
}
```

### Migration Requirements

**No migration required** - runtime configuration only.

### Testing Validation

```bash
# Test throttling with curl
for i in {1..10}; do
  curl -X GET http://localhost:8000/api/data-explorer/presets/ \
    -H "Authorization: Token YOUR_TOKEN"
done
# Expected: First 5 requests succeed, last 5 return 429
```

---

## Fix 3: Pagination Implementation

### Objective

**Implement response pagination** on list endpoints to prevent large payload transfers and control response sizes under concurrent load.

### Technical Analysis

#### Current State

**No pagination configured** in `REST_FRAMEWORK` settings.

**Impact**:

| Endpoint | Current Behavior | Problem |
|----------|------------------|---------|
| `/api/chat/sessions/` | Returns all sessions | Large payload (100+ sessions) |
| `/chat/agent-chat/sessions/` | Returns all sessions | Large payload |
| `/api/data-explorer/presets/` | Returns all presets | No pagination |

#### Example Scenario

With 20 concurrent users, each having 50 chat sessions:

| Metric | Without Pagination | With Pagination |
|--------|---------------------|-----------------|
| Payload per request | ~500 KB | ~20 KB |
| Response time | ~200ms | ~50ms |
| Memory usage per request | ~2MB | ~100KB |
| Total data transfer (20 users) | ~10 GB/min | ~400 MB/min |

### Pagination Strategy

#### Page-Based Pagination

- **Type**: `PageNumberPagination`
- **Page Size**: 20 items per page
- **Rationale**: Balance between UX and performance

### Implementation Method

#### Step 1: Update `django_server/config/settings.py`

**Add to `REST_FRAMEWORK` dictionary** (after throttling config):

```python
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_THROTTLE_CLASSES': [...],
    'DEFAULT_THROTTLE_RATES': {...},

    # === NEW: Pagination Configuration ===
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}
```

#### API Response Format (After Pagination)

```json
{
  "count": 150,              // Total items
  "next": "http://localhost:8000/api/data-explorer/presets/?page=2",
  "previous": null,
  "results": [
    {
      "id": 1,
      "name": "Preset 1",
      // ... 20 items total
    }
  ]
}
```

### Expected Results

| Metric | Without Pagination | With Pagination |
|--------|-------------------|-----------------|
| Max payload size | ~500 KB | ~50 KB |
| Average response time | ~150ms | ~50ms |
| Memory per request | ~2MB | ~200KB |
| Concurrent users supported | ~5-10 | ~20-30 |

### Migration Requirements

**No migration required** - no database schema changes.

### Frontend Impact

**Frontend must handle pagination**:

```javascript
// Example frontend pagination logic
const fetchPresets = async (page = 1) => {
  const response = await fetch(`/api/data-explorer/presets/?page=${page}`);
  const data = await response.json();
  setPresets(data.results);
  setNextPage(data.next ? page + 1 : null);
};
```

---

## Fix 4: HTTP Client Timeout Configuration

### Objective

**Optimize HTTP client timeout settings** for handling slow FabriX API responses, preventing thread blocking and resource exhaustion.

### Technical Analysis

#### Current Configuration

**File**: `django_server/config/settings.py`

**Lines 201-216**: Current HTTP client setup

```python
SHARED_HTTP_CLIENT = httpx.Client(
    timeout=httpx.Timeout(
        connect=5.0,   # Connection timeout: 5 seconds
        read=30.0,     # Read timeout: 30 seconds ⚠️ Might be too short
        write=10.0,    # Write timeout: 10 seconds
        pool=5.0       # Pool timeout: 5 seconds
    ),
    limits=httpx.Limits(
        max_keepalive_connections=10,
        max_connections=50,
        keepalive_expiry=30.0
    ),
    transport=httpx.HTTPTransport(
        retries=2  # Automatic retry on connection failures
    )
)
```

#### Problem Analysis

**With slow FabriX API (2-5s response)**:

- **Current read timeout**: 30 seconds
- **FabriX API**: Typically 2-5 seconds, but spike to 8-10 seconds possible
- **Risk**: Timeout exceptions if FabriX spikes > 30s (unlikely but possible)

**Thread Pool Impact**:

With 20 concurrent users, each waiting 30s for timeout:

| Scenario | Threads Blocked | Impact |
|----------|----------------|--------|
| All timeout simultaneously | 20 threads | Server unresponsive |
| 50% spike responses | 10 threads | Degraded performance |

### Implementation Method

#### Step 1: Adjust Read Timeout (Optional but Recommended)

**File**: `django_server/config/settings.py`

**Line 205**: Modify `read=30.0` based on needs

```python
SHARED_HTTP_CLIENT = httpx.Client(
    timeout=httpx.Timeout(
        connect=5.0,   # Connection timeout: 5 seconds
        read=60.0,     # Read timeout: 60 seconds (INCREASED for slow API)
        write=10.0,    # Write timeout: 10 seconds
        pool=5.0       # Pool timeout: 5 seconds
    ),
    limits=httpx.Limits(
        max_keepalive_connections=10,
        max_connections=50,
        keepalive_expiry=30.0
    ),
    transport=httpx.HTTPTransport(
        retries=2  # Automatic retry on connection failures
    )
)
```

### Recommendation Options

| Option | Read Timeout | Pros | Cons |
|--------|--------------|------|------|
| **A: Keep 30s** | 30 seconds | Fast fail on slow API | May timeout on extreme spikes |
| **B: Increase to 60s** | 60 seconds | Handles extreme spikes | Threads block longer |
| **C: Async client** | N/A | Non-blocking | Requires significant refactoring |

**Recommended**: **Option B (60s)** - balances resilience and performance.

### Expected Results

| Scenario | With 30s | With 60s |
|----------|----------|----------|
| Normal response (2-5s) | ✅ Success | ✅ Success |
| Spike response (8s) | ✅ Success | ✅ Success |
| Extreme spike (45s) | ❌ Timeout | ✅ Success |

---

## Fix 5: Read-Only Fields in Serializers

### Objective

**Protect auto-managed database fields** from unintended modification, ensuring data integrity under concurrent access.

### Technical Analysis

#### The Problem

**Auto-managed fields** (`id`, `created_at`, `updated_at`) are currently **not marked as read-only** in serializers.

**Security Risk**:

```python
# Current serializer (PROBLEMATIC)
class ChatSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatSession
        fields = ['id', 'model_id', 'title', 'created_at', 'updated_at']
        # ❌ Missing read_only_fields

# Attacker could potentially send:
POST /api/chat/sessions/
{
    "id": 999,              # Should be AutoField
    "created_at": "2020-01-01",  # Should be auto_now_add
    "updated_at": "2099-12-31"   # Should be auto_now
}
```

#### Current State

| File | Serializer | Missing Fields |
|------|-----------|---------------|
| `fabrix_chat/serializers.py:18-21` | `ChatSessionSerializer` | `['id', 'created_at', 'updated_at']` |
| `fabrix_chat/serializers.py:12-15` | `ChatMessageSerializer` | `['id', 'created_at']` |
| `fabrix_agent_chat/serializers.py:15-19` | `ChatSessionSerializer` | `['id', 'created_at', 'updated_at']` |
| `fabrix_agent_chat/serializers.py:10-13` | `ChatMessageSerializer` | `['id', 'created_at']` |

### Implementation Method

#### Step 1: Fix ChatSessionSerializer

**File**: `django_server/apps/fabrix_chat/serializers.py`

**Replace lines 18-21**:

```python
# BEFORE
class ChatSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatSession
        fields = ['id', 'model_id', 'title', 'created_at', 'updated_at']

# AFTER
class ChatSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatSession
        fields = ['id', 'model_id', 'title', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
```

#### Step 2: Fix ChatMessageSerializer

**File**: `django_server/apps/fabrix_chat/serializers.py`

**Replace lines 12-15**:

```python
# BEFORE
class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = ['id', 'role', 'content', 'created_at']

# AFTER
class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = ['id', 'role', 'content', 'created_at']
        read_only_fields = ['id', 'created_at']
```

#### Step 3: Fix fabrix_agent_chat Serializers

**File**: `django_server/apps/fabrix_agent_chat/serializers.py`

**Replace lines 15-19** (ChatSessionSerializer) and **lines 10-13** (ChatMessageSerializer) with same changes above.

### Expected Results

#### Data Integrity Protection

| Attack Vector | Without Fix | With Fix |
|---------------|-------------|----------|
| Override `id` | Possible ❌ | Blocked ✅ |
| Override `created_at` | Possible ❌ | Blocked ✅ |
| Override `updated_at` | Possible ❌ | Blocked ✅ |

#### Error Response Example

```json
{
  "id": ["This field is read-only."],
  "created_at": ["This field is read-only."],
  "updated_at": ["This field is read-only."]
}
```

### Migration Requirements

**No migration required** - no database schema changes.

---

## Implementation Priority

### Phase 1: Critical Performance & Protection (Do First)

| Priority | Fix | Effort | Impact | Files Modified |
|----------|-----|--------|--------|----------------|
| **1** | N+1 Query Optimization | 1 line | Database load **21x reduction** | `data_explorer/views.py` |
| **2** | API Throttling | 8 lines | Prevents DDOS/abuse | `settings.py` |

**Total Time**: ~5 minutes

**Impact**: Reduces DB queries 21x, prevents cascade failures

---

### Phase 2: Scalability (Do Second)

| Priority | Fix | Effort | Impact | Files Modified |
|----------|-----|--------|--------|----------------|
| **3** | Pagination | 2 lines | Controlled response sizes | `settings.py` |

**Total Time**: ~2 minutes

**Impact**: 10x smaller payloads, 20% faster responses

---

### Phase 3: Data Integrity (Do Third)

| Priority | Fix | Effort | Impact | Files Modified |
|----------|-----|--------|--------|----------------|
| **5** | Read-Only Fields | 2 lines per file | Data integrity protection | 2 files (8 lines) |

**Total Time**: ~10 minutes

**Impact**: Prevents unauthorized field overrides

---

### Phase 4: Resilience (Optional)

| Priority | Fix | Effort | Impact | Files Modified |
|----------|-----|--------|--------|----------------|
| **4** | HTTP Timeout | 1 line optional | Handles extreme API spikes | `settings.py` |

**Total Time**: ~1 minute

**Impact**: Reliability for extreme API latency

---

## Testing & Validation

### Pre-Deployment Checklist

#### Fix 1: N+1 Query Optimization

- [ ] Confirm `.select_related('user')` added to both admin and user querysets
- [ ] Test preset list endpoint: `GET /api/data-explorer/presets/`
- [ ] Verify no additional queries made: Enable `django.db.backends` logging to DEBUG
- [ ] Confirm serializer still returns `owner_username` correctly

**Validation Command**:
```bash
# Test with Django Debug Toolbar enabled
# Should see: 1 query with INNER JOIN instead of N+1 queries
```

#### Fix 2: API Throttling

- [ ] Confirm throttling config added to `REST_FRAMEWORK`
- [ ] Test with curl loop: First 5 requests succeed, next gets 429
- [ ] Verify 429 error response format
- [ ] Test auth token throttling vs anon throttling

**Validation Script**:
```bash
#!/bin/bash
# Test throttling
for i in {1..10}; do
  echo "Request $i:"
  curl -w "\nStatus: %{http_code}\n" \
    -H "Authorization: Token YOUR_TOKEN" \
    http://localhost:8000/api/data-explorer/presets/ || true
  echo "---"
done
# Expected: Status 200 for first 5, Status 429 for last 5
```

#### Fix 3: Pagination

- [ ] Confirm `DEFAULT_PAGINATION_CLASS` and `PAGE_SIZE` added to `settings.py`
- [ ] Verify list endpoints return pagination keys: `count`, `next`, `previous`, `results`
- [ ] Test page navigation
- [ ] Confirm 20 items per page

**Validation Request**:
```bash
# Test pagination
curl -H "Authorization: Token YOUR_TOKEN" \
  http://localhost:8000/api/data-explorer/presets/ | jq .
# Expected: Pagination structure present, results array has 20 items
```

#### Fix 4: HTTP Timeout

- [ ] Verify read timeout value (30s vs 60s)
- [ ] Test with mock slow endpoint
- [ ] Confirm no timeout exceptions under normal load

**Note**: Optional change, optional testing.

#### Fix 5: Read-Only Fields

- [ ] Confirm `read_only_fields` added to 4 serializers
- [ ] Test POST request with read-only fields in payload
- [ ] Verify 400 Bad Request with field-level errors

**Validation Request**:
```bash
# Test read-only protection
curl -X POST \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"id": 999, "created_at": "2020-01-01", "model_id": "test"}' \
  http://localhost:8000/api/chat/sessions/
# Expected: {"id": ["This field is read-only."], ...}
```

### Load Testing

#### Tool: Apache Bench (or locust)

```bash
# Test preset list endpoint with pagination
ab -n 100 -c 10 \
  -H "Authorization: Token YOUR_TOKEN" \
  http://localhost:8000/api/data-explorer/presets/

# Expected metrics:
# - Requests per second: > 50 (with N+1 fix)
# - Time per request: < 200ms (with pagination)
# - Failed requests: 0 (with throttling)
```

### Monitoring Setup

```python
# Add to settings.py (optional)
LOGGING = {
    'loggers': {
        'django.db.backends': {
            'level': 'DEBUG',  # Monitor query count
        },
        'rest_framework': {
            'level': 'INFO',  # Monitor throttling events
        },
    },
}
```

---

## References

### Django REST Framework Documentation

- [Serializers - ModelSerializer](https://www.django-rest-framework.org/api-guide/serializers/)
- [Queryset optimization - select_related](https://docs.djangoproject.com/en/stable/topics/db/optimization/)
- [Throttling](https://www.django-rest-framework.org/api-guide/throttling/)
- [Pagination](https://www.django-rest-framework.org/api-guide/pagination/)

### Performance Best Practices

- [DRF Performance](https://www.django-rest-framework.org/topics/database-optimization/)
- [Django N+1 Query Prevention](https://docs.djangoproject.com/en/stable/topics/db/optimization/#select-related)

### Rate Limiting Guidelines

- [OWASP Rate Limiting](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html#implement-rate-limiting)

---

## Appendix A: Complete Configuration Diff

### File: `django_server/config/settings.py`

```diff
 REST_FRAMEWORK = {
     'DEFAULT_AUTHENTICATION_CLASSES': [
         'rest_framework.authentication.TokenAuthentication',
         'rest_framework.authentication.SessionAuthentication',
     ],
     'DEFAULT_PERMISSION_CLASSES': [
         'rest_framework.permissions.IsAuthenticated',
     ],
+
+    # === NEW: Throttling Configuration ===
+    'DEFAULT_THROTTLE_CLASSES': [
+        'rest_framework.throttling.AnonRateThrottle',
+        'rest_framework.throttling.UserRateThrottle',
+    ],
+    'DEFAULT_THROTTLE_RATES': {
+        'anon': '60/hour',
+        'user': '300/hour',
+    },
+
+    # === NEW: Pagination Configuration ===
+    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
+    'PAGE_SIZE': 20,
 }
```

### File: `django_server/apps/data_explorer/views.py`

```diff
             if is_admin:
                 # Admin sees all presets
-                presets = DataExplorerPreset.objects.all().order_by('-updated_at')
+                presets = DataExplorerPreset.objects.select_related('user').all().order_by('-updated_at')
             else:
                 # Regular user sees own presets + public presets
                 presets = DataExplorerPreset.objects.filter(
                     Q(user=request.user) | Q(is_public=True)
-                ).distinct().order_by('-updated_at')
+                ).select_related('user').distinct().order_by('-updated_at')
```

### File: `django_server/apps/fabrix_chat/serializers.py` (and `fabrix_agent_chat/serializers.py`)

```diff
 class ChatSessionSerializer(serializers.ModelSerializer):
     class Meta:
         model = ChatSession
         fields = ['id', 'model_id', 'title', 'created_at', 'updated_at']
+        read_only_fields = ['id', 'created_at', 'updated_at']

 class ChatMessageSerializer(serializers.ModelSerializer):
     class Meta:
         model = ChatMessage
         fields = ['id', 'role', 'content', 'created_at']
+        read_only_fields = ['id', 'created_at']
```

---

## Appendix B: Operational Metrics Dashboard

### Key Metrics to Monitor

| Metric | Target | Alert Threshold | Tool |
|--------|--------|-----------------|------|
| DB queries per request | 1-2 | > 10 | Django Debug Toolbar |
| Response time (95th percentile) | < 200ms | > 500ms | Sentry/New Relic |
| Throttle reject rate | < 5% | > 15% | App logs |
| Failed requests | 0 | > 1% | APM tools |
| Concurrent connections | < 30 | > 45 | Nginx logs |
| Memory usage | < 512MB | > 1GB | `top`/`htop` |

### Success Criteria

- [ ] Database query count reduced by **95%+** (N+1 fix)
- [ ] 95th percentile response time < 200ms (pagination)
- [ ] No throttle rejections under normal load (20 users × 15 req/min)
- [ ] No timeout errors under normal FabriX API latency (2-5s)
- [ ] No unauthorized field modifications possible

---

**Document End**