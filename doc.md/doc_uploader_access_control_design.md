# Doc Uploader 카테고리 접근 권한 설계 — 검토 보류 문서

> 최종 검토일: 2026-04-02  
> 상태: **구현 보류 — 그룹 멤버십 등록 방법 최종 확정 후 진행**

---

## 배경 및 목적

현재 Doc Uploader 앱의 카테고리는 모든 인증된 사용자가 동등하게 접근 가능하다.  
이를 아래 3가지 접근 수준으로 구분하고자 함:
- **Private**: 나만 볼 수 있는 폴더
- **Group**: 특정 그룹 멤버만 접근 가능한 폴더 (전체 공개 아님)
- **Public**: 모든 인증 사용자 접근 가능

FabriX Chat의 MCP/RAG 검색도 이 권한에 연동되어, 사용자는 접근 가능한 카테고리 문서만 검색할 수 있어야 한다.

---

## 현재 시스템 구조 (탐색 결과)

### 인증
- DRF Token 방식 (`authtoken_token` 테이블)
- FastAPI는 SQLite 직접 접근으로 토큰 유효성 확인 (Django API 호출 없음)
- **현재 FastAPI는 user_id/groups를 추출하지 않음** — 개선 필요

### Django Groups
- `django.contrib.auth.models.Group` 설치되어 있으나 **전혀 미사용**
- 이것을 권한 컨테이너로 재활용하는 것이 핵심 아이디어

### FabriX Chat MCP 검색 흐름
```
Frontend → FastAPI /mcp-command/rag-search
        → FastMCP 서버 (http://127.0.0.1:8002/mcp)
        → search_docs_rag(query, category, ...)
        → doc_data/ 파일시스템에서 BM25 검색
```
현재: 사용자 식별 없이 전체 카테고리 검색 가능

---

## 설계 원칙 (확정)

### 원칙 1: 그룹은 완전 Flat

```
[ 팀A ]  [ 팀B ]  [ 마케팅팀 ]  [ 공통문서팀 ]
  — 모두 동등한 레벨, 부모/자식 관계 없음 —
  — 권한 상속 없음, 순환참조 불가, 트리 구조 불필요 —
```

### 원칙 2: 카테고리 1개 = 그룹 1개 귀속

폴더 소유권 명확화. "복수 그룹이 하나의 폴더 공유" 아님.  
사용자가 여러 그룹에 속하면 각 그룹 소속 폴더를 모두 볼 수 있는 구조.

### 원칙 3: 권한 판단 로직 (단 4줄)

```python
def user_can_access_category(user_id, is_superuser, user_group_ids, category):
    if is_superuser:                       return True   # 슈퍼유저 전체 접근
    if category.visibility == 'public':   return True
    if category.visibility == 'private':  return category.owner_id == user_id
    if category.visibility == 'group':
        return category.group_id in user_group_ids
```

### 원칙 4: 사용자×그룹 행렬로 관리

복잡한 트리 대신 직관적 행렬:
```
사용자   팀A  팀B  마케팅  공통문서팀
홍길동    ✓        ✓       ✓
김철수         ✓          ✓
```

---

## DB 모델 (구현 시 추가)

### `Category` (doc_uploader 앱에 추가)

```python
class Category(models.Model):
    VISIBILITY_PRIVATE = 'private'
    VISIBILITY_GROUP   = 'group'
    VISIBILITY_PUBLIC  = 'public'

    name       = models.CharField(max_length=255, unique=True)
    owner      = models.ForeignKey(User, on_delete=models.CASCADE)
    visibility = models.CharField(max_length=10, choices=..., default='private')
    group      = models.ForeignKey(
        'auth.Group', null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['visibility']),
            models.Index(fields=['owner']),
            models.Index(fields=['group']),
        ]
```

### `BundleInviteCode` (그룹 멤버십 등록 도구 — 미결 이슈 있음)

```python
class BundleInviteCode(models.Model):
    label      = models.CharField(max_length=100)    # 관리용 이름 ("개발팀 온보딩")
    code       = models.CharField(max_length=30, unique=True)
    groups     = models.ManyToManyField('auth.Group', related_name='bundle_codes')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    is_active  = models.BooleanField(default=True)   # 명시적 폐기 전까지 유효
    used_by    = models.ManyToManyField(User, related_name='joined_via_bundles', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
```

