import React, { useState } from 'react';
import { SlidersHorizontal, ChevronDown, ChevronUp, Layers } from 'lucide-react';

const SettingsPanel = ({ settings, onSettingsChange, colors }) => {
  const { mode, diffThreshold, featureCount, cadMode, cadLineWidth } = settings;
  const [isConfigOpen, setIsConfigOpen] = useState(false);

  return (
    <div>
      {/* ── Mode Select ── */}
      <div className="mb-4">
        <div className="flex items-center gap-2 mb-3">
          <Layers size={14} className="text-gray-400 shrink-0" />
          <span className="text-xs font-bold text-[var(--text-secondary)] uppercase tracking-wider">
            Mode Select
          </span>
        </div>

        {/* 비교 모드 버튼 */}
        <div className="flex flex-col gap-1.5 mb-3">
          <button
            onClick={() => onSettingsChange({ ...settings, mode: 'difference' })}
            className={`
              w-full px-3 py-2 text-sm rounded-lg border transition-all text-left
              ${mode === 'difference'
                ? 'bg-blue-50 border-blue-500 text-blue-700 font-medium'
                : 'bg-white border-gray-300 text-gray-700 hover:border-gray-400'
              }
            `}
          >
            차이점 강조
          </button>
          <button
            onClick={() => onSettingsChange({ ...settings, mode: 'overlay' })}
            className={`
              w-full px-3 py-2 text-sm rounded-lg border transition-all text-left
              ${mode === 'overlay'
                ? 'bg-blue-50 border-blue-500 text-blue-700 font-medium'
                : 'bg-white border-gray-300 text-gray-700 hover:border-gray-400'
              }
            `}
          >
            오버레이
          </button>
          <button
            onClick={() => onSettingsChange({ ...settings, mode: 'split-overlay' })}
            className={`
              w-full px-3 py-2 text-sm rounded-lg border transition-all text-left
              ${mode === 'split-overlay'
                ? 'bg-blue-50 border-blue-500 text-blue-700 font-medium'
                : 'bg-white border-gray-300 text-gray-700 hover:border-gray-400'
              }
            `}
          >
            차이점+오버레이
          </button>
        </div>

        {/* 색상 범례 — 모든 모드에서 동일한 3색 표시 */}
        <div className="flex flex-wrap gap-2">
          <div className="flex items-center gap-1 text-[10px] text-gray-500">
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: colors?.diff_file1 || '#3B82F6' }}></span>
            파일1
          </div>
          <div className="flex items-center gap-1 text-[10px] text-gray-500">
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: colors?.diff_file2 || '#DC2626' }}></span>
            파일2
          </div>
          <div className="flex items-center gap-1 text-[10px] text-gray-500">
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: colors?.diff_common || '#000000' }}></span>
            공통
          </div>
        </div>
      </div>

      {/* ── Configuration (fold) ── */}
      <div className="border-t border-gray-200 pt-3">
        <button
          onClick={() => setIsConfigOpen(v => !v)}
          className="w-full flex items-center justify-between mb-3 group"
        >
          <div className="flex items-center gap-2">
            <SlidersHorizontal size={14} className="text-gray-400 shrink-0" />
            <span className="text-xs font-bold text-[var(--text-secondary)] uppercase tracking-wider">
              Configuration
            </span>
          </div>
          {isConfigOpen
            ? <ChevronUp size={14} className="text-gray-400" />
            : <ChevronDown size={14} className="text-gray-400" />
          }
        </button>

        {isConfigOpen && (
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <input
                id="cadMode"
                type="checkbox"
                checked={cadMode ?? false}
                onChange={(e) => onSettingsChange({ ...settings, cadMode: e.target.checked })}
                className="w-4 h-4 accent-blue-500 cursor-pointer"
              />
              <label htmlFor="cadMode" className="text-xs font-medium text-gray-700 cursor-pointer select-none">
                CAD 모드 (Thin Line)
              </label>
              <span className="ml-auto flex items-center gap-1 text-xs text-gray-600">
                선두께
                <div className="flex items-stretch border border-gray-300 rounded overflow-hidden">
                  <input
                    type="number"
                    step="0.05"
                    min="0.05"
                    max="2.0"
                    value={cadLineWidth ?? 0.2}
                    onChange={(e) => onSettingsChange({ ...settings, cadLineWidth: parseFloat(e.target.value) || 0.2 })}
                    className="w-12 px-1 py-0.5 text-xs text-center [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                  />
                  <div className="flex flex-col border-l border-gray-300">
                    <button
                      type="button"
                      onClick={() => onSettingsChange({ ...settings, cadLineWidth: parseFloat(Math.min(2.0, (cadLineWidth ?? 0.2) + 0.05).toFixed(2)) })}
                      className="flex items-center justify-center px-0.5 flex-1 hover:bg-gray-100"
                    >
                      <ChevronUp size={10} />
                    </button>
                    <button
                      type="button"
                      onClick={() => onSettingsChange({ ...settings, cadLineWidth: parseFloat(Math.max(0.05, (cadLineWidth ?? 0.2) - 0.05).toFixed(2)) })}
                      className="flex items-center justify-center px-0.5 flex-1 hover:bg-gray-100 border-t border-gray-300"
                    >
                      <ChevronDown size={10} />
                    </button>
                  </div>
                </div>
                pt
              </span>
            </div>

            <p className="text-xs text-gray-500 -mt-2">
              CAD 선두께는 PDF 단위 pt로 적용됩니다. 일반적으로 0.1~0.3pt가 얇은 선 표현에 적합합니다.
            </p>

            {/* 차이 임계값 */}
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-2">
                차이 임계값: {diffThreshold}
              </label>
              <input
                type="range"
                min="10"
                max="100"
                step="5"
                value={diffThreshold}
                onChange={(e) => onSettingsChange({ ...settings, diffThreshold: parseInt(e.target.value) })}
                className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-500"
              />
              <div className="flex justify-between text-xs text-gray-500 mt-1">
                <span>민감 (10)</span>
                <span>둔감 (100)</span>
              </div>
            </div>

            {/* 특징점 개수 */}
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-2">
                특징점 개수: {featureCount.toLocaleString()}
              </label>
              <input
                type="range"
                min="1000"
                max="10000"
                step="1000"
                value={featureCount}
                onChange={(e) => onSettingsChange({ ...settings, featureCount: parseInt(e.target.value) })}
                className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-500"
              />
              <div className="flex justify-between text-xs text-gray-500 mt-1">
                <span>빠름 (1000)</span>
                <span>정밀 (10000)</span>
              </div>
              <p className="text-xs text-gray-500 mt-1">
                값이 클수록 정렬 정확도가 높아지지만 처리 시간이 증가합니다.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default SettingsPanel;
