import React from 'react';

const YEARS = Array.from({ length: 20 }, (_, i) => 2015 + i);
const MONTHS = Array.from({ length: 12 }, (_, i) => String(i + 1).padStart(2, '0'));

function YearMonthSelect({ label, value, onChange }) {
  const year = value ? value.slice(0, 4) : '';
  const month = value ? value.slice(4, 6) : '';
  return (
    <div className="flex items-center gap-1">
      <span className="text-sm text-gray-600 w-20 shrink-0">{label}</span>
      <select
        className="border border-yellow-400 bg-yellow-50 rounded px-2 py-1 text-sm"
        value={year}
        onChange={e => onChange(e.target.value + (month || '01'))}
      >
        <option value="">년도</option>
        {YEARS.map(y => <option key={y} value={y}>{y}</option>)}
      </select>
      <select
        className="border border-yellow-400 bg-yellow-50 rounded px-2 py-1 text-sm"
        value={month}
        onChange={e => onChange((year || '2021') + e.target.value)}
      >
        <option value="">월</option>
        {MONTHS.map(m => <option key={m} value={m}>{m}</option>)}
      </select>
    </div>
  );
}

function NumberInput({ label, value, onChange, unit = '원', hint }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-sm text-gray-600 w-40 shrink-0">{label}</span>
      <input
        type="number"
        className="border border-yellow-400 bg-yellow-50 rounded px-2 py-1 text-sm text-right w-40"
        value={value ?? ''}
        onChange={e => onChange(e.target.value === '' ? '' : Number(e.target.value))}
      />
      <span className="text-xs text-gray-500">{unit}</span>
      {hint && <span className="text-xs text-gray-400">{hint}</span>}
    </div>
  );
}

export default function InputForm({ inputs, onChange }) {
  const { baseMonth, endMonth, materialCost, laborCost, otherCost,
    expectedAmount, advanceRate, monthlyProgress } = inputs;

  const handleMonthlyAmount = (month, value) => {
    const updated = (monthlyProgress || []).map(p =>
      p.month === month ? { ...p, amount: value === '' ? 0 : Number(value) } : p
    );
    onChange({ ...inputs, monthlyProgress: updated });
  };

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4 space-y-4">
      <h2 className="text-base font-semibold text-gray-800 border-b pb-2">📋 입력 데이터</h2>

      {/* 기간 */}
      <div className="space-y-2">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">계산 기간</p>
        <YearMonthSelect label="기준시점" value={baseMonth}
          onChange={v => onChange({ ...inputs, baseMonth: v })} />
        <YearMonthSelect label="종료시점" value={endMonth}
          onChange={v => onChange({ ...inputs, endMonth: v })} />
      </div>

      {/* 금액 */}
      <div className="space-y-2">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">금액 입력</p>
        <NumberInput label="자재비 [A1]" value={materialCost}
          onChange={v => onChange({ ...inputs, materialCost: v })} />
        <NumberInput label="노무비 [A2]" value={laborCost}
          onChange={v => onChange({ ...inputs, laborCost: v })} />
        <NumberInput label="물가변동대상외금액" value={otherCost}
          onChange={v => onChange({ ...inputs, otherCost: v })} hint="경비, 간접비 등" />
        <NumberInput label="정산예상금액" value={expectedAmount}
          onChange={v => onChange({ ...inputs, expectedAmount: v })} />
        <NumberInput label="선금율" value={advanceRate != null ? advanceRate * 100 : ''}
          onChange={v => onChange({ ...inputs, advanceRate: v === '' ? 0 : Number(v) / 100 })}
          unit="%" hint="선금 없으면 0" />
      </div>

      {/* 월별 기성금액 */}
      {monthlyProgress && monthlyProgress.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
            월별 기성금액 <span className="text-gray-400">(기준시점부터)</span>
          </p>
          <div className="overflow-x-auto">
            <table className="text-sm border-collapse">
              <thead>
                <tr className="bg-gray-100">
                  <th className="border border-gray-300 px-3 py-1 text-left w-24">월</th>
                  <th className="border border-gray-300 px-3 py-1 text-right w-36">기성금액 (원)</th>
                </tr>
              </thead>
              <tbody>
                {monthlyProgress.map(({ month, amount }) => (
                  <tr key={month}>
                    <td className="border border-gray-300 px-3 py-1 text-sm text-gray-600">
                      {month.slice(0, 4)}.{month.slice(4, 6)}
                    </td>
                    <td className="border border-gray-300 px-1 py-1">
                      <input
                        type="number"
                        className="w-full text-right bg-yellow-50 border border-yellow-300 rounded px-2 py-0.5 text-sm"
                        value={amount ?? ''}
                        onChange={e => handleMonthlyAmount(month, e.target.value)}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