---

## 그룹 멤버십 등록 방법: "번들 코드" 방식 (확정)

### 개념 정리

```
그룹 (auth.Group)   = 폴더 접근 권한의 단위
번들 코드           = 사람을 여러 그룹에 동시 등록하는 입장권 (그룹 자체가 아님)
```

번들 코드를 사용하면 코드에 묶인 기존 그룹들에 직접 추가됨.  
"번들 코드 이름"은 그룹이 아닌 단순 관리 라벨.

---

### 공용 폴더가 필요한 경우 — "공용 그룹" 패턴

```
그룹 구성 (모두 Flat):
  [ 팀A ]  [ 팀B ]  [ 개발팀-공용 ]  [ 공통문서팀 ]

폴더 귀속:
  팀A 전용폴더    → group: 팀A
  팀B 전용폴더    → group: 팀B
  개발팀 공용폴더 → group: 개발팀-공용  ← 팀A + 팀B 모두 접근

번들 코드:
  "개발팀A_온보딩" → [ 팀A + 개발팀-공용 + 공통문서팀 ] 동시 가입
  "개발팀B_온보딩" → [ 팀B + 개발팀-공용 + 공통문서팀 ] 동시 가입
```

→ 계층 없이 Flat하게 유지하면서 공용 폴더 공유 가능

---

### 번들 코드 그룹 목록 수정 UI

관리자가 기존 번들 코드의 포함 그룹을 변경할 수 있어야 함.

#### 번들 코드 상세/수정 화면

```
┌──────────────────────────────────────────────────────┐
│  번들 코드 상세                                       │
│  DEV-NEW-2026  [📋복사]                    [폐기]    │
│  라벨: 개발팀 신규입사자 온보딩                        │
│  가입자: 7명  |  생성일: 2026-01-15                  │
├──────────────────────────────────────────────────────┤
│  포함 그룹 수정                                       │
│  ☑ 팀A                                              │
│  ☐ 팀B          ← 추가 체크 가능                     │
│  ☑ 개발팀-공용                                       │
│  ☑ 공통문서팀   ← 체크 해제로 제거 가능              │
│                                                       │
│                           [그룹 목록 저장]            │
├──────────────────────────────────────────────────────┤
│  ⚠️ 변경은 앞으로 이 코드를 사용하는 신규 가입자에만  │
│     자동 적용됩니다.                                  │
│                                                       │
│  기존 가입자(7명)에게도 반영하려면:                   │
│    [➕ 추가된 그룹 기존 가입자에게 반영]              │
│    [➖ 제거된 그룹 기존 가입자에서 제거]  ⚠️ 주의    │
└──────────────────────────────────────────────────────┘
```

---

### 기존 가입자 처리 방법 (구체화)

#### Case 1: 그룹 추가 후 기존 가입자에게 반영

**버튼**: `[➕ 추가된 그룹 기존 가입자에게 반영]`

- 처리 로직: `used_by` 목록의 모든 사용자에게 새로 추가된 그룹을 `user.groups.add()` 실행
- 안전: 이미 그룹에 속해 있으면 Django M2M이 중복 없이 처리
- 확인 다이얼로그 없이 즉시 실행 가능 (가입만 추가, 제거 없음)

```
[확인] 7명의 기존 가입자에게 '인프라팀' 그룹을 추가하시겠습니까?
              [취소]  [추가]
  → 완료: 7명 모두에게 인프라팀 추가됨
```

#### Case 2: 그룹 제거 후 기존 가입자에서 제거

**버튼**: `[➖ 제거된 그룹 기존 가입자에서 제거]` (⚠️ 경고 표시)

복잡도가 있음 — **다른 번들을 통해 동일 그룹에 속한 사용자를 보호**해야 함.

**중복 경로 보호 로직:**

