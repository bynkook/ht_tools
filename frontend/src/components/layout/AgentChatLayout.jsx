import React, { useState, useEffect } from 'react';
import { Outlet, useNavigate, useSearchParams } from 'react-router-dom';
import { ChevronRight, Home } from 'lucide-react';
import Sidebar from '../../features/agentChat/components/Sidebar';
import { agentChatApi, agentApi, authApi } from '../../api/djangoApi';

/**
 * AgentChatLayout - FabriX Agent Chat 전용 레이아웃
 * Agent 기반 채팅을 위한 사이드바와 메인 콘텐츠 영역 관리
 */
const AgentChatLayout = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const currentSessionId = searchParams.get('session_id');

  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  
  // Sidebar 데이터 관리
  const [sessions, setSessions] = useState([]);
  const [isLoadingSessions, setIsLoadingSessions] = useState(false);
  const [agents, setAgents] = useState([]);
  const [selectedAgent, setSelectedAgent] = useState(null);

  // 사용자 정보
  const username = sessionStorage.getItem('username') || 'User';
  const userEmail = sessionStorage.getItem('email') || '';

  // 수정함 (최근대화목록 출력 오류 방지)
  const normalizeSessions = (data) => {
    if (Array.isArray(data)) return data;
    if (Array.isArray(data?.sessions)) return data.sessions;
    if (Array.isArray(data?.results)) return data.results;
    return [];
  };

  // Sessions 로드
  const loadSessions = async () => {
    try {
      setIsLoadingSessions(true);
      const data = await agentChatApi.getSessions();
      setSessions(normalizeSessions(data)); // 수정함 (최근대화목록 출력 오류 방지)
    } catch (error) {
      console.error("Failed to load sessions:", error);
    } finally {
      setIsLoadingSessions(false);
    }
  };

  // Agents 로드
  const loadAgents = async () => {
    try {
      const data = await agentApi.getAgents();
      console.log('[AgentChatLayout] Agents API Response:', data);
      
      const items = data.items || [];
      console.log('[AgentChatLayout] Agents List:', items);
      setAgents(items);
      
      // 기본 Agent 선택
      if (items.length > 0 && !selectedAgent) {
        const firstAgent = items[0];
        // agentId 필드 fallback 처리
        const agentId = firstAgent.agentId || firstAgent.id || firstAgent.agent_id || '';
        console.log('[AgentChatLayout] Auto-selecting first agent:', firstAgent, 'agentId:', agentId);
        setSelectedAgent(firstAgent);
        // ChatPage에 전달
        window.dispatchEvent(new CustomEvent('agent-selected', { 
          detail: { 
            agentId: agentId,
            agent: firstAgent
          } 
        }));
      }
    } catch (error) {
      console.error("[AgentChatLayout] Failed to load agents:", error);
    }
  };

  // 초기 로드 및 session 변경 감지
  useEffect(() => {
    loadSessions();
    loadAgents();
    
    // Session 생성 이벤트 리스너
    const handleSessionCreated = () => loadSessions();
    window.addEventListener('session-created', handleSessionCreated);
    
    return () => window.removeEventListener('session-created', handleSessionCreated);
  }, []);

  // Handlers
  const handleNewChat = () => {
    window.dispatchEvent(new CustomEvent('new-chat-requested'));
    navigate('/agent-chat');
  };
  
  const handleSelectSession = (sessionId) => {
    navigate(`/agent-chat?session_id=${sessionId}`);
  };

  const handleDeleteSession = async (sessionId) => {
    try {
      await agentChatApi.deleteSession(sessionId);
      setSessions(prev => prev.filter(s => s.id !== sessionId));
      
      // 현재 세션 삭제 시 새 채팅으로 이동
      if (String(currentSessionId) === String(sessionId)) {
        navigate('/agent-chat');
      }
    } catch (error) {
      alert('Failed to delete session');
      console.error(error);
    }
  };

  const handleAgentSelect = (agent) => {
    // agentId 필드 fallback 처리
    const agentId = agent.agentId || agent.id || agent.agent_id || '';
    console.log('[AgentChatLayout] Agent selected:', agent, 'agentId:', agentId);
    setSelectedAgent(agent);
    // ChatPage에 전달
    window.dispatchEvent(new CustomEvent('agent-selected', { 
      detail: { 
        agentId: agentId,
        agent: agent
      } 
    }));
  };

  const handleGoHome = () => {
    navigate('/');
  };

  const handleLogout = async () => {
    if (window.confirm('Are you sure you want to logout?')) {
      try {
        // 로그아웃 전에 현재 앱 저장
        sessionStorage.setItem('returnTo', '/agent-chat');
        
        // 백엔드 로그아웃 호출
        await authApi.logout();
        console.log('[Logout] Backend logout successful');
      } catch (error) {
        console.error('[Logout] Backend logout failed:', error);
        // 백엔드 실패해도 프론트엔드 정리는 진행
      } finally {
        // returnTo는 유지하고 나머지 세션 정리
        const returnTo = sessionStorage.getItem('returnTo');
        sessionStorage.clear();
        if (returnTo) {
          sessionStorage.setItem('returnTo', returnTo);
        }
        console.log('[Logout] SessionStorage cleared, returnTo preserved');
        navigate('/login');
      }
    }
  };

  return (
    <div className="flex h-screen bg-[var(--bg-primary)] overflow-hidden">
      {/* Sidebar Area */}
      <aside
        className={`
          relative z-30 flex-shrink-0 bg-[var(--bg-secondary)]
          transition-all duration-300 ease-[cubic-bezier(0.25,0.1,0.25,1.0)]
          ${isSidebarOpen ? 'w-[280px]' : 'w-0 overflow-hidden'}
        `}
      >
        <div className="w-[280px] h-full flex flex-col">
          <Sidebar 
            sessions={sessions}
            currentSessionId={currentSessionId}
            onSelectSession={handleSelectSession}
            onNewChat={handleNewChat}
            isLoading={isLoadingSessions}
            onDeleteSession={handleDeleteSession}
            selectedAgent={selectedAgent}
            agents={agents}
            onAgentSelect={handleAgentSelect}
            username={username}
            userEmail={userEmail}
            onLogout={handleLogout}
            onGoHome={handleGoHome}
            toggleSidebar={() => setIsSidebarOpen(false)}
          />
        </div>
      </aside>

      {/* Main Content Area */}
      <main className={`flex-1 flex flex-col h-full min-w-0 overflow-hidden bg-[var(--bg-primary)] relative transition-all duration-300 ${!isSidebarOpen ? 'ml-16' : ''}`}>
        <Outlet />
      </main>

      {/* Collapsed Sidebar - FabriX Chat style */}
      {!isSidebarOpen && (
        <div className="fixed left-0 top-0 h-full w-16 bg-[var(--bg-secondary)] border-r border-[var(--border-color)] flex flex-col items-center py-4 z-40">
          <button
            onClick={() => setIsSidebarOpen(true)}
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
      )}
    </div>
  );
};

export default AgentChatLayout;
