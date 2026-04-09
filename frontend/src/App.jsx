import React, { Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { getDjangoUrl } from './api/axiosConfig';

// Lazy loading for code splitting and better performance
const LoginPage = lazy(() => import('./features/auth/LoginPage'));
const ForgotPasswordPage = lazy(() => import('./features/auth/ForgotPasswordPage'));

// Agent Chat (기존 FabriX Agent Chat)
const AgentChatLayout = lazy(() => import('./components/layout/AgentChatLayout'));
const AgentChatPage = lazy(() => import('./features/agentChat/ChatPage'));

// Model Chat (새 FabriX Chat)
const ChatLayout = lazy(() => import('./components/layout/ChatLayout'));
const ChatPage = lazy(() => import('./features/chat/ChatPage'));

// Other Pages
const ImageComparePage = lazy(() => import('./features/imageCompare/ImageComparePage'));
const DataExplorerPage = lazy(() => import('./features/dataExplorer/DataExplorerPage'));
const AppSelectorPage = lazy(() => import('./features/appSelector/AppSelectorPage'));
const BoardPage = lazy(() => import('./features/board/BoardPage'));
const RedditPostDetailPage = lazy(() => import('./features/board/RedditPostDetailPage'));
const SettingsPage = lazy(() => import('./features/settings/SettingsPage'));
const ProfilePage = lazy(() => import('./features/profile/ProfilePage'));
const HelpPage = lazy(() => import('./features/help/HelpPage'));
const DocUploaderPage = lazy(() => import('./features/docUploader/DocUploaderPage'));
const EscCalculatorPage = lazy(() => import('./features/escCalculator/EscCalculatorPage'));
const PeLogSheetPage = lazy(() => import('./features/peLogSheet/PeLogSheetPage'));

// Error Boundary Component
class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: '20px', color: 'red' }}>
          <h1>Something went wrong.</h1>
          <pre>{this.state.error?.toString()}</pre>
        </div>
      );
    }
    return this.props.children;
  }
}

// --- Route Guard ---
// 토큰이 없으면 로그인 페이지로 리다이렉트시키는 보호 컴포넌트
const PrivateRoute = ({ children }) => {
  const token = sessionStorage.getItem('authToken');
  const location = useLocation();
  
  if (!token) {
    // 로그인 후 돌아올 경로 저장
    sessionStorage.setItem('returnTo', location.pathname);
    return <Navigate to="/login" replace />;
  }
  
  return children;
};

// Loading fallback component
const LoadingFallback = () => (
  <div style={{ 
    display: 'flex', 
    justifyContent: 'center', 
    alignItems: 'center', 
    height: '100vh',
    backgroundColor: 'var(--bg-primary, #ffffff)'
  }}>
    <div style={{ textAlign: 'center' }}>
      <div style={{ 
        width: '40px', 
        height: '40px', 
        border: '3px solid #e5e7eb',
        borderTopColor: '#3b82f6',
        borderRadius: '50%',
        animation: 'spin 1s linear infinite',
        margin: '0 auto 16px'
      }} />
      <p style={{ color: '#6b7280' }}>Loading...</p>
    </div>
    <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
  </div>
);

const DjangoAdminRedirect = () => {
  const location = useLocation();

  React.useEffect(() => {
    const targetPath = `${location.pathname}${location.search}${location.hash}`;
    window.location.replace(getDjangoUrl(targetPath));
  }, [location]);

  return <LoadingFallback />;
};

const App = () => {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <Suspense fallback={<LoadingFallback />}>
          <Routes>
            {/* Public Route: 로그인/회원가입/비밀번호찾기 */}
            <Route path="/login" element={<LoginPage />} />
            <Route path="/forgot-password" element={<ForgotPasswordPage />} />

            {/* Protected Routes: 인증된 사용자만 접근 가능 */}
            
            {/* Root - 앱 선택 페이지 */}
            <Route path="/" element={<PrivateRoute><AppSelectorPage /></PrivateRoute>} />
            
            {/* Settings & Profile & Help */}
            <Route path="/settings" element={<PrivateRoute><SettingsPage /></PrivateRoute>} />
            <Route path="/profile" element={<PrivateRoute><ProfilePage /></PrivateRoute>} />
            <Route path="/help" element={<PrivateRoute><HelpPage /></PrivateRoute>} />
            {/* Image Compare - 독립적인 레이아웃 */}
            <Route path="/image-compare" element={<PrivateRoute><ImageComparePage /></PrivateRoute>} />

            {/* Django Admin should never be claimed by board slug routing */}
            <Route path="/admin/*" element={<DjangoAdminRedirect />} />
            <Route path="/api/*" element={<DjangoAdminRedirect />} />
            
            {/* FabriX Chat (Model Chat) - 새 앱, /chat 경로 */}
            <Route path="/chat" element={<PrivateRoute><ChatLayout /></PrivateRoute>}>
              <Route index element={<ChatPage />} />
            </Route>

            {/* FabriX Agent Chat - 기존 앱, /agent-chat 경로로 이동 */}
            <Route path="/agent-chat" element={<PrivateRoute><AgentChatLayout /></PrivateRoute>}>
              <Route index element={<AgentChatPage />} />
            </Route>

            {/* Data Explorer - Standalone Layout */}
            <Route path="/data-explorer" element={<PrivateRoute><DataExplorerPage /></PrivateRoute>} />

            {/* Doc Uploader */}
            <Route path="/doc-uploader" element={<PrivateRoute><DocUploaderPage /></PrivateRoute>} />

            {/* ESC 물가변동 산출 */}
            <Route path="/esc-calculator" element={<PrivateRoute><EscCalculatorPage /></PrivateRoute>} />

            {/* PE Log Sheet */}
            <Route path="/pe-log-sheet" element={<PrivateRoute><PeLogSheetPage /></PrivateRoute>} />

            {/* Board Pages - root-level slug policy */}
            <Route path="/:boardSlug/post/:postId" element={<PrivateRoute><RedditPostDetailPage /></PrivateRoute>} />
            <Route path="/:boardSlug" element={<PrivateRoute><BoardPage /></PrivateRoute>} />

            {/* 404: 알 수 없는 경로는 로그인 페이지로 리다이렉트 */}
            <Route path="*" element={<Navigate to="/login" replace />} />
          </Routes>
        </Suspense>
      </BrowserRouter>
    </ErrorBoundary>
  );
};

export default App;
