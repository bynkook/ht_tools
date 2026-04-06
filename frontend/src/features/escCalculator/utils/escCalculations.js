/**
 * ESC 물가변동 비용 산출 핵심 계산 함수
 *
 * 공식: 산정금액[D] = 물가변동대상금액[A] × 잔여기성률[B] × 물가변동률[C]
 *       C = C1 + C2
 *       C1 = (D1 - 1) × (A1 / A)
 *       C2 = (D2 - 1) × (A2 / A)
 *       D1 = 해당월 PPI / 기준시점 PPI
 *       D2 = 해당반기 노임단가 / 기준시점 반기 노임단가
 *
 * 검증 기준: 기준시점 2021.07, 조정시점 2022.01, C=5.242%, B=20.475%
 */

// ---------------------------------------------------------------------------
// 월 목록 생성
// ---------------------------------------------------------------------------

/**
 * 시작월~종료월 사이의 YYYYMM 배열 생성 (시작월 포함)
 * 기준시점부터 종료시점까지
 */
export function generateMonths(startYYYYMM, endYYYYMM) {
  const months = [];
  let year = parseInt(startYYYYMM.slice(0, 4));
  let month = parseInt(startYYYYMM.slice(4, 6)); // 기준시점 포함

  const endYear = parseInt(endYYYYMM.slice(0, 4));
  const endMonth = parseInt(endYYYYMM.slice(4, 6));

  while (year < endYear || (year === endYear && month <= endMonth)) {
    months.push(`${year}${String(month).padStart(2, '0')}`);
    month++;
    if (month > 12) { month = 1; year++; }
  }
  return months;
}

// ---------------------------------------------------------------------------
// 기준값 조회
// ---------------------------------------------------------------------------

/**
 * 기준시점의 PPI(공산품) 값 반환
 * @param {Array} ppiData - [{시점:'YYYYMM', 공산품:float}]
 * @param {string} baseMonth - 'YYYYMM'
 */
export function getBasePpi(ppiData, baseMonth) {
  const item = ppiData.find(d => d['시점'] === baseMonth);
  if (!item) throw new Error(`기준시점(${baseMonth}) PPI 데이터가 없습니다.`);
  return item['공산품'];
}

/**
 * 기준시점의 반기 노임단가 값 반환.
 * 기준시점(월) → 해당 반기(YYYYHH) 매핑: 1~6월=XX01, 7~12월=XX02
 * @param {Array} wageData - [{시점:'YYYYHH', 값:int}]
 * @param {string} baseMonth - 'YYYYMM'
 */
export function getBaseWage(wageData, baseMonth) {
  const halfKey = monthToHalfKey(baseMonth);
  const item = wageData.find(d => d['시점'] === halfKey);
  if (!item) throw new Error(`기준시점(${baseMonth} → ${halfKey}) 노임단가 데이터가 없습니다.`);
  return item['값'];
}

// ---------------------------------------------------------------------------
// D1, D2 시리즈 계산
// ---------------------------------------------------------------------------

/**
 * 월별 D1 배열 계산 (기준시점 PPI 대비 비율)
 * @returns {Array} [{month:'YYYYMM', ppi:float, D1:float}, ...]  D1 = PPI_month / PPI_base
 */
export function calcD1Series(ppiData, basePpi, months) {
  return months.map(month => {
    const item = ppiData.find(d => d['시점'] === month);
    const ppi = item ? item['공산품'] : null;
    const D1 = ppi != null ? ppi / basePpi : null;
    return { month, ppi, D1 };
  });
}

/**
 * 월별 D2 배열 계산 (기준시점 노임단가 대비 비율, 반기 단위)
 * @returns {Array} [{month:'YYYYMM', halfKey, wage, D2:float}, ...]
 */
export function calcD2Series(wageData, baseWage, months) {
  return months.map(month => {
    const halfKey = monthToHalfKey(month);
    const item = wageData.find(d => d['시점'] === halfKey);
    const wage = item ? item['값'] : null;
    const D2 = wage != null ? wage / baseWage : null;
    return { month, halfKey, wage, D2 };
  });
}

// ---------------------------------------------------------------------------
// C1, C2, C 계산
// ---------------------------------------------------------------------------

/**
 * Cx = (Dx - 1) × (Ax / A)
 * @param {number|null} Dx - D1 or D2 비율 (1.00644 형태)
 * @param {number} Ax - A1 or A2
 * @param {number} A  - A1 + A2
 * @returns {number|null}
 */
export function calcCx(Dx, Ax, A) {
  if (Dx == null || A === 0) return null;
  return (Dx - 1) * (Ax / A);
}

// ---------------------------------------------------------------------------
// 잔여기성률[B] 계산
// ---------------------------------------------------------------------------

/**
 * 월별 기성금액 배열로 누계기성률, 잔여기성률 계산
 * @param {Array} monthlyProgress - [{month:'YYYYMM', amount:number}, ...]
 * @param {number} totalExpected - 정산예상금액
 * @param {string[]} months - 전체 월 배열
 * @returns {Array} [{month, amount, rate월별, rate누계, remaining}, ...]
 */
export function calcProgressSeries(monthlyProgress, totalExpected, months) {
  let cumulative = 0;
  return months.map(month => {
    const found = monthlyProgress.find(p => p.month === month);
    const amount = found ? (found.amount || 0) : 0;
    const rateMonthly = totalExpected > 0 ? amount / totalExpected : 0;
    cumulative += rateMonthly;
    const remaining = Math.max(0, 1 - cumulative);
    return { month, amount, rateMonthly, rateCumulative: cumulative, remaining };
  });
}

