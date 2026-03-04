import React, { useState } from 'react';
import { SlidersHorizontal, ChevronDown, ChevronUp, Layers } from 'lucide-react';

const SettingsPanel = ({ settings, onSettingsChange, colors }) => {
  const { mode, diffThreshold, featureCount } = settings;
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
            {/* 차이 임계값 (difference/split-overlay 모드에만 표시) */}
            {(mode === 'difference' || mode === 'split-overlay') && (
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
            )}

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
