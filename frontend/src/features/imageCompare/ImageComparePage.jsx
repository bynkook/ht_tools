import React, { useState, useRef, useEffect, useCallback, memo } from 'react';
import { Menu, AlertCircle, Link, ChevronLeft, ChevronRight } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import ImageCompareSidebar from './components/ImageCompareSidebar';
import ResultViewer from './components/ResultViewer';
import LoadingOverlay from './components/LoadingOverlay';
import CropSelector from './components/CropSelector';
import { fastApi } from '../../api/fastapiApi';
import { authApi, settingsApi } from '../../api/djangoApi';

const normalizeAlignmentAlgorithm = (value) => value === 'orb' ? 'orb' : 'drawing_hybrid';
const isDrawingHybridAlgorithm = (value) => normalizeAlignmentAlgorithm(value) === 'drawing_hybrid';

// Extract PageControl component outside main component to prevent re-creation on each render
const PageControl = memo(({ label, currentPage, totalPages, onPrev, onNext, disabled }) => (
  <div className="flex flex-col items-center gap-1">
    <span className="text-xs font-medium text-gray-500">{label}</span>
    <div className="flex items-center gap-2 bg-white rounded-lg border border-gray-200 p-1 shadow-sm">
      <button
        onClick={onPrev}
        disabled={disabled || currentPage <= 0}
        className="p-1 hover:bg-gray-100 rounded disabled:opacity-30 disabled:cursor-not-allowed"
      >
        <ChevronLeft size={16} />
      </button>
      <span className="text-sm font-mono w-16 text-center">
        {currentPage + 1} / {totalPages}
      </span>
      <button
        onClick={onNext}
        disabled={disabled || currentPage >= totalPages - 1}
        className="p-1 hover:bg-gray-100 rounded disabled:opacity-30 disabled:cursor-not-allowed"
      >
        <ChevronRight size={16} />
      </button>
    </div>
  </div>
));

// LRU Cache implementation for image comparison results
class LRUCache {
  constructor(maxSize = 10) {
    this.maxSize = maxSize;
    this.cache = new Map();
  }

  get(key) {
    if (this.cache.has(key)) {
      // Move to end (most recently used)
      const value = this.cache.get(key);
      this.cache.delete(key);
      this.cache.set(key, value);
      return value;
    }
    return undefined;
  }

  set(key, value) {
    if (this.cache.size >= this.maxSize) {
      // Remove least recently used (first item in Map)
      const firstKey = this.cache.keys().next().value;
      this.cache.delete(firstKey);
    }
    this.cache.set(key, value);
  }

  clear() {
    this.cache.clear();
  }

  get size() {
    return this.cache.size;
  }
}

const ImageComparePage = () => {
  const navigate = useNavigate();
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [file1, setFile1] = useState(null);
  const [file2, setFile2] = useState(null);
  const [page1, setPage1] = useState(0);
  const [page2, setPage2] = useState(0);
  const [file1Pages, setFile1Pages] = useState(1);
  const [file2Pages, setFile2Pages] = useState(1);
  const [resetKey, setResetKey] = useState(0);
  const [isResetHovered, setIsResetHovered] = useState(false);
  const [isSyncNav, setIsSyncNav] = useState(true);
  
  // 사용자 설정 (색상 등)
  const [userSettings, setUserSettings] = useState(null);

  useEffect(() => {
    // 앱 진입 시 사용자 설정 로드
    const loadSettings = async () => {
      try {
        const data = await settingsApi.getSettings();
        if (data && data.preferences && data.preferences.image_inspector) {
          const imageInspectorSettings = data.preferences.image_inspector;
          const alignmentAlgorithm = normalizeAlignmentAlgorithm(imageInspectorSettings.alignment_algorithm || 'orb');
          setUserSettings(imageInspectorSettings);
          setSettings(prev => ({
            ...prev,
            alignmentAlgorithm,
          }));
        }
      } catch (error) {
        console.error('Failed to load user settings:', error);
      }
    };
    loadSettings();
  }, []);
  
// Cache for storing comparison results to avoid re-fetching
  const resultCache = useRef(new LRUCache(10));
  
  const [settings, setSettings] = useState({
    mode: 'difference',
    diffThreshold: 30,
    featureCount: 4000,
    alignmentAlgorithm: 'orb',
    cadLineWidth: 0.2,
    cadLineWidthEnabled: false,
    hideHatchTransparency: false,
    cadAlignTolerance: 0.22,
    cadQualityThreshold: 0.35,
  });
  const [resultData, setResultData] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  // CROP 관련 상태
  const [cropRect, setCropRect] = useState(null);           // { x, y, width, height } 0-1 정규화 또는 null
  const [showCropSelector, setShowCropSelector] = useState(false);
  const [cropPreviewImage, setCropPreviewImage] = useState(null);    // base64 string (data URI 제외)
  const [cropPreviewCacheKey, setCropPreviewCacheKey] = useState(null);
  const [cropPreviewLoading, setCropPreviewLoading] = useState(false);
  const isCadAlgorithm = isDrawingHybridAlgorithm(settings.alignmentAlgorithm);
  const isCadLineWidthActive = isCadAlgorithm && settings.cadLineWidthEnabled;
  const isCadPreprocessActive = isCadAlgorithm && (settings.cadLineWidthEnabled || settings.hideHatchTransparency);

  // 모드 변경 시 캐시된 결과의 _currentMode만 업데이트 (API 재호출 없음)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (resultData && resultData._currentMode !== settings.mode) {
      setResultData(prev => prev ? { ...prev, _currentMode: settings.mode } : null);
    }
  }, [settings.mode]);  // resultData 제외: 모드 변경 시에만 트리거

  useEffect(() => {
    setCropPreviewImage(null);
    setCropPreviewCacheKey(null);
  }, [
    file1,
    page1,
    settings.alignmentAlgorithm,
    settings.cadLineWidthEnabled,
    settings.cadLineWidth,
    settings.hideHatchTransparency,
    userSettings?.pdf_dpi,
  ]);

