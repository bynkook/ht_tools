import React, { useState } from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from '../../features/chat/components/Sidebar';

/**
 * ChatLayout - FabriX Chat (Model Chat) 전용 레이아웃
 * Model 기반 채팅을 위한 사이드바와 메인 콘텐츠 영역 관리
 * Sidebar가 자체적으로 상태를 관리하므로 레이아웃은 단순함
 */
const ChatLayout = () => {
  const [isCollapsed, setIsCollapsed] = useState(false);

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
