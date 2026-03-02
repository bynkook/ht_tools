# Feature: Data Explorer (Computation Mode Refactoring)

## 1. 개요
**Data Explorer**는 대용량 데이터셋을 실시간으로 탐색하고 분석할 수 있는 고성능 시각화 도구입니다. 최신 리팩토링을 통해 **Computation Mode**를 도입하여, 수백 MB에서 수 GB에 이르는 대용량 데이터를 브라우저 메모리 부하 없이 처리할 수 있도록 설계되었습니다.

## 2. 주요 기능
- **Computation Mode (서버 사이드 연산)**: 데이터를 브라우저로 가져오지 않고, 모든 집계 연산(Aggregation)을 서버의 DuckDB 엔진에서 처리합니다.
- **Quick Select Dataset**: 서버 로컬 디렉토리(`root/data/data_explorer/`)에 저장된 데이터셋을 즉시 로드합니다.
- **고속 파일 업로드**: 사용자 로컬 파일을 업로드하여 즉시 분석할 수 있습니다 (최대 100MB).
- **스마트한 파일명 관리**: 업로드된 임시 파일 대신 원본 파일명을 UI에 표시하여 가독성을 높였습니다.
- **자동 리소스 관리**: 분석이 끝난 업로드 원본 파일은 즉시 삭제하며, 임시 DB 파일은 24시간 후 자동으로 청소됩니다.

## 3. 기술 구현 (Architecture)

### Backend (Django & DuckDB)
- **핵심 엔진**: **DuckDB** (Persistent Store Mode)
- **API 구성**:
    - `DatasetListView`: 서버 내 가용 데이터셋 목록 제공.
    - `DatasetUploadView`: 100MB 제한의 파일 업로드 처리.
    - `DatasetInitView`: 선택된 파일을 DuckDB로 인덱싱하고 필드 메타데이터(Schema) 반환.
    - `DatasetQueryView`: Graphic Walker가 보낸 JSON 워크플로우를 SQL로 변환하여 DuckDB에서 실행.
- **주요 기술**:
    - **SQL Transpiler**: Graphic Walker의 JSON DSL을 DuckDB SQL로 변환하는 자체 엔진 구현.
    - **Metadata Caching**: 파일의 `mtime`과 `size` 기반 해싱으로 로컬 데이터셋에 대한 즉각적인 세션 복구 지원.
    - **Probabilistic GC**: 1% 확률의 백그라운드 스레드 실행으로 오래된 임시 `.duckdb` 파일 자동 삭제.

### Frontend (React)
- **컴포넌트**: `GraphicWalker` (v0.5.0+)
- **데이터 처리 모드**: `computation` 인터페이스 구현.
    - `getFields`: 세션 초기화 시 서버에서 스키마 수신.
    - `sqlService`: 사용자의 드래그 앤 드롭 액션마다 서버로 쿼리 요청 및 결과 수신.
- **UX 최적화**:
    - 사이드바에서 데이터셋 선택 시 로딩 상태(Loading State) 완벽 제어.
    - 파일 크기 포맷팅 및 긴 파일명 축약(Ellipsis) 처리.

## 4. 파일 구조

```text
django_server/apps/data_explorer/
├── utils.py          # DuckDBEngine (쿼리 실행 및 캐시 관리)
├── views.py          # API 엔드포인트 (Init, Query, Upload, List)
└── urls.py           # API 라우팅

frontend/src/features/dataExplorer/
├── components/
│   └── DataExplorerSidebar.jsx  # 데이터 소스 관리 사이드바
└── DataExplorerPage.jsx         # Computation Mode 통합 메인 뷰
```

## 5. 보안 및 성능 최적화
1. **Path Traversal 방지**: 파일 접근 시 경로 정규화 및 상위 디렉토리 접근 차단 로직 적용.
2. **Zero-Copy 데이터 전송**: 집계된 결과(결과 행)만 전송하므로 네트워크 대역폭 및 브라우저 메모리 소모 최소화.
3. **리소스 격리**: 각 유저의 요청은 독립적인 DuckDB 세션에서 처리되어 상호 간섭 방지.
4. **자동 클린업**: `uploaded_` 접두사가 붙은 원본 파일은 DuckDB 로딩 직후 즉시 삭제 (`DatasetInitView`).

## 6. 사용 방법
1. **서버 데이터셋**: `Quick Select Dataset` 목록에서 원하는 파일을 클릭하여 즉시 분석 시작.
2. **개인 파일**: `Upload File` 버튼을 통해 CSV/Parquet 파일을 업로드 (100MB 이하).
3. **분석**: 필드를 행(Row)이나 열(Column)로 드래그하여 실시간 집계 차트 생성.
4. **초기화**: 사이드바의 홈 버튼을 통해 언제든지 초기 화면으로 복귀 가능.