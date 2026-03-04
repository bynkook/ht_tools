import React, { useCallback } from 'react';

/**
 * 슬라이더 + 숫자 입력 조합 컴포넌트
 *
 * 두 입력이 양방향으로 동기화되며 값은 항상 [min, max] 범위로 클램핑된다.
 */
const SliderInput = ({ label, description, value, onChange, min, max, step = 1, unit = '' }) => {
  const clamp = useCallback(
    (v) => Math.min(max, Math.max(min, v)),
    [min, max]
  );

  const handleSlider = (e) => {
    onChange(clamp(Number(e.target.value)));
  };

  const handleNumber = (e) => {
    const raw = e.target.value;
    // 입력 중 빈 문자열이나 중간값 허용 (blur 시 최종 클램핑)
    if (raw === '' || raw === '-') return;
    const num = Number(raw);
    if (!isNaN(num)) onChange(clamp(num));
  };

  const handleBlur = (e) => {
    const num = Number(e.target.value);
    if (isNaN(num) || e.target.value === '') {
      onChange(min);
    } else {
      onChange(clamp(num));
    }
  };

  // 슬라이더 채워진 비율 계산 (배경 그라디언트용)
  const pct = ((value - min) / (max - min)) * 100;

  return (
    <div className="group flex flex-col gap-3 p-4 rounded-2xl bg-slate-50 border border-transparent hover:border-slate-200 hover:bg-white hover:shadow-sm transition-all duration-200">
      <div>
        <label className="text-sm font-bold text-slate-700 block mb-1">{label}</label>
        {description && (
          <p className="text-xs text-slate-500 leading-relaxed">{description}</p>
        )}
      </div>

      <div className="flex items-center gap-4">
        {/* 슬라이더 */}
        <div className="relative flex-1 h-2">
          <input
            type="range"
            min={min}
            max={max}
            step={step}
            value={value}
            onChange={handleSlider}
            className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
          />
          {/* 커스텀 트랙 */}
          <div className="absolute inset-0 rounded-full bg-slate-200 overflow-hidden pointer-events-none">
            <div
              className="h-full bg-slate-700 transition-all duration-100"
              style={{ width: `${pct}%` }}
            />
          </div>
          {/* 썸 */}
          <div
            className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-4 h-4 bg-slate-900 rounded-full shadow pointer-events-none transition-all duration-100"
            style={{ left: `${pct}%` }}
          />
        </div>

        {/* 숫자 입력 */}
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <input
            type="number"
            min={min}
            max={max}
            step={step}
            value={value}
            onChange={handleNumber}
            onBlur={handleBlur}
            className="w-20 text-center text-sm font-mono font-bold text-slate-900 bg-white border border-slate-200 rounded-xl px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-slate-300 focus:border-transparent"
          />
          {unit && (
            <span className="text-xs font-bold text-slate-400 uppercase">{unit}</span>
          )}
        </div>
      </div>

      {/* 범위 표시 */}
      <div className="flex justify-between text-[10px] font-semibold text-slate-400 px-0.5">
        <span>{min.toLocaleString()}{unit && ` ${unit}`}</span>
        <span>{max.toLocaleString()}{unit && ` ${unit}`}</span>
      </div>
    </div>
  );
};

export default SliderInput;
