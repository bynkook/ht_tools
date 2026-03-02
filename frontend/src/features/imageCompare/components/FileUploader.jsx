import React, { useState, useRef } from 'react';
import { Upload, X, FileImage, File as FileIcon } from 'lucide-react';

const FileUploader = ({ onFileSelect, label, accept = "image/*,application/pdf,.tif,.tiff", maxSizeMB = 30 }) => {
  const [selectedFile, setSelectedFile] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [pageCount, setPageCount] = useState(1);
  const [selectedPage, setSelectedPage] = useState(0);
  const fileInputRef = useRef(null);

  const handleFileChange = (file) => {
    if (!file) return;

    // 파일 크기 검증
    const fileSizeMB = file.size / 1024 / 1024;
    if (fileSizeMB > maxSizeMB) {
      alert(`파일 크기가 너무 큽니다. 최대 ${maxSizeMB}MB까지 업로드 가능합니다.`);
      return;
    }

    setSelectedFile(file);
    
    // PDF 또는 TIFF인 경우 다중 페이지 가능성 설정
    const isMultiPage = file.type === 'application/pdf' || 
                        file.type === 'image/tiff' || 
                        file.type === 'image/tif' ||
                        file.name.toLowerCase().endsWith('.tif') ||
                        file.name.toLowerCase().endsWith('.tiff');
    
    if (isMultiPage) {
      setPageCount(1); // 백엔드에서 실제 페이지 수를 반환받을 수 있음
    }
    
    onFileSelect(file, 0); // 초기 페이지는 0
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    
    const file = e.dataTransfer.files[0];
    handleFileChange(file);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleRemove = () => {
    setSelectedFile(null);
    setPageCount(1);
    setSelectedPage(0);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
    onFileSelect(null, 0);
  };

  const handlePageChange = (newPage) => {
    setSelectedPage(newPage);
    onFileSelect(selectedFile, newPage);
  };

  const isMultiPage = selectedFile && (
    selectedFile.type === 'application/pdf' || 
    selectedFile.type === 'image/tiff' || 
    selectedFile.type === 'image/tif' ||
    selectedFile.name.toLowerCase().endsWith('.tif') ||
    selectedFile.name.toLowerCase().endsWith('.tiff')
  );

  return (
    <div className="w-full">
      <label className="block text-sm font-medium text-[var(--text-primary)] mb-2">
        {label}
      </label>
      
      {!selectedFile ? (
        <div
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onClick={() => fileInputRef.current?.click()}
          className={`
            relative border-2 border-dashed rounded-lg p-8 text-center cursor-pointer
            transition-all duration-200
            ${isDragging 
              ? 'border-blue-500 bg-blue-50' 
              : 'border-gray-300 hover:border-gray-400 bg-gray-50'
            }
          `}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept={accept}
            onChange={(e) => handleFileChange(e.target.files[0])}
            className="hidden"
          />
          
          <Upload className="mx-auto mb-3 text-gray-400" size={32} />
          <p className="text-sm text-gray-600 mb-1">
            클릭하거나 파일을 드래그하세요
          </p>
          <p className="text-xs text-gray-500">
            이미지 (JPEG, PNG, GIF, TIFF) 또는 PDF (최대 {maxSizeMB}MB)
          </p>
        </div>
      ) : (
        <div className="border border-gray-300 rounded-lg p-4 bg-white">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-blue-100 rounded-lg">
                {isMultiPage ? (
                  <FileIcon className="text-blue-600" size={20} />
                ) : (
                  <FileImage className="text-blue-600" size={20} />
                )}
              </div>
              <div>
                <p className="text-sm font-medium text-[var(--text-primary)] truncate max-w-[200px]">
                  {selectedFile.name}
                </p>
                <p className="text-xs text-gray-500">
                  {(selectedFile.size / 1024 / 1024).toFixed(2)} MB
                </p>
              </div>
            </div>
            
            <button
              onClick={handleRemove}
              className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
              title="제거"
            >
              <X size={18} className="text-gray-500" />
            </button>
          </div>
          
          {/* 다중 페이지 선택 (PDF/TIFF) */}
          {isMultiPage && pageCount > 1 && (
            <div className="pt-3 border-t border-gray-200">
              <label className="block text-xs font-medium text-gray-700 mb-2">
                페이지 선택 (PDF/TIFF)
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  min="0"
                  max={pageCount - 1}
                  value={selectedPage}
                  onChange={(e) => handlePageChange(parseInt(e.target.value))}
                  className="w-20 px-2 py-1 text-sm border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <span className="text-xs text-gray-500">/ {pageCount - 1} (0-based)</span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default FileUploader;
