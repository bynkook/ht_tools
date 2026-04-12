import React, { useState, useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from '../../features/chat/components/Sidebar';
import { initTheme } from '../../lib/theme';

/**
 * ChatLayout - FabriX Chat (Model Chat) 전용 레이아웃
 * Model 기반 채팅을 위한 사이드바와 메인 콘텐츠 영역 관리
 * Sidebar가 자체적으로 상태를 관리하므로 레이아웃은 단순함
 *
 * 다크 모드 스코프: html.dark 는 이 레이아웃이 마운트된 동안만 유효.
 * 다른 앱(/agent-chat, /data-explorer 등)은 항상 light mode 유지.
 */
const ChatLayout = () => {
  const [isCollapsed, setIsCollapsed] = useState(false);

  useEffect(() => {
    // FabriX Chat 진입: 저장된 테마 적용 (dark 또는 light)
    initTheme();

    // FabriX Chat 이탈: 다른 앱들을 위해 html.dark 반드시 제거
    return () => {
      document.documentElement.classList.remove('dark');
    };
  }, []);

  return (
    <div className="flex h-screen bg-[var(--bg-primary)] overflow-hidden">
      {/* Sidebar */}
      <Sidebar isCollapsed={isCollapsed} setIsCollapsed={setIsCollapsed} />

      {/* Main Content Area */}
      <main 
        className={`
          flex-1 flex flex-col h-full min-w-0 overflow-hidden bg-[var(--bg-primary)]
          transition-all duration-300
          ${isCollapsed ? 'ml-16' : 'ml-64'}
        `}
      >
        <Outlet />
      </main>
    </div>
  );
};

export default ChatLayout;
