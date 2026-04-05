import React from 'react';
import { useNavigate } from 'react-router-dom';
import { MessageCircle, ImageIcon, Bot, ChevronRight, BarChart3, Settings, Sparkles, LogOut, UserCircle, HelpCircle, FolderUp, LayoutGrid, Calculator } from 'lucide-react';

const AppSelectorPage = () => {
  const navigate = useNavigate();

  const apps = [
    {
      id: 'chat',
      name: 'FabriX Chat',
      description: 'LLM 모델과 자유롭게 대화합니다',
      icon: Sparkles,
      color: 'from-cyan-500 to-blue-600',
      path: '/chat'
    },
    {
      id: 'agent-chat',
      name: 'FabriX Agent Chat',
      description: 'AI 에이전트와 대화하고 파일을 분석합니다',
      icon: MessageCircle,
      color: 'from-blue-500 to-indigo-600',
      path: '/agent-chat'
    },
    {
      id: 'image-inspector',
      name: 'Image Inspector',
      description: '두 이미지/도면을 비교하고 차이점을 분석합니다',
      icon: ImageIcon,
      color: 'from-purple-500 to-pink-600',
      path: '/image-compare'
    },
    {
      id: 'data-explorer',
      name: 'Data Explorer',
      description: '데이터를 탐색하고 시각화하여 인사이트를 도출합니다',        
      icon: BarChart3,
      color: 'from-green-500 to-emerald-600',
      path: '/data-explorer'
    },
    {
      id: 'dashboard-list',
      name: 'Dashboard List',
      description: '운영중인 태블로 대시보드 목록을 보여줍니다',
      icon: LayoutGrid,
      color: 'from-zinc-800 to-zinc-600',
      path: '/dashboard-list'
    },
    {
      id: 'doc-uploader',
      name: 'Doc Uploader',
      description: 'PDF/Office 문서를 Markdown으로 변환하여 RAG 검색에 활용합니다',
      icon: FolderUp,
      color: 'from-violet-500 to-purple-600',
      path: '/doc-uploader'
    },
    {
      id: 'esc-calculator',
      name: 'ESC 물가변동 산출',
      description: '건설공사 물가변동(ESC) 보정금액을 자동 산출합니다',
      icon: Calculator,
      color: 'from-orange-500 to-amber-600',
      path: '/esc-calculator'
    }
  ];

  const handleSelectApp = (app) => {
    navigate(app.path);
  };

  const handleLogout = () => {
    if (window.confirm('로그아웃 하시겠습니까?')) {
      sessionStorage.clear();
      navigate('/login');
    }
  };

  // 사용자 정보
  const username = sessionStorage.getItem('username') || 'User';

  return (
    <div className="min-h-screen bg-gradient-to-br from-white to-indigo-100 flex flex-col">
      {/* Main Content */}
      <div className="pt-8 pb-3 md:pt-10">
        {/* Header - centered */}
        <div className="mx-auto max-w-7xl w-full px-4 text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-600 mb-4 shadow-lg">
            <Bot className="text-white" size={28} />
          </div>
          <h1 className="text-3xl font-bold text-gray-900 mb-2">
            HT Auto-Tools 2026
          </h1>
          <p className="text-gray-600 text-sm">
            안녕하세요, <span className="font-semibold text-gray-800">{username}</span>님! 사용할 앱을 선택하세요.
          </p>
        </div>

        {/* App Cards - 전체 너비 사용 */}
        <div className="px-4">
          <div className="flex flex-wrap justify-center gap-4">
            {apps.map((app) => {
              const Icon = app.icon;
              const borderClass = app.id === 'chat'
                ? 'border-orange-400 hover:border-orange-300'
                : 'border-transparent hover:border-blue-200';

              return (
                <button
                  key={app.id}
                  onClick={() => handleSelectApp(app)}
                  className={`group relative w-[220px] flex-none bg-white rounded-xl shadow-sm hover:shadow-lg transition-all duration-300 p-4 text-left overflow-hidden border-2 ${borderClass}`}
                >
                  {/* Background Gradient */}
                  <div className={`absolute inset-0 bg-gradient-to-br ${app.color} opacity-0 group-hover:opacity-5 transition-opacity`} />

                  {/* Content */}
                  <div className="relative z-10">
                    <div className={`inline-flex items-center justify-center w-9 h-9 rounded-lg bg-gradient-to-br ${app.color} mb-2 shadow-sm group-hover:scale-110 transition-transform`}>
                      <Icon className="text-white" size={18} />
                    </div>

                    <h3 className="text-lg font-bold text-gray-900 mb-1 group-hover:text-blue-600 transition-colors">
                      {app.name}
                    </h3>

                    <p className="text-gray-500 text-xs mb-2 leading-relaxed line-clamp-2">
                      {app.description}
                    </p>

                    <div className="flex items-center text-xs text-blue-600 font-semibold group-hover:translate-x-1 transition-transform">
                      <span>시작하기</span>
                      <ChevronRight size={14} className="ml-0.5" />
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

      </div>

      {/* Footer Settings & Logout */}
      <div className="w-full max-w-7xl mx-auto px-4 pb-8 pt-0 md:pt-1">
        <div className="flex flex-col gap-4 md:gap-5">
          <div className="text-center space-y-1">
            <div className="text-sm text-gray-500">
              앱:
              <a href="/chat" className="ml-2 hover:underline">/chat</a>
              <span className="mx-1">,</span>
              <a href="/agent-chat" className="hover:underline">/agent-chat</a>
              <span className="mx-1">,</span>
              <a href="/image-compare" className="hover:underline">/image-compare</a>
              <span className="mx-1">,</span>
              <a href="/data-explorer" className="hover:underline">/data-explorer</a>
              <span className="mx-1">,</span>
              <a href="/dashboard-list" className="hover:underline">/dashboard-list</a>
            </div>
          </div>

          <div className="w-full h-px bg-gray-200" />

          <div className="flex flex-wrap justify-center items-center gap-x-8 gap-y-4 md:gap-x-12">
          {/* Profile */}
          <button
            onClick={() => navigate('/profile')}
            className="group flex flex-col items-center gap-1.5 text-gray-500 hover:text-blue-600 transition-colors"
          >
            <div className="p-2.5 bg-white rounded-full shadow-sm group-hover:shadow-md border border-gray-100 group-hover:border-blue-100 transition-all">
              <UserCircle size={16} />
            </div>
            <span className="text-xs font-medium">Profile</span>
          </button>

          {/* Help */}
          <button
            onClick={() => navigate('/help')}
            className="group flex flex-col items-center gap-1.5 text-gray-500 hover:text-blue-600 transition-colors"
          >
            <div className="p-2.5 bg-white rounded-full shadow-sm group-hover:shadow-md border border-gray-100 group-hover:border-blue-100 transition-all">
              <HelpCircle size={16} />
            </div>
            <span className="text-xs font-medium">Help</span>
          </button>

          {/* Settings */}
          <button
            onClick={() => navigate('/settings')}
            className="group flex flex-col items-center gap-1.5 text-gray-500 hover:text-gray-800 transition-colors"
          >
            <div className="p-2.5 bg-white rounded-full shadow-sm group-hover:shadow-md border border-gray-100 group-hover:border-gray-300 transition-all">
              <Settings size={16} />
            </div>
            <span className="text-xs font-medium">Settings</span>
          </button>

          {/* Logout */}
          <button
            onClick={handleLogout}
            className="group flex flex-col items-center gap-1.5 text-gray-500 hover:text-red-600 transition-colors"
          >
            <div className="p-2.5 bg-white rounded-full shadow-sm group-hover:shadow-md border border-gray-100 group-hover:border-red-100 transition-all">
              <LogOut size={16} />
            </div>
            <span className="text-xs font-medium">Log out</span>
          </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AppSelectorPage;
