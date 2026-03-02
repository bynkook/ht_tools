# Graphic Walker Settings Guide

FabriX Data Explorer에서 사용하는 Graphic Walker 컴포넌트의 전체 설정 항목 가이드입니다.

**문서 버전**: 2026-02-23  
**Graphic Walker 버전**: 0.5.0+  
**소스 파일**: `frontend/src/features/dataExplorer/DataExplorerPage.jsx`

---

## 현재 적용된 설정

```jsx
<GraphicWalker
    key={currentFile}
    fields={fields}
    appearance="light"
    computation={computation}
    storeRef={storeRef}
    chart={chartSpec}
    i18nLang="en-US"
    hideDataSourceConfig={true}
    experimentalFeatures={{ computedField: true }}
/>
```

---

## 전체 설정 항목

### 1. UI 표시/숨김 옵션

| Prop | 타입 | 기본값 | 현재 설정 | 설명 |
|------|------|--------|----------|------|
| `hideDataSourceConfig` | `boolean` | `false` | ✅ `true` | 상단 데이터 import/upload UI 숨김. 서버사이드 computation 사용 시 권장 |
| `hideChartNav` | `boolean` | `false` | ❌ 미설정 | 차트 탭 네비게이션 숨김 (단일 차트만 편집 시 사용) |
| `hideSegmentNav` | `boolean` | `false` | ❌ 미설정 | 세그먼트(Data/Vis/Chat) 탭 네비게이션 숨김 |
| `hideProfiling` | `boolean` | `false` | ❌ 미설정 | 필드 프로파일링(통계 정보) UI 숨김 |

**권장 설정**:
```jsx
hideDataSourceConfig={true}  // 커스텀 사이드바로 데이터 로드 관리
hideSegmentNav={true}        // Data 탭 불필요 (선택적)
```

---

### 2. 실험적 기능 (Experimental Features)

| Prop | 타입 | 기본값 | 현재 설정 | 설명 |
|------|------|--------|----------|------|
| `experimentalFeatures.computedField` | `boolean` | `false` | ✅ `true` | **Computed Field 추가 기능** 활성화. 기존 필드를 조합하여 새 계산 필드 생성 |

**설정 예시**:
```jsx
experimentalFeatures={{ computedField: true }}
```

---

### 3. 언어/국제화 (I18n)

| Prop | 타입 | 기본값 | 현재 설정 | 설명 |
|------|------|--------|----------|------|
| `i18nLang` | `string` | `'en-US'` | ✅ `'en-US'` | UI 언어 설정 |
| `i18nResources` | `object` | `undefined` | ❌ 미설정 | 커스텀 번역 리소스 |

**지원 언어**:
- `'en-US'` / `'en'` - English
- `'zh-CN'` / `'zh'` - 简体中文
- `'ja-JP'` / `'ja'` - 日本語

**커스텀 번역 예시**:
```jsx
i18nResources={{
    'ko-KR': {
        'App.segments.data': '데이터',
        'App.segments.vis': '시각화',
        // ...
    }
}}
```

---

### 4. 테마/외관 (Theme & Appearance)

| Prop | 타입 | 기본값 | 현재 설정 | 설명 |
|------|------|--------|----------|------|
| `appearance` | `'media' \| 'light' \| 'dark'` | `'media'` | ✅ `'light'` | 다크모드 설정 |
| `vizThemeConfig` | `IThemeKey \| GWGlobalConfig` | `'vega'` | ❌ 미설정 | 차트 시각화 테마 |
| `uiTheme` | `IUIThemeConfig` | `undefined` | ❌ 미설정 | 커스텀 UI 색상 설정 |

**appearance 옵션**:
- `'media'` - 시스템 설정 따름
- `'light'` - 항상 라이트 모드
- `'dark'` - 항상 다크 모드

**vizThemeConfig 옵션**:
- `'vega'` - Vega 기본 테마
- `'g2'` - G2 테마
- `'streamlit'` - Streamlit 스타일 테마

**커스텀 UI 테마 예시**:
```jsx
import { getColorConfigFromPalette, getPaletteFromColor } from '@kanaries/graphic-walker';

const uiTheme = getColorConfigFromPalette(getPaletteFromColor('#6366f1'));
// 또는
const uiTheme = {
    light: {
        background: 'white',
        foreground: 'zinc-950',
        primary: 'indigo-600',
        'primary-foreground': 'white',
        muted: 'zinc-100',
        'muted-foreground': 'zinc-500',
        border: 'zinc-200',
        ring: 'indigo-600',
    },
    dark: {
        background: 'zinc-950',
        foreground: 'zinc-50',
        // ...
    }
};
```