```python
def remove_group_from_bundle_users(bundle, group_to_remove):
    for user in bundle.used_by.all():
        # 다른 활성 번들 코드를 통해서도 이 그룹에 속해 있는지 확인
        other_bundles = BundleInviteCode.objects.filter(
            is_active=True,
            groups=group_to_remove,
            used_by=user,
        ).exclude(pk=bundle.pk)

        if other_bundles.exists():
            # 다른 경로로도 속해 있음 → 제거하지 않음
            skip.append(user.username)
        else:
            user.groups.remove(group_to_remove)
            removed.append(user.username)

    return removed, skip
```

**확인 다이얼로그 (미리보기 포함):**

```
┌──────────────────────────────────────────────────────┐
│  ⚠️ 그룹 제거 확인                                   │
├──────────────────────────────────────────────────────┤
│  '공통문서팀' 그룹을 기존 가입자에서 제거합니다.      │
│                                                       │
│  제거 예정 (5명):                                     │
│    홍길동, 이영희, 박민수, 최지훈, 강수진             │
│                                                       │
│  유지됨 — 다른 번들에도 속해 있음 (2명):             │
│    김철수 (PARTNER-2026 번들로도 공통문서팀 소속)     │
│    정예슬 (ADMIN-ALL 번들로도 공통문서팀 소속)        │
│                                                       │
│         [취소]          [5명에서 제거 확인]           │
└──────────────────────────────────────────────────────┘
```

---

### "슈퍼 번들 코드" 패턴 (전체 그룹 접근)

Django `is_staff` 등록 없이 모든 그룹 폴더에 접근하는 사람을 만들려면:

```
번들 코드 생성: "전체관리자_2026"
  ☑ 팀A
  ☑ 팀B
  ☑ 개발팀-공용
  ☑ 마케팅팀
  ☑ 공통문서팀   (현재 존재하는 모든 그룹 체크)
```

> ⚠️ **주의**: 이후 새 그룹이 생성되면 이 슈퍼 번들 코드를 수정하여 새 그룹을 추가해야 함.  
> 새 그룹 추가 시 관리자 패널에서 "슈퍼 번들에 포함되지 않은 그룹" 경고 표시 권장.

```
┌─────────────────────────────────────────────────┐
│  번들 코드 생성                                   │
├─────────────────────────────────────────────────┤
│  코드 이름 (라벨)                                 │
│  ┌──────────────────────────────────────────┐    │
│  │ 개발팀 신규입사자 온보딩                   │    │
│  └──────────────────────────────────────────┘    │
│                                                   │
│  이 코드를 입력하면 가입될 그룹 (복수 선택)       │
│  ┌──────────────────────────────────────────┐    │
│  │ ☑ 팀A                                    │    │
│  │ ☐ 팀B                                    │    │
│  │ ☑ 개발팀-공용                             │    │
│  │ ☐ 마케팅팀                               │    │
│  │ ☑ 공통문서팀                             │    │
│  └──────────────────────────────────────────┘    │
│                                                   │
│  생성될 코드 (자동 생성, 수정 가능)               │
│  ┌──────────────────────────────────────────┐    │
│  │ DEV-NEW-2026                             │    │
│  └──────────────────────────────────────────┘    │
│                                                   │
│              [취소]  [코드 생성]                  │
└─────────────────────────────────────────────────┘
```

#### STEP 2: 코드 생성 완료 → 복사 화면

```
┌─────────────────────────────────────────────────┐
│  ✅ 코드가 생성되었습니다                         │
├─────────────────────────────────────────────────┤
│  코드:  DEV-NEW-2026           [📋 복사]         │
│                                                   │
│  이 코드를 입력하면 자동으로 가입되는 그룹:       │
│  • 팀A                                           │
│  • 개발팀-공용                                    │
│  • 공통문서팀                                     │
│                                                   │
│  → 이 코드를 카카오톡/메신저로 대상자에게 전달    │
└─────────────────────────────────────────────────┘
```

#### STEP 3: 번들 코드 목록 (관리 화면)

