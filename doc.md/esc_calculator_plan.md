# ESC 물가변동 비용 산출 앱 개발계획서

## 개요
건설공사 계약 물가변동(ESC) 정산 보정금액 산출 앱을 ht_tools 플랫폼에 추가 구현한다.  
기존 채팅/AI 기능과 무관한 독립 앱이며, 기존 앱들과 동일한 아키텍처(React + Django + SQLite)를 따른다.

**참고 자료**: `test/kosis_test/산출서메인창.png`, `test/kosis_test/Instruction창.png`, `test/kosis_test/fetch_kosis_data.py`

---

## 핵심 공식 및 산출 로직

```
산정금액[D] = 물가변동대상금액[A] × 잔여기성률[B] × 물가변동률[C]
집행금액    = 산정금액 - 공제금액
공제금액    = 산정금액 × 선금율  (선금 지급 시)
```

| 기호 | 정의 |
|------|------|
| A = A1 + A2 | 자재비[A1] + 노무비[A2] |
| B | (정산예상금액 - 조정시점까지의 누적기성금액) / 정산예상금액 |
| C = C1 + C2 | 자재비 물가변동률[C1] + 노무비 물가변동률[C2] |
| C1 | (D1 − 1) × (A1 / A) |
| C2 | (D2 − 1) × (A2 / A) |
| D1 | 해당월 생산자물가지수(공산품) ÷ 기준시점 생산자물가지수 |
| D2 | 해당반기 시중노임단가(일반공사직종) ÷ 기준시점 반기 노임단가 |
| 조정시점 | C ≥ 3% 가 최초로 성립하는 월 |

> **근거서류**: 생산자물가지수(공산품), 시중노임단가, 기성현황  
> **생산자물가지수**: 한국은행 발표, 품목은 '공산품' 기준  
> **시중노임단가**: 대한건설협회 연 2회 발표, 직종은 '일반공사직종' 기준

---

## 설계 결정사항 (확정)

| 항목 | 결정 |
|------|------|
| KOSIS API Key | `secrets.toml` 서버 공용 키 1개 (`[kosis].api_key`) |
| 계산 로직 위치 | **프론트엔드(JS)** — 백엔드는 KOSIS 데이터 프록시만 담당 |
| 스프레드시트 컴포넌트 | **@fortune-sheet/react** (GitHub: ruilisi/fortune-sheet) |
| FortuneSheet 인스턴스 | 3개 독립 테이블, React state로 데이터 공유 |
| 데이터 저장 | Django DB (SQLite + JSONField) — 기존 앱들과 동일 |
| KOSIS 데이터 캐싱 | Django DB에 기간별 캐싱 |
| URL 경로 | `/esc-calculator` |

---

## 아키텍처

### Backend (Django)

```
django_server/apps/esc_calculator/
├── __init__.py
├── apps.py
├── models.py          # EscProject, KosisCache
├── serializers.py
├── views.py           # API views
├── urls.py
└── services/
    └── kosis_service.py  # KOSIS API 호출 + DB 캐싱 로직
```

**Models**

```python
class EscProject(models.Model):
    user        = ForeignKey(User, on_delete=CASCADE)
    name        = CharField(max_length=200)
    input_data  = JSONField()   # 사용자 입력 전체 (아래 입력 항목 참조)
    created_at  = DateTimeField(auto_now_add=True)
    updated_at  = DateTimeField(auto_now=True)

class KosisCache(models.Model):
    data_type    = CharField(max_length=10)  # 'ppi' | 'wage'
    period_start = CharField(max_length=6)   # 'YYYYMM'
    period_end   = CharField(max_length=6)   # 'YYYYMM'
    payload      = JSONField()               # API 응답 원본 (정규화된 형태)
    fetched_at   = DateTimeField(auto_now=True)
```

**API Endpoints**

