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

  // ── A. 물가변동대상금액 테이블 헤더 (row 0) ──────────────────
  // (집행금액/산정금액/공제금액 블록은 HTML 테이블로 분리)
  const summaryHeaders = [
    '자재비[A1]', '노무비[A2]', '계(A1+A2)',
    '물가변동대상외금액\n(경비, 간접비 등)',
    '정산예상금액',
    '잔여기성률[B]', '물가변동률[C]', '산정금액\n[D=A×B×C]',
  ];
  summaryHeaders.forEach((h, i) => cellData.push(cell(0, i, h, CELL_STYLE.header)));

  // 요약 값 (row 1)
  cellData.push(
    numCell(1, 0, A1, CELL_STYLE.normal),
    numCell(1, 1, A2, CELL_STYLE.normal),
    numCell(1, 2, A, CELL_STYLE.normal),
    numCell(1, 3, otherCost   || null, CELL_STYLE.normal),
    numCell(1, 4, expectedAmt || null, CELL_STYLE.normal),
    pctCell(1, 5, B, CELL_STYLE.normal),
    pctCell(1, 6, adjustmentC, CELL_STYLE.normal),
    numCell(1, 7, calcAmount, CELL_STYLE.normal),
  );

  // ── B. 잔여기성률[B] 상세 (rows 3+) ─────────────────────────
  const bStart = 3;
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

function ResultSummaryTable({ result, inputs = {} }) {
  if (!result) return null;
  const {
    baseMonth, adjustmentMonth,
    calcAmount, deductAmount, executionAmount,
  } = result;
  const advRate = result.advanceRate ?? Number(inputs.advanceRate) ?? 0;

  return (
    <div className="flex gap-3">
      {/* 좌측: 금액 테이블 — 컨텐츠 너비에 맞게 */}
      <table className="text-sm border-collapse shrink-0">
        <tbody>
          <tr>
            <td className="border border-gray-300 bg-gray-100 px-3 py-1.5 font-bold text-gray-700 whitespace-nowrap">집행금액(원)</td>
            <td className="border border-gray-300 px-3 py-1.5 text-right font-bold text-blue-800 whitespace-nowrap">{formatNumber(executionAmount)}</td>
            <td className="border border-gray-300 px-3 py-1.5 text-gray-500 text-xs whitespace-nowrap">( 산정금액 - 공제금액 )</td>
          </tr>
          <tr>
            <td className="border border-gray-300 bg-gray-100 px-3 py-1.5 text-gray-600 whitespace-nowrap pl-6">- 산정금액(원)</td>
            <td className="border border-gray-300 px-3 py-1.5 text-right whitespace-nowrap">{formatNumber(calcAmount)}</td>
            <td className="border border-gray-300 px-3 py-1.5"></td>
          </tr>
          <tr>
            <td className="border border-gray-300 bg-gray-100 px-3 py-1.5 text-gray-600 whitespace-nowrap pl-6">- 공제금액(원)</td>
            <td className="border border-gray-300 px-3 py-1.5 text-right whitespace-nowrap">{formatNumber(deductAmount)}</td>
            <td className="border border-gray-300 px-3 py-1.5 text-gray-500 text-xs whitespace-nowrap">
              {calcAmount != null ? `( ${calcAmount.toLocaleString('ko-KR')} × 선금율 ${(advRate * 100).toFixed(0)}% )` : ''}
            </td>
          </tr>
        </tbody>
      </table>

      {/* 우측: 단일 CSS Grid — 열 폭 자동 일치, 콘텐츠 크기에 유동적 */}
      <div
        className="shrink-0 text-sm border border-gray-300"
        style={{ display: 'grid', gridTemplateColumns: 'auto auto', gridTemplateRows: 'auto 1fr' }}
      >
        <div className="bg-gray-100 py-1.5 px-4 font-semibold text-gray-700 text-center whitespace-nowrap border-r border-b border-gray-300">기준시점</div>
        <div className="bg-gray-100 py-1.5 px-4 font-semibold text-gray-700 text-center whitespace-nowrap border-b border-gray-300">조정시점</div>
        <div className="px-4 flex items-center justify-center whitespace-nowrap border-r border-gray-300">{formatYM(baseMonth)}</div>
        <div className={`px-4 flex items-center justify-center whitespace-nowrap font-bold ${adjustmentMonth ? 'bg-blue-200 text-blue-900' : 'text-gray-400'}`}>
          {adjustmentMonth ? formatYM(adjustmentMonth) : '미달성'}
        </div>
      </div>
    </div>
  );
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
      {result && (
        <div className="px-2 pt-2 pb-3">
          <ResultSummaryTable result={result} inputs={inputs} />
        </div>
      )}
      <div style={{ height: 580 }}>
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
