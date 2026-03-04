import React, { useRef, useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Upload, BarChart3, ChevronLeft, ChevronDown, ChevronUp, Home, FileText, Database, Save, Globe, Lock, MoreVertical, Pencil, Trash2, LogOut, RefreshCw, Search } from 'lucide-react';

const DataExplorerSidebar = ({ 
  onClose, 
  onFileUpload, 
  onLoadLocalDataset, 
  serverDatasets, 
  isLoading,
  // Preset props
  presets = [],
  onSavePreset,
  onLoadPreset,
  onDeletePreset,
  onRenamePreset,
  canSavePreset = false,
  isAdmin = false,
  // Rebuild props
  onRebuildClick,
  // User props
  username = 'User',
  userEmail = '',
}) => {
  const navigate = useNavigate();
  const fileInputRef = useRef(null);
  
  // Fold/Unfold state for sections
  const [isDatasetExpanded, setIsDatasetExpanded] = useState(true);
  const [isPublicExpanded, setIsPublicExpanded] = useState(false);
  const [isPrivateExpanded, setIsPrivateExpanded] = useState(true);
  const [publicFilter, setPublicFilter] = useState('');
  const [privateFilter, setPrivateFilter] = useState('');

  // 3-dot 메뉴 열림 상태 (현재 열린 preset의 id, 없으면 null)
  const [openMenuPresetId, setOpenMenuPresetId] = useState(null);
  const menuRef = useRef(null);

  // 메뉴 외부 클릭 시 닫기
  useEffect(() => {
    if (!openMenuPresetId) return;
    const handleMouseDown = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setOpenMenuPresetId(null);
      }
    };
    document.addEventListener('mousedown', handleMouseDown);
    return () => document.removeEventListener('mousedown', handleMouseDown);
  }, [openMenuPresetId]);

  const handleLogout = () => {
    sessionStorage.clear();
    navigate('/login');
  };

  const onFileChange = (e) => {
    if (e.target.files?.[0]) {
      onFileUpload(e.target.files[0]);
    }
    e.target.value = '';
  };

  // 파일 크기 포맷팅 유틸리티
  const formatFileSize = (bytes) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  // 날짜 포맷팅 유틸리티
  const formatDate = (dateString) => {
    if (!dateString) return '';
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now - date;
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
    
    if (diffDays === 0) {
      const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
      if (diffHours === 0) {
        const diffMins = Math.floor(diffMs / (1000 * 60));
        return diffMins <= 1 ? '방금 전' : `${diffMins}분 전`;
      }
      return `${diffHours}시간 전`;
    } else if (diffDays === 1) {
      return '어제';
    } else if (diffDays < 7) {
      return `${diffDays}일 전`;
    } else {
      return date.toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' });
    }
  };

  const formatCreatedDate = (dateString) => {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleString('ko-KR');
  };

  return (
    <div className="w-full h-full bg-[var(--bg-secondary)] flex flex-col">
      {/* Header */}
      <div className="p-4 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2 overflow-hidden">
          <div className="w-8 h-8 bg-blue-100 rounded-lg flex items-center justify-center shrink-0">
            <BarChart3 className="text-blue-600" size={20} />
          </div>
          <h1 className="text-xl font-bold text-[var(--text-primary)] truncate">
            Data Explorer
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
            onClick={onClose}
            className="p-2 text-gray-500 hover:bg-gray-200 rounded-lg transition-colors"
            title="Shrink Sidebar"
          >
            <ChevronLeft size={18} />
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 p-4 space-y-6 overflow-y-auto custom-scrollbar">
        {/* Section 1: Upload */}
        <div>
          <div className="text-xs font-bold text-[var(--text-secondary)] uppercase tracking-wider mb-3">
            Local Upload
          </div>
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isLoading}
            className="flex items-center gap-3 w-full p-3 bg-white rounded-xl border border-gray-200 hover:shadow-md transition-all text-left group disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <div className="p-2 bg-green-50 text-green-600 rounded-lg shrink-0 group-hover:bg-green-100">
              <Upload size={20} />
            </div>
            <div>
              <p className="font-semibold text-sm text-[var(--text-primary)]">Upload File</p>
              <p className="text-[10px] text-[var(--text-secondary)]">CSV, Parquet (max 100MB)</p>
            </div>
          </button>
          <input 
            type="file" 
            accept=".csv,.parquet" 
            ref={fileInputRef} 
            onChange={onFileChange} 
            className="hidden" 
          />
        </div>

        {/* Section 2: Server Datasets (Quick Select) */}
        <div>
          <button
            onClick={() => setIsDatasetExpanded(!isDatasetExpanded)}
            className="w-full text-xs font-bold text-[var(--text-secondary)] uppercase tracking-wider mb-3 flex items-center gap-2 hover:text-[var(--text-primary)] transition-colors"
          >
            <Database size={12} />
            <span className="flex-1 text-left">Quick Select Dataset</span>
            {isDatasetExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
          
          {isDatasetExpanded && <div className="space-y-2">
            {serverDatasets.length > 0 ? (
              serverDatasets.map((dataset) => (
                <button
                  key={dataset.name}
                  onClick={() => onLoadLocalDataset(dataset.name)}
                  disabled={isLoading}
                  className="w-full flex items-center gap-3 p-1.5 bg-white rounded-lg border border-transparent hover:border-blue-200 hover:shadow-sm transition-all text-left group disabled:opacity-50"
                >
                  <div className="p-1.5 bg-blue-50 text-blue-500 rounded-md shrink-0 group-hover:bg-blue-100">
                    <FileText size={16} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="font-medium text-xs text-[var(--text-primary)] truncate" title={dataset.name}>
                      {dataset.name}
                    </p>
                    <p className="text-[9px] text-[var(--text-secondary)] mt-0.5">
                      {formatFileSize(dataset.size)} • {dataset.extension.toUpperCase()}
                    </p>
                  </div>
                </button>
              ))
            ) : (
              <div className="py-8 text-center bg-gray-50/50 rounded-xl border border-dashed border-gray-200">
                <p className="text-[10px] text-gray-400">서버 데이터셋이 없습니다.</p>
              </div>
            )}
            
            {/* Rebuild Cache Button */}
            {serverDatasets.length > 0 && (
              <button
                onClick={onRebuildClick}
                disabled={isLoading}
                className="w-full mt-2 flex items-center justify-center gap-2 py-2 px-3 text-xs text-gray-600 bg-gray-50 hover:bg-gray-100 border border-gray-200 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                title="캐시 상태 확인 및 재구축"
              >
                <RefreshCw size={14} />
                <span>Rebuild Cache...</span>
              </button>
            )}
          </div>}
        </div>

        {/* Section 3: Saved Presets */}
        <div className="space-y-4">
          {/* Save Preset Button */}
          <button
            onClick={onSavePreset}
            disabled={isLoading || !canSavePreset}
            className="flex items-center gap-3 w-full p-3 bg-white rounded-xl border border-gray-200 hover:shadow-md transition-all text-left group disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <div className="p-2 bg-purple-50 text-purple-600 rounded-lg shrink-0 group-hover:bg-purple-100">
              <Save size={20} />
            </div>
            <div>
              <p className="font-semibold text-sm text-[var(--text-primary)]">Save Preset</p>
              <p className="text-[10px] text-[var(--text-secondary)]">현재 차트를 저장</p>
            </div>
          </button>

          {/* Preset Item 렌더 함수 */}
          {[
            {
              key: 'public',
              label: 'Public Presets',
              icon: <Globe size={12} />,
              expanded: isPublicExpanded,
              setExpanded: setIsPublicExpanded,
              filter: publicFilter,
              setFilter: setPublicFilter,
              items: presets
                .filter(p => p.is_public)
                .sort((a, b) => a.name.localeCompare(b.name, 'ko')),
            },
            {
              key: 'private',
              label: 'My Presets',
              icon: <Lock size={12} />,
              expanded: isPrivateExpanded,
              setExpanded: setIsPrivateExpanded,
              filter: privateFilter,
              setFilter: setPrivateFilter,
              items: presets
                .filter(p => !p.is_public)
                .sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at)),
            },
          ].map(({ key, label, icon, expanded, setExpanded, filter, setFilter, items }) => {
            const filtered = filter
              ? items.filter(p => p.name.toLowerCase().includes(filter.toLowerCase()))
              : items;
            return (
              <div key={key}>
                {/* Box Header */}
                <button
                  onClick={() => setExpanded(v => !v)}
                  className="w-full text-xs font-bold text-[var(--text-secondary)] uppercase tracking-wider mb-2 flex items-center gap-2 hover:text-[var(--text-primary)] transition-colors"
                >
                  {icon}
                  <span className="flex-1 text-left">{label}</span>
                  <span className="font-normal normal-case text-[10px] text-gray-400">{items.length}</span>
                  {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                </button>

                {expanded && (
                  <div className="space-y-1.5">
                    {/* Quick filter */}
                    <div className="relative mb-2">
                      <Search size={11} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
                      <input
                        type="text"
                        value={filter}
                        onChange={e => setFilter(e.target.value)}
                        placeholder="이름 검색..."
                        className="w-full pl-7 pr-2 py-1.5 text-[11px] border border-gray-200 rounded-lg bg-gray-50 focus:outline-none focus:border-blue-300 focus:bg-white transition-colors"
                      />
                    </div>

                    {/* Preset List Box */}
                    <div className="max-h-[200px] overflow-y-auto custom-scrollbar space-y-1">
                      {filtered.length > 0 ? filtered.map((preset) => (
                        <div
                          key={preset.id}
                          className="w-full flex items-center gap-2 p-1.5 bg-white rounded-lg border border-transparent hover:border-purple-200 hover:shadow-sm transition-all group"
                          title={`Preset name: ${preset.name}\nMemo: ${preset.description || '-'}\nOwner: ${preset.owner_username || '-'}\nCreated: ${formatCreatedDate(preset.created_at)}`}
                        >
                          <button
                            onClick={() => onLoadPreset(preset.id)}
                            disabled={isLoading}
                            className="flex items-center gap-2 flex-1 min-w-0 text-left disabled:opacity-50"
                          >
                            <div className="p-1.5 bg-purple-50 text-purple-500 rounded-md shrink-0 group-hover:bg-purple-100">
                              <BarChart3 size={14} />
                            </div>
                            <div className="min-w-0 flex-1">
                              <p
                                className="font-medium text-xs text-[var(--text-primary)] leading-tight"
                                style={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}
                              >
                                {preset.name}
                              </p>
                              <div className="flex items-center gap-1.5 mt-0.5">
                                <span className="text-[9px] text-[var(--text-secondary)]">{formatDate(preset.updated_at)}</span>
                                {!preset.is_owner && (
                                  <span className="text-[8px] text-gray-400 bg-gray-100 px-1 rounded">@{preset.owner_username}</span>
                                )}
                              </div>
                            </div>
                          </button>
                          {/* 3-dot 메뉴: 소유자 또는 Admin에게만 표시 */}
                          {(preset.is_owner || isAdmin) && (
                            <div className="relative shrink-0" ref={openMenuPresetId === preset.id ? menuRef : null}>
                              <button
                                onClick={(e) => { e.stopPropagation(); setOpenMenuPresetId(openMenuPresetId === preset.id ? null : preset.id); }}
                                disabled={isLoading}
                                className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-md transition-colors opacity-0 group-hover:opacity-100 disabled:opacity-50"
                                title="옵션"
                              >
                                <MoreVertical size={14} />
                              </button>
                              {openMenuPresetId === preset.id && (
                                <div className="absolute right-0 top-full mt-0.5 bg-white rounded-lg shadow-lg border border-gray-200 py-1 z-50 min-w-[110px]">
                                  {preset.is_owner && (
                                    <button
                                      onClick={(e) => { e.stopPropagation(); setOpenMenuPresetId(null); onRenamePreset(preset); }}
                                      className="w-full flex items-center gap-2 px-3 py-2 text-xs text-gray-700 hover:bg-gray-50 transition-colors"
                                    >
                                      <Pencil size={12} />이름 변경
                                    </button>
                                  )}
                                  <button
                                    onClick={(e) => { e.stopPropagation(); setOpenMenuPresetId(null); onDeletePreset(preset); }}
                                    className="w-full flex items-center gap-2 px-3 py-2 text-xs text-red-600 hover:bg-red-50 transition-colors"
                                  >
                                    <Trash2 size={12} />삭제
                                  </button>
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      )) : (
                        <div className="py-4 text-center bg-gray-50/50 rounded-xl border border-dashed border-gray-200">
                          <p className="text-[10px] text-gray-400">
                            {filter ? '검색 결과 없음' : '저장된 프리셋이 없습니다.'}
                          </p>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* User Info Section (Fixed at bottom) */}
      <div className="p-4 bg-[var(--bg-secondary)] shrink-0">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 flex-1 min-w-0">
            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-green-500 to-emerald-600 flex items-center justify-center text-white font-bold shadow-md shrink-0">
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
    </div>
  );
};

export default DataExplorerSidebar;