| Method | URL | 설명 |
|--------|-----|------|
| GET | `/api/esc/projects/` | 내 프로젝트 목록 |
| POST | `/api/esc/projects/` | 프로젝트 저장 |
| PUT | `/api/esc/projects/{id}/` | 프로젝트 수정 |
| DELETE | `/api/esc/projects/{id}/` | 프로젝트 삭제 |
| GET | `/api/esc/kosis/ppi/?start=YYYYMM&end=YYYYMM` | 생산자물가지수(공산품) 월별 |
| GET | `/api/esc/kosis/wage/?start=YYYYMM&end=YYYYMM` | 시중노임단가(일반공사직종) 반기 |

**KOSIS 캐싱 정책**
- 동일 기간 데이터가 DB에 존재하면 DB에서 반환 (KOSIS API 호출 생략)
- 요청 기간이 캐시 범위를 벗어나면 KOSIS API 재호출 후 캐시 갱신
- `kosis_service.py`는 `test/kosis_test/fetch_kosis_data.py` 로직을 서비스 클래스로 이식

---

### Frontend (React)

```
frontend/src/features/escCalculator/
├── EscCalculatorPage.jsx         # 메인 페이지 (Streamlit-like 세로 스크롤)
├── components/
│   ├── TopBar.jsx                 # 프로젝트 드롭다운 + Load/Save/Recalc/New 버튼
│   ├── InputForm.jsx              # 사용자 입력 영역 (노란색 강조)
│   ├── MainCalculationSheet.jsx   # FortuneSheet ① - 메인 계산 테이블
│   ├── PpiDataSheet.jsx           # FortuneSheet ② - 생산자물가지수 테이블
│   ├── WageDataSheet.jsx          # FortuneSheet ③ - 노임단가 테이블
│   └── HelpSection.jsx            # 도움말 (토글 + Markdown 렌더)
├── hooks/
│   └── useEscData.js              # 데이터 패칭 훅 (KOSIS API, 프로젝트 CRUD)
└── utils/
    └── escCalculations.js         # 순수 계산 함수 모음
```

---

## FortuneSheet 설계

### 설치
```bash
npm install @fortune-sheet/react @fortune-sheet/core
```
> FortuneSheet 개발 지침과 표준(ruilisi/fortune-sheet)을 엄격히 따른다.

### 3개의 독립 Sheet 인스턴스

| # | 컴포넌트 | 내용 | 특이사항 |
|---|----------|------|---------|
| 1 | `MainCalculationSheet` | 집행금액 요약 + 잔여기성률[B] 상세 + 물가변동률[C] 종합 | 조정시점 열 파란색 강조 |
| 2 | `PpiDataSheet` | 생산자물가지수(공산품) + D1 변동률 + C1 | 월별, 가로 확장 |
| 3 | `WageDataSheet` | 시중노임단가 + D2 변동률 + C2 | 반기별, 가로 확장 |

- 각 FortuneSheet는 계산 결과를 표시하는 **read-only** 테이블 (직접 편집 불가)
- 노란색 입력 셀은 `InputForm`의 React 입력 필드로 별도 구현
- 계산 완료 후 FortuneSheet `data` prop을 업데이트하여 결과 렌더링
- 월 수에 따라 열 수가 동적으로 변동 (기준시점 ~ 종료시점)
- 페이지는 세로 스크롤, 각 FortuneSheet는 `overflow: hidden` 컨테이너로 감쌈

### 데이터 공유 방식
```
InputForm (사용자 입력)
      ↓  [Recalc 버튼 클릭]
useEscData.js (KOSIS 데이터 패칭)
      ↓
escCalculations.js (순수 JS 계산)
      ↓
shared React state: escResult
      ├──→ MainCalculationSheet (FortuneSheet data prop 업데이트)
      ├──→ PpiDataSheet         (FortuneSheet data prop 업데이트)
      └──→ WageDataSheet        (FortuneSheet data prop 업데이트)
```

---

## 사용자 입력 항목

