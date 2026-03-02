import React, { useState } from 'react';
import { Outlet } from 'react-router-dom';
import { Menu } from 'lucide-react';

const SidebarLayout = ({ sidebar: SidebarComponent }) => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  return (
    <div className="flex h-screen bg-[var(--bg-primary)] overflow-hidden">
      {/* Sidebar Area */}
      <aside
        className={`
          relative z-10 flex-shrink-0 bg-[var(--bg-secondary)] border-r border-[var(--border-color)]
          transition-all duration-300 ease-[cubic-bezier(0.25,0.1,0.25,1.0)]
          ${isSidebarOpen ? 'w-[280px]' : 'w-[56px]'}
        `}
      >
        {isSidebarOpen ? (
          <div className="w-[280px] h-full flex flex-col">
            <SidebarComponent onClose={() => setIsSidebarOpen(false)} />
          </div>
        ) : (
          <div className="w-[56px] h-full flex flex-col">
            <div className="flex-shrink-0 h-14 flex items-center justify-center">
              <button
                onClick={() => setIsSidebarOpen(true)}
                className="p-2 text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] rounded-lg transition-all duration-200"
                title="Open Sidebar"
              >
                <Menu size={20} />
              </button>
            </div>
          </div>
        )}
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col h-full min-w-0 overflow-hidden bg-[var(--bg-primary)]">
        <Outlet />
      </main>
    </div>
  );
};

export default SidebarLayout;
