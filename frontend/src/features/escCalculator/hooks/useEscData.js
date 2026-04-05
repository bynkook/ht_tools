import { useState, useCallback } from 'react';
import { escApi } from '../../../api/djangoApi';

export function useEscData() {
  const [projects, setProjects] = useState([]);
  const [kosisData, setKosisData] = useState({ ppi: [], wage: [] });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // ------------------------------------------------------------------
  // 프로젝트 목록
  // ------------------------------------------------------------------
  const loadProjects = useCallback(async () => {
    try {
      const data = await escApi.getProjects();
      setProjects(data);
      return data;
    } catch (e) {
      setError('프로젝트 목록 로드 실패: ' + (e.response?.data?.error || e.message));
      return [];
    }
  }, []);

  // ------------------------------------------------------------------
  // 프로젝트 저장 (새로 만들기 or 덮어쓰기)
  // ------------------------------------------------------------------
  const saveProject = useCallback(async (name, inputData, existingId = null) => {
    try {
      setLoading(true);
      let saved;
      if (existingId) {
        saved = await escApi.updateProject(existingId, { name, input_data: inputData });
      } else {
        saved = await escApi.createProject({ name, input_data: inputData });
      }
      await loadProjects();
      return saved;
    } catch (e) {
      setError('저장 실패: ' + (e.response?.data?.error || e.message));
      throw e;
    } finally {
      setLoading(false);
    }
  }, [loadProjects]);

  // ------------------------------------------------------------------
  // 프로젝트 삭제
  // ------------------------------------------------------------------
  const deleteProject = useCallback(async (id) => {
    try {
      await escApi.deleteProject(id);
      await loadProjects();
    } catch (e) {
      setError('삭제 실패: ' + (e.response?.data?.error || e.message));
    }
  }, [loadProjects]);

  // ------------------------------------------------------------------
  // KOSIS 데이터 패칭
  // ------------------------------------------------------------------
  const fetchKosisData = useCallback(async (startMonth, endMonth) => {
    if (!startMonth || !endMonth) return;
    setLoading(true);
    setError(null);
    try {
      const [ppi, wage] = await Promise.all([
        escApi.getKosisPpi(startMonth, endMonth),
        escApi.getKosisWage(startMonth, endMonth),
      ]);
      setKosisData({ ppi, wage });
      return { ppi, wage };
    } catch (e) {
      const msg = e.response?.data?.error || e.message;
      setError('KOSIS 데이터 로드 실패: ' + msg);
      throw e;
    } finally {
      setLoading(false);
    }
  }, []);

  const clearError = useCallback(() => setError(null), []);

  return {
    projects,
    kosisData,
    loading,
    error,
    loadProjects,
    saveProject,
    deleteProject,
    fetchKosisData,
    clearError,
  };
}