| 항목 | UI 타입 | 설명 |
|------|---------|------|
| 기준시점 | 년/월 select | 1차 조정: 계약체결일, 2차+: 직전 조정일 |
| 계산 종료시점 | 년/월 select | 조정시점 탐색 종료 월 |
| 산정금액 | 숫자 입력 | |
| 선금율 | % 숫자 | 0이면 공제 없음 |
| 자재비[A1] | 숫자 입력 | 물가변동대상금액 중 자재비 |
| 노무비[A2] | 숫자 입력 | 물가변동대상금액 중 노무비 |
| 물가변동대상외금액 | 숫자 입력 | 경비, 간접비 등 |
| 정산예상금액 | 숫자 입력 | |
| 월별 기성금액 | 숫자 배열 | 기준시점부터 종료시점까지 동적 행 추가/삭제 |

---

## 페이지 레이아웃

```
┌──────────────────────────────────────────────────────────────┐
│  TopBar: [프로젝트 선택 ▼]  [Load] [Save] [Recalc] [New]    │
├──────────────────────────────────────────────────────────────┤
│  InputForm                                                   │
│  - 기준시점 / 종료시점 (년/월)                               │
│  - 산정금액, 선금율, A1(자재비), A2(노무비)                  │
│  - 물가변동대상외금액, 정산예상금액                           │
│  - 월별 기성금액 테이블 (노란색 강조, 동적 행)               │
├──────────────────────────────────────────────────────────────┤
│  MainCalculationSheet  (FortuneSheet ①)                     │
│  ▶ 상단 요약: 집행금액 / 산정금액 / 공제금액 / 기준·조정시점 │
│  ▶ 잔여기성률[B] 산출 상세                                   │
│  ▶ 물가변동률[C] 종합 (C1 + C2)                             │
│     ※ 조정시점 열 파란색 강조, "물가변동률 3% 이상" 표시    │
├──────────────────────────────────────────────────────────────┤
│  PpiDataSheet  (FortuneSheet ②)                             │
│  - 생산자물가지수(공산품) 월별 + D1 변동률 + C1             │
├──────────────────────────────────────────────────────────────┤
│  WageDataSheet  (FortuneSheet ③)                            │
│  - 시중노임단가(일반공사직종) 반기 + D2 변동률 + C2         │
├──────────────────────────────────────────────────────────────┤
│  [▶ 세부기준 도움말]  ← 클릭 시 토글 show/hide              │
│  (Markdown 렌더 — Instruction창.png 내용)                   │
└──────────────────────────────────────────────────────────────┘
```

---

## 계산 함수 설계 (escCalculations.js)

```javascript
/**
 * ESC 전체 계산 진입점
 * @param {Object} inputs   - 사용자 입력 전체
 * @param {Array}  ppiData  - [{시점:'202107', 공산품:111.81}, ...]  (월별)
 * @param {Array}  wageData - [{시점:'202101', 값:219213}, ...]       (반기)
 * @returns {Object} { mainSheet, ppiSheet, wageSheet, 조정시점, 산정금액, 집행금액 }
 */
export function calculateEsc(inputs, ppiData, wageData) { ... }

// 내부 헬퍼 함수
function getBasePpi(ppiData, 기준시점)          // 기준시점 PPI 값 조회
function getBaseWage(wageData, 기준시점)        // 기준시점 반기 노임단가 조회
function calcD1Series(ppiData, basePpi, months) // 월별 D1 배열
function calcD2Series(wageData, baseWage, months) // 월→반기 매핑 D2 배열
function calcC(D, A_part, A_total)             // Cx = (D-1) × (Ax/A)
function findAdjustmentPoint(cSeries)          // C >= 3% 최초 월
function calcRemainingProgress(기성금액Array, 정산예상금액, 조정시점) // B
function buildFortuneSheetData(calcResult)     // FortuneSheet cell array 생성
```

**검증**: `산출서메인창.png` 예제값(기준시점 2021.07, 조정시점 2022.01, C=5.242%, B=20.475%)으로 단위 테스트

---

## 구현 단계 (7 Phases)

