import React, { useState, useEffect, useCallback } from 'react';
import { AlertCircle, X } from 'lucide-react';
import TopBar from './components/TopBar';
import InputForm from './components/InputForm';
import MainCalculationSheet from './components/MainCalculationSheet';
import PpiDataSheet from './components/PpiDataSheet';
import WageDataSheet from './components/WageDataSheet';
import HelpSection from './components/HelpSection';
import { useEscData } from './hooks/useEscData';
import { generateMonths, calculateEsc } from './utils/escCalculations';

// ── 기본 입력 초기값 ──────────────────────────────────────────────
const DEFAULT_INPUTS = {
  baseMonth: '202107',
  endMonth: '202204',
  materialCost: 13_000_000_000,
  laborCost: 34_700_000_000,
  otherCost: 7_000_000_000,
  expectedAmount: 54_700_000_000,
  advanceRate: 0.10,
  monthlyProgress: [
    { month: '202107', amount: 3_500_000_000 },
    { month: '202108', amount: 5_000_000_000 },
    { month: '202109', amount: 5_500_000_000 },
    { month: '202110', amount: 6_000_000_000 },
    { month: '202111', amount: 6_800_000_000 },
    { month: '202112', amount: 7_600_000_000 },
    { month: '202201', amount: 9_100_000_000 },
    { month: '202202', amount: 6_000_000_000 },
    { month: '202203', amount: 4_700_000_000 },
    { month: '202204', amount:   500_000_000 },
  ],
};

function syncProgressRows(inputs) {
  if (!inputs.baseMonth || !inputs.endMonth) return inputs;
  const months = generateMonths(inputs.baseMonth, inputs.endMonth);
  const existing = inputs.monthlyProgress || [];
  const updated = months.map(month => {
    const found = existing.find(p => p.month === month);
    return found ?? { month, amount: 0 };
  });
  return { ...inputs, monthlyProgress: updated };
}

