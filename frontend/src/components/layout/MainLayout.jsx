import React, { useState, useEffect } from 'react';
import { Outlet, useNavigate, useSearchParams } from 'react-router-dom';
import { Menu } from 'lucide-react';
import Sidebar from '../../features/chat/components/Sidebar';
import { chatApi, agentApi, authApi } from '../../api/djangoApi';

const MainLayout = () => {
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

  // Sessions 로드
  const loadSessions = async () => {
    try {
      setIsLoadingSessions(true);
      const data = await chatApi.getSessions();
      setSessions(data);
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
      console.log('[MainLayout] Agents API Response:', data);
      
      const items = data.items || [];
      console.log('[MainLayout] Agents List:', items);
      setAgents(items);
      
      // 기본 Agent 선택
      if (items.length > 0 && !selectedAgent) {
        const firstAgent = items[0];
        // agentId 필드 fallback 처리
        const agentId = firstAgent.agentId || firstAgent.id || firstAgent.agent_id || '';
        console.log('[MainLayout] Auto-selecting first agent:', firstAgent, 'agentId:', agentId);
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
      console.error("[MainLayout] Failed to load agents:", error);
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
  const handleNewChat = () => navigate('/chat');
  
  const handleSelectSession = (sessionId) => {
    navigate(`/chat?session_id=${sessionId}`);
  };

  const handleDeleteSession = async (sessionId) => {
    try {
      await chatApi.deleteSession(sessionId);
      setSessions(prev => prev.filter(s => s.id !== sessionId));
      
      // 현재 세션 삭제 시 새 채팅으로 이동
      if (String(currentSessionId) === String(sessionId)) {
        navigate('/chat');
      }
    } catch (error) {
      alert('Failed to delete session');
      console.error(error);
    }
  };

  const handleAgentSelect = (agent) => {
    // agentId 필드 fallback 처리
    const agentId = agent.agentId || agent.id || agent.agent_id || '';
    console.log('[MainLayout] Agent selected:', agent, 'agentId:', agentId);
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
        sessionStorage.setItem('returnTo', '/chat');
        
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
      <main className="flex-1 flex flex-col h-full min-w-0 overflow-hidden bg-[var(--bg-primary)] relative">
        {!isSidebarOpen && (
          <button
            onClick={() => setIsSidebarOpen(true)}
            className="absolute top-4 left-4 z-40 p-2 bg-white shadow-md rounded-lg text-gray-600 hover:text-blue-600 border border-gray-100"
          >
            <Menu size={20} />
          </button>
        )}
        <Outlet />
      </main>
    </div>
  );
};

export default MainLayout;