### Phase 1 — Django Backend 기반
1. `esc_calculator` Django app 생성
2. `EscProject`, `KosisCache` 모델 + 마이그레이션
3. `settings.py` INSTALLED_APPS 등록, `config/urls.py` `/api/esc/` 등록
4. `secrets.toml`에 `[kosis].api_key` 항목 추가

### Phase 2 — KOSIS 서비스
1. `kosis_service.py` 작성 — `fetch_kosis_data.py` 로직 이식
2. DB 캐싱 로직 구현 (hit/miss 판단, 갱신)
3. DRF serializers + KosisPpiView + KosisWageView

### Phase 3 — 프로젝트 CRUD API
1. `EscProjectSerializer`, `EscProjectViewSet`
2. URL 연결

### Phase 4 — 프론트엔드 기반
1. `npm install @fortune-sheet/react @fortune-sheet/core`
2. `App.jsx` `/esc-calculator` route + lazy import 추가
3. `AppSelectorPage.jsx` ESC 계산기 앱 카드 추가
4. `djangoApi.js` ESC API 함수 추가 (getProjects, saveProject, getKosisPpi, getKosisWage)
5. `EscCalculatorPage.jsx` 페이지 뼈대 + 세로 스크롤 레이아웃

### Phase 5 — 입력 폼
1. `TopBar.jsx` — 프로젝트 드롭다운 + Load/Save/Recalc/New 버튼
2. `InputForm.jsx` — 기간 select, 금액 입력 필드, 월별 기성금액 동적 테이블
3. 노란색 강조 스타일 (Tailwind `bg-yellow-100 border-yellow-400`)
4. `useEscData.js` 훅 — 프로젝트 CRUD + KOSIS 패칭

### Phase 6 — 계산 로직 + FortuneSheet 렌더링
1. `escCalculations.js` 순수 함수 전체 구현
2. 예제값으로 수동 검증
3. `MainCalculationSheet.jsx` — FortuneSheet 셀 데이터 빌더 (조정시점 강조 포함)
4. `PpiDataSheet.jsx`, `WageDataSheet.jsx` — FortuneSheet 셀 데이터 빌더
5. Recalc 버튼 클릭 시 전체 재계산 → 3개 Sheet 동시 업데이트

### Phase 7 — 저장/로드 + 도움말
1. Load 버튼: 선택 프로젝트 → InputForm 복원 + 자동 Recalc
2. Save 버튼: 현재 입력 데이터 → POST/PUT
3. New 버튼: 입력 초기화
4. `HelpSection.jsx` — 클릭 토글, `Instruction창.png` 내용을 Markdown으로 작성
5. `react-markdown` + `remark-gfm` 렌더 (이미 package.json에 존재)

---

## 기존 코드베이스 수정 파일 목록

| 파일 | 변경 내용 |
|------|-----------|
| `frontend/package.json` | `@fortune-sheet/react`, `@fortune-sheet/core` 추가 |
| `frontend/src/App.jsx` | `/esc-calculator` route lazy import 추가 |
| `frontend/src/api/djangoApi.js` | ESC API 함수 추가 |
| `frontend/src/features/appSelector/AppSelectorPage.jsx` | ESC 계산기 앱 카드 추가 |
| `django_server/config/settings.py` | `esc_calculator` app 등록 |
| `django_server/config/urls.py` | `/api/esc/` URL 등록 |
| `secrets.toml` | `[kosis].api_key` 항목 추가 |

---

## 미결 사항 (구현 중 검토)

- FortuneSheet 인스턴스의 동적 높이 계산 방법 (월 수에 따라 열/행 수 변동)
- 조정시점이 없는 경우 (계산 기간 내 C < 3%) 처리 및 사용자 안내
- 조정시점이 여러 개 발생 시 처리 (현재 계획: 최초 1개만)
- KOSIS API 응답 지연 시 로딩 UX (기존 Spinner 컴포넌트 재사용)
- 인쇄/PDF 출력 기능 (현재 계획 외, 추후 검토)

---

*작성일: 2026-04-05*
