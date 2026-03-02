import React, { useState, useRef, useCallback } from 'react';
import { Menu, AlertCircle } from 'lucide-react';
import { GraphicWalker } from '@kanaries/graphic-walker';
import DataExplorerSidebar from './components/DataExplorerSidebar';
import ColumnConfigModal from './components/ColumnConfigModal';
import PresetSaveModal from './components/PresetSaveModal';
import DeleteConfirmModal from './components/DeleteConfirmModal';
import RebuildModal from './components/RebuildModal';
import { dataExplorerApi, presetApi } from '../../api/djangoApi';

const DataExplorerPage = () => {
  // User info from session storage
  const username = sessionStorage.getItem('username') || 'User';
  const userEmail = sessionStorage.getItem('email') || '';
  
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  
  // 현재 선택된 파일명 (세션 키)
  const [currentFile, setCurrentFile] = useState(null);
  // 화면에 표시될 파일명
  const [displayName, setDisplayName] = useState(null);
  
  // 서버 데이터셋 여부 (업로드 파일인 경우 false -> Preset 저장 비활성화)
  const [isServerDataset, setIsServerDataset] = useState(false);
  
  // Graphic Walker Fields (Schema)
  const [fields, setFields] = useState([]);
  
  // 데이터셋 행 개수
  const [rowCount, setRowCount] = useState(null);

  // 서버 데이터셋 목록 상태 (캐싱용)
  const [serverDatasets, setServerDatasets] = useState([]);

  // Column Config Modal states
  const [modalOpen, setModalOpen] = useState(false);
  const [pendingFile, setPendingFile] = useState(null);
  const [pendingDisplayName, setPendingDisplayName] = useState(null);
  const [previewData, setPreviewData] = useState([]);
  const [detectedColumns, setDetectedColumns] = useState([]);
  // 업로드 파일 구분용 플래그
  const [pendingIsUpload, setPendingIsUpload] = useState(false);

  // ==== Preset 기능 관련 상태 ====
  // Graphic Walker storeRef - 차트 상태 접근용
  const storeRef = useRef(null);

  // 429 throttle 만료 타임스탬프 (ms) - 이 시각 이전에는 API 호출 차단
  const throttledUntilRef = useRef(null);
  // 429 에러 배너 자동 닫기 타이머 ID
  const errorTimerRef = useRef(null);
  
  // Preset 목록
  const [presets, setPresets] = useState([]);
  
  // Admin 여부 (Backend에서 반환)
  const [isAdmin, setIsAdmin] = useState(false);
  
  // Preset 저장 모달
  const [presetSaveModalOpen, setPresetSaveModalOpen] = useState(false);
  
  // 현재 선택된 컬럼 설정 (Preset 저장 시 필요)
  const [selectedColumns, setSelectedColumns] = useState([]);
  
  // Preset 로딩 중 (chart prop으로 전달할 차트 spec)
  const [chartSpec, setChartSpec] = useState(null);
  
  // 삭제 확인 모달 상태
  const [deleteConfirmModalOpen, setDeleteConfirmModalOpen] = useState(false);
  const [pendingDeletePreset, setPendingDeletePreset] = useState(null);
  const [deleteLoading, setDeleteLoading] = useState(false);

  // ==== Rebuild 기능 관련 상태 ====
  const [rebuildModal, setRebuildModal] = useState({
    isOpen: false,
    mode: null,     // "multi" | "single" | "empty"
    files: [],      // For multi mode - files with status
    pendingFile: null,  // For single mode - the file user clicked
  });
  // 개별 파일 클릭 후 리빌드 완료시 자동 로드할 파일명
  const [pendingLoadAfterRebuild, setPendingLoadAfterRebuild] = useState(null);
  // Preset 리빌드 후 로드할 Preset 데이터 (캐시 rebuild 후 Preset 로드 계속)
  const [pendingPresetAfterRebuild, setPendingPresetAfterRebuild] = useState(null);

  // 파일 선택/업로드 시 기존 차트 영역을 즉시 초기화
  const resetChartArea = useCallback(() => {
    setCurrentFile(null);
    setFields([]);
    setDisplayName(null);
    setRowCount(null);
    setChartSpec(null);
    setSelectedColumns([]);
    setIsServerDataset(false);
  }, []);

  // 데이터셋 목록 로드
  React.useEffect(() => {
    const fetchDatasets = async () => {
      try {
        const response = await dataExplorerApi.getDatasets();
        setServerDatasets(response.datasets || []);
      } catch (err) {
        console.error("Failed to fetch server datasets:", err);
      }
    };
    fetchDatasets();
  }, []);

  // Preset 목록 로드
  React.useEffect(() => {
    const fetchPresets = async () => {
      try {
        const response = await presetApi.list();
        setPresets(response.presets || []);
        setIsAdmin(response.is_admin || false);
      } catch (err) {
        console.error("Failed to fetch presets:", err);
      }
    };
    fetchPresets();
  }, []);

  // Preset 목록 새로고침
  const refreshPresets = useCallback(async () => {
    try {
      const response = await presetApi.list();
      setPresets(response.presets || []);
    } catch (err) {
      console.error("Failed to refresh presets:", err);
    }
  }, []);

  // ==== Preset 저장 핸들러 ====
  const handleOpenPresetSaveModal = useCallback(() => {
    if (!currentFile || !fields.length) {
      setError("저장할 차트가 없습니다. 먼저 데이터셋을 로드하세요.");
      return;
    }
    setPresetSaveModalOpen(true);
  }, [currentFile, fields]);

  const handleSavePreset = useCallback(async (presetData) => {
    // presetData: { name, description, is_public }
    setPresetSaveModalOpen(false);
    setIsLoading(true);
    setError(null);

    try {
      // 현재 차트 상태 추출
      let chartToSave = null;
      if (storeRef.current) {
        const allCharts = storeRef.current.exportCode();
        const currentIndex = storeRef.current.visIndex || 0;
        chartToSave = allCharts?.[currentIndex] || allCharts?.[0];
      }

      if (!chartToSave) {
        throw new Error("차트 상태를 추출할 수 없습니다.");
      }

      const fullPresetData = {
        name: presetData.name,
        description: presetData.description || "",
        is_public: presetData.is_public || false,  // Public visibility
        data_config: {
          filename: currentFile,
          selectedColumns: selectedColumns,
        },
        chart_spec: chartToSave,
        fields_meta: fields,
      };

      const response = await presetApi.create(fullPresetData);
      
      if (response.success) {
        await refreshPresets();
        setError(null);
      } else {
        throw new Error("프리셋 저장에 실패했습니다.");
      }
    } catch (err) {
      console.error("Preset save error:", err);
      const errorMessage = err.response?.data?.errors 
        ? JSON.stringify(err.response.data.errors) 
        : err.message || "프리셋 저장에 실패했습니다.";
      setError(errorMessage);
    } finally {
      setIsLoading(false);
    }
  }, [currentFile, selectedColumns, fields, refreshPresets]);

  // ==== Preset 로드 핸들러 ====
  const handleLoadPreset = useCallback(async (presetId) => {
    resetChartArea();
    setIsLoading(true);
    setError(null);

    try {
      const response = await presetApi.get(presetId);
      
      if (!response.success) {
        throw new Error("프리셋을 불러올 수 없습니다.");
      }

      const preset = response.preset;
      
      // 파일 존재 여부 확인
      if (!preset.file_exists) {
        throw new Error(`원본 데이터 파일 '${preset.data_config?.filename}'을 찾을 수 없습니다. 파일이 삭제되었거나 이동되었을 수 있습니다.`);
      }

      // file_changed는 cache status 체크에서 통합 처리됨 (RebuildModal로 사용자 확인)

      const { data_config } = preset;
      const filename = data_config.filename;

      // 캐시 상태 확인 (캐시가 없거나 stale이면 Rebuild 확인 필요)
      const cacheStatus = await dataExplorerApi.getCacheStatus(filename);
      const fileStatus = cacheStatus.files?.[0];
      
      if (fileStatus && (fileStatus.status === 'stale' || fileStatus.status === 'none')) {
        // 캐시 rebuild 필요 - 사용자 확인 팝업
        setPendingPresetAfterRebuild(preset);  // Rebuild 후 로드할 Preset 저장
        setRebuildModal({
          isOpen: true,
          mode: 'single',
          files: [],
          pendingFile: filename,
        });
        setIsLoading(false);
        return;  // Rebuild 확인 후 진행
      }

      // 캐시가 valid - 바로 Preset 로드 진행
      await loadPresetInternal(preset);

    } catch (err) {
      console.error("Preset load error:", err);
      const errorMessage = err.response?.data?.error || err.message || "프리셋 로드에 실패했습니다.";
      setError(errorMessage);
      setIsLoading(false);
    }
  }, [resetChartArea]);

  // Preset 내부 로드 함수 (캐시 확인 후 호출됨)
  const loadPresetInternal = useCallback(async (preset) => {
    setIsLoading(true);
    setError(null);

    try {
      const { data_config, chart_spec, fields_meta } = preset;
      
      // 1. 세션 초기화 (저장된 컬럼 설정으로)
      const initResponse = await dataExplorerApi.initSession(
        data_config.filename,
        data_config.selectedColumns || null
      );

      if (!initResponse.success) {
        throw new Error("데이터셋 세션 초기화에 실패했습니다.");
      }

      // 2. 상태 설정
      setFields(fields_meta || initResponse.fields);
      setRowCount(initResponse.row_count);
      setCurrentFile(data_config.filename);
      setDisplayName(data_config.filename);
      setSelectedColumns(data_config.selectedColumns || []);
      setIsServerDataset(true);  // Preset은 항상 서버 데이터셋을 참조함
      
      // 3. 차트 스펙 설정 (GraphicWalker가 이 스펙으로 초기화됨)
      setChartSpec([chart_spec]);

    } catch (err) {
      console.error("Preset load error:", err);
      const errorMessage = err.response?.data?.error || err.message || "프리셋 로드에 실패했습니다.";
      setError(errorMessage);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // ==== Preset 삭제 핸들러 ====
  const handleDeletePreset = useCallback(async (preset) => {
    setPendingDeletePreset(preset);
    setDeleteConfirmModalOpen(true);
  }, []);

  // 삭제 확인 후 삭제 실행
  const handleConfirmDelete = useCallback(async () => {
    if (!pendingDeletePreset) return;
    
    setDeleteLoading(true);
    try {
      const response = await presetApi.delete(pendingDeletePreset.id);
      if (response.success) {
        setDeleteConfirmModalOpen(false);
        setPendingDeletePreset(null);
        await refreshPresets();
      }
    } catch (err) {
      console.error("Preset delete error:", err);
      const errorMsg = err.response?.data?.error || "삭제에 실패했습니다.";
      setError(errorMsg);
      setDeleteConfirmModalOpen(false);
      setPendingDeletePreset(null);
    } finally {
      setDeleteLoading(false);
    }
  }, [pendingDeletePreset, refreshPresets]);

  // ==== Rebuild 핸들러 ====
  
  // Rebuild 버튼 클릭 핸들러 (전체 캐시 상태 확인)
  const handleRebuildButtonClick = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    
    try {
      const response = await dataExplorerApi.getCacheStatus();
      const files = response.files || [];
      
      // Filter files that need rebuild
      const needsRebuild = files.filter(f => f.status === 'stale' || f.status === 'none');
      
      if (needsRebuild.length === 0) {
        // All caches are valid
        setRebuildModal({
          isOpen: true,
          mode: 'empty',
          files: [],
          pendingFile: null,
        });
      } else {
        // Show multi-select modal
        setRebuildModal({
          isOpen: true,
          mode: 'multi',
          files: files,
          pendingFile: null,
        });
      }
    } catch (err) {
      console.error("Failed to get cache status:", err);
      setError("캐시 상태 확인에 실패했습니다.");
    } finally {
      setIsLoading(false);
    }
  }, []);
  
  // Rebuild 모달 닫기
  const handleCloseRebuildModal = useCallback(() => {
    setRebuildModal({
      isOpen: false,
      mode: null,
      files: [],
      pendingFile: null,
    });
    setPendingLoadAfterRebuild(null);
    setPendingPresetAfterRebuild(null);
  }, []);
  
  // Rebuild 완료 콜백
  const handleRebuildComplete = useCallback((result) => {
    // Refresh dataset list
    dataExplorerApi.getDatasets()
      .then(response => setServerDatasets(response.datasets || []))
      .catch(console.error);
    
    // If there's a pending file to load after rebuild (single mode - file click)
    if (pendingLoadAfterRebuild && result.status === 'completed') {
      // Close modal and proceed to load
      handleCloseRebuildModal();
      // Load the file (call preview API to show column config modal)
      handleLoadDatasetInternal(pendingLoadAfterRebuild);
      return;
    }
    
    // If there's a pending preset to load after rebuild (single mode - preset click)
    if (pendingPresetAfterRebuild && result.status === 'completed') {
      const preset = pendingPresetAfterRebuild;
      // Close modal and proceed to load preset
      handleCloseRebuildModal();
      // Load the preset
      loadPresetInternal(preset);
      return;
    }
  }, [pendingLoadAfterRebuild, pendingPresetAfterRebuild, handleCloseRebuildModal, loadPresetInternal]);

  // Cancel 버튼 핸들러 - 앱 초기 상태로 리셋 (클라이언트 전용, API 호출 없음)
  const handleCancelModal = () => {
    // 단일 렌더 사이클에서 모든 상태 일괄 리셋 (React 18+ 자동 batching)
    setModalOpen(false);
    setPendingFile(null);
    setPendingDisplayName(null);
    setPreviewData([]);
    setDetectedColumns([]);
    setPendingIsUpload(false);
    setCurrentFile(null);
    setFields([]);
    setDisplayName(null);
    setRowCount(null);
    setError(null);
    setIsLoading(false);
    setChartSpec(null);
    setSelectedColumns([]);
    setIsServerDataset(false);
  };

  // OK 버튼 핸들러 - 선택된 컬럼으로 세션 초기화
  const handleConfirmColumns = async (columns) => {
    setModalOpen(false);
    setIsLoading(true);
    setError(null);
    setChartSpec(null); // 새 데이터셋 로드 시 차트 스펙 초기화
    
    // 업로드 파일인지 서버 데이터셋인지 저장
    const wasUpload = pendingIsUpload;
    
    try {
      // 세션 초기화 with user-selected columns
      const response = await dataExplorerApi.initSession(pendingFile, columns);
      
      if (response.success) {
        setFields(response.fields);
        setRowCount(response.row_count);
        setCurrentFile(pendingFile);
        setDisplayName(pendingDisplayName);
        setSelectedColumns(columns || []); // 선택된 컬럼 저장 (Preset용)
        setIsServerDataset(!wasUpload);    // 업로드 파일이 아니면 서버 데이터셋
      } else {
        throw new Error("Failed to initialize session");
      }
    } catch (err) {
      console.error(err);
      const errorMessage = err.response?.data?.error || err.message || "데이터셋 로드에 실패했습니다.";
      setError(errorMessage);
    } finally {
      setIsLoading(false);
      setPendingFile(null);
      setPendingDisplayName(null);
      setPreviewData([]);
      setDetectedColumns([]);
      setPendingIsUpload(false);
    }
  };

  const handleFileUpload = async (file) => {
    if (!file) return;
    resetChartArea();
    setIsLoading(true);
    setError(null);
    try {
      // 1. Upload File
      const uploadResponse = await dataExplorerApi.uploadDataset(file);
      
      // 2. Refresh Dataset List (Optional, but good for UX)
      try {
        const listResponse = await dataExplorerApi.getDatasets();
        setServerDatasets(listResponse.datasets || []);
      } catch (e) { console.warn("Failed to refresh list", e); }

      // 3. Get preview and show modal
      const previewResponse = await dataExplorerApi.previewDataset(uploadResponse.filename);
      
      if (previewResponse.success) {
        setPendingFile(uploadResponse.filename);
        setPendingDisplayName(uploadResponse.original_name || file.name);
        setPreviewData(previewResponse.preview);
        setDetectedColumns(previewResponse.detected_columns);
        setPendingIsUpload(true);  // 업로드 파일 표시
        setModalOpen(true);
      } else {
        throw new Error("Failed to get preview data");
      }
    } catch (err) {
      console.error(err);
      const errorMessage = err.response?.data?.error || err.message || "파일 업로드에 실패했습니다.";
      setError(errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  // [Computation Mode] 데이터셋 선택 핸들러 (캐시 상태 확인 → 필요시 Rebuild 팝업)
  const handleLoadDataset = async (filename) => {
    resetChartArea();
    setIsLoading(true);
    setError(null);

    try {
      // 1. Check cache status first
      const cacheStatus = await dataExplorerApi.getCacheStatus(filename);
      const fileStatus = cacheStatus.files?.[0];
      
      if (fileStatus && (fileStatus.status === 'stale' || fileStatus.status === 'none')) {
        // Cache needs rebuild - show single-mode confirmation
        setPendingLoadAfterRebuild(filename);  // 리빌드 후 자동 로드할 파일 저장
        setRebuildModal({
          isOpen: true,
          mode: 'single',
          files: [],
          pendingFile: filename,
        });
        setIsLoading(false);
        return;  // Don't proceed until rebuild is done
      }
      
      // 2. Cache is valid - proceed to load normally
      await handleLoadDatasetInternal(filename);
    } catch (err) {
      console.error(err);
      const errorMessage = err.response?.data?.error || err.message || "데이터셋 로드에 실패했습니다.";
      setError(errorMessage);
      setIsLoading(false);
    }
  };
  
  // 내부 데이터셋 로드 함수 (캐시 확인 후 호출됨)
  const handleLoadDatasetInternal = async (filename) => {
    setIsLoading(true);
    setError(null);

    try {
      // Get preview data
      const response = await dataExplorerApi.previewDataset(filename);
      
      if (response.success) {
        setPendingFile(filename);
        setPendingDisplayName(filename);
        setPreviewData(response.preview);
        setDetectedColumns(response.detected_columns);
        setPendingIsUpload(false);  // 서버 데이터셋 표시
        setModalOpen(true);
      } else {
        throw new Error("Failed to get preview data");
      }
    } catch (err) {
      console.error(err);
      const errorMessage = err.response?.data?.error || err.message || "데이터셋 로드에 실패했습니다.";
      setError(errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  // [Computation Mode] Graphic Walker용 Computation Provider
  // Graphic Walker가 쿼리가 필요할 때마다 이 함수를 호출합니다.
  const computation = React.useMemo(() => {
    if (!currentFile) return undefined;

    return async (query) => {
      // 429 throttle 차단 체크: 만료 시각 이전이면 API 호출 없이 조기 반환
      if (throttledUntilRef.current && Date.now() < throttledUntilRef.current) {
        return [];
      }

      try {
        const sql = query.sql || query; 
        const response = await dataExplorerApi.queryParams(currentFile, sql);
        // throttle 활성 중에는 성공 응답으로 에러 배너를 지우지 않음
        // (병렬 쿼리 중 일부 200 응답이 429 배너를 덮어쓰는 것 방지)
        if (!throttledUntilRef.current || Date.now() >= throttledUntilRef.current) {
          setError(null);
        }
        return response;
      } catch (err) {
        // Extract error details from response
        const statusCode = err.response?.status;
        const errorMessage = err.response?.data?.error || err.message || "쿼리 실행에 실패했습니다.";
        const errorDetail = err.response?.data?.detail;  // Only present in DEBUG mode

        // 429 전용 처리: Retry-After 헤더 활용 + 실질 차단
        if (statusCode === 429) {
          const retryAfterSec = parseInt(
            err.response?.headers?.['retry-after'] ||
            err.response?.headers?.['Retry-After'] ||
            '10',
            10
          );
          throttledUntilRef.current = Date.now() + retryAfterSec * 1000;
          setError(`요청 한도 초과. 약 ${retryAfterSec}초 후 자동 재개됩니다. (잠시 기다려주세요)`);
          // 기존 타이머 취소 후 Retry-After 시간 후 배너 자동 닫기
          if (errorTimerRef.current) clearTimeout(errorTimerRef.current);
          errorTimerRef.current = setTimeout(() => setError(null), retryAfterSec * 1000);
          return [];
        }

        // Provide context-appropriate error messages
        let displayMessage;
        switch (statusCode) {
          case 404:
            // Session expired - suggest reload
            displayMessage = `${errorMessage} 사이드바에서 데이터셋을 다시 선택해주세요.`;
            break;
          case 400:
            // Validation error (query or DSL parsing)
            displayMessage = `쿼리 오류: ${errorMessage}`;
            break;
          default:
            // Generic server error
            displayMessage = `쿼리 오류: ${errorMessage}`;
        }
        
        // Add debug detail if available
        if (errorDetail) {
          displayMessage += ` (${errorDetail})`;
        }
        
        setError(displayMessage);
        // Return empty array to prevent GraphicWalker crash
        return [];
      }
    };
  }, [currentFile]);

  return (
    <div className="flex h-screen bg-white overflow-hidden">
        {/* Sidebar */}
        <div className={`${
            isSidebarOpen ? 'w-80' : 'w-0'
        } flex-shrink-0 transition-all duration-300 ease-in-out overflow-hidden bg-[var(--bg-secondary)]`}>
             <DataExplorerSidebar 
                onClose={() => setIsSidebarOpen(false)}
                onFileUpload={handleFileUpload}
                onLoadLocalDataset={handleLoadDataset}
                serverDatasets={serverDatasets}
                isLoading={isLoading}
                // Preset props
                presets={presets}
                onSavePreset={handleOpenPresetSaveModal}
                onLoadPreset={handleLoadPreset}
                onDeletePreset={handleDeletePreset}
                canSavePreset={!!currentFile && fields.length > 0 && isServerDataset}
                isAdmin={isAdmin}
                // Rebuild props
                onRebuildClick={handleRebuildButtonClick}
                // User props
                username={username}
                userEmail={userEmail}
             />
        </div>

        {/* Main Content */}
        <div className={`flex-1 flex flex-col min-w-0 relative bg-white ${!isSidebarOpen ? 'pl-16' : ''}`}>
            {/* Toggle Button */}
            {!isSidebarOpen && (
                <button
                    onClick={() => setIsSidebarOpen(true)}
                    className="absolute top-4 left-4 z-50 p-2 bg-white shadow-md border rounded-lg text-gray-600 hover:text-blue-600 hover:bg-gray-50 transition-colors"
                >
                    <Menu size={20} />
                </button>
            )}

            {/* Error Banner */}
            {error && (
                <div className="flex-shrink-0 bg-red-50 text-red-600 px-4 py-3 text-sm flex items-center gap-2 border-b border-red-100 z-40">
                    <AlertCircle size={16} />
                    {error}
                    <button 
                        onClick={() => setError(null)} 
                        className="ml-auto text-xs hover:underline"
                    >
                        닫기
                    </button>
                </div>
            )}

            {/* Graphic Walker Area */}
            <div className="flex-1 w-full h-full relative overflow-auto">
                {!modalOpen && currentFile && fields.length > 0 ? (
                    <div className="w-full h-full p-4">
                        <div className="mb-2 text-sm text-gray-600">
                            <span className="font-semibold">{displayName}</span>
                            {rowCount !== null && (
                                <span className="text-gray-500">
                                    {' '}(rows: {rowCount.toLocaleString()}, columns: {fields.length})
                                </span>
                            )}
                        </div>
                        {/* Computation Mode: data prop is NOT used. store/computation prop is used. */}
                        {/* key prop forces remount when dataset changes */}
                        {/* storeRef allows accessing chart state for preset save */}
                        {/* chart prop loads saved preset visualization */}
                        <GraphicWalker
                            key={currentFile}
                            fields={fields}
                            appearance="light"
                            computation={computation}
                            storeRef={storeRef}
                            chart={chartSpec}
                            i18nLang="en-US"
                            hideDataSourceConfig={true}
                            hideProfiling={true}
                            experimentalFeatures={{ computedField: true }}
                            onError={(err) => setError(err.message)}
                        />
                    </div>
                ) : (
                    <div className="flex flex-col items-center justify-center h-full text-gray-400">
                        <p>왼쪽 사이드바에서 데이터셋을 선택하세요.</p>
                        <p className="text-sm mt-2 text-gray-300">(대용량 데이터 최적화 모드)</p>
                    </div>
                )}
            </div>
        </div>

        {/* Column Config Modal */}
        <ColumnConfigModal
          isOpen={modalOpen}
          onClose={handleCancelModal}
          onConfirm={handleConfirmColumns}
          filename={pendingDisplayName || pendingFile}
          previewData={previewData}
          detectedColumns={detectedColumns}
        />

        {/* Preset Save Modal */}
        <PresetSaveModal
          isOpen={presetSaveModalOpen}
          onClose={() => setPresetSaveModalOpen(false)}
          onSave={handleSavePreset}
          currentFilename={displayName || currentFile}
        />

        {/* Delete Confirm Modal for Preset Deletion */}
        <DeleteConfirmModal
          isOpen={deleteConfirmModalOpen}
          onClose={() => {
            setDeleteConfirmModalOpen(false);
            setPendingDeletePreset(null);
          }}
          onConfirm={handleConfirmDelete}
          presetName={pendingDeletePreset?.name || ''}
          isLoading={deleteLoading}
        />

        {/* Rebuild Modal */}
        <RebuildModal
          isOpen={rebuildModal.isOpen}
          onClose={handleCloseRebuildModal}
          mode={rebuildModal.mode}
          files={rebuildModal.files}
          pendingFile={rebuildModal.pendingFile}
          onComplete={handleRebuildComplete}
        />
    </div>
  );
};

export default DataExplorerPage;
