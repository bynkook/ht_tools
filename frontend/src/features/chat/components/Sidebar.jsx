import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { 
  ChevronLeft, ChevronRight, Plus, MessageSquare, Trash2, 
  Home, Sparkles, Cpu, LogOut, ChevronDown, Check // 수정함 (모델선택창 수정)
} from 'lucide-react';
import { modelApi, modelChatApi, authApi } from '../../../api/djangoApi';

/**
 * Sidebar component for Model Chat (FabriX Chat)
 * Features: Model selection dropdown, session list, new chat button
 */
const Sidebar = ({ isCollapsed, setIsCollapsed }) => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const currentSessionId = searchParams.get('session_id');

  const [models, setModels] = useState([]);
  const [selectedModelId, setSelectedModelId] = useState('');
  const [selectedModel, setSelectedModel] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [isModelMenuOpen, setIsModelMenuOpen] = useState(false); // 추가함 (모델선택창 수정)
  const [isLoadingModels, setIsLoadingModels] = useState(false);
  const [isLoadingSessions, setIsLoadingSessions] = useState(false);
  const [error, setError] = useState(null);

  // 모델목록 출력오류 방지
  const normalizeSessions = (data) => {
    if (Array.isArray(data)) return data;
    if (Array.isArray(data?.sessions)) return data.sessions;
    if (Array.isArray(data?.results)) return data.results;
    return [];
  };
  
  // 선호모델 선택: "gpt"와 "oss" 두 단어가 모두 포함된 모델 우선
  const getPreferredModel = (modelList) => {
    if (!Array.isArray(modelList) || modelList.length === 0) return null;

    const preferred = modelList.find((model) => {
      const nameText = Array.isArray(model?.name)
        ? model.name.map((n) => n?.content || '').join(' ')
        : (model?.name || '');
      const searchable = `${model?.id || ''} ${model?.modelId || ''} ${model?.displayName || ''} ${nameText}`.toLowerCase();
      return searchable.includes('gpt') && searchable.includes('oss');
    });

    return preferred || modelList[0];
  };

  // Load models on mount
  useEffect(() => {
    const loadModels = async () => {
      setIsLoadingModels(true);
      try {
        const data = await modelApi.getModels();
        // FabriX API가 배열을 직접 반환하거나 {items: [...]} 또는 {models: [...]} 형태
        let rawModels;
        if (Array.isArray(data)) {
          rawModels = data;
        } else if (data.models) {
          rawModels = data.models;
        } else if (data.items) {
          rawModels = data.items;
        } else {
          rawModels = [];
        }
        // normalize model ID field (FabriX uses 'modelId', we use 'id')
        const modelList = rawModels.map(model => ({
          ...model,
          id: model.id || model.modelId || model.model_id || model.uuid || '',
        }));
        setModels(modelList);
        // Auto-select preferred model (gpt-oss first) if available (선호모델 선택)
        if (modelList.length > 0 && !selectedModelId) {
          //const firstModel = modelList[0];
          //setSelectedModelId(firstModel.id);
          //setSelectedModel(firstModel);
          // 선호모델 선택
          const preferredModel = getPreferredModel(modelList);
          setSelectedModelId(preferredModel.id);
          setSelectedModel(preferredModel);

          // Dispatch event for ChatPage
          window.dispatchEvent(new CustomEvent('model-selected', {
            // detail: { modelId: firstModel.id, model: firstModel }
            // 선호모델 선택
            detail: { modelId: preferredModel.id, model: preferredModel }
          }));
        }
      } catch (err) {
        console.error('[Sidebar] Failed to load models:', err);
        setError('Failed to load models');
      } finally {
        setIsLoadingModels(false);
      }
    };
    loadModels();
  }, []);

  // Load sessions on mount and when session-created event fires
  const loadSessions = useCallback(async () => {
    setIsLoadingSessions(true);
    try {
      const data = await modelChatApi.getSessions();
      //setSessions(data.sessions || []); 수정함
      setSessions(normalizeSessions(data)); // (최근대화목록 출력 오류 방지)
    } catch (err) {
      console.error('[Sidebar] Failed to load sessions:', err);
    } finally {
      setIsLoadingSessions(false);
    }
  }, []);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  // Listen for session-created event
  useEffect(() => {
    const handleSessionCreated = () => {
      loadSessions();
    };
    window.addEventListener('session-created', handleSessionCreated);
    return () => window.removeEventListener('session-created', handleSessionCreated);
  }, [loadSessions]);

  // Handle model selection
  // const handleModelChange = (e) => {  삭제함 (모델선택메뉴 수정)
  const handleModelSelect = (modelId) => {
    // const modelId = e.target.value;  삭제함 (모델선택메뉴 수정)
    setSelectedModelId(modelId);
    const model = models.find(m => m.id === modelId);
    setSelectedModel(model);
    setIsModelMenuOpen(false); // 추가함 (모델선택메뉴 수정)
    // Dispatch event for ChatPage
    window.dispatchEvent(new CustomEvent('model-selected', {
      detail: { modelId, model }
    }));
  };

  // Handle new chat
  const handleNewChat = () => {
    navigate('/chat');
  };

  // Handle session click
  const handleSessionClick = (sessionId) => {
    navigate(`/chat?session_id=${sessionId}`);
  };

  // Handle session delete
  const handleDeleteSession = async (sessionId, e) => {
    e.stopPropagation();
    if (!window.confirm('Delete this conversation?')) return;
    try {
      await modelChatApi.deleteSession(sessionId);
      setSessions(prev => prev.filter(s => s.id !== sessionId));
      if (currentSessionId === String(sessionId)) {
        navigate('/chat');
      }
    } catch (err) {
      console.error('[Sidebar] Failed to delete session:', err);
    }
  };

  // Get display name for model
  const getModelDisplayName = (model) => {
    // 방어적 코딩: displayName 또는 name 배열에서 한국어/영어 찾기
    if (model.displayName) return model.displayName;
    if (model.name && Array.isArray(model.name)) {
      const ko = model.name.find(n => n.languageCode === 'ko');
      if (ko?.content) return ko.content;
      const en = model.name.find(n => n.languageCode === 'en');
      if (en?.content) return en.content;
      if (model.name[0]?.content) return model.name[0].content;
    }
    return model.id;
  };

  if (isCollapsed) {
    return (
      <div className="fixed left-0 top-0 h-full w-16 bg-[var(--bg-secondary)] border-r border-[var(--border-color)] flex flex-col items-center py-4 z-40">
        <button
          onClick={() => setIsCollapsed(false)}
          className="p-2 rounded-lg hover:bg-[var(--hover-bg)] text-[var(--text-secondary)] transition-colors mb-4"
          title="Expand sidebar"
        >
          <ChevronRight size={20} />
        </button>
        <button
          onClick={() => navigate('/')}
          className="p-2 rounded-lg hover:bg-[var(--hover-bg)] text-[var(--text-secondary)] transition-colors"
          title="Home"
        >
          <Home size={20} />
        </button>
      </div>
    );
  }

  return (
    <div className="fixed left-0 top-0 h-full w-64 bg-[var(--bg-secondary)] border-r border-[var(--border-color)] flex flex-col z-40">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-gradient-to-tr from-cyan-500 to-blue-500 rounded-lg flex items-center justify-center">
            <Sparkles size={16} className="text-white" />
          </div>
          <span className="font-semibold text-[var(--text-primary)]">FabriX Chat</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => navigate('/')}
            className="p-1.5 rounded-md hover:bg-[var(--hover-bg)] text-[var(--text-secondary)] transition-colors"
            title="Home"
          >
            <Home size={16} />
          </button>
          <button
            onClick={() => setIsCollapsed(true)}
            className="p-1.5 rounded-md hover:bg-[var(--hover-bg)] text-[var(--text-secondary)] transition-colors"
            title="Collapse sidebar"
          >
            <ChevronLeft size={16} />
          </button>
        </div>
      </div>

      {/* Model Selection (%%% 여긴 전체 수정함%%%)*/}
      <div className="px-2 py-2 relative z-50">
        <div className="px-4 text-[10px] font-bold text-[var(--text-secondary)] uppercase tracking-widest mb-2 opacity-60">          
          Select Model
        </div>
        <div className="relative">
          <button
            onClick={() => !isLoadingModels && models.length > 0 && setIsModelMenuOpen(!isModelMenuOpen)}
            disabled={isLoadingModels || models.length === 0}
            className="flex items-center justify-between gap-2.5 w-full px-3 py-2 bg-white border border-[var(--border-color)] rounded-xl hover:border-blue-300 hover:shadow-md transition-all text-left group disabled:opacity-60 disabled:cursor-not-allowed"
          >
            <div className="flex items-center gap-2.5 overflow-hidden">
              <div className="p-1.5 bg-cyan-50 text-cyan-600 rounded-lg group-hover:bg-cyan-100 shrink-0">
                <Cpu size={12} />
              </div>
              <div className="overflow-hidden">
                <p className="text-[10px] text-[var(--text-secondary)] uppercase font-bold tracking-wider">Model</p>
                <p className="font-semibold text-[12px] text-[var(--text-primary)] text-gray-700 truncate">
                  {isLoadingModels
                    ? 'Loading...'
                    : selectedModel
                    ? getModelDisplayName(selectedModel)
                    : models.length === 0
                    ? 'No models available'
                    : 'Choose a model'}
                </p>
              </div>
            </div>
            <ChevronDown size={16} className={`text-gray-400 transition-transform ${isModelMenuOpen ? 'rotate-180' : ''}`} />
          </button>

          {isModelMenuOpen && (
            <>
              <div className="fixed inset-0 z-40" onClick={() => setIsModelMenuOpen(false)} />
              <div className="absolute top-full left-0 right-0 mt-2 bg-white border border-gray-200 rounded-xl shadow-xl z-50 max-h-64 overflow-y-auto custom-scrollbar overflow-x-hidden py-2">
                {models.length > 0 ? (
                  models.map((model) => {
                    const isSelected = selectedModelId === model.id;
                    return (
                      <button
                        key={model.id}
                        onClick={() => handleModelSelect(model.id)}
                        className={`flex items-center gap-2.5 w-full px-3 py-2 hover:bg-cyan-50 transition-colors text-left ${isSelected ? 'bg-cyan-50' : ''}`}
                      >
                        <div className="flex-1 overflow-hidden">
                          <p className={`font-semibold text-[12px] truncate ${isSelected ? 'text-cyan-700' : 'text-gray-700'}`}>
                            {getModelDisplayName(model)}
                          </p>
                          <p className="text-[10px] text-gray-400 truncate tracking-tight">{model.id}</p>
                        </div>
                        {isSelected && <Check size={16} className="text-cyan-600 shrink-0" />}
                      </button>
                    );
                  })
                ) : (
                  <div className="px-4 py-6 text-center text-gray-400">
                    <p className="text-sm">No models available</p>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
        {error && (
          <p className="text-xs text-red-500 mt-1">{error}</p>
        )}
      </div>

      {/* New Chat Button */}
      <div className="px-3 py-3">
        <button
          onClick={handleNewChat}
          className="w-full flex items-center justify-center gap-2 py-2.5 bg-gradient-to-r from-cyan-500 to-blue-500 text-white rounded-lg hover:shadow-lg transition-all font-medium text-sm"
        >
          <Plus size={18} />
          New Chat
        </button>
      </div>

      {/* Session List */}
      <div className="flex-1 overflow-y-auto px-2 py-2 space-y-1 custom-scrollbar">
        <div className="px-4 text-[10px] font-bold text-[var(--text-secondary)] uppercase tracking-widest mb-2 opacity-60">
          Recent Conversations
        </div>
        
        {isLoadingSessions ? (
          <div className="p-4 text-center text-gray-400 text-xs animate-pulse">
            Loading history...
          </div>
        ) : sessions.length === 0 ? (
          <div className="p-4 text-center text-gray-400 text-xs">
            No history yet
          </div>
        ) : (
          sessions.map(session => (
            <div
              key={session.id}
              onClick={() => handleSessionClick(session.id)}
              className={`
                group relative flex items-center gap-3 px-4 py-1.5 rounded-xl cursor-pointer transition-all
                ${currentSessionId === String(session.id)
                  ? 'bg-white shadow-sm border border-blue-100 text-blue-500 font-medium'
                  : 'text-[var(--text-secondary)] hover:bg-white/50 hover:text-[var(--text-primary)]'
                }
              `}
            >
              <MessageSquare size={12} className={`${currentSessionId === String(session.id) ? 'text-blue-500' : 'text-gray-400'} shrink-0`} />
              <span className="text-xs truncate pr-6">{session.title || "New Conversation"}</span>
              
              <button
                onClick={(e) => handleDeleteSession(session.id, e)}
                className="absolute right-2 opacity-0 group-hover:opacity-100 p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-all"
                title="Delete"
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))
        )}
      </div>

      {/* Footer - User Info */}
      <div className="p-4 bg-[var(--bg-secondary)] mt-auto shrink-0">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-10 h-10 rounded-full bg-gradient-to-tr from-cyan-500 to-blue-500 flex items-center justify-center text-white font-bold shadow-sm shrink-0">
              {(sessionStorage.getItem('username') || 'U').charAt(0).toUpperCase()}
            </div>
            <div className="overflow-hidden">
              <p className="text-sm font-bold text-[var(--text-primary)] truncate">
                {sessionStorage.getItem('username') || 'User'}
              </p>
              <p className="text-[10px] text-[var(--text-secondary)] truncate">
                {sessionStorage.getItem('email') || ''}
              </p>
            </div>
          </div>
          <button 
            onClick={async () => {
              if (window.confirm('Are you sure you want to logout?')) {
                try {
                  await authApi.logout();
                } catch (e) {
                  console.error('[Logout] Backend logout failed:', e);
                } finally {
                  const returnTo = '/chat';
                  sessionStorage.clear();
                  sessionStorage.setItem('returnTo', returnTo);
                  navigate('/login');
                }
              }
            }}
            className="p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
            title="Log out"
          >
            <LogOut size={18} />
          </button>
        </div>
      </div>
    </div>
  );
};

export default Sidebar;