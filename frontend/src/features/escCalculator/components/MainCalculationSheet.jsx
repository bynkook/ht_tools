import React, { useRef, useEffect } from 'react';
import { Workbook } from '@fortune-sheet/react';
import '@fortune-sheet/react/dist/index.css';
import { formatNumber, formatPct, formatYM } from '../utils/escCalculations';

/**
 * FortuneSheet 셀 데이터 빌더 — 메인 계산 테이블 (①)
 * 구성:
 *   A. 상단 요약 블록 (집행금액/산정금액/공제금액/기준시점/조정시점/A/B/C/D)
 *   B. 잔여기성률[B] 산출 상세 (월별)
 *   C. 물가변동률[C] 종합 (C1+C2+C, 월별)
 */

const CELL_STYLE = {
  header: { bg: '#E8E8E8', bold: true, ht: 0, vt: 0 },
  yellow: { bg: '#FFFF99', ht: 0, vt: 0 },
  blue:   { bg: '#BDD7EE', bold: true, ht: 0, vt: 0 },
  normal: { ht: 0, vt: 0 },
  label:  { bg: '#F2F2F2', ht: 0, vt: 0 },
};

function cell(r, c, v, style = {}) {
  return { r, c, v: { v, m: v == null ? '' : String(v), ...style, ct: { fa: '@', t: 'inlineStr' } } };
}
function numCell(r, c, v, style = {}) {
  const m = v != null ? formatNumber(v) : '-';
  return { r, c, v: { v: v ?? '', m, ...style, ct: { fa: '#,##0', t: 'n' } } };
}
function pctCell(r, c, v, style = {}) {
  const m = v != null ? (v * 100).toFixed(3) + '%' : '-';
  return { r, c, v: { v: v ?? '', m, ...style, ct: { fa: '0.000%', t: 'n' } } };
}

