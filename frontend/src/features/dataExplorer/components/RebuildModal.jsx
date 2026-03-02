/**
 * RebuildModal - DuckDB Cache Rebuild Modal
 * 
 * Three modes:
 * - "multi": Bulk rebuild selection (checkbox list)
 * - "single": Single file confirmation dialog
 * - "empty": No files need rebuild (info only)
 * 
 * Also handles progress display during rebuild execution.
 */

import { useState, useEffect, useRef } from 'react';
import { X, RefreshCw, AlertCircle, CheckCircle, XCircle, Loader2 } from 'lucide-react';
import { dataExplorerApi } from '@/api/djangoApi';

export default function RebuildModal({
  isOpen,
  onClose,
  mode,           // "multi" | "single" | "empty"
  files,          // Array of {name, status} objects
  pendingFile,    // For single mode - the file user clicked
  onComplete,     // Callback when rebuild completes successfully
}) {
  // Selection state (for multi mode)
  const [selectedFiles, setSelectedFiles] = useState(new Set());
  
  // Progress state
  const [isRebuilding, setIsRebuilding] = useState(false);
  const [taskId, setTaskId] = useState(null);
  const [progress, setProgress] = useState(null);
  
  // Error state
  const [error, setError] = useState(null);
  
  // Polling ref
  const pollIntervalRef = useRef(null);
  
  // Initialize selection when files change
  useEffect(() => {
    if (mode === 'multi' && files) {
      // Pre-select all stale/none files by default
      const needsRebuild = files
        .filter(f => f.status === 'stale' || f.status === 'none')
        .map(f => f.name);
      setSelectedFiles(new Set(needsRebuild));
    }
  }, [mode, files]);
  
  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, []);
  
  // Poll for task status
  const startPolling = (id) => {
    setTaskId(id);
    
    pollIntervalRef.current = setInterval(async () => {
      try {
        const status = await dataExplorerApi.getRebuildStatus(id);
        setProgress(status);
        
        // Stop polling when task is done
        if (['completed', 'partial', 'failed'].includes(status.status)) {
          clearInterval(pollIntervalRef.current);
          pollIntervalRef.current = null;
          
          // Notify completion
          if (status.status === 'completed' || status.status === 'partial') {
            onComplete?.(status);
          }
        }
      } catch (err) {
        console.error('Failed to poll rebuild status:', err);
        setError('상태 조회 실패');
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
    }, 1000); // Poll every second
  };
  
  // Handle start rebuild
  const handleStartRebuild = async () => {
    setError(null);
    setIsRebuilding(true);
    
    let filesToRebuild;
    if (mode === 'single') {
      filesToRebuild = [pendingFile];
    } else {
      filesToRebuild = Array.from(selectedFiles);
    }
    
    if (filesToRebuild.length === 0) {
      setError('선택된 파일이 없습니다.');
      setIsRebuilding(false);
      return;
    }
    
    try {
      const result = await dataExplorerApi.startRebuild(filesToRebuild);
      setProgress({
        task_id: result.task_id,
        status: 'pending',
        total: result.total,
        completed: 0,
        current: null,
        results: [],
      });
      startPolling(result.task_id);
    } catch (err) {
      console.error('Failed to start rebuild:', err);
      setError(err.response?.data?.error || 'Rebuild 시작 실패');
      setIsRebuilding(false);
    }
  };
  
  // Handle close
  const handleClose = () => {
    if (isRebuilding && progress?.status === 'running') {
      // Don't allow closing while running
      return;
    }
    
    // Cleanup
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
    setIsRebuilding(false);
    setTaskId(null);
    setProgress(null);
    setError(null);
    setSelectedFiles(new Set());
    
    onClose();
  };
  
  // Toggle file selection (multi mode)
  const toggleFile = (filename) => {
    const newSet = new Set(selectedFiles);
    if (newSet.has(filename)) {
      newSet.delete(filename);
    } else {
      newSet.add(filename);
    }
    setSelectedFiles(newSet);
  };
  
  // Select all / Deselect all
  const selectAll = () => {
    const needsRebuild = files
      .filter(f => f.status === 'stale' || f.status === 'none')
      .map(f => f.name);
    setSelectedFiles(new Set(needsRebuild));
  };
  
  const deselectAll = () => {
    setSelectedFiles(new Set());
  };
  
  if (!isOpen) return null;
  
  // Filter files that need rebuild (for multi mode)
  const filesNeedingRebuild = files?.filter(f => f.status === 'stale' || f.status === 'none') || [];
  
  // Render progress view
  const renderProgress = () => (
    <div className="space-y-4">
      {/* Progress bar */}
      <div>
        <div className="flex justify-between text-sm mb-1">
          <span>{progress?.current ? `처리 중: ${progress.current}` : '준비 중...'}</span>
          <span>{progress?.completed || 0} / {progress?.total || 0}</span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-2.5">
          <div 
            className="bg-blue-600 h-2.5 rounded-full transition-all duration-300"
            style={{ width: `${progress?.total ? (progress.completed / progress.total) * 100 : 0}%` }}
          />
        </div>
      </div>
      
      {/* Results list */}
      {progress?.results && progress.results.length > 0 && (
        <div className="max-h-48 overflow-y-auto border rounded p-2 text-sm space-y-1">
          {progress.results.map((result, idx) => (
            <div key={idx} className="flex items-center gap-2">
              {result.success ? (
                <CheckCircle className="w-4 h-4 text-green-500 flex-shrink-0" />
              ) : (
                <XCircle className="w-4 h-4 text-red-500 flex-shrink-0" />
              )}
              <span className="truncate flex-1">{result.name}</span>
              {result.success && (
                <span className="text-gray-500 text-xs">{result.row_count?.toLocaleString()} rows</span>
              )}
              {!result.success && (
                <span className="text-red-500 text-xs truncate" title={result.message}>
                  {result.message}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
      
      {/* Status message */}
      {progress?.status === 'completed' && (
        <div className="flex items-center gap-2 text-green-600">
          <CheckCircle className="w-5 h-5" />
          <span>모든 파일이 Rebuild 되었습니다.</span>
        </div>
      )}
      {progress?.status === 'partial' && (
        <div className="flex items-center gap-2 text-yellow-600">
          <AlertCircle className="w-5 h-5" />
          <span>일부 파일이 실패했습니다.</span>
        </div>
      )}
      {progress?.status === 'failed' && (
        <div className="flex items-center gap-2 text-red-600">
          <XCircle className="w-5 h-5" />
          <span>{progress.error || 'Rebuild에 실패했습니다.'}</span>
        </div>
      )}
    </div>
  );
  
  // Render different modes
  const renderContent = () => {
    // If rebuilding, show progress
    if (isRebuilding) {
      return (
        <div className="space-y-4">
          {renderProgress()}
          
          {/* Close button when done */}
          {['completed', 'partial', 'failed'].includes(progress?.status) && (
            <div className="flex justify-end">
              <button
                onClick={handleClose}
                className="px-4 py-2 bg-gray-100 text-gray-700 rounded hover:bg-gray-200"
              >
                닫기
              </button>
            </div>
          )}
        </div>
      );
    }
    
    // Empty mode
    if (mode === 'empty') {
      return (
        <div className="space-y-4">
          <div className="flex items-center gap-2 text-green-600">
            <CheckCircle className="w-5 h-5" />
            <span>모든 캐시가 최신 상태입니다.</span>
          </div>
          <div className="flex justify-end">
            <button
              onClick={handleClose}
              className="px-4 py-2 bg-gray-100 text-gray-700 rounded hover:bg-gray-200"
            >
              확인
            </button>
          </div>
        </div>
      );
    }
    
    // Single mode
    if (mode === 'single') {
      return (
        <div className="space-y-4">
          <div className="flex items-start gap-2 text-yellow-600">
            <AlertCircle className="w-5 h-5 mt-0.5 flex-shrink-0" />
            <div>
              <p>원본 파일이 변경되었습니다. Rebuild 하시겠습니까?</p>
              <p className="font-medium mt-1">{pendingFile}</p>
              <p className="text-sm text-gray-600 mt-2">
                Rebuild를 실행하면 최신 데이터로 캐시가 갱신됩니다.
              </p>
            </div>
          </div>
          
          {error && (
            <div className="text-red-600 text-sm flex items-center gap-1">
              <AlertCircle className="w-4 h-4" />
              {error}
            </div>
          )}
          
          <div className="flex justify-end gap-2">
            <button
              onClick={handleClose}
              className="px-4 py-2 bg-gray-100 text-gray-700 rounded hover:bg-gray-200"
            >
              취소
            </button>
            <button
              onClick={handleStartRebuild}
              className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 flex items-center gap-2"
            >
              <RefreshCw className="w-4 h-4" />
              Rebuild
            </button>
          </div>
        </div>
      );
    }
    
    // Multi mode (default)
    return (
      <div className="space-y-4">
        {/* File selection controls */}
        <div className="flex items-center justify-between">
          <span className="text-sm text-gray-600">
            {filesNeedingRebuild.length}개 파일 중 {selectedFiles.size}개 선택됨
          </span>
          <div className="flex gap-2">
            <button
              onClick={selectAll}
              className="text-xs px-2 py-1 bg-gray-100 text-gray-700 rounded hover:bg-gray-200"
            >
              전체 선택
            </button>
            <button
              onClick={deselectAll}
              className="text-xs px-2 py-1 bg-gray-100 text-gray-700 rounded hover:bg-gray-200"
            >
              선택 해제
            </button>
          </div>
        </div>
        
        {/* File list with checkboxes */}
        <div className="max-h-64 overflow-y-auto border rounded divide-y">
          {filesNeedingRebuild.length === 0 ? (
            <div className="p-4 text-center text-gray-500">
              Rebuild 필요한 파일이 없습니다.
            </div>
          ) : (
            filesNeedingRebuild.map(file => (
              <label 
                key={file.name}
                className="flex items-center gap-3 p-2 hover:bg-gray-50 cursor-pointer"
              >
                <input
                  type="checkbox"
                  checked={selectedFiles.has(file.name)}
                  onChange={() => toggleFile(file.name)}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="flex-1 truncate text-sm">{file.name}</span>
                <span className={`text-xs px-2 py-0.5 rounded ${
                  file.status === 'stale' 
                    ? 'bg-yellow-100 text-yellow-700' 
                    : 'bg-gray-100 text-gray-600'
                }`}>
                  {file.status === 'stale' ? '갱신 필요' : '캐시 없음'}
                </span>
              </label>
            ))
          )}
        </div>
        
        {error && (
          <div className="text-red-600 text-sm flex items-center gap-1">
            <AlertCircle className="w-4 h-4" />
            {error}
          </div>
        )}
        
        <div className="flex justify-end gap-2">
          <button
            onClick={handleClose}
            className="px-4 py-2 bg-gray-100 text-gray-700 rounded hover:bg-gray-200"
          >
            취소
          </button>
          <button
            onClick={handleStartRebuild}
            disabled={selectedFiles.size === 0}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed flex items-center gap-2"
          >
            <RefreshCw className="w-4 h-4" />
            Rebuild ({selectedFiles.size})
          </button>
        </div>
      </div>
    );
  };
  
  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-lg w-full max-h-[90vh] overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b">
          <div className="flex items-center gap-2">
            {isRebuilding && progress?.status === 'running' ? (
              <Loader2 className="w-5 h-5 text-blue-600 animate-spin" />
            ) : (
              <RefreshCw className="w-5 h-5 text-blue-600" />
            )}
            <h3 className="font-semibold text-lg">DuckDB Cache Rebuild</h3>
          </div>
          {(!isRebuilding || ['completed', 'partial', 'failed'].includes(progress?.status)) && (
            <button
              onClick={handleClose}
              className="text-gray-400 hover:text-gray-600"
            >
              <X className="w-5 h-5" />
            </button>
          )}
        </div>
        
        {/* Content */}
        <div className="p-4">
          {renderContent()}
        </div>
      </div>
    </div>
  );
}