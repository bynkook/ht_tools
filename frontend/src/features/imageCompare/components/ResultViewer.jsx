import React, { useRef, useEffect } from 'react';
import { Download, ZoomIn, ZoomOut, Maximize2 } from 'lucide-react';

const ResultViewer = ({ resultData, onDownload, colors }) => {
  const containerRef = useRef(null);

  // Default colors (Fallback)
  const defaultColors = {
    diff_file1: '#0000FF', // Blue
    diff_file2: '#FF0000'  // Red
  };
  
  const activeColors = colors || defaultColors;

  if (!resultData) {
    return (
      <div className="h-full flex items-center justify-center rounded-xl bg-gray-50/50 m-4">
        <div className="text-center">
          <Maximize2 className="mx-auto mb-3 text-gray-300" size={48} />
          <p className="text-gray-400 font-medium mb-1">비교 결과가 여기에 표시됩니다</p>
          <p className="text-sm text-gray-400">두 파일을 업로드하고 "비교 시작" 버튼을 클릭하세요</p>
        </div>
      </div>
    );
  }

  // resultData now contains file1_base64, file2_base64, result_base64, metadata
  const { result_base64, file1_base64, file2_base64, download_base64, metadata } = resultData;
  const isDiffMode = metadata.mode === 'difference';

  return (
    <div className="flex flex-col h-full overflow-hidden bg-white mx-4 mb-4">
      {/* Header */}
      <div className="flex-shrink-0 px-4 py-3 bg-white flex items-center justify-between">
        <div>
          <h3 className="text-sm font-bold text-[var(--text-primary)]">
            {isDiffMode ? "비교 결과 (차이점 강조)" : "비교 결과 (오버레이)"}
          </h3>
          <p className="text-xs text-gray-400 mt-0.5">
            {metadata.result_size} • 매칭 품질: {(metadata.match_quality * 100).toFixed(0)}%
          </p>
        </div>
        
        {isDiffMode && (
           <div className="flex items-center gap-4 text-xs font-medium">
             {/* Indicators moved to pane headers */}
           </div>
        )}

        <button
          onClick={() => onDownload(download_base64, metadata)}
          className="flex items-center gap-2 px-3 py-2 bg-blue-600 text-white text-sm font-bold rounded-lg hover:bg-blue-700 transition-colors shadow-sm"
        >
          <Download size={16} />
          PNG 다운로드
        </button>
      </div>
      
      {/* Viewer Body */}
      <div 
        ref={containerRef}
        className="flex-1 relative overflow-auto bg-gray-50 flex"
      >
        {isDiffMode && file1_base64 && file2_base64 ? (
          // Split View (Difference Mode)
          <div className="flex w-full h-full">
            {/* Left Pane (File 1) */}
            <div className="flex-1 flex flex-col">
              <div className="p-2 flex items-center justify-center gap-2 text-xs font-bold text-gray-400 bg-white sticky top-0 z-10 uppercase">
                <span className="w-3 h-3 rounded-full shadow-sm" style={{ backgroundColor: activeColors.diff_file1 || '#0000FF' }}></span>
                File 1 (기준)
              </div>
              <div className="flex-1 overflow-auto p-4 flex items-center justify-center">
                <img 
                   src={file1_base64} 
                   alt="File 1" 
                   className="max-w-full max-h-full object-contain" 
                />
              </div>
            </div>

            {/* Right Pane (File 2) */}
            <div className="flex-1 flex flex-col border-l border-gray-100">
              <div className="p-2 flex items-center justify-center gap-2 text-xs font-bold text-gray-400 bg-white sticky top-0 z-10 uppercase">
                <span className="w-3 h-3 rounded-full shadow-sm" style={{ backgroundColor: activeColors.diff_file2 || '#FF0000' }}></span>
                File 2 (비교군)
              </div>
              <div className="flex-1 overflow-auto p-4 flex items-center justify-center">
                <img 
                   src={file2_base64} 
                   alt="File 2" 
                   className="max-w-full max-h-full object-contain" 
                />
              </div>
            </div>
          </div>
        ) : (
          // Single View (Overlay Mode or Fallback)
          <div className="w-full h-full flex flex-col">            
            <div className="flex-1 overflow-auto p-4 flex items-center justify-center">
              <img
                src={result_base64}
                alt="Comparison Result"
                className="max-w-full max-h-full object-contain shadow-lg"
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default ResultViewer;
