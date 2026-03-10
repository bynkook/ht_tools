# Image Inspector CAD PDF Preprocessing

## 개요

이 문서는 Image Inspector의 CAD PDF 전처리 구현을 상세히 설명한다. 대상 범위는 PDF 기반 도면 비교에서 사용하는 해치 투명화와 선두께 변경 로직이며, 일반 사용자 기능 소개는 [FEATURE_IMAGE_INSPECTOR.md](FEATURE_IMAGE_INSPECTOR.md)에서 유지한다.

현재 구현 목표는 다음 3가지를 동시에 만족하는 것이다.

- 해치만 최대한 정확하게 숨긴다.
- 해치 숨기기와 선두께 변경을 독립적으로 제어한다.
- 텍스트와 일반 선 요소를 가능한 한 보존한다.

## 요청 경로

CAD PDF 전처리 옵션은 프론트엔드에서 시작해 FastAPI와 PDF stream 편집 코드까지 그대로 전달된다.

1. 프론트엔드 상태
   - `settings.cadLineWidthEnabled`
   - `settings.cadLineWidth`
   - `settings.hideHatchTransparency`
2. API 요청 생성
   - `frontend/src/api/fastapiApi.js`
   - `cad_mode`
   - `cad_line_width`
   - `apply_line_width`
   - `hide_hatch_transparency`
3. FastAPI 수신
   - `ai_gateway/routers/image.py`
4. 이미지 로드/비교 orchestration
   - `ai_gateway/services/image_processor.py`
5. PDF 렌더 직전 전처리
   - `ai_gateway/services/pdf2img.py`

핵심 규칙:

- 해치만 숨길 때는 반드시 `apply_line_width=false` 여야 한다.
- `cad_mode=true` 라고 해서 선두께 변경이 자동으로 켜지면 안 된다.

## 처리 파이프라인

PDF는 다음 순서로 처리된다.

1. PyPDF2 기반 단일 페이지 재기록
2. pikepdf로 content stream 편집
3. fitz로 최종 렌더링

stream 편집의 기본 원칙은 다음과 같다.

- 페이지 `/Contents`를 flatten해서 재조립하지 않는다.
- 원본 stream 위치를 유지한 채 필요한 graphics 연산만 바꾼다.
- BT/ET 텍스트 객체는 해치 검출 시에만 동일 길이 공백으로 마스킹한다.
- 실제 출력 바이트에서는 텍스트 객체를 재배치하지 않는다.

## 해치 검출 전략

현재 해치 검출은 단일 엔트리 함수 `_find_hatch_fill_ranges()` 안에서 수행된다. 구현 형태는 전역 2-pass 파이프라인이 아니라, fill 연산자를 한 번 순회하면서 각 fill을 `rect 계열` 또는 `polygon 계열`로 분기 판정하는 single-pass branching 구조다.

즉, 현재 동작은 다음과 같다.

1. 전체 fill 연산자 목록을 수집한다.
2. 각 fill마다 텍스트 근접 여부를 먼저 걸러낸다.
3. rect 문맥이면 large clip-path blob 규칙을 적용한다.
4. polygon 문맥이면 small polygon 규칙을 적용한다.

현재는 "큰 blob 전체를 먼저 탐색한 뒤 남은 fill에 대해 polygon 탐색"을 수행하는 2단계 파이프라인은 아니다. 대신 blob과 polygon의 튜닝 상수와 상태/문맥 lookback은 분리되어 있어, 한 계열의 튜닝이 다른 계열에 번지는 범위를 줄인다.

### 튜닝 상수 분리 원칙

현재 구현은 상수를 아래 두 그룹으로 분리한다.

- polygon 전용
   - `_HATCH_POLYGON_MAX_DIM`
   - `_HATCH_POLYGON_MIN_LINE_OPS`
   - `_HATCH_POLYGON_LOOKBACK_BYTES`
   - `_HATCH_POLYGON_STATE_LOOKBACK_BYTES`
- blob / rect 전용
   - `_HATCH_RECT_MAX_DIM`
   - `_HATCH_RECT_LOOKBACK_BYTES`
   - `_HATCH_BLOB_MIN_DIM`
   - `_HATCH_BLOB_STATE_LOOKBACK_BYTES`
   - `_HATCH_BLOB_RECENT_PATH_LOOKBACK_BYTES`
   - `_HATCH_BLOB_PATH_LOOKBACK_BYTES`

이 구조의 목적은 다음과 같다.

- small triangle hatch 조정 시 big blob 검출 성능을 불필요하게 흔들지 않는다.
- big blob 탐색 범위를 넓힐 때 polygon 탐색 조건까지 같이 느슨해지지 않게 한다.
- 향후 필요 시 blob-first 2단계 파이프라인으로 확장하더라도 현재 상수 체계를 그대로 재사용할 수 있다.

### 1. small polygon hatch

주로 반복적인 소형 다각형 해치 샘플에서 보이는 패턴이다.

특징:

- 매우 작은 다각형이 연속적으로 반복된다.
- `m`, `l`, `f*` 조합이 짧은 간격으로 계속 이어진다.
- `gs`, `cm`, non-stroking color 같은 graphics state가 앞에 잡힌다.

검출 포인트:

- token-aware operator regex를 사용한다.
- polygon 전용 shape/state lookback을 분리해 사용한다.
- 긴 hatch run에서 앞부분의 state를 뒤 연산까지 재사용할 수 있게 한다.
- 작은 polygon fill chain이 반복되면 hatch 신호로 본다.

