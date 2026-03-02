import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Save, RotateCcw, Palette, CheckCircle, AlertCircle, ShieldCheck, BarChart2, ExternalLink } from 'lucide-react';
import { settingsApi } from '../../api/djangoApi';
import { djangoClient } from '../../api/axiosConfig';

const SettingsPage = () => {
  const navigate = useNavigate();
  const isAdmin = sessionStorage.getItem('is_staff') === 'true';
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [preferences, setPreferences] = useState(null);
  const [originalPreferences, setOriginalPreferences] = useState(null);
  const [message, setMessage] = useState(null);
  const [isDirty, setIsDirty] = useState(false);

  useEffect(() => {
    loadSettings();
  }, []);

  // Browser refresh protection
  useEffect(() => {
    const handleBeforeUnload = (e) => {
      if (isDirty) {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [isDirty]);

  const loadSettings = async () => {
    try {
      setLoading(true);
      const data = await settingsApi.getSettings();
      setPreferences(data.preferences);
      setOriginalPreferences(JSON.parse(JSON.stringify(data.preferences)));
      setIsDirty(false);
    } catch (error) {
      console.error('Failed to load settings:', error);
      setMessage({ type: 'error', text: '설정을 불러오는데 실패했습니다.' });
    } finally {
      setLoading(false);
    }
  };

  const handleBack = () => {
    if (isDirty) {
      if (window.confirm('저장되지 않은 변경사항이 있습니다. 나가시겠습니까?')) {
        navigate('/');
      }
    } else {
      navigate('/');
    }
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      await settingsApi.updateSettings(preferences);
      setOriginalPreferences(JSON.parse(JSON.stringify(preferences)));
      setIsDirty(false);
      setMessage({ type: 'success', text: '설정이 저장되었습니다.' });
      setTimeout(() => setMessage(null), 3000);
    } catch (error) {
      console.error('Failed to save settings:', error);
      setMessage({ type: 'error', text: '설정 저장에 실패했습니다.' });
    } finally {
      setSaving(false);
    }
  };

  const handleColorChange = (section, key, value) => {
    setPreferences(prev => {
      const next = {
        ...prev,
        [section]: {
          ...(prev[section] || {}),
          [key]: value
        }
      };
      // Check if actually different from original
      const isActuallyChanged = JSON.stringify(next) !== JSON.stringify(originalPreferences);
      setIsDirty(isActuallyChanged);
      return next;
    });
  };

  const handleReset = () => {
    if (window.confirm('Image Inspector 설정을 기본값으로 되돌리시겠습니까? (저장 버튼을 눌러야 반영됩니다)')) {
        const imageInspectorDefaults = {
            "diff_file1": "#3B82F6",
            "diff_file2": "#DC2626",
            "diff_common": "#000000",
            "overlay_file1": "#F97316",
            "overlay_file2": "#22C55E"
        };
        
        setPreferences(prev => ({
            ...prev,
            "image_inspector": imageInspectorDefaults
        }));
        setIsDirty(true);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50/50 flex flex-col items-center justify-center gap-4">
        <div className="w-10 h-10 border-4 border-slate-200 border-t-slate-900 rounded-full animate-spin" />
        <p className="text-slate-500 font-medium">설정을 불러오는 중...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50/50 p-8">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-10">
          <div className="flex items-center gap-4">
            <button 
              onClick={handleBack}
              className="group flex items-center justify-center w-10 h-10 bg-white border border-slate-200 rounded-xl shadow-sm hover:bg-slate-50 transition-all active:scale-95"
              title="홈으로 돌아가기"
            >
              <ArrowLeft size={20} className="text-slate-600 group-hover:text-slate-900" />
            </button>
            <div>
              <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">환경 설정</h1>
              <p className="text-sm text-slate-500 font-medium">서비스 사용 환경을 개인화합니다.</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
             {isDirty && (
               <span className="text-xs font-bold text-amber-500 bg-amber-50 px-2 py-1 rounded-md border border-amber-100 animate-pulse mr-2">
                 저장 필요
               </span>
             )}
             <button
              onClick={handleReset}
              className="flex items-center gap-2 px-4 py-2.5 bg-white border border-slate-200 text-slate-700 text-sm font-semibold rounded-xl hover:bg-slate-50 hover:border-slate-300 transition-all shadow-sm active:scale-95"
            >
              <RotateCcw size={16} />
              기본값
            </button>
            <button
              onClick={handleSave}
              disabled={saving || !isDirty}
              className="flex items-center gap-2 px-6 py-2.5 bg-slate-900 text-white text-sm font-semibold rounded-xl hover:bg-slate-800 transition-all shadow-md shadow-slate-200 disabled:opacity-50 disabled:cursor-not-allowed active:scale-95"
            >
              {saving ? (
                <>
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  저장 중
                </>
              ) : (
                <>
                  <Save size={16} />
                  설정 저장
                </>
              )}
            </button>
          </div>
        </div>

        {/* Message Toast */}
        {message && (
          <div className={`mb-8 p-4 rounded-2xl flex items-center gap-3 animate-in fade-in slide-in-from-top-2 duration-300 ${
            message.type === 'success' 
              ? 'bg-emerald-50 text-emerald-800 border border-emerald-100' 
              : 'bg-rose-50 text-rose-800 border border-rose-100'
          }`}>
            {message.type === 'success' ? (
              <CheckCircle size={18} className="text-emerald-500" />
            ) : (
              <AlertCircle size={18} className="text-rose-500" />
            )}
            <p className="text-sm font-semibold">{message.text}</p>
          </div>
        )}

        {/* Image Inspector Settings */}
        <div className="bg-white rounded-2xl shadow-sm border border-slate-400/60 overflow-hidden mb-8">
          <div className="px-8 py-6 border-b border-slate-100 bg-white flex items-center gap-4">
            <div className="w-12 h-12 rounded-2xl bg-purple-50 flex items-center justify-center">
              <Palette className="text-purple-600" size={24} />
            </div>
            <div>
              <h2 className="text-lg font-bold text-slate-900">Image Inspector 색상 설정</h2>
              <p className="text-sm text-slate-500">이미지 비교 시 사용되는 하이라이트 색상을 커스터마이징합니다.</p>
            </div>
          </div>
          
          <div className="p-8">
            <div className="mb-10">
              <div className="flex items-center gap-2 mb-6">
                <div className="w-1.5 h-1.5 rounded-full bg-slate-400"></div>
                <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider">비교 (Difference Mode)</h3>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                <ColorPicker 
                  label="File 1 (기준 파일)" 
                  description="기준 파일에만 존재하는 요소"
                  value={preferences?.image_inspector?.diff_file1}
                  onChange={(v) => handleColorChange('image_inspector', 'diff_file1', v)}
                />
                <ColorPicker 
                  label="File 2 (비교 파일)" 
                  description="비교 파일에만 존재하는 요소"
                  value={preferences?.image_inspector?.diff_file2}
                  onChange={(v) => handleColorChange('image_inspector', 'diff_file2', v)}
                />
                <ColorPicker 
                  label="공통 요소" 
                  description="두 파일 모두에 존재하는 요소"
                  value={preferences?.image_inspector?.diff_common}
                  onChange={(v) => handleColorChange('image_inspector', 'diff_common', v)}
                />
              </div>
            </div>

            <div className="h-px bg-slate-100 mb-10"></div>

            <div>
              <div className="flex items-center gap-2 mb-6">
                <div className="w-1.5 h-1.5 rounded-full bg-slate-400"></div>
                <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider">오버레이 (Overlay Mode)</h3>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                <ColorPicker 
                  label="File 1 레이어" 
                  description="첫 번째 이미지의 오버레이 색상"
                  value={preferences?.image_inspector?.overlay_file1}
                  onChange={(v) => handleColorChange('image_inspector', 'overlay_file1', v)}
                />
                <ColorPicker 
                  label="File 2 레이어" 
                  description="두 번째 이미지의 오버레이 색상"
                  value={preferences?.image_inspector?.overlay_file2}
                  onChange={(v) => handleColorChange('image_inspector', 'overlay_file2', v)}
                />
              </div>
            </div>
          </div>
        </div>

      {/* Admin Section */}
      {isAdmin && (
        <div className="bg-white rounded-2xl shadow-sm border border-slate-400/60 overflow-hidden mb-8">
          <div className="px-8 py-6 border-b border-slate-100 bg-white flex items-center gap-4">
            <div className="w-12 h-12 rounded-2xl bg-indigo-50 flex items-center justify-center">
              <ShieldCheck className="text-indigo-600" size={24} />
            </div>
            <div>
              <h2 className="text-lg font-bold text-slate-900">Admin</h2>
              <p className="text-sm text-slate-500">관리자 전용 기능입니다.</p>
            </div>
          </div>

          <div className="p-4">
            <a
              href={djangoClient.defaults.baseURL + '/admin/usage-stats/'}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-3 px-4 py-3 rounded-xl hover:bg-indigo-50 transition-colors text-sm group"
            >
              <BarChart2 size={18} className="text-indigo-500 flex-shrink-0" />
              <div className="flex-1">
                <div className="font-semibold text-slate-800">사용자별 이용량 통계</div>
                <div className="text-xs text-slate-500 mt-0.5">채팅 앱 및 Data Explorer 주간/월간 이용량</div>
              </div>
              <ExternalLink size={14} className="text-slate-400 group-hover:text-indigo-500 transition-colors" />
            </a>
            <a
              href={djangoClient.defaults.baseURL + '/admin/'}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-3 px-4 py-3 rounded-xl hover:bg-slate-50 transition-colors text-sm group"
            >
              <ShieldCheck size={18} className="text-slate-400 flex-shrink-0" />
              <div className="flex-1">
                <div className="font-semibold text-slate-800">Django Admin</div>
                <div className="text-xs text-slate-500 mt-0.5">데이터베이스 직접 관리</div>
              </div>
              <ExternalLink size={14} className="text-slate-400 group-hover:text-slate-600 transition-colors" />
            </a>
          </div>
        </div>
      )}
      </div>
    </div>
  );
};

const ColorPicker = ({ label, description, value, onChange }) => (
  <div className="group flex flex-col gap-3 p-4 rounded-2xl bg-slate-50 border border-transparent hover:border-slate-200 hover:bg-white hover:shadow-sm transition-all duration-200">
    <div>
      <label className="text-sm font-bold text-slate-700 block mb-1">{label}</label>
      <p className="text-xs text-slate-500 leading-relaxed">{description}</p>
    </div>
    <div className="flex items-center gap-4">
      <div className="relative w-12 h-12 flex-shrink-0">
        <input
          type="color"
          value={value || '#000000'}
          onChange={(e) => onChange(e.target.value)}
          className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
        />
        <div 
          className="w-full h-full rounded-xl border-2 border-white shadow-sm ring-1 ring-slate-200"
          style={{ backgroundColor: value || '#000000' }}
        />
      </div>
      <div className="flex flex-col">
        <span className="text-sm font-mono font-bold text-slate-900 uppercase tracking-tight">{value}</span>
        <span className="text-[10px] font-bold text-slate-400 uppercase">HEX CODE</span>
      </div>
    </div>
  </div>
);

export default SettingsPage;