// ── 메인 페이지 ──────────────────────────────────────────────────
export default function EscCalculatorPage() {
  const [inputs, setInputs] = useState(() => syncProgressRows(DEFAULT_INPUTS));
  const [escResult, setEscResult] = useState(null);
  const [recalcKey, setRecalcKey] = useState(0);
  const [selectedProjectId, setSelectedProjectId] = useState(null);
  const [banner, setBanner] = useState(null); // { type: 'success'|'error', msg }

  const { projects, kosisData, loading, error, loadProjects, saveProject, fetchKosisData, clearError } = useEscData();

  // 프로젝트 목록 초기 로드
  useEffect(() => { loadProjects(); }, []);

  // 에러를 배너로 표시
  useEffect(() => {
    if (error) { showBanner('error', error); clearError(); }
  }, [error]);

  function showBanner(type, msg) {
    setBanner({ type, msg });
    setTimeout(() => setBanner(null), 6000);
  }

  // ── 입력 변경 핸들러 ──────────────────────────────────────────
  const handleInputChange = useCallback((newInputs) => {
    // 기간이 변경되면 월별 기성금액 행을 자동 동기화
    const synced = syncProgressRows(newInputs);
    setInputs(synced);
  }, []);

  // ── 계산 실행 ─────────────────────────────────────────────────
  const handleRecalc = useCallback(async () => {
    const { baseMonth, endMonth } = inputs;
    if (!baseMonth || !endMonth) {
      showBanner('error', '기준시점과 종료시점을 먼저 입력하세요.');
      return;
    }
    if (baseMonth >= endMonth) {
      showBanner('error', '종료시점이 기준시점보다 이후여야 합니다.');
      return;
    }

    try {
      // 월별 기성금액 합계 검증
      const progressTotal = (inputs.monthlyProgress || []).reduce((s, p) => s + (Number(p.amount) || 0), 0);
      const expected = Number(inputs.expectedAmount) || 0;
      if (expected > 0 && progressTotal !== expected) {
        showBanner('error',
          `월별 기성금액 합계(${progressTotal.toLocaleString('ko-KR')}원)가 정산예상금액(${expected.toLocaleString('ko-KR')}원)과 일치하지 않습니다.`
        );
        return;
      }

      // KOSIS 데이터 패칭 (없으면 새로 요청)
      let { ppi, wage } = kosisData;
      const needFetch = !ppi.length || !wage.length;
      if (needFetch) {
        const fetched = await fetchKosisData(baseMonth, endMonth);
        ppi = fetched.ppi;
        wage = fetched.wage;
      }

      const result = calculateEsc(inputs, ppi, wage);
      setEscResult(result);
      setRecalcKey(k => k + 1);

      if (!result.adjustmentMonth) {
        showBanner('error', `물가변동률이 3%에 도달하지 않아 조정시점이 없습니다. (최대 C=${result.cSeries.length ? (Math.max(...result.cSeries.filter(c=>c.C!=null).map(c=>c.C)) * 100).toFixed(3) : '-'}%)`);
      } else {
        showBanner('success', `계산 완료 — 조정시점: ${result.adjustmentMonth.slice(0,4)}.${result.adjustmentMonth.slice(4,6)}, 집행금액: ${result.executionAmount?.toLocaleString('ko-KR')}원`);
      }
    } catch (e) {
      showBanner('error', '계산 오류: ' + e.message);
    }
  }, [inputs, kosisData, fetchKosisData]);

  // ── 저장 ─────────────────────────────────────────────────────
  const handleSave = useCallback(async (name, existingId) => {
    try {
      const saved = await saveProject(name, inputs, existingId);
      setSelectedProjectId(saved.id);
      showBanner('success', `"${saved.name}" 저장 완료`);
    } catch (_) {}
  }, [inputs, saveProject]);

  // ── 로드 ─────────────────────────────────────────────────────
  const handleLoad = useCallback((projectId) => {
    if (!projectId) { setSelectedProjectId(null); return; }
    const project = projects.find(p => p.id === projectId);
    if (!project) return;
    setSelectedProjectId(projectId);
    const loaded = syncProgressRows(project.input_data || DEFAULT_INPUTS);
    setInputs(loaded);
    setEscResult(null);
    showBanner('success', `"${project.name}" 불러옴`);
  }, [projects]);

  // ── 새로만들기 ────────────────────────────────────────────────
  const handleNew = useCallback(() => {
    setInputs(syncProgressRows(DEFAULT_INPUTS));
    setEscResult(null);
    setSelectedProjectId(null);
  }, []);

  return (
    <div className="min-h-screen bg-gray-50">
      {/* TopBar */}
      <TopBar
        projects={projects}
        selectedId={selectedProjectId}
        onLoad={handleLoad}
        onSave={handleSave}
        onRecalc={handleRecalc}
        onNew={handleNew}
        loading={loading}
      />

      {/* 배너 */}
      {banner && (
        <div className={`mx-4 mt-3 flex items-center gap-2 rounded-lg px-4 py-2 text-sm
          ${banner.type === 'error' ? 'bg-red-100 text-red-700 border border-red-300' : 'bg-green-100 text-green-700 border border-green-300'}`}>
          <AlertCircle size={15} />
          <span className="flex-1">{banner.msg}</span>
          <button onClick={() => setBanner(null)}><X size={14} /></button>
        </div>
      )}

      {/* 본문 */}
      <div className="max-w-screen-xl mx-auto px-4 py-4 space-y-6">

        {/* 앱 제목 */}
        <div className="flex items-baseline gap-3">
          <h1 className="text-xl font-bold text-gray-800">📊 물가변동(ESC) 비용 산출</h1>
          <span className="text-sm text-gray-500">건설공사 계약금액 조정 계산기</span>
        </div>

        {/* ① 입력 */}
        <InputForm inputs={inputs} onChange={handleInputChange} />

        {/* ② 메인 계산 결과 */}
        <MainCalculationSheet result={escResult} inputs={inputs} recalcKey={recalcKey} />

        {/* ③ 생산자물가지수 */}
        <PpiDataSheet result={escResult} />

        {/* ④ 노임단가 */}
        <WageDataSheet result={escResult} />

        {/* ⑤ 도움말 */}
        <HelpSection />

      </div>
    </div>
  );
}
