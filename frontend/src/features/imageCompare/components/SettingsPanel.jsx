import React from 'react';
import { Settings } from 'lucide-react';

const SettingsPanel = ({ settings, onSettingsChange, colors }) => {
  const { mode, diffThreshold, featureCount } = settings;

  // 색상 정보 레이블 생성
  const getColorLabel = () => {
    if (mode === 'difference') {
      return '사용자 정의 색상으로 차이점이 표시됩니다.';
    } else {
      return '사용자 정의 색상으로 레이어가 겹쳐서 표시됩니다.';
    }
  };

  return (
    <div className="p-4 bg-white">
      <div className="flex items-center gap-2 mb-4">
        <Settings size={18} className="text-gray-400" />
        <h3 className="text-sm font-bold text-[var(--text-primary)]">비교 설정</h3>
      </div>
      
      {/* 비교 모드 */}
      <div className="mb-4">
        <label className="block text-xs font-medium text-gray-700 mb-2">
          비교 모드
        </label>
        <div className="flex gap-2">
          <button
            onClick={() => onSettingsChange({ ...settings, mode: 'difference' })}
            className={`
              flex-1 px-3 py-2 text-sm rounded-lg border transition-all
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
              flex-1 px-3 py-2 text-sm rounded-lg border transition-all
              ${mode === 'overlay' 
                ? 'bg-blue-50 border-blue-500 text-blue-700 font-medium' 
                : 'bg-white border-gray-300 text-gray-700 hover:border-gray-400'
              }
            `}
          >
            오버레이
          </button>
        </div>
        <div className="mt-2 flex flex-wrap gap-2">
          {mode === 'difference' ? (
            <>
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
            </>
          ) : (
            <>
              <div className="flex items-center gap-1 text-[10px] text-gray-500">
                <span className="w-2 h-2 rounded-full" style={{ backgroundColor: colors?.overlay_file1 || '#F97316' }}></span>
                파일1
              </div>
              <div className="flex items-center gap-1 text-[10px] text-gray-500">
                <span className="w-2 h-2 rounded-full" style={{ backgroundColor: colors?.overlay_file2 || '#22C55E' }}></span>
                파일2
              </div>
            </>
          )}
        </div>
      </div>
      
      {/* 차이 임계값 (difference 모드에만 표시) */}
      {mode === 'difference' && (
        <div className="mb-4">
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
          특징점 개수: {featureCount}
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
  );
};

export default SettingsPanel;
