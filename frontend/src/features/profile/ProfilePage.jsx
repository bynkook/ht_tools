import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { authApi } from '../../api/djangoApi';
import { User, Mail, Lock, ArrowLeft, Save, ShieldCheck } from 'lucide-react';

const ProfilePage = () => {
  const navigate = useNavigate();
  const [profile, setProfile] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const [formData, setFormData] = useState({
    new_password: '',
    new_password_confirm: '',
    new_pin: '',
    new_pin_confirm: '',
  });

  useEffect(() => {
    const fetchProfile = async () => {
      try {
        const data = await authApi.getProfile();
        setProfile(data);
      } catch (err) {
        console.error('Failed to fetch profile:', err);
        setError('Failed to load profile information.');
      } finally {
        setIsLoading(false);
      }
    };

    fetchProfile();
  }, []);

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSuccess('');

    // Validation
    if (!formData.new_password && !formData.new_pin) {
      setError('Please enter a new password or PIN to update.');
      return;
    }

    if (formData.new_password && formData.new_password !== formData.new_password_confirm) {
      setError('New passwords do not match.');
      return;
    }

    if (formData.new_pin) {
      if (formData.new_pin !== formData.new_pin_confirm) {
        setError('New PINs do not match.');
        return;
      }
      if (!/^\d{4,6}$/.test(formData.new_pin)) {
        setError('PIN must be 4 to 6 digits.');
        return;
      }
    }

    setIsSaving(true);

    try {
      const updateData = {};
      if (formData.new_password) updateData.new_password = formData.new_password;
      if (formData.new_pin) updateData.new_pin = formData.new_pin;

      await authApi.updateProfile(updateData);
      
      setSuccess('Profile updated successfully.');
      setFormData({
        new_password: '',
        new_password_confirm: '',
        new_pin: '',
        new_pin_confirm: '',
      });
      
      // Refresh profile data to update has_recovery_pin status
      const data = await authApi.getProfile();
      setProfile(data);
      
    } catch (err) {
      console.error('Failed to update profile:', err);
      setError(err.response?.data?.error || 'Failed to update profile.');
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-[var(--bg-primary)] flex items-center justify-center">
        <div className="w-8 h-8 border-4 border-[var(--accent-color)] border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[var(--bg-primary)] p-6 flex justify-center items-start pt-20">
      <div className="w-full max-w-md bg-[var(--bg-secondary)] rounded-2xl shadow-xl border border-[var(--border-color)] overflow-hidden">
        
        {/* Header */}
        <div className="px-6 py-5 border-b border-[var(--border-color)] flex items-center gap-4">
          <button 
            onClick={() => navigate('/')}
            className="p-2 hover:bg-[var(--bg-tertiary)] rounded-lg text-[var(--text-secondary)] transition-colors"
          >
            <ArrowLeft size={20} />
          </button>
          <div>
            <h1 className="text-xl font-bold text-[var(--text-primary)]">User Profile</h1>
            <p className="text-xs text-[var(--text-secondary)]">Manage your account security</p>
          </div>
        </div>

        <div className="p-6 space-y-8">
          {/* Messages */}
          {error && (
            <div className="p-3 bg-red-50 text-red-600 text-sm rounded-lg border border-red-100">
              {error}
            </div>
          )}
          {success && (
            <div className="p-3 bg-green-50 text-green-600 text-sm rounded-lg border border-green-100">
              {success}
            </div>
          )}

          {/* Read-only Info */}
          <div className="space-y-4">
            <h2 className="text-sm font-semibold text-[var(--text-secondary)] uppercase tracking-wider flex items-center gap-2">
              <User size={16} /> Account Information
            </h2>
            
            <div className="bg-[var(--bg-tertiary)] p-4 rounded-xl space-y-3">
              <div>
                <label className="text-xs text-[var(--text-secondary)]">Username</label>
                <div className="text-sm font-medium text-[var(--text-primary)]">{profile?.username}</div>
              </div>
              <div>
                <label className="text-xs text-[var(--text-secondary)]">Email</label>
                <div className="text-sm font-medium text-[var(--text-primary)]">{profile?.email}</div>
              </div>
              <div>
                <label className="text-xs text-[var(--text-secondary)]">Recovery PIN Status</label>
                <div className="flex items-center gap-2 mt-1">
                  {profile?.has_recovery_pin ? (
                    <span className="inline-flex items-center gap-1 px-2 py-1 bg-green-100 text-green-700 text-xs font-medium rounded-md">
                      <ShieldCheck size={14} /> Set
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 px-2 py-1 bg-yellow-100 text-yellow-700 text-xs font-medium rounded-md">
                      Not Set
                    </span>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Update Form */}
          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="space-y-4">
              <h2 className="text-sm font-semibold text-[var(--text-secondary)] uppercase tracking-wider flex items-center gap-2">
                <Lock size={16} /> Security Settings
              </h2>
              
              {/* Password Update */}
              <div className="space-y-3">
                <div>
                  <label className="block text-xs text-[var(--text-secondary)] mb-1">New Password</label>
                  <input
                    type="password"
                    name="new_password"
                    value={formData.new_password}
                    onChange={handleChange}
                    className="w-full px-3 py-2 bg-[var(--bg-tertiary)] border border-[var(--border-color)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[var(--accent-color)]"
                    placeholder="Leave blank to keep current"
                  />
                </div>
                <div>
                  <label className="block text-xs text-[var(--text-secondary)] mb-1">Confirm New Password</label>
                  <input
                    type="password"
                    name="new_password_confirm"
                    value={formData.new_password_confirm}
                    onChange={handleChange}
                    className="w-full px-3 py-2 bg-[var(--bg-tertiary)] border border-[var(--border-color)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[var(--accent-color)]"
                    placeholder="Confirm new password"
                  />
                </div>
              </div>

              <div className="h-px bg-[var(--border-color)] my-4"></div>

              {/* PIN Update */}
              <div className="space-y-3">
                <div>
                  <label className="block text-xs text-[var(--text-secondary)] mb-1">New Recovery PIN</label>
                  <input
                    type="password"
                    name="new_pin"
                    value={formData.new_pin}
                    onChange={handleChange}
                    maxLength={6}
                    className="w-full px-3 py-2 bg-[var(--bg-tertiary)] border border-[var(--border-color)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[var(--accent-color)]"
                    placeholder="4-6 digits (Leave blank to keep current)"
                  />
                </div>
                <div>
                  <label className="block text-xs text-[var(--text-secondary)] mb-1">Confirm New PIN</label>
                  <input
                    type="password"
                    name="new_pin_confirm"
                    value={formData.new_pin_confirm}
                    onChange={handleChange}
                    maxLength={6}
                    className="w-full px-3 py-2 bg-[var(--bg-tertiary)] border border-[var(--border-color)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[var(--accent-color)]"
                    placeholder="Confirm new PIN"
                  />
                </div>
              </div>
            </div>

            <button
              type="submit"
              disabled={isSaving || (!formData.new_password && !formData.new_pin)}
              className="w-full py-2.5 bg-[var(--accent-color)] hover:bg-[var(--accent-hover)] text-white font-medium rounded-lg shadow-md transition-colors flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSaving ? (
                <span className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <>
                  <Save size={18} />
                  Save Changes
                </>
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
};

export default ProfilePage;