```
┌──────────────────────────────────────────────────────────────────┐
│  번들 코드 목록                              [+ 새 코드 생성]    │
├────────────────┬──────────────┬───────────────────┬──────────────┤
│ 라벨           │ 코드         │ 가입 그룹          │ 상태 / 가입자│
├────────────────┼──────────────┼───────────────────┼──────────────┤
│ 개발팀 신규입사 │ DEV-NEW-2026 │ 팀A, 개발팀-공용, │ 활성  3명   │
│                │  [📋복사]    │ 공통문서팀        │  [폐기]      │
├────────────────┼──────────────┼───────────────────┼──────────────┤
│ 협력사 공유    │ PARTNER-2026 │ 팀B, 공통문서팀   │ 활성  1명   │
│                │  [📋복사]    │                   │  [폐기]      │
├────────────────┼──────────────┼───────────────────┼──────────────┤
│ 구버전         │ OLD-2024     │ 팀A               │ ❌폐기됨      │
└────────────────┴──────────────┴───────────────────┴──────────────┘
```

---

### 사용자 UI — Settings 페이지 GroupJoinWidget

```
┌──────────────────────────────────────┐
│  그룹 참가                            │
├──────────────────────────────────────┤
│  관리자에게 받은 참가 코드를 입력하세요 │
│  ┌────────────────────────┐  [참가]  │
│  │ DEV-NEW-2026           │         │
│  └────────────────────────┘         │
│                                       │
│  ✅ 3개 그룹에 가입되었습니다:        │
│     팀A / 개발팀-공용 / 공통문서팀    │
│                                       │
│  현재 내 그룹:                        │
│  🏷 팀A   🏷 개발팀-공용   🏷 공통문서팀 │
└──────────────────────────────────────┘
```

---

### 슈퍼 번들 코드 패턴 (전체 그룹 접근)

Django `is_superuser`/`is_staff` 등록 없이 모든 그룹 폴더에 접근하려면:

```
번들 코드 "전체관리자_2026"
  포함 그룹: ☑팀A  ☑팀B  ☑개발팀-공용  ☑마케팅팀  ☑공통문서팀 ... (전체)
  → 코드 1개로 모든 그룹 동시 가입
```

> ⚠️ 새 그룹이 추가될 때마다 이 번들 코드에도 해당 그룹을 추가해야 함.  
> 아래 번들 코드 수정 기능으로 처리.

---

### 번들 코드 수정 UI (그룹 추가/제거)

```
┌──────────────────────────────────────────────────────┐
│  번들 코드 상세                                       │
│  DEV-NEW-2026  [📋복사]                    [폐기]    │
│  라벨: 개발팀 신규입사자 온보딩                        │
│  가입자: 7명  |  생성일: 2026-01-15                  │
├──────────────────────────────────────────────────────┤
│  포함 그룹 수정                                       │
│  ☑ 팀A                                              │
│  ☐ 팀B          ← 체크하면 추가                      │
│  ☑ 개발팀-공용                                       │
│  ☑ 공통문서팀   ← 체크 해제하면 제거                 │
│                                                       │
│                           [그룹 목록 저장]            │
├──────────────────────────────────────────────────────┤
│  ⚠️ 변경은 앞으로 이 코드를 사용하는 신규 가입자에만  │
│     자동 적용됩니다.                                  │
│                                                       │
│  기존 가입자(7명)에게도 반영하려면:                   │
│    [➕ 추가된 그룹을 기존 가입자에게 반영]            │
│    [➖ 제거된 그룹을 기존 가입자에서 제거]  ⚠️ 주의  │
└──────────────────────────────────────────────────────┘
```

---

### 기존 가입자 처리 로직

#### 케이스 A: 그룹 추가 시 (`[➕ 추가된 그룹을 기존 가입자에게 반영]`)

단순하게 처리 가능. 부작용 없음.

```
처리 흐름:
  bundle.used_by 사용자 전원에 대해
    user.groups.add(새로 추가된 그룹)
  → 이미 그 그룹에 속해 있어도 오류 없음 (add는 중복 무시)
```

```
UI 확인 다이얼로그:
  ┌─────────────────────────────────────────┐
  │  다음 7명에게 [인프라팀] 그룹을 추가합니다. │
  │  홍길동, 김철수, 이영희 외 4명            │
  │              [취소]  [적용]              │
  └─────────────────────────────────────────┘
```

#### 케이스 B: 그룹 제거 시 (`[➖ 제거된 그룹을 기존 가입자에서 제거]`)