### 2. large clip-path blob hatch

주로 큰 면적의 clip-path blob 해치 샘플에서 보이는 패턴이다.

특징:

- 작은 삼각형 hatch가 아니라 큰 면적의 blob fill로 나타난다.
- 큰 rect clip과 폐합 path가 붙어 있다.
- `re W n` 또는 `re W* n` 뒤에 large closed path fill이 이어진다.
- blob이 1개가 아니라 여러 개 존재할 수 있다.

검출 포인트:

- 큰 rect라고 무조건 제외하지 않는다.
- blob / rect 전용 state/path lookback을 따로 사용한다.
- 최근 path 문맥에서 단서가 부족하면 더 긴 deep path lookback으로 재탐색한다.
- 아래 조건을 만족하면 large blob hatch로 인정한다.
  - rect 크기가 `_HATCH_BLOB_MIN_DIM` 이상
  - clip state 존재
  - 최근 path 구간에 `m`, `l`, `h`가 충분히 존재
  - `re W n` 또는 `re W* n` sequence가 실제로 존재

이 규칙은 fill 단위로 적용되므로 여러 개의 large blob이 있어도 각각 independent하게 검출된다.

추가로, 원본 대형 PDF처럼 path 힌트가 fill 직전 짧은 구간에만 모여 있지 않은 경우를 위해 blob 탐색 범위를 확대했다. 현재는 다음 두 레벨을 사용한다.

- recent path lookback: 비교적 가까운 path/clip 단서를 확인
- deep path lookback: recent 구간에서 단서가 부족할 때 더 긴 구간을 다시 스캔

이 확장은 blob 계열에만 적용되며, small polygon 탐색 경로는 유지된다.

## 투명도 주입 방식

검출된 fill 범위에는 다음과 같은 방식으로 ExtGState를 주입한다.

```text
q
/FxHatchHide gs
... original fill operator ...
Q
```

의미:

- `q` / `Q` 로 graphics state를 지역화한다.
- `/FxHatchHide` 는 non-stroking/stroking alpha를 0.0으로 둔 ExtGState다.
- 원본 연산자를 삭제하지 않고 앞뒤에 감싸서 적용한다.

## 선두께 변경

선두께 변경은 별도 로직이다.

- `apply_line_width=true` 일 때만 수행한다.
- text object 밖의 `w` 연산자만 교체한다.
- hatch hide와 별개이므로 둘 중 하나만 사용할 수 있다.

이 분리가 중요한 이유:

- 과거에는 해치 숨기기만 켠 요청에서도 기본값 때문에 선두께가 같이 바뀌어 line blur처럼 보이는 문제가 있었다.
- 현재는 `apply_line_width` 를 명시적으로 전달해 이 문제를 방지한다.

## 텍스트 보존 전략

텍스트 보존은 두 층으로 확인한다.

1. content stream 수준
   - BT/ET text chunk를 재조립하지 않는다.
   - text chunk equality를 회귀 테스트로 본다.
2. 렌더/추출 수준
   - fitz `get_text("text")` 결과가 동일한지 확인한다.

주의:

- word bounding box darkness 비교는 hatch가 글자 주변 배경과 겹칠 때 false alarm을 낼 수 있다.
- large hatch blob 제거 후에는 이 지표가 텍스트 손실이 아닌 배경 변화도 함께 반영하므로 주된 텍스트 보존 지표로 쓰지 않는다.

## 현재 회귀 테스트

테스트 파일:

- `test/pdf_solidhatch_1.pdf`
- `test/pdf_solidhatch_1_small.pdf`
- `test/pdf_solidhatch_2_small.pdf`
- `test/pdf_test_1.pdf`

주요 검증 항목:

- text chunk 보존
- fitz 렌더 가능 여부
- 대형 blob 샘플 extracted text equality
- 축소 blob 샘플 extracted text equality
- blob/polygon 계열 샘플 hatch darkness 감소
- 축소 blob 샘플 multiple large blob 검출 수
- 대형 blob 샘플 large blob 검출 수

현재 기대 동작:

- 대형 blob 샘플: large clip-path blob hatch가 여러 개 검출되고, darkness ratio가 실제로 감소해야 한다.
- 축소 blob 샘플: large clip-path blob hatch가 여러 개 검출되고 큰 면적이 사라져야 한다.
- 반복 polygon 샘플: small polygon hatch가 크게 감소해야 한다.

## 알려진 한계

- PDF 제작 도구별로 hatch 표현 방식이 달라 완전한 일반화는 어렵다.
- 현재 검출은 single-pass branching 구조이며, 작은 polygon chain과 large clip-path blob에 최적화되어 있다.
- blob-first 후 polygon-second 형태의 전역 2단계 파이프라인은 아직 구현하지 않았다.
- file2 류에서 사용자가 시각적으로 글자 손실을 관찰하면, 해당 샘플을 기준으로 text-near-path 예외 규칙을 추가 보정해야 한다.

## 관련 파일

- `ai_gateway/services/pdf2img.py`
- `ai_gateway/services/image_processor.py`
- `ai_gateway/routers/image.py`
- `frontend/src/api/fastapiApi.js`
- `frontend/src/features/imageCompare/ImageComparePage.jsx`
- `test/test_pdf_cad_text_preservation.py`

Last updated: 2026-03-10 (single-pass branching 구조, polygon/blob 상수 분리, big file1 blob 탐색 범위 확장 반영)