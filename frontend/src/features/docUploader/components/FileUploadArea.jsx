import React, { useState, useRef, useCallback } from 'react';
import { Upload, FileText, File, X, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';
import { docConverterApi } from '../../../api/fastapiApi';

const SUPPORTED_LABELS = [
  { ext: 'PDF', color: 'bg-red-100 text-red-600' },
  { ext: 'DOCX', color: 'bg-blue-100 text-blue-600' },
  { ext: 'PPTX', color: 'bg-orange-100 text-orange-600' },
  { ext: 'XLSX', color: 'bg-green-100 text-green-600' },
  { ext: 'TXT / MD', color: 'bg-gray-100 text-gray-600' },
];

const ACCEPTED_TYPES =
  '.pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.txt,.md';

function FileItem({ name, status, message }) {
  return (
    <div className="flex items-center gap-2 text-xs py-1">
      {status === 'uploading' && (
        <Loader2 size={13} className="animate-spin text-blue-500 shrink-0" />
      )}
      {status === 'done' && (
        <CheckCircle size={13} className="text-green-500 shrink-0" />
      )}
      {status === 'error' && (
        <AlertCircle size={13} className="text-red-500 shrink-0" />
      )}
      <span className="truncate text-gray-700">{name}</span>
      {message && <span className="text-gray-400 ml-auto shrink-0">{message}</span>}
    </div>
  );
}

export default function FileUploadArea({ selectedCategory, onUploadComplete }) {
  const [isDragging, setIsDragging] = useState(false);
  const [fileStatuses, setFileStatuses] = useState([]);
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef(null);

  const updateStatus = (index, patch) => {
    setFileStatuses((prev) =>
      prev.map((item, i) => (i === index ? { ...item, ...patch } : item))
    );
  };

  const processFiles = useCallback(
    async (files) => {
      if (!selectedCategory) {
        alert('카테고리를 먼저 선택하세요.');
        return;
      }

      const fileList = Array.from(files);
      const initial = fileList.map((f) => ({
        name: f.name,
        status: 'uploading',
        message: '',
      }));
      setFileStatuses(initial);
      setIsUploading(true);

      for (let i = 0; i < fileList.length; i++) {
        const f = fileList[i];
        try {
          await docConverterApi.uploadFile(f, selectedCategory);
          updateStatus(i, { status: 'done', message: '추가됨' });
        } catch (err) {
          const detail = err?.response?.data?.detail || err.message || '업로드 실패';
          updateStatus(i, { status: 'error', message: detail });
        }
      }

      setIsUploading(false);
      onUploadComplete?.();

      // 3초 후 목록 초기화
      setTimeout(() => setFileStatuses([]), 3000);
    },
    [selectedCategory, onUploadComplete]
  );

  // ── Drag & Drop 이벤트 ────────────────────────────────────────────────────
  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };
  const handleDragLeave = () => setIsDragging(false);
  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files.length > 0) {
      processFiles(e.dataTransfer.files);
    }
  };
  const handleInputChange = (e) => {
    if (e.target.files?.length > 0) {
      processFiles(e.target.files);
      e.target.value = '';
    }
  };

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-4">
      <h2 className="text-sm font-semibold text-gray-700 mb-3">문서 업로드</h2>

      {/* 드롭 영역 */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => !isUploading && fileInputRef.current?.click()}
        className={`
          flex flex-col items-center justify-center gap-2 border-2 border-dashed rounded-lg
          py-8 cursor-pointer transition-colors select-none
          ${isDragging ? 'border-blue-400 bg-blue-50' : 'border-gray-300 hover:border-blue-300 hover:bg-gray-50'}
          ${isUploading ? 'pointer-events-none opacity-60' : ''}
        `}
      >
        <Upload size={28} className="text-gray-400" />
        <p className="text-sm text-gray-600 font-medium">
          파일을 끌어다 놓거나 클릭하여 선택
        </p>
        <p className="text-xs text-gray-400">
          {selectedCategory
            ? `카테고리: ${selectedCategory}`
            : '왼쪽에서 카테고리를 먼저 선택하세요'}
        </p>
        <div className="flex gap-1 mt-1 flex-wrap justify-center">
          {SUPPORTED_LABELS.map((l) => (
            <span
              key={l.ext}
              className={`px-2 py-0.5 rounded text-xs font-medium ${l.color}`}
            >
              {l.ext}
            </span>
          ))}
        </div>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept={ACCEPTED_TYPES}
        onChange={handleInputChange}
        className="hidden"
      />

      {/* 업로드 진행 현황 */}
      {fileStatuses.length > 0 && (
        <div className="mt-3 border border-gray-100 rounded-lg px-3 py-2 bg-gray-50">
          {fileStatuses.map((item, i) => (
            <FileItem
              key={i}
              name={item.name}
              status={item.status}
              message={item.message}
            />
          ))}
        </div>
      )}
    </div>
  );
}
