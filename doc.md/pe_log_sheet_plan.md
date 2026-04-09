# PE Log Sheet 협업 앱 개발 계획서

## 1. 문서 목적

`test\pe_log\pe-log-sheet 개발 프롬프트.md`를 기준으로, `pe_log.csv`를 모든 사용자가 함께 조회·수정·저장하는 새 앱을 ht_tools에 추가하기 위한 구현 계획을 정리한다.

- 목표: Excel-like 공동 작업 시트 앱 추가
- 대상 독자: 이 저장소를 수정할 개발자
- 범위 포함: 아키텍처, 데이터 모델, API, 동시성 제어, 프론트엔드 UI, 단계별 구현 순서
- 범위 제외: 실제 코드 구현, 운영 배포 스크립트 작성, 별도 외부 인프라 도입

---

## 2. 현재 코드베이스 분석

### 2.1 독립 앱 추가 패턴은 이미 존재한다

- 프론트 라우트: `frontend\src\App.jsx`
  - 독립 페이지를 lazy import 후 `PrivateRoute`로 연결한다.
  - 현재 `/esc-calculator`, `/data-explorer`, `/image-compare`, `/doc-uploader` 패턴이 이미 있다.
- 앱 선택 화면: `frontend\src\features\appSelector\AppSelectorPage.jsx`
  - 앱 카드 목록에 새 항목을 추가하면 된다.
- Django 앱 등록: `django_server\config\settings.py`, `django_server\config\urls.py`
  - `INSTALLED_APPS`와 `/api/<app>/` include 패턴이 이미 정리되어 있다.

### 2.2 ESC Calculator가 가장 가까운 baseline 이다

- 프론트엔드: `frontend\src\features\escCalculator\*`
- 백엔드: `django_server\apps\esc_calculator\*`
- API 계층: `frontend\src\api\djangoApi.js`
- 특징:
  - 독립 페이지 + 독립 Django app
  - FortuneSheet 사용 경험이 이미 있음
  - 새 앱 추가 시 어떤 파일을 만져야 하는지 선례가 명확함

단, ESC Calculator의 FortuneSheet는 **계산 결과를 보여주는 read-only 중심 구현**이며, 이번 요구사항처럼 여러 사용자의 동시 수정/저장 문제는 아직 해결하지 않는다.

### 2.3 현재 플랫폼의 동시성 기반

- DB: SQLite + WAL (`django_server\config\settings.py`)
- 인증: Django Token, 프론트 저장소는 `sessionStorage`
- SSE 인프라: 현재 FastAPI가 채팅 스트리밍에서 사용 중 (`ai_gateway\routers\chat.py`, `agent_chat.py`)
- 원자적 DB 작업: 기존 Django 앱들에서 `transaction.atomic` 패턴을 사용 중

즉, **"공유 문서 상태는 Django가 authoritative source"**, **"실시간 반영은 SSE 패턴 재사용"** 구성이 현재 코드베이스와 가장 잘 맞는다.

---

## 3. 입력 데이터와 업무 규칙

### 3.1 원본 CSV 스키마

`test\pe_log\pe_log.csv`

| 컬럼 | 의미 |
|---|---|
| 직무 | 요청자 업무 분류 |
| 시스템 | 대상 시스템 |
| Web_App_구분 | Web/App 구분 |
| 요청일 | 요청 발생일 |
| 요청_주차 | `요청일` 기준 주차 텍스트 |
| 유형 | 사용자 문의/요청 유형 |
| 문의내용 | 상세 VOC 내용 |
| 시스템PE | 담당 PE |
| 조치시작일 | 대응 시작일 |
| 조치완료일 | 대응 완료일 |
| 조치내용 | 조치 결과 |
| 완료여부 | 완료 / null |

### 3.2 요구사항으로 고정할 비즈니스 규칙

1. `조치완료일`이 비어 있으면 `완료여부`도 반드시 `null`
2. `요청_주차`는 프론트엔드 local helper로 `요청일 -> n월 n주차` 자동 산출
3. `Help` 버튼 클릭 시 `유형 분류 기준`을 모달로 표시
4. 모든 사용자가 **같은 시트 하나**를 공유
5. 동시 수정 상황에서 다음을 구현
   - 낙관적 동시성 제어
   - 비관적 잠금
   - 원자적 트랜잭션
   - 실시간 이벤트 전파
   - 충돌 해결 정책
   - 읽기/쓰기 분리
   - 작업 단위 최소화

