import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Save, RotateCcw, Palette, CheckCircle, AlertCircle, ShieldCheck, BarChart2, ExternalLink, SlidersHorizontal, ChevronDown, ChevronUp } from 'lucide-react';
import { settingsApi } from '../../api/djangoApi';
import { djangoClient } from '../../api/axiosConfig';
import PresetAdminPanel from './components/PresetAdminPanel';
import SliderInput from './components/SliderInput';

// Image Inspector 설정 기본값
const COLOR_DEFAULTS = {
  diff_file1: '#3B82F6',
  diff_file2: '#DC2626',
  diff_common: '#000000',
};

const QUALITY_DEFAULTS = {
  output_quality: 85,
  output_resolution: 2000,
  processing_resolution: 6000,
  pdf_dpi: 200,
};

const SettingsPage = () => {
  const navigate = useNavigate();
  const isAdmin = sessionStorage.getItem('is_staff') === 'true';
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [preferences, setPreferences] = useState(null);
  const [originalPreferences, setOriginalPreferences] = useState(null);
  const [message, setMessage] = useState(null);
  const [isDirty, setIsDirty] = useState(false);
  const [isAdvancedOpen, setIsAdvancedOpen] = useState(false);

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
      const isActuallyChanged = JSON.stringify(next) !== JSON.stringify(originalPreferences);
      setIsDirty(isActuallyChanged);
      return next;
    });
  };

  const handleQualityChange = (key, value) => {
    setPreferences(prev => {
      const next = {
        ...prev,
        image_inspector: {
          ...(prev.image_inspector || {}),
          [key]: value,
        },
      };
      const isActuallyChanged = JSON.stringify(next) !== JSON.stringify(originalPreferences);
      setIsDirty(isActuallyChanged);
      return next;
    });
  };

  // 색상만 기본값 복원 (품질 설정 유지)
  const handleResetColors = () => {
    if (window.confirm('색상 설정을 기본값으로 되돌리시겠습니까? (저장 버튼을 눌러야 반영됩니다)')) {
      setPreferences(prev => ({
        ...prev,
        image_inspector: {
          ...(prev.image_inspector || {}),
          ...COLOR_DEFAULTS,
        },
      }));
      setIsDirty(true);
    }
  };

  // 품질 설정만 기본값 복원 (색상 유지)
  const handleResetQuality = () => {
    if (window.confirm('이미지 품질 설정을 기본값으로 되돌리시겠습니까? (저장 버튼을 눌러야 반영됩니다)')) {
      setPreferences(prev => ({
        ...prev,
        image_inspector: {
          ...(prev.image_inspector || {}),
          ...QUALITY_DEFAULTS,
        },
      }));
      setIsDirty(true);
    }
  };

  // 전체 기본값 복원 (헤더 버튼)
  const handleReset = () => {
    if (window.confirm('Image Inspector 모든 설정을 기본값으로 되돌리시겠습니까? (저장 버튼을 눌러야 반영됩니다)')) {
      setPreferences(prev => ({
        ...prev,
        image_inspector: {
          ...(prev.image_inspector || {}),
          ...COLOR_DEFAULTS,
          ...QUALITY_DEFAULTS,
        },
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
            <div className="flex-1">
              <h2 className="text-lg font-bold text-slate-900">Image Inspector 색상 설정</h2>
              <p className="text-sm text-slate-500">이미지 비교 시 사용되는 하이라이트 색상을 커스터마이징합니다.</p>
            </div>
            <button
              onClick={handleResetColors}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-50 border border-slate-200 text-slate-600 text-xs font-semibold rounded-xl hover:bg-slate-100 transition-all"
              title="색상 기본값 복원"
            >
              <RotateCcw size={12} />
              기본값
            </button>
          </div>
          
          <div className="p-8">
            <div className="mb-10">              
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
          </div>
        </div>

        {/* Image Inspector Quality Settings */}
        <div className="bg-white rounded-2xl shadow-sm border border-slate-400/60 overflow-hidden mb-8">
          {/* 헤더 */}
          <div className="px-8 py-6 border-b border-slate-100 bg-white flex items-center gap-4">
            <div className="w-12 h-12 rounded-2xl bg-sky-50 flex items-center justify-center">
              <SlidersHorizontal className="text-sky-600" size={24} />
            </div>
            <div className="flex-1">
              <h2 className="text-lg font-bold text-slate-900">Image Inspector 품질 설정</h2>
              <p className="text-sm text-slate-500">이미지 변환 및 출력 품질을 조정합니다.</p>
            </div>
            <button
              onClick={handleResetQuality}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-50 border border-slate-200 text-slate-600 text-xs font-semibold rounded-xl hover:bg-slate-100 transition-all"
              title="품질 기본값 복원"
            >
              <RotateCcw size={12} />
              기본값
            </button>
          </div>

          <div className="p-8">
            {/* 출력 품질 섹션 */}
            <div className="mb-8">
              <div className="flex items-center gap-2 mb-6">
                <div className="w-1.5 h-1.5 rounded-full bg-slate-400"></div>
                <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider">비교 결과 출력 품질</h3>
              </div>
              <p className="text-xs text-slate-500 mb-6 leading-relaxed">
                비교 연산이 완료된 후 브라우저에 표시할 이미지의 해상도와 품질입니다.
                값을 낮추면 응답 속도가 향상됩니다.
              </p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <SliderInput
                  label="출력 해상도"
                  description="화면에 표시되는 이미지의 최대 크기"
                  value={preferences?.image_inspector?.output_resolution ?? QUALITY_DEFAULTS.output_resolution}
                  onChange={(v) => handleQualityChange('output_resolution', v)}
                  min={1000}
                  max={4000}
                  step={100}
                  unit="px"
                />
                <SliderInput
                  label="JPEG 출력 품질"
                  description="비교 결과 이미지의 JPEG 압축 품질"
                  value={preferences?.image_inspector?.output_quality ?? QUALITY_DEFAULTS.output_quality}
                  onChange={(v) => handleQualityChange('output_quality', v)}
                  min={50}
                  max={100}
                  step={1}
                  unit="%"
                />
              </div>
            </div>

            <div className="h-px bg-slate-100 mb-6"></div>

            {/* 비교 연산 품질 섹션 (접이식) */}
            <div>
              <button
                onClick={() => setIsAdvancedOpen(v => !v)}
                className="w-full flex items-center justify-between group"
              >
                <div className="flex items-center gap-2">
                  <div className="w-1.5 h-1.5 rounded-full bg-slate-400"></div>
                  <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider">비교 연산 품질 (고급)</h3>
                </div>
                {isAdvancedOpen
                  ? <ChevronUp size={16} className="text-slate-400" />
                  : <ChevronDown size={16} className="text-slate-400" />
                }
              </button>

              {isAdvancedOpen && (
                <div className="mt-6">
                  <p className="text-xs text-slate-500 mb-6 p-3 bg-amber-50 rounded-xl border border-amber-100 leading-relaxed">
                    ⚠️ 비교 연산에 사용되는 이미지 해상도를 설정합니다.
                    값을 높이면 미세한 차이를 더 정확하게 감지하지만 처리 시간과 메모리 사용량이 증가합니다.
                  </p>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <SliderInput
                      label="연산용 해상도"
                      description="비교 연산 시 사용하는 이미지 최대 크기. 클수록 정확하나 느림"
                      value={preferences?.image_inspector?.processing_resolution ?? QUALITY_DEFAULTS.processing_resolution}
                      onChange={(v) => handleQualityChange('processing_resolution', v)}
                      min={4000}
                      max={8000}
                      step={500}
                      unit="px"
                    />
                    <SliderInput
                      label="PDF 변환 DPI"
                      description="PDF 페이지를 이미지로 변환할 때의 해상도"
                      value={preferences?.image_inspector?.pdf_dpi ?? QUALITY_DEFAULTS.pdf_dpi}
                      onChange={(v) => handleQualityChange('pdf_dpi', v)}
                      min={100}
                      max={300}
                      step={25}
                      unit="dpi"
                    />
                  </div>
                </div>
              )}
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
            <PresetAdminPanel />
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
