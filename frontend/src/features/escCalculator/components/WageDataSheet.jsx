import React from 'react';
import { Workbook } from '@fortune-sheet/react';
import '@fortune-sheet/react/dist/index.css';
import { monthToHalfKey } from '../utils/escCalculations';

const CELL_STYLE = {
  header: { bg: '#E8E8E8', bold: true, ht: 0, vt: 0 },
  blue:   { bg: '#BDD7EE', bold: true, ht: 0, vt: 0 },
  normal: { ht: 0, vt: 0 },
};

function cell(r, c, v, style = {}) {
  return { r, c, v: { v, m: v == null ? '' : String(v), ...style, ct: { fa: '@', t: 'inlineStr' } } };
}
function numCell(r, c, v, style = {}, decimal = 0) {
  const m = v != null ? Number(v).toLocaleString('ko-KR', { maximumFractionDigits: decimal }) : '-';
  return { r, c, v: { v: v ?? '', m, ...style, ct: { fa: '#,##0', t: 'n' } } };
}
function pctCell(r, c, v, style = {}) {
  const m = v != null ? (v * 100).toFixed(3) + '%' : '-';
  return { r, c, v: { v: v ?? '', m, ...style, ct: { fa: '0.000%', t: 'n' } } };
}

function buildWageSheetData(result) {
  if (!result) return [];
  const { months, wageSeries, adjustmentMonth } = result;

  const cellData = [];
  const headers = ['시점(반기)', '시중노임단가\n(일반공사)', 'D2\n(변동비율)', 'C2\n(노무비 물가변동률)'];
  headers.forEach((h, c) => cellData.push(cell(0, c, h, CELL_STYLE.header)));

  // 반기 단위로 중복 제거해서 표시 (같은 반기 데이터는 한 행으로)
  const seen = new Set();
  let row = 1;
  wageSeries.forEach(({ month, period, wage, D2, C2 }) => {
    if (seen.has(period)) return;
    seen.add(period);
    const isAdj = month === adjustmentMonth || (adjustmentMonth ? monthToHalfKey(adjustmentMonth) === period : false);
    const style = isAdj ? CELL_STYLE.blue : CELL_STYLE.normal;
    cellData.push(
      cell(row, 0, period.slice(0, 4) + '년 ' + (period.slice(4) === '01' ? '상반기' : '하반기'), style),
      numCell(row, 1, wage, style),
      numCell(row, 2, D2, style, 5),
      pctCell(row, 3, C2, style),
    );
    row++;
  });
  return cellData;
}

export default function WageDataSheet({ result }) {
  const sheets = [{
    name: '노임단가',
    id: 'wage',
    celldata: buildWageSheetData(result),
    row: (result?.wageSeries?.length || 0) + 5,
    column: 5,
    showGridLines: 1,
    defaultRowHeight: 22,
    defaultColWidth: 130,
  }];

  return (
    <div className="border border-gray-200 rounded-lg">
      <div className="bg-gray-50 px-4 py-2 border-b border-gray-200">
        <span className="text-sm font-semibold text-gray-700">③ 시중노임단가 (일반공사직종)</span>
        {!result && <span className="ml-2 text-xs text-gray-400">계산 실행 후 표시됩니다</span>}
      </div>
      <div style={{ height: 280 }}>
        <Workbook
          key={`wage-${result?.adjustmentMonth}-${result?.wageSeries?.length}`}
          data={sheets}
          showToolbar={false}
          showFormulaBar={false}
          showSheetTabs={true}
          allowEdit={false}
        />
      </div>
    </div>
  );
}
