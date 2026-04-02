# Doc Uploader 앱 구현 정리

> 커밋: `6d05051` — `feat: Implement document uploader functionality with Django and React`
> 날짜: 2026-04-02

---

## 1. 개요

PDF·Office 문서를 업로드하면 자동으로 Markdown으로 변환하여 `doc_data/` 디렉터리에 저장하는 앱.
변환된 파일은 FabriX Chat의 RAG(`/mcp`) 검색 소스로 직접 활용된다.

### 변환 흐름 요약
```
Browser → FastAPI /doc-converter/upload
  ├─ .txt/.md → 즉시 doc_data/<category>/<stem>.md 저장 (변환 없음)
  └─ PDF/Office → BackgroundTask
       ├─ Django 내부 API로 ConversionJob 레코드 생성
       ├─ asyncio.Lock (직렬화, GPU OOM 방지)
       ├─ dev_marker 프로젝트 subprocess 호출 (convert_pdf.py / convert_office.py)
       └─ 성공/실패 → Django callback API로 상태 업데이트
```

---

## 2. 아키텍처 결정 사항 (ADR)

| 결정 | 이유 |
|------|------|
| BackgroundTask + asyncio.Lock 직렬화 | 한 번에 하나씩 변환 → GPU OOM 방지 |
| FastAPI → Django 내부 API (`X-Internal-Secret`) | 공유 인증 없이 서비스 간 안전한 통신 |
| `callback_token` (UUID) 기반 콜백 | FastAPI가 일반 Django Auth 없이도 자신의 job만 업데이트 가능 |
| 카테고리 = 실제 OS 폴더 | Django DB에 카테고리 테이블 불필요, 파일시스템이 단일 truth |
| `startup-reset` API | FastAPI 재시작 시 `working` 상태로 남은 좀비 job 자동 정리 |
| 파일 크기 50 MB 제한 | FastAPI 업로드 엔드포인트 레벨 검증 |

---

## 3. 추가된 파일 목록

### Django (`django_server/apps/doc_uploader/`)
| 파일 | 역할 |
|------|------|
| `models.py` | `ConversionJob` 모델 |
| `serializers.py` | 공개용 / 내부 생성용 시리얼라이저 2종 |
| `views.py` | 5개 뷰 (아래 API 섹션 참고) |
| `urls.py` | URL 라우팅 |
| `admin.py` | Django 관리자 인터페이스 |
| `migrations/0001_initial.py` | 최초 마이그레이션 |

### FastAPI (`ai_gateway/`)
| 파일 | 역할 |
|------|------|
| `routers/doc_upload.py` | `POST /doc-converter/upload` 엔드포인트 |
| `services/doc_converter.py` | BackgroundTask 변환 로직, subprocess 호출, 상태 업데이트 |

### Frontend (`frontend/src/features/docUploader/`)
| 파일 | 역할 |
|------|------|
| `DocUploaderPage.jsx` | 페이지 루트, 레이아웃 조립 |
| `components/CategoryManager.jsx` | 카테고리 사이드바 (생성/선택/이름변경) |
| `components/FileUploadArea.jsx` | 드래그&드롭 + 클릭 파일 업로드 |
| `components/JobQueueTable.jsx` | 변환 작업 큐 테이블 (폴링 실시간 업데이트) |

---

## 4. 데이터 모델

### `ConversionJob`

```python
class ConversionJob(models.Model):
    original_filename  # CharField(500)
    category_name      # CharField(255)
    status             # choices: waiting / working / completed / failed
    error_message      # TextField (실패 시 500자 이내)
    created_at         # auto_now_add
    callback_token     # UUIDField(unique, editable=False) — FastAPI 콜백 전용
```

**인덱스**: `status`, `created_at`  
**정렬 기본값**: `-created_at` (최신순)  
**자동 정리**: 목록 조회 시 100건 초과분 중 completed/failed를 오래된 것부터 삭제

---

## 5. API 설계

### Django REST (`/api/doc-uploader/`)

