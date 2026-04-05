import React from 'react';
import { Workbook } from '@fortune-sheet/react';
import '@fortune-sheet/react/dist/index.css';
import { formatYM } from '../utils/escCalculations';

const CELL_STYLE = {
  header: { bg: '#E8E8E8', bold: true, ht: 0, vt: 0 },
  blue:   { bg: '#BDD7EE', bold: true, ht: 0, vt: 0 },
  normal: { ht: 0, vt: 0 },
  label:  { bg: '#F2F2F2', ht: 0, vt: 0 },
};

function cell(r, c, v, style = {}) {
  return { r, c, v: { v, m: v == null ? '' : String(v), ...style, ct: { fa: '@', t: 'inlineStr' } } };
}
function numCell(r, c, v, style = {}, decimal = 2) {
  const fmt = '#,##0.' + '0'.repeat(decimal);
  const m = v != null ? Number(v).toFixed(decimal) : '-';
  return { r, c, v: { v: v ?? '', m, ...style, ct: { fa: fmt, t: 'n' } } };
}
function pctCell(r, c, v, style = {}) {
  const m = v != null ? (v * 100).toFixed(3) + '%' : '-';
  return { r, c, v: { v: v ?? '', m, ...style, ct: { fa: '0.000%', t: 'n' } } };
}

function buildPpiSheetData(result) {
  if (!result) return [];
  const { months, ppiSeries, adjustmentMonth } = result;

  const cellData = [];
  const headers = ['시점', '생산자물가지수\n(공산품)', 'D1\n(변동비율)', 'C1\n(자재비 물가변동률)'];
  headers.forEach((h, c) => cellData.push(cell(0, c, h, CELL_STYLE.header)));

  ppiSeries.forEach(({ month, ppi, D1, C1 }, i) => {
    const isAdj = month === adjustmentMonth;
    const style = isAdj ? CELL_STYLE.blue : CELL_STYLE.normal;
    const r = i + 1;
    cellData.push(
      cell(r, 0, formatYM(month), style),
      numCell(r, 1, ppi, style, 2),
      numCell(r, 2, D1, style, 5),
      pctCell(r, 3, C1, style),
    );
  });
  return cellData;
}

export default function PpiDataSheet({ result }) {
  const sheets = [{
    name: '생산자물가지수',
    id: 'ppi',
    celldata: buildPpiSheetData(result),
    row: (result?.ppiSeries?.length || 0) + 5,
    column: 5,
    showGridLines: 1,
    defaultRowHeight: 22,
    defaultColWidth: 130,
  }];

  return (
    <div className="border border-gray-200 rounded-lg">
      <div className="bg-gray-50 px-4 py-2 border-b border-gray-200">
        <span className="text-sm font-semibold text-gray-700">② 생산자물가지수 (공산품)</span>
        {!result && <span className="ml-2 text-xs text-gray-400">계산 실행 후 표시됩니다</span>}
      </div>
      <div style={{ height: 380 }}>
        <Workbook
          key={`ppi-${result?.adjustmentMonth}-${result?.ppiSeries?.length}`}
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