const handleFile1Select = useCallback((file, page) => {
    setFile1(file);
    setPage1(page);
    setFile1Pages(1); // Reset page count on new file
    setResultData(null);
    resultCache.current.clear(); // Clear cache when file changes
    // 파일 교체 시 crop 해제
    setCropRect(null);
    setCropPreviewImage(null);
    setCropPreviewCacheKey(null);
  }, []);

  const handleFile2Select = useCallback((file, page) => {
    setFile2(file);
    setPage2(page);
    setFile2Pages(1); // Reset page count on new file
    setResultData(null);
    resultCache.current.clear(); // Clear cache when file changes
  }, []); // file2 교체 시 crop은 유지 (crop은 file1 기준)

  const handleCompare = useCallback(async (overridePage1, overridePage2, overrideCropRect) => {
    if (!file1 || !file2) {
      setError('두 개의 파일을 모두 업로드해주세요.');
      return;
    }

    const p1 = typeof overridePage1 === 'number' ? overridePage1 : page1;
    const p2 = typeof overridePage2 === 'number' ? overridePage2 : page2;
    // overrideCropRect가 undefined인 경우 현재 state cropRect 사용, null이면 crop 없음
    const activeCropRect = overrideCropRect !== undefined ? overrideCropRect : cropRect;

    // 캐시 키: 파일+페이지+품질 설정만 (mode 제외 → 모드 변경 시 캐시 재사용)
    const qualityKey = userSettings
      ? `q${userSettings.output_quality ?? 85}-r${userSettings.output_resolution ?? 2000}-p${userSettings.processing_resolution ?? 6000}-d${userSettings.pdf_dpi ?? 300}`
      : 'q-default';
    const cropKey = activeCropRect
      ? `crop(${activeCropRect.x.toFixed(4)},${activeCropRect.y.toFixed(4)},${activeCropRect.width.toFixed(4)},${activeCropRect.height.toFixed(4)})`
      : 'nocrop';
    const cadKey = isCadAlgorithm
      ? `cad-lw${settings.cadLineWidth}-en${settings.cadLineWidthEnabled ? 1 : 0}-hh${settings.hideHatchTransparency ? 1 : 0}-tol${settings.cadAlignTolerance}-qt${settings.cadQualityThreshold}`
      : 'std';
    const cacheKey = `${settings.alignmentAlgorithm}-${p1}-${p2}-${settings.diffThreshold}-${settings.featureCount}-${cadKey}-${qualityKey}-${cropKey}`;

    // Check cache first - return immediately without triggering loading state
    const cachedResult = resultCache.current.get(cacheKey);
    if (cachedResult) {
      // 캐시된 결과에 현재 모드 반영
      setResultData({ ...cachedResult, _currentMode: settings.mode });
      if (cachedResult.metadata) {
        if (cachedResult.metadata.file1_pages) setFile1Pages(cachedResult.metadata.file1_pages);
        if (cachedResult.metadata.file2_pages) setFile2Pages(cachedResult.metadata.file2_pages);
      }
      return;
    }

    // Save current scroll position before loading
    const mainContent = document.querySelector('.flex-1.overflow-auto');
    const scrollTop = mainContent?.scrollTop || 0;

    setError(null);
    setIsLoading(true);

    try {
      const commonParams = {
        file1,
        file2,
        mode: settings.mode,
        diffThreshold: settings.diffThreshold,
        featureCount: settings.featureCount,
        alignmentAlgorithm: settings.alignmentAlgorithm,
        page1: p1,
        page2: p2,
        cadMode: isCadAlgorithm,
        cadLineWidth: settings.cadLineWidth,
        cadLineWidthEnabled: settings.cadLineWidthEnabled,
        applyLineWidth: settings.cadLineWidthEnabled,
        hideHatchTransparency: settings.hideHatchTransparency,
        cadAlignTolerance: settings.cadAlignTolerance,
        cadQualityThreshold: settings.cadQualityThreshold,
        cropRect: activeCropRect ?? undefined,
        colors: userSettings
          ? {
              diff_file1:  userSettings.diff_file1,
              diff_file2:  userSettings.diff_file2,
              diff_common: userSettings.diff_common,
            }
          : null,
        quality: userSettings
          ? {
              output_quality:        userSettings.output_quality,
              output_resolution:     userSettings.output_resolution,
              processing_resolution: userSettings.processing_resolution,
              pdf_dpi:               userSettings.pdf_dpi,
            }
          : null,
      };

      // 비교 실행
      const result = await fastApi.compareImages({ ...commonParams });

      // Store result in cache (LRU automatically handles size limit)
      resultCache.current.set(cacheKey, result);

      // 현재 모드 정보 추가하여 state에 저장
      setResultData({ ...result, _currentMode: settings.mode });
      
      // Update total pages from metadata
      if (result.metadata) {
        if (result.metadata.file1_pages) setFile1Pages(result.metadata.file1_pages);
        if (result.metadata.file2_pages) setFile2Pages(result.metadata.file2_pages);
      }

      // Restore scroll position after a short delay
      setTimeout(() => {
        if (mainContent) {
          mainContent.scrollTop = scrollTop;
        }
      }, 50);

    } catch (err) {
      console.error('Image comparison failed:', err);
      
      if (err.response?.status === 413) {
        setError('파일 크기가 너무 큽니다. 30MB 이하의 파일을 사용해주세요.');
      } else if (err.response?.status === 429) {
        setError('동시 처리 제한에 도달했습니다. 잠시 후 다시 시도해주세요.');
      } else if (err.response?.status === 504) {
        setError('처리 시간이 초과되었습니다. 잠시 후 다시 시도해주세요.');
      } else if (err.code === 'ECONNABORTED' || /timeout/i.test(err.message || '')) {
        setError('비교 처리 시간이 초과되었습니다. 잠시 후 다시 시도해주세요.');
      } else if (err.request && !err.response) {
        setError('서버 응답을 받지 못했습니다. 네트워크 상태 또는 처리 시간을 확인해주세요.');
      } else if (err.response?.data?.detail) {
        setError(err.response.data.detail);
      } else {
        setError('이미지 비교 중 오류가 발생했습니다. 다시 시도해주세요.');
      }
    } finally {
      setIsLoading(false);
    }
  }, [settings, userSettings, file1, file2, page1, page2, cropRect, isCadAlgorithm]);

