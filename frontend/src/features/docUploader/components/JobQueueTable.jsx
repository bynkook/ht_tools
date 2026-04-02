import React, { useState, useEffect, useRef, useCallback } from 'react';
import { CheckCircle, XCircle, Clock, Loader2, RefreshCw } from 'lucide-react';
import { docUploaderApi } from '../../../api/djangoApi';

const STATUS_CONFIG = {
  waiting: {
    label: '대기',
    icon: Clock,
    cls: 'bg-yellow-100 text-yellow-700',
    animate: false,
  },
  working: {
    label: '변환중',
    icon: Loader2,
    cls: 'bg-blue-100 text-blue-700',
    animate: true,
  },
  completed: {
    label: '완료',
    icon: CheckCircle,
    cls: 'bg-green-100 text-green-700',
    animate: false,
  },
  failed: {
    label: '실패',
    icon: XCircle,
    cls: 'bg-red-100 text-red-700',
    animate: false,
  },
};

const FAST_POLL_MS = 5_000;   // 대기/진행 중 작업이 있을 때
const SLOW_POLL_MS = 30_000;  // 모두 완료/실패 시

export default function JobQueueTable({ refreshTrigger }) {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const timerRef = useRef(null);

  const fetchJobs = useCallback(async () => {
    try {
      const data = await docUploaderApi.listJobs();
      setJobs(data);
      setError(null);
      return data;
    } catch (err) {
      setError('작업 목록을 불러오지 못했습니다.');
      return [];
    } finally {
      setLoading(false);
    }
  }, []);

  const scheduleNext = useCallback(
    (data) => {
      if (timerRef.current) clearTimeout(timerRef.current);
      const hasActive = data.some(
        (j) => j.status === 'waiting' || j.status === 'working'
      );
      const delay = hasActive ? FAST_POLL_MS : SLOW_POLL_MS;
      timerRef.current = setTimeout(async () => {
        const fresh = await fetchJobs();
        scheduleNext(fresh);
      }, delay);
    },
    [fetchJobs]
  );

  useEffect(() => {
    fetchJobs().then(scheduleNext);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [fetchJobs, scheduleNext]);

  // 외부에서 refreshTrigger 가 바뀔 때 즉시 폴링
  useEffect(() => {
    if (refreshTrigger === 0) return;
    if (timerRef.current) clearTimeout(timerRef.current);
    fetchJobs().then(scheduleNext);
  }, [refreshTrigger, fetchJobs, scheduleNext]);

  const handleManualRefresh = () => {
    setLoading(true);
    if (timerRef.current) clearTimeout(timerRef.current);
    fetchJobs().then(scheduleNext);
  };

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
      {/* 헤더 */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 bg-gray-50">
        <h2 className="text-sm font-semibold text-gray-700">변환 작업 현황</h2>
        <button
          onClick={handleManualRefresh}
          className="text-gray-400 hover:text-blue-500 transition-colors"
          title="새로고침"
        >
          <RefreshCw size={16} />
        </button>
      </div>

      {/* 에러 */}
      {error && (
        <div className="px-4 py-2 bg-red-50 text-red-600 text-xs">{error}</div>
      )}

      {/* 테이블 */}
      <div className="overflow-y-auto max-h-72">
        {loading && jobs.length === 0 ? (
          <div className="py-8 text-center text-gray-400 text-sm">
            <Loader2 size={14} className="animate-spin mx-auto mb-2" />
            불러오는 중...
          </div>
        ) : jobs.length === 0 ? (
          <div className="py-8 text-center text-gray-400 text-sm">
            아직 변환 작업이 없습니다.
          </div>
        ) : (
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-gray-500 border-b border-gray-100">
                <th className="px-3 py-2 w-10">#</th>
                <th className="px-3 py-2">파일명</th>
                <th className="px-3 py-2 w-100">카테고리</th>
                <th className="px-3 py-2 w-40">추가된 시각</th>
                <th className="px-3 py-2 w-32">상태</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job, idx) => {
                const cfg = STATUS_CONFIG[job.status] || STATUS_CONFIG.waiting;
                const Icon = cfg.icon;
                return (
                  <tr
                    key={job.id}
                    className="border-b border-gray-50 hover:bg-gray-50 transition-colors"
                    title={job.error_message || ''}
                  >
                    <td className="px-3 py-2 text-gray-400">{idx + 1}</td>
                    <td className="px-3 py-2 text-gray-700 max-w-[180px] truncate">
                      {job.original_filename}
                    </td>
                    <td className="px-3 py-2 text-gray-500 truncate">
                      {job.category_name}
                    </td>
                    <td className="px-3 py-2 text-gray-400">
                      {new Date(job.created_at).toLocaleString('ko-KR', {
                        month: '2-digit',
                        day: '2-digit',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </td>
                    <td className="px-3 py-2">
                      <span
                        className={`inline-flex items-center gap-2 px-4 py-0.5 rounded-full text-xs font-medium ${cfg.cls}`}
                      >
                        <Icon
                          size={11}
                          className={cfg.animate ? 'animate-spin' : ''}
                        />
                        {cfg.label}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
