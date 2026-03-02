import React, { useState } from 'react';
import { 
  MessageSquare, 
  Trash2, 
  Plus, 
  Bot, 
  ChevronDown,
  ChevronLeft,
  Home,
  Check, 
  LogOut,
  LayoutGrid
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';

const Sidebar = ({ 
  sessions = [], 
  currentSessionId, 
  onSelectSession,
  onNewChat, 
  isLoading,
  onDeleteSession,
  selectedAgent = null,
  agents = [],
  onAgentSelect,
  username = 'User',
  userEmail = '',
  onLogout,
  onGoHome,
  toggleSidebar
}) => {
  const [isAgentMenuOpen, setIsAgentMenuOpen] = useState(false);
  const navigate = useNavigate();

  const handleSelectSession = (sessionId) => {
    if (onSelectSession) onSelectSession(sessionId);
  };

  const handleNewChat = () => {
    if (onNewChat) onNewChat();
  };

  const handleDeleteSession = (e, sessionId) => {
    e.stopPropagation();
    if (window.confirm("Are you sure you want to delete this conversation?")) {
      if (onDeleteSession) onDeleteSession(sessionId);
    }
  };

  const handleAgentSelect = (agent) => {
    if (onAgentSelect) onAgentSelect(agent);
    setIsAgentMenuOpen(false);
  };

  const handleLogout = () => {
    if (onLogout) onLogout();
  };

  const handleGoHome = () => {
    if (onGoHome) onGoHome();
    else navigate('/');
  };

  return (
    <div className="w-full h-full bg-[var(--bg-secondary)] flex flex-col overflow-hidden">
      {/* 1. Header Area (Unified Design) */}
      <div className="p-4 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2 overflow-hidden">
          <div className="w-8 h-8 bg-blue-100 rounded-lg flex items-center justify-center shrink-0">
            <MessageSquare className="text-blue-600" size={20} />
          </div>
          <h1 className="text-xl font-bold text-[var(--text-primary)] truncate">
            FabriX Chat
          </h1>
        </div>
        
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={handleGoHome}
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

      {/* 2. Agent Selector Area (Fixed Popup & Spacing) */}
      <div className="px-4 mb-8 relative z-50">
        <div className="relative">
          <button
            onClick={() => setIsAgentMenuOpen(!isAgentMenuOpen)}
            className="flex items-center justify-between gap-3 w-full px-4 py-2 bg-white border border-[var(--border-color)] rounded-xl hover:border-blue-300 hover:shadow-md transition-all text-left group"
          >
            <div className="flex items-center gap-3 overflow-hidden">
              <div className="p-2 bg-blue-50 text-blue-600 rounded-lg group-hover:bg-blue-100 shrink-0">
                <Bot size={20} />
              </div>
              <div className="overflow-hidden">
                <p className="text-[10px] text-[var(--text-secondary)] uppercase font-bold tracking-wider">Select Agent</p>
                <p className="font-semibold text-[12px] text-[var(--text-secondary)] truncate">
                  {selectedAgent ? (selectedAgent.name || selectedAgent.label || selectedAgent.agentId || selectedAgent.id || 'Selected Agent') : 'Choose an AI agent'}
                </p>
              </div>
            </div>
            <ChevronDown size={18} className={`text-gray-400 transition-transform ${isAgentMenuOpen ? 'rotate-180' : ''}`} />
          </button>

          {isAgentMenuOpen && (
            <>
                <div className="fixed inset-0 z-40" onClick={() => setIsAgentMenuOpen(false)} />
                <div className="absolute top-full left-0 right-0 mt-2 bg-white border border-gray-200 rounded-xl shadow-xl z-50 max-h-64 overflow-y-auto custom-scrollbar overflow-x-hidden py-2">
                {agents.length > 0 ? (
                    agents.map((agent) => {
                    const agentId = agent.agentId || agent.id || agent.agent_id || '';
                    const selectedId = selectedAgent?.agentId || selectedAgent?.id || selectedAgent?.agent_id || '';
                    const isSelected = agentId && selectedId && agentId === selectedId;
                    return (
                    <button
                        key={agentId || Math.random()}
                        onClick={() => handleAgentSelect(agent)}
                        className={`flex items-center gap-3 w-full px-4 py-3 hover:bg-blue-50 transition-colors text-left ${isSelected ? 'bg-blue-50' : ''}`}
                    >
                        <div className={`p-2 rounded-lg shrink-0 ${isSelected ? 'bg-blue-100 text-blue-600' : 'bg-gray-100 text-gray-400'}`}>
                        <Bot size={18} />
                        </div>
                        <div className="flex-1 overflow-hidden">
                        <p className={`font-semibold text-sm truncate ${isSelected ? 'text-blue-700' : 'text-gray-700'}`}>
                            {agent.name || agent.label || agentId}
                        </p>
                        <p className="text-[10px] text-gray-400 truncate tracking-tight">{agentId}</p>
                        </div>
                        {isSelected && <Check size={16} className="text-blue-600 shrink-0" />}
                    </button>
                    );
                    })
                ) : (
                    <div className="px-4 py-6 text-center text-gray-400">
                    <p className="text-sm">No agents available</p>
                    </div>
                )}
                </div>
            </>
          )}
        </div>
      </div>

      {/* 3. New Chat Button Area */}
      <div className="px-4 mb-6">
        <button
          onClick={handleNewChat}
          className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 transition-all shadow-md hover:shadow-lg active:scale-[0.98]"
        >
          <Plus size={20} />
          <span className="font-bold">New Chat</span>
        </button>
      </div>

      {/* 4. Session List Area */}
      <div className="flex-1 overflow-y-auto px-2 py-2 space-y-1 custom-scrollbar">
        <div className="px-4 text-[10px] font-bold text-[var(--text-secondary)] uppercase tracking-widest mb-2 opacity-60">
          Recent Conversations
        </div>
        
        {isLoading && sessions.length === 0 ? (
          <div className="p-4 text-center text-gray-400 text-xs animate-pulse">
            Loading history...
          </div>
        ) : sessions.length === 0 ? (
          <div className="p-4 text-center text-gray-400 text-xs">
            No history yet
          </div>
        ) : (
          sessions.map((session) => (
            <div
              key={session.id}
              onClick={() => handleSelectSession(session.id)}
              className={`
                group relative flex items-center gap-3 px-4 py-3 rounded-xl cursor-pointer transition-all
                ${String(currentSessionId) === String(session.id)
                  ? 'bg-white shadow-sm border border-indigo-100 text-indigo-500 font-medium'
                  : 'text-[var(--text-secondary)] hover:bg-white/50 hover:text-[var(--text-primary)]'
                }
              `}
            >
              <MessageSquare size={16} className={String(currentSessionId) === String(session.id) ? 'text-indigo-500' : 'text-gray-400'} />
              <span className="text-sm truncate pr-6">{session.title || "New Conversation"}</span>
              
              <button
                onClick={(e) => handleDeleteSession(e, session.id)}
                className="absolute right-2 opacity-0 group-hover:opacity-100 p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-all"
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))
        )}
      </div>

      {/* 5. Footer Area */}
      <div className="p-4 bg-[var(--bg-secondary)] mt-auto shrink-0">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-10 h-10 rounded-full bg-gradient-to-tr from-blue-500 to-indigo-500 flex items-center justify-center text-white font-bold shadow-sm shrink-0">
              {username.charAt(0).toUpperCase()}
            </div>
            <div className="overflow-hidden">
              <p className="text-sm font-bold text-[var(--text-primary)] truncate">{username}</p>
              <p className="text-[10px] text-[var(--text-secondary)] truncate">{userEmail}</p>
            </div>
          </div>
          <button 
            onClick={handleLogout}
            className="p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
          >
            <LogOut size={18} />
          </button>
        </div>
      </div>
    </div>
  );
};

export default Sidebar;
