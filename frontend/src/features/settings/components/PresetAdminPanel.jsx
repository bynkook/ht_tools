import React, { useState, useEffect, useCallback } from 'react';
import { BarChart3, ChevronDown, ChevronUp, Trash2, Loader2, AlertCircle, Search } from 'lucide-react';
import { presetApi } from '../../../api/djangoApi';

const PresetList = ({ label, items, selected, onToggle, onToggleAll, filter, setFilter }) => {
  const filtered = filter ? items.filter(p => p.name.toLowerCase().includes(filter.toLowerCase())) : items;
  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">{label} ({items.length})</span>
        {filtered.length > 0 && (
          <button onClick={() => onToggleAll(filtered)} className="text-[10px] text-slate-400 hover:text-slate-600 transition-colors">
            {filtered.every(p => selected.has(p.id)) ? '전체 해제' : '전체 선택'}
          </button>
        )}
      </div>
      <div className="relative mb-1.5">
        <Search size={11} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
        <input
          type="text"
          value={filter}
          onChange={e => setFilter(e.target.value)}
          placeholder="이름 검색..."
          className="w-full pl-7 pr-2 py-1.5 text-[11px] border border-slate-200 rounded-lg bg-slate-50 focus:outline-none focus:border-indigo-300 focus:bg-white transition-colors"
        />
      </div>
      <div className="max-h-[200px] overflow-y-auto border border-slate-200 rounded-xl bg-slate-50">
        {filtered.length === 0 ? (
          <p className="text-xs text-slate-400 text-center py-4">{filter ? '검색 결과 없음' : '없음'}</p>
        ) : filtered.map(p => (
          <label key={p.id} className="flex items-center gap-2.5 px-3 py-2 hover:bg-white cursor-pointer border-b border-slate-100 last:border-0 transition-colors">
            <input type="checkbox" checked={selected.has(p.id)} onChange={() => onToggle(p.id)} className="rounded accent-indigo-500" />
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium text-slate-800 truncate">{p.name}</p>
              <p className="text-[10px] text-slate-400">@{p.owner_username} · {new Date(p.updated_at).toLocaleDateString('ko-KR')}</p>
            </div>
          </label>
        ))}
      </div>
    </div>
  );
};

const PresetAdminPanel = () => {
  const [open, setOpen] = useState(false);
  const [presets, setPresets] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [loading, setLoading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState(null);
  const [publicFilter, setPublicFilter] = useState('');
  const [privateFilter, setPrivateFilter] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await presetApi.list();
      setPresets(data.presets || []);
    } catch {
      setError('프리셋 목록을 불러오는데 실패했습니다.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { if (open) load(); }, [open, load]);

  const publicPresets = presets.filter(p => p.is_public).sort((a, b) => a.name.localeCompare(b.name, 'ko'));
  const privatePresets = presets.filter(p => !p.is_public).sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at));

  const toggle = (id) => setSelected(prev => {
    const next = new Set(prev);
    next.has(id) ? next.delete(id) : next.add(id);
    return next;
  });

  const toggleAll = (items) => {
    const ids = items.map(p => p.id);
    const allSelected = ids.every(id => selected.has(id));
    setSelected(prev => {
      const next = new Set(prev);
      ids.forEach(id => allSelected ? next.delete(id) : next.add(id));
      return next;
    });
  };

  const handleDelete = async () => {
    if (!selected.size) return;
    if (!window.confirm(`선택한 ${selected.size}개 프리셋을 삭제하시겠습니까?`)) return;
    setDeleting(true);
    try {
      await Promise.all([...selected].map(id => presetApi.delete(id)));
      setSelected(new Set());
      await load();
    } catch {
      setError('일부 프리셋 삭제에 실패했습니다.');
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="border-t border-slate-100 mt-1">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center gap-3 px-4 py-3 rounded-xl hover:bg-orange-50 transition-colors text-sm"
      >
        <BarChart3 size={18} className="text-orange-500 flex-shrink-0" />
        <div className="flex-1 text-left">
          <div className="font-semibold text-slate-800">Data Explorer Preset 관리</div>
          <div className="text-xs text-slate-500 mt-0.5">공용/개인 프리셋 일괄 삭제</div>
        </div>
        {open ? <ChevronUp size={14} className="text-slate-400" /> : <ChevronDown size={14} className="text-slate-400" />}
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-4">
          {error && (
            <div className="flex items-center gap-2 text-xs text-red-600 bg-red-50 px-3 py-2 rounded-lg border border-red-100">
              <AlertCircle size={13} /> {error}
            </div>
          )}
          {loading ? (
            <div className="flex justify-center py-6">
              <Loader2 size={20} className="animate-spin text-slate-400" />
            </div>
          ) : (
            <>
              <PresetList label="공용" items={publicPresets} selected={selected} onToggle={toggle} onToggleAll={toggleAll} filter={publicFilter} setFilter={setPublicFilter} />
              <PresetList label="개인" items={privatePresets} selected={selected} onToggle={toggle} onToggleAll={toggleAll} filter={privateFilter} setFilter={setPrivateFilter} />
              <button
                onClick={handleDelete}
                disabled={!selected.size || deleting}
                className="flex items-center gap-2 px-4 py-2 bg-red-500 text-white text-xs font-semibold rounded-lg hover:bg-red-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                {deleting ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
                선택 삭제{selected.size > 0 && ` (${selected.size})`}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
};

export default PresetAdminPanel;