/**
 * 조정시점에서의 잔여기성률[B]
 * 조정시점 월의 remaining 값 사용
 */
export function getRemainingAtAdjustment(progressSeries, adjustmentMonth) {
  const item = progressSeries.find(p => p.month === adjustmentMonth);
  return item ? item.remaining : null;
}

// ---------------------------------------------------------------------------
// 조정시점 탐색
// ---------------------------------------------------------------------------

/**
 * 물가변동률[C] >= 3% 최초 월 탐색
 * @param {Array} cSeries - [{month, C:number|null}, ...]
 * @returns {string|null} 'YYYYMM' or null
 */
export function findAdjustmentPoint(cSeries) {
  const found = cSeries.find(item => item.C != null && item.C >= 0.03);
  return found ? found.month : null;
}

// ---------------------------------------------------------------------------
// 메인 계산 진입점
// ---------------------------------------------------------------------------

/**
 * ESC 전체 계산
 * @param {Object} inputs - 사용자 입력
 * @param {Array}  ppiData  - [{시점:'YYYYMM', 공산품:float}]
 * @param {Array}  wageData - [{시점:'YYYYHH', 값:int}]
 * @returns {Object} 전체 계산 결과
 */
export function calculateEsc(inputs, ppiData, wageData) {
  const {
    baseMonth,        // 기준시점 'YYYYMM'
    endMonth,         // 종료시점 'YYYYMM'
    materialCost,     // 자재비 A1
    laborCost,        // 노무비 A2
    expectedAmount,   // 정산예상금액
    advanceRate,      // 선금율 (0~1)
    monthlyProgress,  // [{month, amount}]
  } = inputs;

  const A1 = Number(materialCost) || 0;
  const A2 = Number(laborCost) || 0;
  const A = A1 + A2;

  const months = generateMonths(baseMonth, endMonth);

  // 기준값
  const basePpi = getBasePpi(ppiData, baseMonth);
  const baseWage = getBaseWage(wageData, baseMonth);

  // D1, D2 시리즈
  const d1Series = calcD1Series(ppiData, basePpi, months);
  const d2Series = calcD2Series(wageData, baseWage, months);

  // C1, C2, C 시리즈
  const cSeries = months.map((month, i) => {
    const C1 = calcCx(d1Series[i].D1, A1, A);
    const C2 = calcCx(d2Series[i].D2, A2, A);
    const C = C1 != null && C2 != null ? C1 + C2 : null;
    return { month, C1, C2, C };
  });

  // 조정시점
  const adjustmentMonth = findAdjustmentPoint(cSeries);

  // 기성률 계산
  const progressSeries = calcProgressSeries(monthlyProgress || [], Number(expectedAmount) || 0, months);

  // 잔여기성률 B (조정시점 기준)
  const B = adjustmentMonth ? getRemainingAtAdjustment(progressSeries, adjustmentMonth) : null;

  // 조정시점 C 값
  const adjustmentC = adjustmentMonth
    ? cSeries.find(c => c.month === adjustmentMonth)?.C ?? null
    : null;

  // 산정금액, 공제금액, 집행금액
  const calcAmount = A != null && B != null && adjustmentC != null
    ? Math.round(A * B * adjustmentC)
    : null;
  const deductAmount = calcAmount != null ? Math.round(calcAmount * (Number(advanceRate) || 0)) : null;
  const executionAmount = calcAmount != null && deductAmount != null ? calcAmount - deductAmount : null;

  const otherCostVal = Number(inputs.otherCost) || 0;
  const expectedAmountVal = Number(expectedAmount) || 0;

  // PpiDataSheet용: month, ppi, D1, C1 병합
  const ppiSeries = d1Series.map((d, i) => ({
    ...d,
    C1: cSeries[i].C1,
  }));

  // WageDataSheet용: month, period(반기), wage, D2, C2 병합
  const wageSeries = d2Series.map((d, i) => ({
    month: d.month,
    period: d.halfKey,
    wage: d.wage,
    D2: d.D2,
    C2: cSeries[i].C2,
  }));

  return {
    months,
    baseMonth,
    endMonth,
    adjustmentMonth,
    A, A1, A2,
    otherCost: otherCostVal,
    expectedAmount: expectedAmountVal,
    advanceRate: Number(advanceRate) || 0,
    basePpi,
    baseWage,
    d1Series,
    d2Series,
    cSeries,
    ppiSeries,
    wageSeries,
    progressSeries,
    B,
    adjustmentC,
    calcAmount,
    deductAmount,
    executionAmount,
  };
}

// ---------------------------------------------------------------------------
// 유틸리티
// ---------------------------------------------------------------------------

/**
 * YYYYMM → 반기 키 변환
 * 표준 반기 기준:
 *   1~6월  → YYYY01
 *   7~12월 → YYYY02
 */
export function monthToHalfKey(yyyymm) {
  const year = yyyymm.slice(0, 4);
  const month = parseInt(yyyymm.slice(4, 6));
  const half = month <= 6 ? '01' : '02';
  return `${year}${half}`;
}

/** 숫자를 천단위 콤마 포맷 */
export function formatNumber(n) {
  if (n == null || isNaN(n)) return '-';
  return Math.round(n).toLocaleString('ko-KR');
}

/** 비율을 퍼센트 문자열로 (소수점 3자리) */
export function formatPct(r) {
  if (r == null || isNaN(r)) return '-';
  return (r * 100).toFixed(3) + '%';
}

/** YYYYMM → 'YYYY.MM월' */
export function formatYM(yyyymm) {
  if (!yyyymm || yyyymm.length < 6) return yyyymm || '';
  return `${yyyymm.slice(0, 4)}.${yyyymm.slice(4, 6)}월`;
}