### 3.3 초기 데이터 파일 위치 계획

현재 원본은 `test\pe_log\pe_log.csv`에 있지만, 이 경로는 테스트/참조 성격이 강하다.

따라서 실제 구현에서는 아래처럼 분리하는 것이 안전하다.

- 참조 원본: `test\pe_log\pe_log.csv`
- 앱 canonical seed: `data\pe_log\pe_log.csv`

이미지 예시(`2025_PE로그.png`, `2026_PE로그.png`)는 요구사항 해석용 참고 자료로만 유지한다.

---

## 4. FortuneSheet 협업 기능 검토 결과

FortuneSheet 문서상:

- `onOp` callback 으로 사용자 조작이 `Op[]` 형태로 방출된다.
- 이 op stream은 backend storage 및 collaboration 연동 용도로 사용 가능하다.
- 공식 문서와 demo는 backend-demo 예제를 제공한다.

하지만 이번 요구사항에 필요한 아래 항목은 FortuneSheet가 자동 보장하지 않는다.

- authoritative revision 관리
- optimistic version check
- pessimistic lock 정책
- transaction commit / rollback
- 충돌 감지 및 사용자 UX
- 커밋 후 이벤트 브로드캐스트 정책

따라서 계획의 핵심은 **FortuneSheet를 편집 UI 엔진으로 쓰되, 정합성 보장은 Django backend가 담당**하도록 설계하는 것이다.

---

## 5. 목표 아키텍처

## 5.1 새 앱 식별자

- 프론트 feature 폴더: `frontend\src\features\peLogSheet\`
- Django app: `django_server\apps\pe_log_sheet\`
- 사용자 라우트: `/pe-log-sheet`
- Django API prefix: `/api/pe-log-sheet/`

## 5.2 저장 구조 권장안

두 옵션을 비교하면, **기능 구현 난이도와 안정성, 표준성** 기준으로는 아래 권장안이 더 낫다.

| 옵션 | 구현 난이도 | 동작 안정성 | 표준성 | 비고 |
|---|---|---|---|---|
| 업무 데이터 1개 table + 운영 메타데이터 table 허용 | 낮음 | 높음 | 높음 | **권장안** |
| 앱 관련 전체 DB table 1개만 허용 | 높음 | 중간 이하 | 낮음 | 축소안 |

권장안의 저장 구조:

```python
class PeLogSheetState(models.Model):
    singleton_key = models.CharField(max_length=32, unique=True, default="main")
    workbook_data = models.JSONField(default=dict)   # FortuneSheet workbook 전체 상태
    revision = models.BigIntegerField(default=0)
    source_checksum = models.CharField(max_length=64, blank=True, default="")
    last_editor = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    initialized_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

```python
class PeLogSheetRevision(models.Model):
    document = models.ForeignKey(PeLogSheetState, on_delete=models.CASCADE, related_name="revisions")
    base_revision = models.BigIntegerField()
    new_revision = models.BigIntegerField()
    ops = models.JSONField(default=list)
    editor = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
```

핵심 원칙:

- **업무 데이터는 `PeLogSheetState`의 단일 row가 authoritative source**
- revision/op 기록은 `PeLogSheetRevision`에 append-only로 남긴다
- per-user 저장은 두지 않는다
- 시트는 기본적으로 1 workbook / 1 shared sheet 로 시작한다

이 구성이 더 나은 이유:

1. 구현 난이도가 더 낮다
   - 현재 snapshot과 revision history의 책임이 분리된다
   - 409 conflict 응답, 재동기화, 디버깅이 단순해진다
2. 기능이 더 잘 작동한다
   - stale write 분석이 쉽다
   - 누가 어떤 batch를 저장했는지 추적 가능하다
   - SSE 재연결 시 `since_revision` 기반 보강 여지가 생긴다
3. 표준적인 방법에 가깝다
   - collaborative editor는 보통 `current state + revision/op log + realtime transport`로 나눈다

## 5.3 엄격 단일-table 축소안

만약 사용자가 앱 관련 DB 전체를 정말 1 table로 제한한다면 다음처럼 축소해야 한다.