**다른 번들 경로 보호** 로직 적용. 신중하게 처리해야 함.

```python
def remove_group_from_bundle_users(bundle, group_to_remove):
    """
    bundle.used_by 사용자 중에서 group_to_remove 그룹을 제거.
    단, 다른 활성 번들 코드를 통해서도 그 그룹에 속한 사람은 유지.
    """
    protected = set()   # 다른 경로가 있어서 제거 안 할 사람
    removed = set()     # 제거 대상

    for user in bundle.used_by.all():
        # 이 그룹을 부여하는 다른 활성 번들이 있는지 확인
        other_bundles = BundleInviteCode.objects.filter(
            is_active=True,
            groups=group_to_remove,
            used_by=user,
        ).exclude(pk=bundle.pk)

        if other_bundles.exists():
            protected.add(user)          # 다른 경로 있음 → 유지
        else:
            user.groups.remove(group_to_remove)
            removed.add(user)

    return removed, protected
```

```
UI 확인 다이얼로그 (경고):
  ┌──────────────────────────────────────────────────────────┐
  │  ⚠️ [팀A] 그룹을 기존 가입자에서 제거합니다.             │
  │                                                          │
  │  제거될 사용자 (5명):                                    │
  │    홍길동, 이영희, 박민준, 최수진, 강동원                │
  │                                                          │
  │  보호됨 — 다른 번들 경로 있음 (2명):                    │
  │    김철수  (PARTNER-2026 번들로도 팀A 보유)              │
  │    오지은  (ALLSTAFF-2026 번들로도 팀A 보유)             │
  │                                                          │
  │  이 작업은 되돌릴 수 없습니다.                           │
  │              [취소]  [5명에서 제거]                      │
  └──────────────────────────────────────────────────────────┘
```

#### 케이스 C: 번들 코드 폐기 시

폐기(`is_active=False`)는 **신규 가입만 차단**, 기존 멤버십은 유지.  
기존 가입자의 그룹 멤버십을 일괄 제거하려면 위 케이스 B를 모든 그룹에 대해 실행.

```
UI:
  ┌──────────────────────────────────────────────────┐
  │  번들 코드 DEV-NEW-2026 폐기                      │
  │                                                   │
  │  ○ 코드만 폐기 (기존 가입자 그룹 유지)  ← 기본   │
  │  ○ 코드 폐기 + 기존 가입자 그룹도 제거           │
  │                                                   │
  │                    [취소]  [폐기]                 │
  └──────────────────────────────────────────────────┘
```

---

### 번들 코드 수정 API

| 엔드포인트 | 설명 |
|-----------|------|
| `PATCH /admin/bundle-codes/<id>/` | 번들 그룹 목록 수정 (코드 문자열 유지) |
| `POST /admin/bundle-codes/<id>/sync-add/` | 추가된 그룹을 기존 가입자에게 반영 |
| `POST /admin/bundle-codes/<id>/sync-remove/` | 제거된 그룹을 기존 가입자에서 제거 (보호 로직 포함) |
| `POST /admin/bundle-codes/<id>/revoke/` | 코드 폐기 (선택적으로 기존 가입자 그룹 제거 포함) |

| 항목 | 설계 |
|------|------|
| 유효 기간 | 없음 (관리자가 명시적으로 폐기할 때까지 유지) |
| 폐기 | `is_active=False` — 관리자 패널에서 [폐기] 클릭 1회 |
| 재사용 방지 | `used_by` M2M — 이미 사용한 사람 기록 (이미 멤버면 안내 메시지) |
| 코드 형식 | 자동 생성 대문자+숫자 (예: `DEV-NEW-2026`) |

### ⚠️ 잔존 불편 사항 (추후 재검토)

- 코드를 메신저로 수동 전달해야 함 (이메일 자동 발송 불가)
- 더 나은 대안 후보:
  - **사용자 신청 + 관리자 승인**: 사용자가 앱 내에서 그룹 가입 신청 → 관리자 알림 → 클릭 1번 승인
  - **이메일 초대**: 이메일 서버 구축 시 적용 가능

---

## FabriX Chat 연동 설계 (구현 시 적용)

### FastAPI `dependencies.py` 개선

