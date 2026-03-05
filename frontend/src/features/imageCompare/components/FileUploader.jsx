import React, { useState, useRef } from 'react';
import { Upload, X, File as FileIcon } from 'lucide-react';

const FileUploader = ({ onFileSelect, label, accept = "image/*,application/pdf,.tif,.tiff", maxSizeMB = 30 }) => {
  const [selectedFile, setSelectedFile] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef(null);

  const handleFileChange = (file) => {
    if (!file) return;

    const isAllowedType = (
      file.type.startsWith('image/') ||
      file.type === 'application/pdf' ||
      file.name.toLowerCase().endsWith('.tif') ||
      file.name.toLowerCase().endsWith('.tiff')
    );
    if (!isAllowedType) {
      alert('지원하지 않는 파일 형식입니다. 이미지(JPEG, PNG, GIF, TIFF) 또는 PDF 파일만 업로드 가능합니다.');
      return;
    }

    const fileSizeMB = file.size / 1024 / 1024;
    if (fileSizeMB > maxSizeMB) {
      alert(`파일 크기가 너무 큽니다. 최대 ${maxSizeMB}MB까지 업로드 가능합니다.`);
      return;
    }

    setSelectedFile(file);
    onFileSelect(file, 0);
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
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
    onFileSelect(null, 0);
  };

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
            relative border-2 border-dashed rounded-lg p-2 text-center cursor-pointer
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
          
          <Upload className="mx-auto mb-1 text-gray-400" size={18} />
          <p className="text-xs text-gray-600 mb-0.5">
            클릭하거나 파일을 드래그하세요
          </p>
          <p className="text-[11px] text-gray-400">
            이미지 (JPEG, PNG, GIF, TIFF) 또는 PDF<br /> (최대 {maxSizeMB}MB)
          </p>
        </div>
      ) : (
        <div className="border border-gray-300 rounded-lg p-2 bg-white overflow-hidden">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-3 min-w-0 flex-1">
              <div className="p-2 bg-blue-100 rounded-lg flex-shrink-0">
                <FileIcon className="text-blue-600" size={14} />
              </div>
              <div className="min-w-0">
                <p className="text-xs font-medium text-[var(--text-primary)] line-clamp-2 break-all">
                  {selectedFile.name}
                </p>
                <p className="text-xs text-gray-500">
                  {(selectedFile.size / 1024 / 1024).toFixed(2)} MB
                </p>
              </div>
            </div>
            
            <button
              onClick={handleRemove}
              className="p-2 hover:bg-gray-100 rounded-lg transition-colors flex-shrink-0"
              title="제거"
            >
              <X size={18} className="text-gray-500" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default FileUploader;