const handleReset = useCallback(() => {
    // Reset all states
    setFile1(null);
    setFile2(null);
    setPage1(0);
    setPage2(0);
    setFile1Pages(1);
    setFile2Pages(1);
    setResultData(null);
    setError(null);
    setResetKey(prev => prev + 1); // Force re-render of components with this key
    resultCache.current.clear(); // Clear cache on reset
    // CROP 초기화
    setCropRect(null);
    setCropPreviewImage(null);
    setCropPreviewCacheKey(null);
    setShowCropSelector(false);
  }, []);

  // CROP 버튼 클릭: file1 preview 이미지 준비 후 CropSelector 오픈
  const handleCropButtonClick = useCallback(async () => {
    if (!file1) return;
    const currentPreviewKey = [
      file1.name,
      file1.size,
      file1.lastModified,
      page1,
      settings.alignmentAlgorithm,
      settings.cadLineWidthEnabled ? 'lw-on' : 'lw-off',
      settings.cadLineWidth,
      settings.hideHatchTransparency ? 'hh-on' : 'hh-off',
      userSettings?.pdf_dpi ?? 150,
    ].join(':');

    if (cropPreviewImage && cropPreviewCacheKey === currentPreviewKey) {
      setShowCropSelector(true);
      return;
    }

    setCropPreviewLoading(true);
    try {
      const previewResult = await fastApi.previewFile({
        file: file1,
        page: page1,
        pdfDpi: userSettings?.pdf_dpi ?? 150,
        cadMode: isCadPreprocessActive,
        cadLineWidth: settings.cadLineWidth,
        applyLineWidth: settings.cadLineWidthEnabled,
        hideHatchTransparency: settings.hideHatchTransparency,
      });
      setCropPreviewImage(previewResult.image_base64);
      setCropPreviewCacheKey(currentPreviewKey);
      setShowCropSelector(true);
    } catch (err) {
      console.error('Preview failed:', err);
      setError('미리보기 로드에 실패했습니다.');
    } finally {
      setCropPreviewLoading(false);
    }
  }, [file1, page1, cropPreviewImage, cropPreviewCacheKey, settings.alignmentAlgorithm, settings.cadLineWidthEnabled, settings.cadLineWidth, settings.hideHatchTransparency, userSettings, isCadPreprocessActive]);

  // CropSelector에서 영역 확정 → crop 설정만 반영하고 비교 결과는 초기화
  const handleCropApply = useCallback((rect) => {
    setCropRect(rect);
    setShowCropSelector(false);
    setResultData(null);
    setError(null);
  }, []);

  // CROP 해제
  const handleCropReset = useCallback(() => {
    setCropRect(null);
    setCropPreviewImage(null);
    setCropPreviewCacheKey(null);
    setResultData(null);
    setError(null);
  }, []);