- `PeLogSheetState` 하나만 유지
- revision/op/history는 `workbook_data` 내부 메타데이터로만 관리
- lock은 persistent table 없이 짧은 server-side mutex로 처리
- conflict 발생 시 항상 최신 snapshot 재로드 위주로 UX 설계

이 안은 가능은 하지만 다음 한계가 있다.

- persistent revision history 부재
- 문제 분석과 감사 추적 어려움
- 멀티프로세스 확장성 저하
- 실시간 동기화 재연결 전략이 약해짐

## 5.4 권장 동기화 계약

### 읽기 API

- `GET /api/pe-log-sheet/state/`
  - 최신 `workbook_data`, `revision`, `server_time`, `help_content`

### 쓰기 API

- `POST /api/pe-log-sheet/ops/`
  - 입력: `base_revision`, `ops`, `client_id`
  - 처리:
    1. 현재 revision 조회
    2. `base_revision` 일치 여부 확인
    3. 일치 시 op 적용 + revision 증가 + 저장
    4. 불일치 시 `409 Conflict`와 최신 snapshot/revision 반환

### 초기화 / 재적재 API

- `POST /api/pe-log-sheet/reset-from-source/`
  - 관리자 또는 내부용
  - CSV에서 workbook 재생성
  - 운영 중 실수 복구 수단

### 이벤트 스트림 API

- `GET /api/pe-log-sheet/stream/`
  - SSE
  - payload: `revision`, `editor`, `changed_at`, 필요 시 `ops`
  - 추후 `since_revision` 지원 시 `PeLogSheetRevision`에서 누락 이벤트 보강 가능

---

## 6. 동시성 제어 설계

## 6.1 낙관적 동시성 제어

서버는 모든 수정 요청에 `base_revision`을 강제한다.

- `base_revision == current_revision`
  - 커밋 진행
- `base_revision != current_revision`
  - 커밋 거부 (`409`)
  - 최신 snapshot/revision 반환
  - 프론트는 재로딩 또는 재적용(rebase) UX 제공

이 방식은 다수 사용자가 읽기만 하는 상황에서 가장 비용이 낮다.

## 6.2 비관적 잠금

이번 기능은 SQLite + 단일 공유 문서 조합이다. 따라서 잠금 단위를 문서 전체로 최소화한다.

권장안:

1. 서버에서 **짧은 critical section**만 잠근다
2. `transaction.atomic()` 내부에서 최신 row를 읽고 저장한다
3. `PeLogSheetState` 갱신과 `PeLogSheetRevision` append를 같은 트랜잭션으로 묶는다
4. 잠금 시간은 `ops 적용 -> 저장 -> revision 증가 -> revision log append` 구간으로 제한한다

주의:

- SQLite는 대규모 다중 writer 환경에 강한 row-level lock DB가 아니다.
- 따라서 잠금은 **짧고 단순한 write transaction**으로 유지해야 한다.
- 최초 구현은 현재 운영 전제(Windows, 단일 서버, SQLite WAL)에 맞춘다.

## 6.3 원자성

한 번의 사용자 편집 flush는 다음을 한 트랜잭션으로 처리한다.

1. revision 검증
2. workbook_data에 op 적용
3. 비즈니스 규칙 재검증
4. revision 증가
5. last_editor / updated_at 갱신
6. revision log append

하나라도 실패하면 전체 rollback 한다.

## 6.4 실시간 이벤트 전파

기본안은 **Django SSE endpoint**다.

선정 이유:

- authoritative state가 Django DB에 있다
- 이번 요구사항은 단일 shared sheet 이다
- authoritative state와 revision metadata를 같은 계층에서 다루기 쉽다

권장 동작:

- commit 성공 후에만 stream 이벤트 발행
- 이벤트는 "새 revision 도착"을 알리는 용도로 최소화
- 다른 사용자는 이벤트 수신 시 `revision` 확인 후 최신 상태를 동기화

## 6.5 충돌 해결 정책

1. 기본 정책은 **server-wins**
2. 사용자가 stale revision 으로 저장하면 즉시 409
3. 프론트는 아래 중 하나를 제공
   - 최신 상태 자동 재로드 후 현재 편집 취소
   - 최신 상태를 다시 받아 사용자가 재입력