---

### 5. 스케일 커스터마이징 (Scales)

| Prop | 타입 | 기본값 | 현재 설정 | 설명 |
|------|------|--------|----------|------|
| `scales` | `IChannelScales` | `undefined` | ❌ 미설정 | 색상/투명도/크기 스케일 커스터마이징 |

**설정 예시**:
```jsx
scales={{
    // 색상 스킴 변경
    color: { scheme: 'tableau10' },
    
    // 다크/라이트 모드별 색상
    color: ({ theme }) => ({
        scheme: theme === 'dark' ? 'darkblue' : 'lightmulti'
    }),
    
    // 커스텀 색상 팔레트
    color: { range: ['#ff0000', '#00ff00', '#0000ff'] },
    
    // 투명도 범위
    opacity: { range: [0, 1], domain: [0, 255] },
    
    // 원 차트 최소 반지름
    radius: { rangeMin: 20 }
}}
```

**사용 가능한 색상 스킴**:
- **Categorical**: `accent`, `category10`, `category20`, `dark2`, `paired`, `pastel1`, `set1`, `tableau10`, `tableau20` 등
- **Sequential**: `blues`, `greens`, `reds`, `viridis`, `magma`, `plasma` 등
- **Diverging**: `blueorange`, `redblue`, `spectral` 등

---

### 6. Computation 설정

| Prop | 타입 | 기본값 | 현재 설정 | 설명 |
|------|------|--------|----------|------|
| `computation` | `IComputationFunction` | `undefined` | ✅ 커스텀 함수 | 서버사이드 computation 함수 |
| `computationTimeout` | `number` | `60000` | ❌ 미설정 (60초) | computation 타임아웃 (ms) |

**현재 구현**:
```jsx
const computation = useCallback(async (query) => {
    const sql = query.sql || query;
    const response = await dataExplorerApi.queryParams(currentFile, sql);
    return response;
}, [currentFile]);
```

**타임아웃 조절 예시**:
```jsx
computationTimeout={120000}  // 대용량 데이터 처리 시 2분으로 설정
```

---

### 7. 상태 관리

| Prop | 타입 | 기본값 | 현재 설정 | 설명 |
|------|------|--------|----------|------|
| `storeRef` | `React.RefObject<IGlobalStore>` | `null` | ✅ `storeRef` | 차트 상태 접근용 ref |
| `keepAlive` | `boolean \| string` | `false` | ❌ 미설정 | 언마운트 시 상태 유지 |
| `chart` | `IChart[]` | `undefined` | ✅ `chartSpec` | 저장된 차트 스펙 로드 |
| `fields` | `IMutField[]` | `[]` | ✅ `fields` | 필드(컬럼) 정의 |

**keepAlive 설정 예시**:
```jsx
// 단일 인스턴스
keepAlive={true}

// 여러 인스턴스 구분
keepAlive="data-explorer-main"
```

**storeRef 사용법**:
```jsx
const storeRef = useRef(null);

// 차트 상태 추출 (저장용)
const allCharts = storeRef.current.exportCode();  // IChart[]
const currentChart = allCharts[storeRef.current.visIndex];

// 현재 차트 인덱스
const currentIndex = storeRef.current.visIndex;
```

---

### 8. 이벤트 콜백

| Prop | 타입 | 기본값 | 현재 설정 | 설명 |
|------|------|--------|----------|------|
| `onMetaChange` | `(fid: string, meta: Partial<IMutField>) => void` | `undefined` | ❌ 미설정 | 필드 메타데이터 변경 콜백 |
| `onError` | `(err: Error) => void` | `undefined` | ❌ 미설정 | 에러 핸들러 콜백 |

**onError 설정 예시**:
```jsx
onError={(err) => {
    console.error('GraphicWalker Error:', err);
    setError(err.message);
}}
```

**onMetaChange 설정 예시**:
```jsx
onMetaChange={(fid, meta) => {
    console.log(`Field ${fid} changed:`, meta);
    // 필드 타입 변경 등 처리
}}
```

---

### 9. 기본 설정

| Prop | 타입 | 기본값 | 현재 설정 | 설명 |
|------|------|--------|----------|------|
| `defaultConfig` | `IDefaultConfig` | `undefined` | ❌ 미설정 | 기본 차트 설정 |
| `defaultRenderer` | `'vega-lite' \| 'observable-plot'` | `'vega-lite'` | ❌ 미설정 | 기본 렌더러 |