const changePage = useCallback((fileNum, delta) => {
    if (isSyncNav) {
      // Synchronized navigation
      // Calculate target page based on the file that triggered the change
      const currentBasePage = fileNum === 1 ? page1 : page2;
      const targetPage = currentBasePage + delta;

      // Determine new pages for both files, clamping to their respective limits
      const newPage1 = Math.min(Math.max(0, targetPage), file1Pages - 1);
      const newPage2 = Math.min(Math.max(0, targetPage), file2Pages - 1);

      // If neither changed (e.g. both at start/end), do nothing
      if (newPage1 === page1 && newPage2 === page2) return;

      setPage1(newPage1);
      setPage2(newPage2);
      handleCompare(newPage1, newPage2);
    } else {
      // Independent navigation
      let newPage, otherPage;

      if (fileNum === 1) {
        newPage = Math.max(0, Math.min(page1 + delta, file1Pages - 1));
        if (newPage === page1) return;
        setPage1(newPage);
        otherPage = page2;
        handleCompare(newPage, otherPage);
      } else {
        newPage = Math.max(0, Math.min(page2 + delta, file2Pages - 1));
        if (newPage === page2) return;
        setPage2(newPage);
        otherPage = page1;
        handleCompare(otherPage, newPage);
      }
    }
  }, [isSyncNav, page1, page2, file1Pages, file2Pages, handleCompare]);

const handleDownload = useCallback((base64Data, metadata) => {
    const byteString = atob(base64Data.split(',')[1]);
    const mimeString = base64Data.split(',')[0].split(':')[1].split(';')[0];
    const ab = new ArrayBuffer(byteString.length);
    const ia = new Uint8Array(ab);

    for (let i = 0; i < byteString.length; i++) {
      ia[i] = byteString.charCodeAt(i);
    }

    const blob = new Blob([ab], { type: mimeString });
    const url = URL.createObjectURL(blob);

    const link = document.createElement('a');
    link.href = url;
    link.download = `comparison_overlay_${Date.now()}.png`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }, []);