초기 버전에서는 Google Sheets 수준의 실시간 cell merge 보다, **충돌을 명확히 감지하고 안전하게 되돌리는 UX**가 더 현실적이다.

## 6.6 읽기-쓰기 분리

- 읽기:
  - 최초 진입 시 전체 snapshot 1회 로드
  - 이후 SSE 이벤트로 최신 revision 감지
- 쓰기:
  - 편집 중 발생한 op를 debounce/batch 하여 서버로 전송

## 6.7 작업 단위 최소화

- cell 한 번 수정할 때마다 전체 workbook 전체를 PUT 하지 않는다
- FortuneSheet `onOp` 결과를 batch 전송한다
- 서버 저장은 snapshot 전체를 최종적으로 갱신하되, 네트워크 payload 는 op 단위로 최소화한다

---

## 7. 프론트엔드 설계

## 7.1 추가 파일 구조

```text
frontend\src\features\peLogSheet\
├── PeLogSheetPage.jsx
├── components\
│   ├── SheetHeader.jsx
│   ├── HelpModal.jsx
│   ├── SyncStatusBadge.jsx
│   └── ConflictBanner.jsx
├── hooks\
│   └── usePeLogSheet.js
└── utils\
    ├── weekLabel.js
    ├── workbookNormalizer.js
    └── opBatcher.js
```

## 7.2 화면 구성

1. 상단 헤더
   - 앱 제목
   - 연결 상태 / 저장 상태
   - Help 버튼
   - 마지막 반영 revision / 마지막 편집자
2. 본문
   - FortuneSheet editable workbook
3. 배너/모달
   - conflict banner
   - error banner
   - 유형 분류 기준 Help modal

## 7.3 프론트 핵심 동작

- 최초 진입 시 `state` API 로드
- FortuneSheet를 editable mode 로 렌더
- `onOp` 발생 시 `opBatcher`에 적재
- debounce 후 `ops` API 전송
- SSE 수신 시 최신 revision 확인
- 다른 사용자의 commit 이 도착하면 현재 상태와 비교 후 안전하게 반영

## 7.4 로컬 규칙

- `요청일` 편집 시 `요청_주차` 자동 계산
- `조치완료일`이 비면 `완료여부`를 자동 `null`
- Help 내용은 정적 상수 또는 프론트 local markdown/table로 관리

---

## 8. 백엔드 설계

## 8.1 Django app 구조

```text
django_server\apps\pe_log_sheet\
├── __init__.py
├── apps.py
├── models.py
├── serializers.py
├── urls.py
├── views.py
├── services\
│   ├── csv_loader.py
│   ├── workbook_service.py
│   ├── op_service.py
│   └── stream_hub.py
└── management\commands\
    └── sync_pe_log_sheet_from_csv.py
```

## 8.2 서비스 책임

- `csv_loader.py`
  - CSV 로드
  - 날짜/null 값 정규화
  - 초기 workbook row 생성
- `workbook_service.py`
  - FortuneSheet workbook 기본 구조 생성
  - help metadata 조립
  - 비즈니스 규칙 보정
- `op_service.py`
  - incoming ops 검증
  - workbook_data 반영
  - revision 충돌 처리
- `stream_hub.py`
  - SSE subscriber 관리
  - commit 이후 이벤트 전달

## 8.3 API 초안

| Method | URL | 목적 |
|---|---|---|
| GET | `/api/pe-log-sheet/state/` | 최신 workbook snapshot 조회 |
| POST | `/api/pe-log-sheet/ops/` | op batch 적용 |
| GET | `/api/pe-log-sheet/stream/` | revision 이벤트 구독 |
| POST | `/api/pe-log-sheet/reset-from-source/` | CSV 기준 재초기화 |

---

## 9. 구현 단계

## Phase 1 — 앱 골격 추가

1. Django `pe_log_sheet` app 생성
2. `settings.py`, `config/urls.py` 등록
3. 프론트 route `/pe-log-sheet` 추가
4. 앱 선택 화면 카드 추가
5. `djangoApi.js`에 `peLogSheetApi` 추가

## Phase 2 — CSV 기반 초기 상태 생성

