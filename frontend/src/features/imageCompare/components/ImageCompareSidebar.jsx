import React from 'react';
import { Image as ImageIcon, RotateCcw, Play, Home, ChevronLeft, LogOut, Upload, Crop, X } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import FileUploader from './FileUploader';
import SettingsPanel from './SettingsPanel';

const ImageCompareSidebar = ({ 
  isOpen, 
  toggleSidebar,
  username,
  userEmail,
  handleLogout,
  // Props for Reset
  handleReset,
  setIsResetHovered,
  isResetHovered,
  // Props for File Upload
  resetKey,
  handleFile1Select,
  handleFile2Select,
  // Props for Settings
  settings,
  setSettings,
  colors,
  // Props for Compare
  handleCompare,
  canCompare,
  canCrop,
  isLoading,
  // Props for Crop
  cropRect,
  onCropClick,
  onCropReset,
  cropPreviewLoading,
}) => {
  const navigate = useNavigate();

  return (
    <aside 
      className={`
        bg-[var(--bg-secondary)] flex flex-col z-20 h-full
        transition-all duration-300 ease-in-out
        ${isOpen ? 'w-[320px]' : 'w-0 opacity-0 overflow-hidden'}
      `}
    >
      {/* 1. Sidebar Header (Design Unified) */}
      <div className="p-4 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2 overflow-hidden">
          <div className="w-8 h-8 bg-blue-100 rounded-lg flex items-center justify-center shrink-0">
            <ImageIcon className="text-blue-600" size={20} />
          </div>
          <h1 className="text-xl font-bold text-[var(--text-primary)] truncate">
            Image Inspector
          </h1>
        </div>
        
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={() => navigate('/')}
            className="p-2 text-gray-500 hover:bg-gray-200 rounded-lg transition-colors"
            title="Go to App Selector"
          >
            <Home size={18} />
          </button>
          <button
            onClick={toggleSidebar}
            className="p-2 text-gray-500 hover:bg-gray-200 rounded-lg transition-colors"
            title="Shrink Sidebar"
          >
            <ChevronLeft size={18} />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4 custom-scrollbar">
        
        <button
          onClick={handleReset}
          onMouseEnter={() => setIsResetHovered(true)}
          onMouseLeave={() => setIsResetHovered(false)}
          className={`
            w-full flex items-center justify-center gap-2 px-3 py-2 mb-4 rounded-lg text-sm border transition-all
            ${isResetHovered 
              ? 'bg-blue-50 border-blue-500 text-blue-700 font-medium' 
              : 'bg-white border-gray-300 text-gray-700'
            }
          `}
        >
          <RotateCcw size={16} />
          새로운 비교 초기화
        </button>

        <div>
          <div className="flex items-center gap-2 mb-3">
            <Upload size={14} className="text-gray-400 shrink-0" />
            <span className="text-xs font-bold text-[var(--text-secondary)] uppercase tracking-wider">
              File Upload
            </span>
          </div>
          <div className="space-y-3">
            <FileUploader
              key={`uploader-1-${resetKey}`}
              label="이미지/도면 1"
              onFileSelect={handleFile1Select}
            />
            <FileUploader
              key={`uploader-2-${resetKey}`}
              label="이미지/도면 2"
              onFileSelect={handleFile2Select}
            />
          </div>
        </div>

        {/* CROP 버튼 */}
        <button
          onClick={onCropClick}
          disabled={!canCrop || cropPreviewLoading}
          className={`
            w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl
            text-sm font-semibold transition-all shadow-md
            ${cropRect
              ? 'bg-gradient-to-r from-indigo-500 to-blue-600 hover:from-indigo-600 hover:to-blue-700 text-white hover:shadow-lg'
              : canCrop
                ? 'bg-gradient-to-r from-blue-500 to-blue-600 hover:from-blue-600 hover:to-blue-700 text-white hover:shadow-lg'
                : 'bg-gray-300 text-gray-500 cursor-not-allowed'
            }
            ${cropPreviewLoading ? 'opacity-70 cursor-wait' : ''}
          `}
        >
          {cropPreviewLoading
            ? <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent" />
            : <Crop size={16} />}
          {cropPreviewLoading ? '준비 중...' : 'Crop 영역 선택'}
        </button>

        {/* CROP 활성 시: 해제 버튼 + 정보 표시 */}
        {cropRect && (
          <div className="flex items-center justify-between bg-indigo-50 border border-indigo-200 rounded-lg px-3 py-2">
            <span className="text-xs text-indigo-700 font-medium">
              {Math.round(cropRect.width * 100)}% × {Math.round(cropRect.height * 100)}% 선택됨
            </span>
            <button
              onClick={onCropReset}
              className="flex items-center gap-1 text-xs text-indigo-500 hover:text-red-500 transition-colors"
            >
              <X size={12} />
              CROP 해제
            </button>
          </div>
        )}
        
        <div>
          <SettingsPanel
            settings={settings}
            onSettingsChange={setSettings}
            colors={colors}
          />
        </div>
        
        <button
          onClick={() => handleCompare()}
          disabled={!canCompare}
          className={`
            w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl
            text-sm font-semibold transition-all shadow-md
            ${canCompare || isLoading
              ? 'bg-gradient-to-r from-blue-500 to-blue-600 hover:from-blue-600 hover:to-blue-700 text-white hover:shadow-lg'
              : 'bg-gray-300 text-gray-500 cursor-not-allowed'
            }
            ${isLoading ? 'opacity-70 cursor-wait' : ''}
          `}
        >
          {isLoading ? <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent" /> : <Play size={18} />}
          {isLoading ? '처리 중...' : '비교 시작'}
        </button>
      </div>

      <div className="p-4 bg-[var(--bg-secondary)]">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 flex-1 min-w-0">
            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-purple-500 to-indigo-600 flex items-center justify-center text-white font-bold shadow-md shrink-0">
              {username.charAt(0).toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold truncate text-[var(--text-primary)]">{username}</p>
              <p className="text-[10px] text-[var(--text-secondary)] truncate" title={userEmail}>
                {userEmail}
              </p>
            </div>
          </div>

          <button 
            onClick={handleLogout}
            className="p-2.5 text-[var(--text-secondary)] hover:text-red-500 hover:bg-red-50 rounded-lg transition-all shrink-0"
            title="Logout"
          >
            <LogOut size={18} />
          </button>
        </div>
      </div>
    </aside>
  );
};

export default ImageCompareSidebar;