const handleLogout = useCallback(async () => {
    try {
      sessionStorage.setItem('returnTo', '/image-compare');
      await authApi.logout();
    } catch (error) {
      console.error('[Logout] Backend logout failed:', error);
    } finally {
      const returnTo = sessionStorage.getItem('returnTo');
      sessionStorage.clear();
      if (returnTo) sessionStorage.setItem('returnTo', returnTo);
      navigate('/login');
    }
  }, []);

  const canCompare = file1 && file2 && !isLoading;
  const canCrop = file1 && !isLoading;
  const username = sessionStorage.getItem('username') || 'User';
  const userEmail = sessionStorage.getItem('email') || '';

  return (
    <>
    <div className="flex h-screen bg-[var(--bg-primary)] overflow-hidden">
      {/* Sidebar - Extracted to component */}
      <ImageCompareSidebar 
        isOpen={isSidebarOpen}
        toggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)}
        username={username}
        userEmail={userEmail}
        handleLogout={handleLogout}
        handleReset={handleReset}
        setIsResetHovered={setIsResetHovered}
        isResetHovered={isResetHovered}
        resetKey={resetKey}
        handleFile1Select={handleFile1Select}
        handleFile2Select={handleFile2Select}
        settings={settings}
        setSettings={setSettings}
        colors={userSettings}
        handleCompare={handleCompare}
        canCompare={canCompare}
        canCrop={canCrop}
        isLoading={isLoading}
        cropRect={cropRect}
        onCropClick={handleCropButtonClick}
        onCropReset={handleCropReset}
        cropPreviewLoading={cropPreviewLoading}
      />

      {/* Main Area */}
      <main className="flex-1 flex flex-col overflow-hidden relative">
        {/* Toggle Button when sidebar closed */}
        {!isSidebarOpen && (
          <button
            onClick={() => setIsSidebarOpen(true)}
            className="absolute top-4 left-4 z-40 p-2 bg-white shadow-md rounded-lg text-gray-600 hover:text-blue-600"
          >
            <Menu size={20} />
          </button>
        )}

        {/* Unified Error Banner (Replaces previous Header) */}
        {error ? (
          <div className="flex-shrink-0 bg-red-50 text-red-600 px-4 py-3 text-sm flex items-center gap-2 border-b border-red-100 z-50">
            <AlertCircle size={16} />
            {error}
            <button 
              onClick={() => setError(null)} 
              className="ml-auto text-xs hover:underline"
            >
              닫기
            </button>
          </div>
        ) : (
          /* Simple Header purely for Title when no error */
          <header className={`flex-shrink-0 h-16 flex items-center justify-between px-6 bg-[var(--bg-primary)]/80 backdrop-blur-md z-10 transition-all ${!isSidebarOpen ? 'pl-20' : ''}`}>
             <div>
              <h2 className="text-lg font-bold text-[var(--text-primary)]">
                이미지/도면 비교 분석
              </h2>
            </div>
          </header>
        )}

        <div className="flex-1 overflow-auto p-6 relative flex flex-col">
          {isLoading && <LoadingOverlay />}
          
          <ResultViewer
            resultData={resultData}
            onDownload={handleDownload}
            colors={userSettings}
          />
        </div>

        {/* Page Selector Footer */}
        {(file1Pages > 1 || file2Pages > 1) && (
          <div className="flex-shrink-0 h-20 bg-[var(--bg-primary)] flex items-center justify-center gap-10 px-6 z-10 relative">
            
            {/* Sync Toggle */}
            <div className="absolute left-6 flex items-center gap-2">
              <button
                onClick={() => setIsSyncNav(!isSyncNav)}
                className={`
                  flex items-center gap-2 px-3 py-2 text-sm transition-all
                  ${isSyncNav 
                    ? 'text-blue-700 font-medium' 
                    : 'text-gray-600'
                  }
                `}
              >
                <Link size={16} className={isSyncNav ? 'text-blue-500' : 'text-gray-400'} />
                1,2 동시 이동
                <div className={`
                  w-4 h-4 rounded border flex items-center justify-center ml-1 transition-colors
                  ${isSyncNav ? 'bg-blue-500 border-blue-500' : 'border-gray-400 bg-white'}
                `}>
                  {isSyncNav && <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" /></svg>}
                </div>
              </button>
            </div>

            {file1Pages > 1 && (
              <PageControl
                label=""
                currentPage={page1}
                totalPages={file1Pages}
                onPrev={() => changePage(1, -1)}
                onNext={() => changePage(1, 1)}
                disabled={isLoading}
              />
            )}
            
            {/* Divider if both exist */}
            {file1Pages > 1 && file2Pages > 1 && (
              <div className="w-px h-10 bg-gray-300"></div>
            )}

            {file2Pages > 1 && (
              <PageControl
                label=""
                currentPage={page2}
                totalPages={file2Pages}
                onPrev={() => changePage(2, -1)}
                onNext={() => changePage(2, 1)}
                disabled={isLoading}
              />
            )}
          </div>
        )}
      </main>
    </div>

    {/* CropSelector 모달 - 전체화면 오버레이 */}
    {showCropSelector && cropPreviewImage && (
      <CropSelector
        previewImage={cropPreviewImage}
        onApply={handleCropApply}
        onCancel={() => setShowCropSelector(false)}
      />
    )}
    </>
  );
};

export default ImageComparePage;