| 메서드 | URL | 인증 | 설명 |
|--------|-----|------|------|
| `GET` | `jobs/` | `IsAuthenticated` | 최근 100건 작업 목록 |
| `POST` | `jobs/internal/` | `X-Internal-Secret` 헤더 | FastAPI가 job 레코드 생성 |
| `POST` | `jobs/startup-reset/` | `X-Internal-Secret` 헤더 | working job → failed 초기화 |
| `PATCH` | `jobs/callback/<uuid:token>/` | `AllowAny` (token 자체가 인증) | FastAPI 변환 완료 상태 업데이트 |
| `GET` | `categories/` | `IsAuthenticated` | 카테고리(폴더) 목록 + `.md` 파일 수 |
| `POST` | `categories/` | `IsAuthenticated` | 새 카테고리 폴더 생성 |
| `PATCH` | `categories/<name>/` | `IsAuthenticated` | 카테고리 폴더 이름 변경 |

#### `callback_token` 보안 설계
- `AllowAny` + `authentication_classes = []` 로 세션/토큰 인증 우회
- UUID v4 토큰이 비밀번호 역할 — FastAPI만 알고 있음
- 해당 job 상태(`working`, `completed`, `failed`)만 변경 가능

#### `X-Internal-Secret` 보안 설계
- `secrets.toml`의 `[doc_converter].internal_secret` 값
- Django `settings.DOC_CONVERTER_INTERNAL_SECRET` 으로 주입
- FastAPI는 `_DOC_CFG["internal_secret"]` 에서 로드

### FastAPI (`/doc-converter/`)

| 메서드 | URL | 설명 |
|--------|-----|------|
| `POST` | `/doc-converter/upload` | 파일 업로드, 변환 큐 등록 |

**요청**: `multipart/form-data`
- `file`: 업로드 파일 (최대 50 MB)
- `category`: 저장 카테고리 이름

**지원 확장자**:
- `.txt`, `.md` → 즉시 저장 (변환 없음)
- `.pdf` → Marker subprocess (`convert_pdf.py`)
- `.doc`, `.docx`, `.ppt`, `.pptx`, `.xls`, `.xlsx` → Markitdown subprocess (`convert_office.py`)

**응답**:
```json
{ "job_id": 1, "status": "waiting", "message": "'파일명' 변환 작업이 대기열에 추가되었습니다." }
```

---

## 6. 변환 서비스 (`doc_converter.py`)

### `process_conversion_job` — BackgroundTask 진입점

```
Lock 대기
  → status: working
  → subprocess 실행 (convert_pdf.py 또는 convert_office.py)
  → returncode != 0 → raise RuntimeError
  → 결과 .md 파일 존재 확인
  → status: completed
  → finally: temp 파일 삭제
  → 예외 발생 시 → status: failed (error_message 포함)
```

### `run_converter_subprocess`
- `asyncio.create_subprocess_exec` 비동기 subprocess
- stdout/stderr 모두 캡처 → INFO 레벨 로깅
- 반환: `(returncode, stderr_text)`

### 변환 도구 의존성 (외부 프로젝트)
- **`dev_marker` 프로젝트** 필요: `secrets.toml`의 `[doc_converter].dev_marker_dir` 경로에 존재해야 함
- `dev_marker/.venv/Scripts/python.exe` 로 실행
- PDF: `dev_marker/convert_pdf.py --input-file <file> --output <dir> [--force-ocr]`
- Office: `dev_marker/convert_office.py --input-file <file> --output <dir>`

---

## 7. Django 설정 변경

### `settings.py` 추가 항목 (섹션 13)
```python
_DOC_CONVERTER_CONFIG = SECRETS.get('doc_converter', {})
DOC_DATA_DIR = str(_DOC_CONVERTER_CONFIG.get('doc_data_dir', Path.home() / 'doc_data'))
DOC_CONVERTER_INTERNAL_SECRET = str(_DOC_CONVERTER_CONFIG.get('internal_secret', ''))
```

### `INSTALLED_APPS` 추가
```python
'apps.doc_uploader',  # 문서 변환 업로더 앱
```

### `config/urls.py` 추가
```python
path('api/doc-uploader/', include('apps.doc_uploader.urls')),
```

---

## 8. FastAPI 변경 (`main.py`)

### 라우터 등록
```python
app.include_router(doc_upload_router, prefix="/doc-converter", tags=["Doc Uploader"])
```

