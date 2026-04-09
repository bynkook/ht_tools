import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchEventSource } from '@microsoft/fetch-event-source';
import { peLogSheetApi } from '../../../api/djangoApi';
import { OpBatcher } from '../utils/opBatcher';

const CLIENT_ID = `client_${Math.random().toString(36).slice(2, 10)}`;

/**
 * usePeLogSheet
 *
 * Manages:
 *  - Initial state load
 *  - SSE subscription for remote edits
 *  - Op batching + server commit
 *  - Conflict detection → authoritative state reload
 */
export function usePeLogSheet(workbookRef) {
  const [workbookData, setWorkbookData] = useState(null);
  const [revision, setRevision] = useState(0);
  const [syncStatus, setSyncStatus] = useState('idle'); // idle | saving | conflict | error
  const [conflictMessage, setConflictMessage] = useState(null);
  const [conflictState, setConflictState] = useState(null);
  const [activeUsers, setActiveUsers] = useState([]);

  const revisionRef = useRef(0);
  const workbookDataRef = useRef(null);

  const updateRevision = useCallback((rev) => {
    setRevision(rev);
    revisionRef.current = rev;
  }, []);

  const applyWorkbookData = useCallback((nextWorkbookData) => {
    setWorkbookData(nextWorkbookData);
    workbookDataRef.current = nextWorkbookData;
  }, []);

  const handleChange = useCallback((nextWorkbookData) => {
    setWorkbookData(nextWorkbookData);
    workbookDataRef.current = nextWorkbookData;
  }, []);

  const updateActiveUsers = useCallback((users) => {
    setActiveUsers(Array.isArray(users) ? users : []);
  }, []);

  // ── Initial load ──────────────────────────────────────────────────
  const loadState = useCallback(async () => {
    try {
      const data = await peLogSheetApi.getState();
      applyWorkbookData(data.workbook_data);
      updateRevision(data.revision);
      return data;
    } catch (err) {
      console.error('[peLogSheet] loadState failed', err);
      return null;
    }
  }, [applyWorkbookData, updateRevision]);

  useEffect(() => {
    loadState();
  }, [loadState]);

  // ── SSE subscription ──────────────────────────────────────────────
  useEffect(() => {
    const token = sessionStorage.getItem('authToken');
    if (!token) return;

    const ctrl = new AbortController();

    const streamUrl = peLogSheetApi.getStreamUrl();

    (async () => {
      try {
        await fetchEventSource(streamUrl, {
          headers: { Authorization: `Token ${token}` },
          signal: ctrl.signal,
          onmessage(event) {
            let msg;
            try { msg = JSON.parse(event.data); } catch { return; }

            if (msg.type === 'op_committed') {
              if (msg.client_id === CLIENT_ID) return; // skip own commits

              if (workbookRef.current && msg.ops?.length) {
                try {
                  workbookRef.current.applyOp(msg.ops);
                } catch (e) {
                  console.warn('[peLogSheet] applyOp failed, reloading', e);
                  loadState();
                }
              }
              updateRevision(msg.revision);
            } else if (msg.type === 'reset') {
              loadState();
              updateRevision(msg.revision);
            } else if (msg.type === 'presence_snapshot') {
              updateActiveUsers(msg.active_users);
            }
          },
          onerror(err) {
            console.warn('[peLogSheet] SSE error', err);
          },
        });
      } catch (err) {
        if (err.name !== 'AbortError') {
          console.error('[peLogSheet] SSE fatal', err);
        }
      }
    })();

    return () => ctrl.abort();
  }, [loadState, updateActiveUsers, workbookRef]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const token = sessionStorage.getItem('authToken');
    if (!token) return;

    let heartbeatId = null;

    const join = async () => {
      try {
        const result = await peLogSheetApi.joinPresence(CLIENT_ID);
        updateActiveUsers(result.active_users);
      } catch (err) {
        console.error('[peLogSheet] presence join failed', err);
      }
    };

    join();

    heartbeatId = window.setInterval(() => {
      peLogSheetApi.heartbeatPresence(CLIENT_ID).catch((err) => {
        console.warn('[peLogSheet] presence heartbeat failed', err);
      });
    }, 15000);

    return () => {
      if (heartbeatId) {
        window.clearInterval(heartbeatId);
      }
      peLogSheetApi.leavePresence(CLIENT_ID).catch(() => {});
    };
  }, [updateActiveUsers]);

  // ── Op batcher ────────────────────────────────────────────────────
  const batcherRef = useRef(null);

  const handleOp = useCallback((ops) => {
    if (!batcherRef.current) return;
    batcherRef.current.push(ops);
  }, []);

  const commitOps = useCallback(async (ops) => {
    if (!ops.length) return;
    setSyncStatus('saving');

    const snapshot = workbookDataRef.current ?? undefined;

    try {
      const result = await peLogSheetApi.submitOps({
        base_revision: revisionRef.current,
        ops,
        snapshot,
        client_id: CLIENT_ID,
      });
      updateRevision(result.new_revision);
      setSyncStatus('idle');
      setConflictMessage(null);
      setConflictState(null);
    } catch (err) {
      if (err.response?.status === 409) {
        const {
          revision: serverRev,
          workbook_data: serverSheet,
          conflicts = [],
        } = err.response.data;
        updateRevision(serverRev);
        setSyncStatus('conflict');
        const isPasteConflict = conflicts.length > 1;
        setConflictMessage(
          isPasteConflict
            ? `동시 편집 충돌로 붙여넣기 작업이 취소되었습니다. 충돌 셀 ${conflicts.length}개를 확인하세요.`
            : '다른 사용자가 같은 셀을 먼저 수정했습니다. 최신 버전으로 복원되었습니다.'
        );
        setConflictState({
          conflicts,
          isPasteConflict,
          canRetry: conflicts.length === 1 && conflicts[0]?.conflict_type === 'cell-edit' && !isPasteConflict,
        });
        if (serverSheet) {
          applyWorkbookData(serverSheet);
        }
      } else {
        setSyncStatus('error');
        console.error('[peLogSheet] submitOps failed', err);
      }
    }
  }, [applyWorkbookData, updateRevision, workbookRef]);

  useEffect(() => {
    batcherRef.current = new OpBatcher({
      flushFn: commitOps,
      debounceMs: 300,
    });
    return () => batcherRef.current?.cancel();
  }, [commitOps]);

  const uploadCsv = useCallback(async (file) => {
    batcherRef.current?.cancel();
    try {
      const result = await peLogSheetApi.uploadCsv(file);
      applyWorkbookData(result.workbook_data);
      updateRevision(result.revision);
      setSyncStatus('idle');
      setConflictMessage(null);
      return result;
    } catch (err) {
      setSyncStatus('error');
      console.error('[peLogSheet] uploadCsv failed', err);
      throw err;
    }
  }, [applyWorkbookData, updateRevision]);

  const downloadCsv = useCallback(async () => {
    try {
      const blob = await peLogSheetApi.downloadCsv();
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = 'pe_log_sheet.csv';
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setSyncStatus('error');
      console.error('[peLogSheet] downloadCsv failed', err);
    }
  }, []);

  return {
    workbookData,
    revision,
    syncStatus,
    activeUsers,
    conflictMessage,
    conflictState,
    dismissConflict: () => {
      setSyncStatus('idle');
      setConflictMessage(null);
      setConflictState(null);
    },
    keepServerConflictResolution: () => {
      setSyncStatus('idle');
      setConflictMessage(null);
      setConflictState(null);
    },
    retryClientConflictValue: () => {
      const conflict = conflictState?.conflicts?.[0];
      if (!conflict || !conflictState?.canRetry || !workbookRef.current) {
        return;
      }
      setSyncStatus('idle');
      setConflictMessage(null);
      setConflictState(null);
      workbookRef.current.setCellValue(
        conflict.row,
        conflict.column,
        conflict.client_cell,
        { id: conflict.sheet_id },
      );
    },
    handleChange,
    handleOp,
    uploadCsv,
    downloadCsv,
  };
}
