import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { authApi } from '../../api/djangoApi';
import { Lock, User, ArrowRight, Eye, EyeOff, ArrowLeft } from 'lucide-react';

const ForgotPasswordPage = () => {
  const navigate = useNavigate();
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showPasswordConfirm, setShowPasswordConfirm] = useState(false);

  const [formData, setFormData] = useState({
    username: '',
    recovery_pin: '',
    new_password: '',
    new_password_confirm: '',
  });

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    
    if (formData.new_password !== formData.new_password_confirm) {
      setError('Passwords do not match. Please try again.');
      return;
    }
    
    setIsLoading(true);

    try {
      await authApi.resetPassword({
        username: formData.username,
        recovery_pin: formData.recovery_pin,
        new_password: formData.new_password
      });
      
      setSuccess('Password reset successful. You can now log in with your new password.');
      setTimeout(() => {
        navigate('/login');
      }, 3000);
    } catch (err) {
      console.error(err);
      const msg = err.response?.data?.error || "Failed to reset password. Please check your information.";
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
        <div className="px-6 pt-6 pb-2 text-center relative">
          <button 
            onClick={() => navigate('/login')}
            className="absolute left-4 top-6 text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
          >
            <ArrowLeft size={20} />
          </button>
          <h1 className="text-xl font-extrabold text-[var(--text-primary)] tracking-tight mb-0.5">
            Reset Password
          </h1>
          <p className="text-[var(--text-secondary)] text-[11px]">
            Enter your ID and recovery PIN to reset your password.
          </p>
        </div>

        {/* 에러/성공 메시지 */}
        {error && (
          <div className="mx-6 mb-3 p-2 bg-red-500/10 border border-red-500/20 rounded-lg flex items-center gap-2 animate-fade-in">
            <div className="w-1 h-1 rounded-full bg-red-500 shrink-0" />
            <p className="text-red-500 text-[10px] font-medium">{error}</p>
          </div>
        )}
        {success && (
          <div className="mx-6 mb-3 p-2 bg-green-500/10 border border-green-500/20 rounded-lg flex items-center gap-2 animate-fade-in">
            <div className="w-1 h-1 rounded-full bg-green-500 shrink-0" />
            <p className="text-green-500 text-[10px] font-medium">{success}</p>
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

          {/* Recovery PIN */}
          <div className="space-y-0.5">
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
                placeholder="Enter your 4-6 digit PIN"
              />
            </div>
          </div>

          {/* New Password */}
          <div className="space-y-0.5">
            <label className="text-[9px] font-semibold text-[var(--text-secondary)] uppercase tracking-wider ml-1">New Password</label>
            <div className="relative group">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-secondary)] group-focus-within:text-[var(--accent-color)] transition-colors" size={16} />
              <input
                type={showPassword ? "text" : "password"}
                name="new_password"
                value={formData.new_password}
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

          {/* Confirm New Password */}
          <div className="space-y-0.5">
            <label className="text-[9px] font-semibold text-[var(--text-secondary)] uppercase tracking-wider ml-1">Confirm New Password</label>
            <div className="relative group">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-secondary)] group-focus-within:text-[var(--accent-color)] transition-colors" size={16} />
              <input
                type={showPasswordConfirm ? "text" : "password"}
                name="new_password_confirm"
                value={formData.new_password_confirm}
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

          {/* Submit Button */}
          <button
            type="submit"
            disabled={isLoading || success}
            className="mt-2 w-full py-2 bg-[var(--accent-color)] hover:bg-[var(--accent-hover)] text-white font-bold rounded-lg shadow-lg hover:shadow-xl hover:-translate-y-0.5 active:translate-y-0 transition-all duration-200 flex items-center justify-center gap-2 disabled:opacity-70 disabled:cursor-not-allowed"
          >
            {isLoading ? (
              <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <>
                <span className="text-sm">Reset Password</span>
                <ArrowRight size={16} />
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  );
};

export default ForgotPasswordPage;