### lifespan 시작 시 startup-reset 호출
FastAPI 시작 시 `working` 상태 좀비 job 정리:
```python
reset_resp = await app.state.http_client.post(
    "http://127.0.0.1:8000/api/doc-uploader/jobs/startup-reset/",
    headers={"X-Internal-Secret": _internal_secret},
    timeout=5.0,
)
```
Django가 아직 준비 안 됐을 수 있으므로 실패 시 `warning` 로그만 기록하고 무시.

---

## 9. 프론트엔드

### 라우팅 (`App.jsx`)
```jsx
<Route path="/doc-uploader" element={<PrivateRoute><DocUploaderPage /></PrivateRoute>} />
```

### 앱 선택 화면 (`AppSelectorPage.jsx`)
```js
{
  id: 'doc-uploader',
  name: 'Doc Uploader',
  description: 'PDF/Office 문서를 Markdown으로 변환하여 RAG 검색에 활용합니다',
  icon: FolderUp,  // lucide-react
  color: 'from-violet-500 to-purple-600',
  path: '/doc-uploader'
}
```

### 페이지 레이아웃 (`DocUploaderPage.jsx`)
```
[상단 헤더: ← Doc Uploader]
[왼쪽 사이드바: CategoryManager (w-56)]  [오른쪽: JobQueueTable + FileUploadArea]
```
- `refreshTrigger` state: 업로드 완료 시 JobQueueTable + CategoryManager 동시 갱신

### `CategoryManager.jsx`
- Django `GET /api/doc-uploader/categories/` 로 초기 로드
- `refreshTrigger` 변경 시 재로드
- **생성**: `FolderPlus` 버튼 → inline 입력 → `POST categories/`
- **이름 변경**: hover 시 `Pencil` 아이콘 표시 → inline 입력 → `PATCH categories/<name>/`
- **삭제 불가** (의도적 — 추후 관리자 메뉴로 구현 예정)
- 선택된 카테고리 하이라이트, 클릭 토글

### `JobQueueTable.jsx`
- 폴링 방식으로 `GET /api/doc-uploader/jobs/` 주기적 조회
- `waiting`/`working` job이 존재하면 짧은 인터벌, 없으면 긴 인터벌 (리소스 절약)
- 컬럼: `#`, 파일명, 카테고리, 날짜, 상태 배지
- 상태 배지 색상: waiting(노랑), working(파랑+spinner), completed(초록), failed(빨강)
- `refreshTrigger` 변경 시 즉시 재조회

### `FileUploadArea.jsx`
- 드래그&드롭 + 클릭 파일 선택 지원
- 카테고리 미선택 시 업로드 비활성화 + 안내 메시지
- FastAPI `POST /doc-converter/upload` 호출 (FormData, multipart)
- 업로드 중 진행 표시, 완료/실패 인라인 메시지
- 지원 확장자 표시

### API 클라이언트

**`djangoApi.js` — `docUploaderApi`**
```js
docUploaderApi.listJobs()
docUploaderApi.listCategories()
docUploaderApi.createCategory(name)
docUploaderApi.renameCategory(oldName, newName)
```

**`fastapiApi.js` — `docConverterApi`**
```js
docConverterApi.uploadFile(file, category)
// POST /doc-converter/upload, multipart/form-data, timeout 30s
```

---

## 10. `secrets.toml` 필수 설정

```toml
[doc_converter]
# dev_marker 프로젝트 루트 (convert_pdf.py / convert_office.py 위치)
dev_marker_dir = "C:/Users/BgKing/mycode/dev_marker"

# 변환 결과 저장 루트 (= RAG doc_data 경로)
doc_data_dir = "C:/Users/BgKing/doc_data"

# FastAPI ↔ Django 내부 통신 시크릿 (임의의 강한 문자열)
internal_secret = "your-strong-internal-secret"

# OCR 강제 적용 여부 (PDF 이미지 문서 등)
force_ocr = false
```

---

## 11. 미완성 / 추후 구현 항목

| 항목 | 비고 |
|------|------|
| 카테고리 삭제 | 관리자 메뉴로 구현 예정 |
| 업로드한 사용자 ID 표시 | 현재 job에 user FK 없음 |
| 실시간 WebSocket 푸시 | 현재 폴링 방식 |
| 변환 진행률 표시 | subprocess 진행상태 스트리밍 미구현 |
| 멀티파일 동시 업로드 UI | 현재 단일 파일 업로드 |
| dev_marker 통합 패키지화 | 현재 별도 프로젝트 subprocess 방식 |