1. `pe_log.csv` 스키마 분석 로직 작성
2. `data\pe_log\pe_log.csv` canonical 위치 확정
3. workbook_data 생성기 작성
4. 초기 shared state row 생성 로직 작성
5. 관리 명령으로 재적재 가능하게 구성

## Phase 3 — 조회/저장 API 계약 구현

1. `state` endpoint 작성
2. `ops` endpoint 작성
3. serializer / payload validation 작성
4. `base_revision` 검증 및 409 응답 포맷 확정

## Phase 4 — 프론트 editable 시트 구현

1. `PeLogSheetPage.jsx` 작성
2. FortuneSheet editable 구성
3. `usePeLogSheet` 훅 작성
4. `onOp` 수집 + debounce flush 구현

## Phase 5 — 정합성 규칙 구현

1. `요청_주차` 자동 계산 helper 구현
2. `조치완료일 / 완료여부` 연동 규칙 구현
3. 서버 저장 전 재검증 로직 구현
4. invalid row 처리 UX 확정

## Phase 6 — 동시성 / 이벤트 전파

1. transaction 기반 commit 구현
2. short critical section 잠금 구현
3. SSE stream endpoint 구현
4. 다른 사용자 저장 반영 시 프론트 동기화 처리
5. conflict banner / reload UX 구현

## Phase 7 — Help / 마감 작업

1. Help modal 구현
2. `유형 분류 기준` 표 렌더링
3. 로딩/저장/충돌 상태 배지 정리
4. 문서와 테스트 보강

---

## 10. 변경 대상 파일

### 프론트엔드

- `frontend\src\App.jsx`
- `frontend\src\features\appSelector\AppSelectorPage.jsx`
- `frontend\src\api\djangoApi.js`
- `frontend\src\features\peLogSheet\*`

### Django

- `django_server\config\settings.py`
- `django_server\config\urls.py`
- `django_server\apps\pe_log_sheet\*`

### 데이터/문서

- `data\pe_log\pe_log.csv` (canonical source 예정)
- `doc.md\pe_log_sheet_plan.md`

---

## 11. 리스크와 결정 사항

### 리스크 1 — SQLite 잠금 한계

해결 방향:

- 문서 전체 단위의 짧은 write transaction
- op batch 최소화
- 충돌 시 merge 대신 명확한 재동기화

### 리스크 2 — `"1개 table data"` 제약 해석

권장 해석은 다음이다.

- 업무 데이터: 1개 shared state table
- 운영 메타데이터: revision/op log는 허용

이 해석이 더 표준적이고 구현 리스크가 낮다.

반대로 앱 관련 전체 DB table을 1개로 제한하면:

- persistent revision history 제거
- 충돌 복구 단순화 대신 UX 후퇴
- 추후 운영 추적성 저하

### 리스크 3 — FortuneSheet op 재적용 복잡도

초기 버전은 아래 우선순위를 따른다.

1. 정확한 저장
2. 충돌 감지
3. 안전한 재동기화
4. 자동 merge 최소화

---

## 12. 완료 기준

다음 조건을 만족하면 1차 구현 완료로 본다.

1. `/pe-log-sheet` 앱이 선택 화면과 라우트에 연결된다.
2. `pe_log.csv` 기반 shared sheet 가 최초 로드된다.
3. 여러 사용자가 같은 시트를 보고 수정할 수 있다.
4. stale revision 저장은 409 conflict 로 안전하게 막힌다.
5. commit 성공 후 다른 사용자 화면에도 최신 revision 이 반영된다.
6. `요청_주차`, `조치완료일 -> 완료여부` 규칙이 유지된다.
7. Help 버튼으로 `유형 분류 기준` 모달이 열린다.

---

## 13. 현재 초안의 핵심 결정

- ESC Calculator의 앱 추가 패턴을 적극 재사용한다.
- FortuneSheet는 편집 UI와 op 생성 도구로 사용한다.
- 정합성은 Django backend가 책임진다.
- **권장안은 shared state table + revision/op log table** 구조다.
- 실시간 전파는 Django SSE를 우선 검토한다.

즉, 기능 구현 난이도, 동작 안정성, 그리고 협업형 에디터의 일반적인 개발 표준을 함께 고려하면, **"업무 데이터는 1개 table로 두되 운영 메타데이터는 분리 허용"**이 가장 현실적인 방향이다.