```python
# 현재: 토큰 존재 확인만
SELECT key FROM authtoken_token WHERE key = ?

# 개선: user_id + is_superuser + group_ids 동시 취득 (SQLite 직접)
SELECT u.id, u.is_superuser, u.is_staff,
       GROUP_CONCAT(ug.group_id) as group_ids
FROM authtoken_token t
JOIN auth_user u ON t.user_id = u.id
LEFT JOIN auth_user_groups ug ON u.id = ug.user_id
WHERE t.key = ?
GROUP BY u.id
```

### FastAPI `doc_search.py` 권한 필터

```python
@router.post("/rag-search")
async def rag_search(body, user_ctx = Depends(verify_token_with_user)):
    user_id = user_ctx.user_id
    is_superuser = user_ctx.is_superuser
    user_group_ids = user_ctx.group_ids

    if not is_superuser:
        # 접근 가능한 카테고리 확인
        if body.category:
            assert_category_access(user_id, is_superuser, user_group_ids, body.category)
        # 카테고리 미지정 시: 접근 가능한 카테고리만 검색 대상으로 제한
```

---

## API 설계 (구현 시 적용)

### doc_uploader 앱 (Django)

| 엔드포인트 | 대상 | 설명 |
|-----------|------|------|
| `GET /categories/` | 전체 사용자 | 접근 가능 카테고리만 반환 |
| `POST /categories/` | 전체 사용자 | visibility, group 필드 추가 |
| `PATCH /categories/<name>/` | owner | owner만 수정 가능 |
| `GET /my-groups/` | 전체 사용자 | 내 그룹 목록 (드롭다운용) |
| `POST /join/` | 전체 사용자 | 번들 코드 입력 → 그룹 가입 |
| `GET/POST /admin/groups/` | is_staff | 그룹 목록/생성 |
| `GET /admin/groups/matrix/` | is_staff | 사용자×그룹 행렬 |
| `GET/POST /admin/bundle-codes/` | is_staff | 번들 코드 목록/생성 |
| `GET /admin/bundle-codes/<id>/` | is_staff | 번들 코드 상세 + 가입자 목록 |
| `PATCH /admin/bundle-codes/<id>/` | is_staff | 번들 코드 그룹 목록 수정 |
| `PATCH /admin/bundle-codes/<id>/revoke/` | is_staff | 코드 폐기 |
| `POST /admin/bundle-codes/<id>/apply-additions/` | is_staff | 추가된 그룹 기존 가입자에게 반영 |
| `POST /admin/bundle-codes/<id>/preview-removals/` | is_staff | 그룹 제거 시 영향 미리보기 (제거/유지 분류) |
| `POST /admin/bundle-codes/<id>/apply-removals/` | is_staff | 제거된 그룹 기존 가입자에서 제거 (중복 경로 보호 포함) |

---

## 구현 작업 목록 (10단계)

> **현재 상태: 보류** — 그룹 멤버십 등록 방법 확정 후 진행

1. `Category` + `BundleInviteCode` 모델 + migration (기존 폴더 자동 import: visibility=public)
2. Django views: 카테고리 CRUD 권한 필터 + 그룹 미소속 제한
3. API: `/my-groups/`, `/join/`, 관리자 그룹·번들코드 CRUD
4. Django Admin: `BundleInviteCode` 등록 (백업용)
5. **FastAPI `dependencies.py`**: verify_token → user_id, is_superuser, group_ids 반환
6. **FastAPI `doc_search.py`**: RAG/검색 시 카테고리 접근 권한 필터
7. FastAPI `doc_upload.py`: 업로드 전 카테고리 접근 권한 확인
8. Frontend `CategoryManager.jsx`: visibility + 그룹 드롭다운 + 배지
9. Frontend Settings(GroupJoinWidget) + 관리자 패널(번들코드 관리 + 행렬)
10. 문서 업데이트

---

## 기존 호환 전략

- OS 폴더 경로 변경 없음: `doc_data/{category.name}` 유지
- 기존 폴더 → migration RunPython으로 `Category(visibility='public', owner=admin)` 자동 생성
- 마이그레이션 전까지 기존 동작과 완전 동일 (모든 카테고리 공개)