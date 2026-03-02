import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { authApi } from '../../api/djangoApi';
import { Lock, Mail, User, Key, ArrowRight, Eye, EyeOff } from 'lucide-react';

const LoginPage = () => {
  const navigate = useNavigate();
  const [isLoginMode, setIsLoginMode] = useState(true);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showPasswordConfirm, setShowPasswordConfirm] = useState(false);

  const [formData, setFormData] = useState({
    username: '',
    password: '',
    password_confirm: '',
    email: '',
    auth_key: '',
    recovery_pin: '',
    recovery_pin_confirm: '',
  });

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    
    if (!isLoginMode && formData.password !== formData.password_confirm) {
      setError('Passwords do not match. Please try again.');
      return;
    }
    
    if (!isLoginMode && formData.recovery_pin !== formData.recovery_pin_confirm) {
      setError('Recovery PINs do not match. Please try again.');
      return;
    }
    
    if (!isLoginMode && (!/^\d{4,6}$/.test(formData.recovery_pin))) {
      setError('Recovery PIN must be 4 to 6 digits.');
      return;
    }
    
    setIsLoading(true);

    try {
      let data;
      if (isLoginMode) {
        data = await authApi.login({
          username: formData.username,
          password: formData.password
        });
      } else {
        data = await authApi.signup(formData);
      }

      if (data.token) {
        sessionStorage.setItem('authToken', data.token);
        sessionStorage.setItem('userId', data.user_id);
        sessionStorage.setItem('username', data.username);
        sessionStorage.setItem('is_staff', data.is_staff ? 'true' : 'false');
        
        const emailToSave = data.email || formData.email || 'user@example.com';
        sessionStorage.setItem('email', emailToSave);
        
        const returnTo = sessionStorage.getItem('returnTo');
        if (returnTo && returnTo.startsWith('/') && returnTo !== '/login') {
          sessionStorage.removeItem('returnTo');
          navigate(returnTo);
        } else {
          navigate('/');
        }
      }
    } catch (err) {
      console.error(err);
      const msg = err.response?.data?.error || "인증에 실패했습니다. 정보를 확인해주세요.";
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--bg-primary)] p-4 overflow-y-auto">
      {/* 배경 데코레이션 */}
      <div className="absolute top-[-10%] left-[-10%] w-[500px] h-[500px] bg-[var(--accent-color)] rounded-full opacity-5 blur-[100px] pointer-events-none"></div>
      <div className="absolute bottom-[-10%] right-[-10%] w-[500px] h-[500px] bg-purple-500 rounded-full opacity-5 blur-[100px] pointer-events-none"></div>

      {/* 메인 카드 컨테이너 */}
      <div className="relative w-full max-w-[340px] my-4 bg-[var(--bg-secondary)] rounded-2xl shadow-2xl border border-[var(--border-color)] overflow-hidden transition-all duration-300 transform scale-[0.9] origin-center">
       
        {/* 상단 헤더 영역 */}
        <div className="px-6 pt-6 pb-2 text-center">
          <h1 className="text-xl font-extrabold text-[var(--text-primary)] tracking-tight mb-0.5">
            {isLoginMode ? 'Welcome Back' : 'Create Account'}
          </h1>
          <p className="text-[var(--text-secondary)] text-[11px]">
            {isLoginMode
              ? 'Enter your credential.'
              : 'Join us to experience the power of AI Agents.'}
          </p>
        </div>

        {/* 에러 메시지 */}
        {error && (
          <div className="mx-6 mb-3 p-2 bg-red-500/10 border border-red-500/20 rounded-lg flex items-center gap-2 animate-fade-in">
            <div className="w-1 h-1 rounded-full bg-red-500 shrink-0" />
            <p className="text-red-500 text-[10px] font-medium">{error}</p>
          </div>
        )}

        {/* 폼 영역 */}
        <form onSubmit={handleSubmit} className="px-6 pb-6 flex flex-col gap-2">
         
          {/* Username */}
          <div className="space-y-0.5">
            <label className="text-[9px] font-semibold text-[var(--text-secondary)] uppercase tracking-wider ml-1">Username</label>
            <div className="relative group">
              <User className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-secondary)] group-focus-within:text-[var(--accent-color)] transition-colors" size={16} />
              <input
                type="text"
                name="username"
                value={formData.username}
                onChange={handleChange}
                required
                className="w-full pl-9 pr-3 py-1.5 bg-[var(--bg-tertiary)] border border-[var(--border-color)] rounded-lg text-sm text-[var(--text-primary)] placeholder-[var(--text-secondary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-color)] focus:border-transparent transition-all duration-200"
                placeholder="Enter your ID"
              />
            </div>
          </div>

          {/* Password */}
          <div className="space-y-0.5">
            <label className="text-[9px] font-semibold text-[var(--text-secondary)] uppercase tracking-wider ml-1">Password</label>
            <div className="relative group">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-secondary)] group-focus-within:text-[var(--accent-color)] transition-colors" size={16} />
              <input
                type={showPassword ? "text" : "password"}
                name="password"
                value={formData.password}
                onChange={handleChange}
                required
                className="w-full pl-9 pr-9 py-1.5 bg-[var(--bg-tertiary)] border border-[var(--border-color)] rounded-lg text-sm text-[var(--text-primary)] placeholder-[var(--text-secondary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-color)] focus:border-transparent transition-all duration-200"
                placeholder="••••••••"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--text-secondary)] hover:text-[var(--accent-color)] transition-colors"
                tabIndex={-1}
              >
                {showPassword ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
          </div>

          {/* 회원가입 추가 필드 */}
          {!isLoginMode && (
            <>
              <div className="space-y-0.5 animate-slide-in">
                <label className="text-[9px] font-semibold text-[var(--text-secondary)] uppercase tracking-wider ml-1">Confirm Password</label>
                <div className="relative group">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-secondary)] group-focus-within:text-[var(--accent-color)] transition-colors" size={16} />
                  <input
                    type={showPasswordConfirm ? "text" : "password"}
                    name="password_confirm"
                    value={formData.password_confirm}
                    onChange={handleChange}
                    required
                    className="w-full pl-9 pr-9 py-1.5 bg-[var(--bg-tertiary)] border border-[var(--border-color)] rounded-lg text-sm text-[var(--text-primary)] placeholder-[var(--text-secondary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-color)] focus:border-transparent transition-all duration-200"
                    placeholder="••••••••"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPasswordConfirm(!showPasswordConfirm)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--text-secondary)] hover:text-[var(--accent-color)] transition-colors"
                    tabIndex={-1}
                  >
                    {showPasswordConfirm ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
              </div>

              <div className="space-y-0.5 animate-slide-in">
                <label className="text-[9px] font-semibold text-[var(--text-secondary)] uppercase tracking-wider ml-1">Email</label>
                <div className="relative group">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-secondary)] group-focus-within:text-[var(--accent-color)] transition-colors" size={16} />
                  <input
                    type="email"
                    name="email"
                    value={formData.email}
                    onChange={handleChange}
                    required
                    className="w-full pl-9 pr-3 py-1.5 bg-[var(--bg-tertiary)] border border-[var(--border-color)] rounded-lg text-sm text-[var(--text-primary)] placeholder-[var(--text-secondary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-color)] focus:border-transparent transition-all duration-200"
                    placeholder="example@samsung.com"
                  />
                </div>
              </div>

              <div className="space-y-0.5 animate-slide-in">
                <label className="text-[9px] font-semibold text-[var(--accent-color)] uppercase tracking-wider ml-1">Admin Key</label>
                <div className="relative group">
                  <Key className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--accent-color)]" size={16} />
                  <input
                    type="text"
                    name="auth_key"
                    value={formData.auth_key}
                    onChange={handleChange}
                    required
                    className="w-full pl-9 pr-3 py-1.5 bg-[var(--bg-tertiary)] border border-[var(--border-color)] rounded-lg text-sm text-[var(--text-primary)] placeholder-[var(--text-secondary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-color)] focus:border-transparent transition-all duration-200"
                    placeholder="6-digit secure key"
                  />
                </div>
              </div>

              <div className="space-y-0.5 animate-slide-in">
                <label className="text-[9px] font-semibold text-[var(--text-secondary)] uppercase tracking-wider ml-1">Recovery PIN</label>
                <div className="relative group">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-secondary)] group-focus-within:text-[var(--accent-color)] transition-colors" size={16} />
                  <input
                    type="password"
                    name="recovery_pin"
                    value={formData.recovery_pin}
                    onChange={handleChange}
                    required
                    maxLength={6}
                    className="w-full pl-9 pr-3 py-1.5 bg-[var(--bg-tertiary)] border border-[var(--border-color)] rounded-lg text-sm text-[var(--text-primary)] placeholder-[var(--text-secondary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-color)] focus:border-transparent transition-all duration-200"
                    placeholder="4-6 digit PIN for password recovery"
                  />
                </div>
              </div>

              <div className="space-y-0.5 animate-slide-in">
                <label className="text-[9px] font-semibold text-[var(--text-secondary)] uppercase tracking-wider ml-1">Confirm Recovery PIN</label>
                <div className="relative group">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-secondary)] group-focus-within:text-[var(--accent-color)] transition-colors" size={16} />
                  <input
                    type="password"
                    name="recovery_pin_confirm"
                    value={formData.recovery_pin_confirm}
                    onChange={handleChange}
                    required
                    maxLength={6}
                    className="w-full pl-9 pr-3 py-1.5 bg-[var(--bg-tertiary)] border border-[var(--border-color)] rounded-lg text-sm text-[var(--text-primary)] placeholder-[var(--text-secondary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-color)] focus:border-transparent transition-all duration-200"
                    placeholder="Confirm your PIN"
                  />
                </div>
              </div>
            </>
          )}

          {/* Submit Button */}
          <button
            type="submit"
            disabled={isLoading}
            className="mt-2 w-full py-2 bg-[var(--accent-color)] hover:bg-[var(--accent-hover)] text-white font-bold rounded-lg shadow-lg hover:shadow-xl hover:-translate-y-0.5 active:translate-y-0 transition-all duration-200 flex items-center justify-center gap-2 disabled:opacity-70 disabled:cursor-not-allowed"
          >
            {isLoading ? (
              <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <>
                <span className="text-sm">{isLoginMode ? 'Sign In' : 'Create Account'}</span>
                <ArrowRight size={16} />
              </>
            )}
          </button>
        </form>

        {/* Footer Toggle */}
        <div className="bg-[var(--bg-tertiary)]/50 px-6 py-3 text-center border-t border-[var(--border-color)] flex flex-col gap-1">
          <p className="text-[var(--text-secondary)] text-[10px]">
            {isLoginMode ? "Don't have an account? " : "Already have an account? "}
            <button
              onClick={() => {
                setIsLoginMode(!isLoginMode);
                setError('');
                setFormData({
                  username: '',
                  password: '',
                  password_confirm: '',
                  email: '',
                  auth_key: '',
                  recovery_pin: '',
                  recovery_pin_confirm: '',
                });
              }}
              className="text-[var(--accent-color)] font-bold hover:underline ml-1 transition-colors outline-none"
            >
              {isLoginMode ? 'Sign Up' : 'Log In'}
            </button>
          </p>
          {isLoginMode && (
            <p className="text-[var(--text-secondary)] text-[10px]">
              <button
                onClick={() => navigate('/forgot-password')}
                className="text-[var(--text-secondary)] hover:text-[var(--accent-color)] hover:underline transition-colors outline-none"
              >
                Forgot password?
              </button>
            </p>
          )}
        </div>
      </div>
    </div>
  );
};

export default LoginPage;
