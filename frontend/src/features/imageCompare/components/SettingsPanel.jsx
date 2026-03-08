import React, { useState } from 'react';
import { SlidersHorizontal, ChevronDown, ChevronUp, Layers, Camera, Ruler } from 'lucide-react';

const SettingsPanel = ({ settings, onSettingsChange, colors }) => {
  const { 
    mode, diffThreshold, featureCount, alignmentAlgorithm, 
    cadLineWidth, cadLineWidthEnabled,
    cadAlignTolerance, cadQualityThreshold
  } = settings;
  const [isConfigOpen, setIsConfigOpen] = useState(false);

  const isPhotoMode = alignmentAlgorithm === 'orb';
  const isCadMode = !isPhotoMode;

  const setPhotoMode = () => {
    onSettingsChange({ ...settings, alignmentAlgorithm: 'orb' });
  };

  const setCadMode = () => {
    onSettingsChange({ ...settings, alignmentAlgorithm: 'drawing_hybrid' });
  };

  return (
    <div>
      {/* ── 분석 모드 (Analysis Mode) ── */}
      <div className="mb-4">
        <div className="flex items-center gap-2 mb-3">
          <Layers size={14} className="text-gray-400 shrink-0" />
          <span className="text-xs font-bold text-[var(--text-secondary)] uppercase tracking-wider">
            분석 모드
          </span>
        </div>

        <div className="flex gap-2 mb-3">
          <button
            onClick={setPhotoMode}
            className={`
              flex-1 px-2.5 py-1.5 text-xs rounded-lg border transition-all flex items-center justify-center gap-1.5 leading-none
              ${isPhotoMode
                ? 'bg-blue-50 border-blue-500 text-blue-700 font-medium'
                : 'bg-white border-gray-300 text-gray-700 hover:border-gray-400'
              }
            `}
          >
            <Camera size={14} />
            사진 모드
          </button>
          <button
            onClick={setCadMode}
            className={`
              flex-1 px-2.5 py-1.5 text-xs rounded-lg border transition-all flex items-center justify-center gap-1.5 leading-none
              ${isCadMode
                ? 'bg-blue-50 border-blue-500 text-blue-700 font-medium'
                : 'bg-white border-gray-300 text-gray-700 hover:border-gray-400'
              }
            `}
          >
            <Ruler size={14} />
            CAD 모드
          </button>
        </div>

        <p className="text-[11px] leading-4 text-gray-500 mb-2.5">
          {isPhotoMode
            ? 'ORB 매칭: 일반 사진, 텍스처 이미지 비교에 적합'
            : 'Hybrid 매칭: PDF 도면, 선 구조 중심 비교에 적합'
          }
        </p>
      </div>

      {/* ── 표시 모드 (Display Mode) ── */}
      <div className="mb-4 border-t border-gray-200 pt-3">
        <div className="flex items-center gap-2 mb-3">
          <Layers size={14} className="text-gray-400 shrink-0" />
          <span className="text-xs font-bold text-[var(--text-secondary)] uppercase tracking-wider">
            표시 모드
          </span>
        </div>

        <div className="flex flex-col gap-1.5 mb-3">
          <button
            onClick={() => onSettingsChange({ ...settings, mode: 'difference' })}
            className={`
              w-full px-2.5 py-1.5 text-xs rounded-lg border transition-all text-left leading-none
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
              w-full px-2.5 py-1.5 text-xs rounded-lg border transition-all text-left leading-none
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
              w-full px-2.5 py-1.5 text-xs rounded-lg border transition-all text-left leading-none
              ${mode === 'split-overlay'
                ? 'bg-blue-50 border-blue-500 text-blue-700 font-medium'
                : 'bg-white border-gray-300 text-gray-700 hover:border-gray-400'
              }
            `}
          >
            차이점+오버레이
          </button>
        </div>

        {/* 색상 범례 */}
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
              {isPhotoMode ? '사진 모드 설정' : 'CAD 모드 설정'}
            </span>
          </div>
          {isConfigOpen
            ? <ChevronUp size={14} className="text-gray-400" />
            : <ChevronDown size={14} className="text-gray-400" />
          }
        </button>

        {isConfigOpen && (
          <div className="space-y-4">
            {/* CAD 모드 전용 설정 */}
            {isCadMode && (
              <>
                {/* CAD 선두께 ON/OFF + 값 */}
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <input
                      id="cadLineWidthEnabled"
                      type="checkbox"
                      checked={cadLineWidthEnabled ?? false}
                      onChange={(e) => onSettingsChange({ ...settings, cadLineWidthEnabled: e.target.checked })}
                      className="w-4 h-4 accent-blue-500 cursor-pointer"
                    />
                    <label htmlFor="cadLineWidthEnabled" className="text-xs font-medium text-gray-700 cursor-pointer select-none">
                      PDF 내부 선 두께 변경
                    </label>
                  </div>
                  {(cadLineWidthEnabled ?? false) && (
                    <div className="ml-6">
                      <div className="flex items-center gap-2">
                        <input
                          type="range"
                          min="0.05"
                          max="1.0"
                          step="0.05"
                          value={cadLineWidth ?? 0.2}
                          onChange={(e) => onSettingsChange({ ...settings, cadLineWidth: parseFloat(e.target.value) })}
                          className="flex-1 h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-500"
                        />
                        <span className="text-xs text-gray-600 w-12 text-right">{cadLineWidth ?? 0.2} pt</span>
                      </div>
                      <p className="text-xs text-gray-500 mt-1">
                        0.1 - 0.3 pt가 얇은 선 표현에 적합합니다.
                      </p>
                    </div>
                  )}
                </div>

                {/* 정렬 허용도 */}
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-2">
                    정렬 허용도: {(cadAlignTolerance ?? 0.22).toFixed(2)}
                  </label>
                  <input
                    type="range"
                    min="0.10"
                    max="0.30"
                    step="0.02"
                    value={cadAlignTolerance ?? 0.22}
                    onChange={(e) => onSettingsChange({ ...settings, cadAlignTolerance: parseFloat(e.target.value) })}
                    className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-500"
                  />
                  <div className="flex justify-between text-xs text-gray-500 mt-1">
                    <span>엄격 (0.10)</span>
                    <span>관대 (0.30)</span>
                  </div>
                  <p className="text-xs text-gray-500 mt-1">
                    점 매칭 허용 거리. 복잡한 도면은 관대하게, 정밀 비교는 엄격하게 설정하세요.
                  </p>
                </div>

                {/* 품질 기준 */}
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-2">
                    품질 기준: {(cadQualityThreshold ?? 0.35).toFixed(2)}
                  </label>
                  <input
                    type="range"
                    min="0.20"
                    max="0.50"
                    step="0.05"
                    value={cadQualityThreshold ?? 0.35}
                    onChange={(e) => onSettingsChange({ ...settings, cadQualityThreshold: parseFloat(e.target.value) })}
                    className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-500"
                  />
                  <div className="flex justify-between text-xs text-gray-500 mt-1">
                    <span>관대 (0.20)</span>
                    <span>엄격 (0.50)</span>
                  </div>
                  <p className="text-xs text-gray-500 mt-1">
                    정렬 품질 통과 기준. 매칭 실패 시 낮추면 정렬이 허용될 수 있습니다.
                  </p>
                </div>
              </>
            )}

            {/* 사진 모드 전용: 특징점 개수 */}
            {isPhotoMode && (
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
                  ORB 특징점 개수. 값이 클수록 정렬 정확도가 높아지지만 처리 시간이 증가합니다.
                </p>
              </div>
            )}

            {/* 공통: 차이 임계값 */}
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
          </div>
        )}
      </div>
    </div>
  );
};

export default SettingsPanel;