**defaultConfig 예시**:
```jsx
defaultConfig={{
    config: {
        defaultAggregated: true,
        geoms: ['auto'],
        limit: 1000,
    },
    layout: {
        showTableSummary: false,
        size: { mode: 'auto', width: 800, height: 600 },
    }
}}
```

---

### 10. 툴바 커스터마이징

| Prop | 타입 | 기본값 | 현재 설정 | 설명 |
|------|------|--------|----------|------|
| `toolbar.extra` | `ToolbarItemProps[]` | `[]` | ❌ 미설정 | 커스텀 툴바 버튼 추가 |
| `toolbar.exclude` | `string[]` | `[]` | ❌ 미설정 | 특정 툴바 버튼 제외 |

**커스텀 버튼 추가 예시**:
```jsx
toolbar={{
    extra: [
        {
            key: 'save-preset',
            label: 'Save Preset',
            icon: SaveIcon,
            onClick: handleSavePreset,
        }
    ],
    exclude: ['export_code']  // 특정 버튼 숨김
}}
```

---

### 11. AI/향상 기능 (외부 API 필요)

| Prop | 타입 | 기본값 | 현재 설정 | 설명 |
|------|------|--------|----------|------|
| `enhanceAPI.features.askviz` | `string \| boolean \| function` | `undefined` | ❌ 미설정 | 자연어 질문 → 차트 생성 |
| `enhanceAPI.features.feedbackAskviz` | `string \| boolean \| function` | `undefined` | ❌ 미설정 | AskViz 피드백 기능 |
| `enhanceAPI.features.vlChat` | `string \| boolean \| function` | `undefined` | ❌ 미설정 | Vega-Lite 채팅 인터페이스 |
| `enhanceAPI.header` | `Record<string, string>` | `undefined` | ❌ 미설정 | API 호출 시 커스텀 헤더 |

**⚠️ 주의**: 이 기능들은 Kanaries의 AI API 또는 자체 AI API 연동이 필요합니다.

**설정 예시**:
```jsx
enhanceAPI={{
    header: { 'Authorization': 'Bearer YOUR_API_KEY' },
    features: {
        askviz: 'https://your-api.com/askviz',
        vlChat: 'https://your-api.com/vlchat',
    }
}}
```

---

### 12. 지도/지리 기능

| Prop | 타입 | 기본값 | 현재 설정 | 설명 |
|------|------|--------|----------|------|
| `geographicData` | `IGeographicData & { key: string }` | `undefined` | ❌ 미설정 | GeoJSON/TopoJSON 데이터 |
| `geoList` | `IGeoDataItem[]` | `undefined` | ❌ 미설정 | 지리 데이터 목록 |

**GeoJSON 설정 예시**:
```jsx
geographicData={{
    type: 'GeoJSON',
    data: geoJsonFeatureCollection,
    key: 'country-map'
}}
```

---

## 권장 설정 (Data Explorer 용)

현재 FabriX Data Explorer에 최적화된 권장 설정입니다:

```jsx
<GraphicWalker
    key={currentFile}
    fields={fields}
    appearance="light"
    computation={computation}
    computationTimeout={120000}
    storeRef={storeRef}
    chart={chartSpec}
    i18nLang="en-US"
    hideDataSourceConfig={true}
    hideSegmentNav={true}
    experimentalFeatures={{ computedField: true }}
    onError={(err) => setError(err.message)}
/>
```

**설정 근거**:
- `hideDataSourceConfig={true}`: 커스텀 사이드바로 데이터 로드 관리
- `hideSegmentNav={true}`: Data 탭 불필요 (서버사이드 computation)
- `computationTimeout={120000}`: 대용량 데이터 처리를 위해 2분으로 확장
- `experimentalFeatures.computedField`: 분석 편의를 위한 계산 필드 지원
- `onError`: 에러 메시지를 앱 UI에 표시

---

## 참고 자료

- [Graphic Walker GitHub](https://github.com/Kanaries/graphic-walker)
- [Graphic Walker Integration Example](https://github.com/Kanaries/graphic-walker-integration-example)
- [gw-dsl-parser (SQL Transpiler)](https://github.com/Kanaries/gw-dsl-parser)
- [Graphic Walker Online Demo](https://graphic-walker.kanaries.net/)

---

Last updated: 2026-02-23