export function buildMainSheetData(result, inputs = {}) {
  if (!result) return [];
  const {
    months, baseMonth, endMonth, adjustmentMonth,
    A, A1, A2, B, adjustmentC,
    calcAmount, deductAmount, executionAmount,
    progressSeries, cSeries,
  } = result;

  // inputs fallback: result에 없으면 inputs에서 직접 읽음
  const otherCost    = result.otherCost    ?? Number(inputs.otherCost)    ?? 0;
  const expectedAmt  = result.expectedAmount ?? Number(inputs.expectedAmount) ?? 0;
  const advanceRate  = result.advanceRate  ?? Number(inputs.advanceRate)  ?? 0;

  const cellData = [];
  const adjIdx = months.indexOf(adjustmentMonth);

  // ── A. 요약 블록 (rows 0~5) ──────────────────────────────────
  // 금액값: C열(col2)→B열(col1), '원' D열(col3) 제거 후 A열 레이블에 (원) 부착
  cellData.push(
    cell(0, 0, '집행금액(원)', CELL_STYLE.label),
    numCell(0, 1, executionAmount, CELL_STYLE.normal),
    cell(0, 2, '( 산정금액 - 공제금액 )', CELL_STYLE.normal),
    cell(0, 5, '기준시점', CELL_STYLE.label),
    cell(0, 6, formatYM(baseMonth), CELL_STYLE.normal),

    cell(1, 0, '  - 산정금액(원)', CELL_STYLE.label),
    numCell(1, 1, calcAmount, CELL_STYLE.normal),
    cell(1, 5, '조정시점', CELL_STYLE.label),
    cell(1, 6, adjustmentMonth ? formatYM(adjustmentMonth) : '미달성', adjustmentMonth ? CELL_STYLE.blue : CELL_STYLE.normal),

    cell(2, 0, '  - 공제금액(원)', CELL_STYLE.label),
    numCell(2, 1, deductAmount, CELL_STYLE.normal),
    cell(2, 2, calcAmount != null ? `( ${calcAmount.toLocaleString('ko-KR')} × 선금율 ${(advanceRate*100).toFixed(0)}% )` : '', CELL_STYLE.normal),
  );

  // 물가변동대상금액 테이블 헤더 (row 4)
  // 8컬럼: 자재비[A1] | 노무비[A2] | 계(A1+A2) | 물가변동대상외금액 | 정산예상금액 | 잔여기성률[B] | 물가변동률[C] | 산정금액[D]
  const summaryHeaders = [
    '자재비[A1]', '노무비[A2]', '계(A1+A2)',
    '물가변동대상외금액\n(경비, 간접비 등)',
    '정산예상금액',
    '잔여기성률[B]', '물가변동률[C]', '산정금액\n[D=A×B×C]',
  ];
  summaryHeaders.forEach((h, i) => cellData.push(cell(4, i, h, CELL_STYLE.header)));

  // 요약 값 (row 5)
  cellData.push(
    numCell(5, 0, A1, CELL_STYLE.normal),
    numCell(5, 1, A2, CELL_STYLE.normal),
    numCell(5, 2, A, CELL_STYLE.normal),
    numCell(5, 3, otherCost   || null, CELL_STYLE.normal),
    numCell(5, 4, expectedAmt || null, CELL_STYLE.normal),
    pctCell(5, 5, B, CELL_STYLE.normal),
    pctCell(5, 6, adjustmentC, CELL_STYLE.normal),
    numCell(5, 7, calcAmount, CELL_STYLE.normal),
  );

  // ── B. 잔여기성률[B] 상세 (rows 7+) ─────────────────────────
  const bStart = 7;
  cellData.push(cell(bStart, 0, '▶ 잔여기성률[B] 산출 상세', { ...CELL_STYLE.header, bold: true }));

  // 연도 그룹 헤더
  const yearRow = bStart + 1;
  const monthRow = bStart + 2;
  const labelCol = 0;

  // 월 헤더 (r=yearRow, r=monthRow)
  let yearMap = {};
  months.forEach((m, i) => {
    const y = m.slice(0, 4);
    if (!yearMap[y]) yearMap[y] = { start: i + 1, end: i + 1 };
    else yearMap[y].end = i + 1;
  });
  Object.entries(yearMap).forEach(([y, { start }]) => {
    cellData.push(cell(yearRow, start, y + '년', CELL_STYLE.header));
  });
  months.forEach((m, i) => {
    const mo = m.slice(4, 6) + '월';
    const style = m === adjustmentMonth ? CELL_STYLE.blue : CELL_STYLE.header;
    cellData.push(cell(monthRow, i + 1, mo, style));
  });
  cellData.push(cell(monthRow, 0, '구분', CELL_STYLE.header), cell(monthRow, months.length + 1, '비고', CELL_STYLE.header));

  // 데이터 행
  const bRows = [
    { label: '기성금액', key: 'amount', fmt: numCell },
    { label: '기성률(월별)', key: 'rateMonthly', fmt: pctCell },
    { label: '기성률(누계)', key: 'rateCumulative', fmt: pctCell },
    { label: '잔여기성률[B]', key: 'remaining', fmt: pctCell, bold: true },
  ];
  bRows.forEach(({ label, key, fmt, bold }, ri) => {
    const r = bStart + 3 + ri;
    const style = bold ? { ...CELL_STYLE.label, bold: true } : CELL_STYLE.label;
    cellData.push(cell(r, 0, label, style));
    progressSeries.forEach((p, i) => {
      const colStyle = p.month === adjustmentMonth
        ? (bold ? CELL_STYLE.blue : { bg: '#DDEEFF', ht: 0, vt: 0 })
        : CELL_STYLE.normal;
      cellData.push(fmt(r, i + 1, p[key], colStyle));
    });
  });

  // ── C. 물가변동률[C] 종합 (rows after B) ─────────────────────
  const cStart = bStart + 3 + bRows.length + 2;
  cellData.push(cell(cStart, 0, '▶ 물가변동률[C] 종합 (C1 + C2)', { ...CELL_STYLE.header, bold: true }));

  const cHeaderRow = cStart + 1;
  months.forEach((m, i) => {
    const style = m === adjustmentMonth ? CELL_STYLE.blue : CELL_STYLE.header;
    cellData.push(cell(cHeaderRow, i + 1, m.slice(4, 6) + '월', style));
  });
  cellData.push(cell(cHeaderRow, 0, '구분', CELL_STYLE.header));

  const cRows = [
    { label: '자재비 물가변동률[C1]', key: 'C1' },
    { label: '노무비 물가변동률[C2]', key: 'C2' },
    { label: '물가변동률[C]', key: 'C', bold: true },
  ];
  cRows.forEach(({ label, key, bold }, ri) => {
    const r = cStart + 2 + ri;
    const style = bold ? { ...CELL_STYLE.label, bold: true } : CELL_STYLE.label;
    cellData.push(cell(r, 0, label, style));
    cSeries.forEach((cs, i) => {
      const isAdj = cs.month === adjustmentMonth;
      const colStyle = isAdj && bold
        ? CELL_STYLE.blue
        : isAdj
          ? { bg: '#DDEEFF', ht: 0, vt: 0 }
          : CELL_STYLE.normal;
      cellData.push(pctCell(r, i + 1, cs[key], colStyle));
    });
    if (bold && adjustmentMonth) {
      // 오렌지 강조 셀 제거됨
    }
  });

  return cellData;
}

export default function MainCalculationSheet({ result, inputs = {}, recalcKey = 0 }) {
  const colCount = result ? result.months.length + 2 : 12;

  const sheets = [{
    name: '메인계산',
    id: 'main',
    celldata: result ? buildMainSheetData(result, inputs) : [],
    row: 40,
    column: colCount,
    showGridLines: 1,
    defaultRowHeight: 22,
    defaultColWidth: 90,
    config: { columnlen: { 0: 160, 1: 140, [colCount - 1]: 120 } },
  }];

  return (
    <div className="border border-gray-200 rounded-lg">
      <div className="bg-gray-50 px-4 py-2 border-b border-gray-200 flex items-center gap-2">
        <span className="text-sm font-semibold text-gray-700">① 메인 계산 결과</span>
        {result?.adjustmentMonth && (
          <span className="text-xs bg-blue-100 text-blue-700 rounded px-2 py-0.5">
            조정시점: {result.adjustmentMonth.slice(0, 4)}.{result.adjustmentMonth.slice(4, 6)}
          </span>
        )}
        {!result && <span className="text-xs text-gray-400">계산 실행 후 결과가 표시됩니다</span>}
      </div>
      <div style={{ height: 640 }}>
        <Workbook
          key={`main-${recalcKey}-${result?.adjustmentMonth}-${result?.months?.length}`}
          data={sheets}
          showToolbar={false}
          showFormulaBar={false}
          showSheetTabs={true}
          allowEdit={false}
          forceCalculation={true}
        />
      </div>
    </div>
  );
}
