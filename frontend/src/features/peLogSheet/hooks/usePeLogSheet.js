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
 *  - Conflict detection → full reload via workbookRef.updateSheet
 */
export function usePeLogSheet(workbookRef) {
  const [workbookData, setWorkbookData] = useState(null);
  const [revision, setRevision] = useState(0);
  const [syncStatus, setSyncStatus] = useState('idle'); // idle | saving | conflict | error
  const [conflictMessage, setConflictMessage] = useState(null);
  const [activeUsers, setActiveUsers] = useState(0);

  const revisionRef = useRef(0);
  const sseAbortCtrlRef = useRef(null);

  const updateRevision = useCallback((rev) => {
    setRevision(rev);
    revisionRef.current = rev;
  }, []);

  // ── Initial load ──────────────────────────────────────────────────
  const loadState = useCallback(async () => {
    try {
      const data = await peLogSheetApi.getState();
      setWorkbookData(data.workbook_data);
      updateRevision(data.revision);
    } catch (err) {
      console.error('[peLogSheet] loadState failed', err);
    }
  }, [updateRevision]);

  useEffect(() => {
    loadState();
  }, [loadState]);

  // ── SSE subscription ──────────────────────────────────────────────
  useEffect(() => {
    const token = sessionStorage.getItem('authToken');
    if (!token) return;

    const ctrl = new AbortController();
    sseAbortCtrlRef.current = ctrl;

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
                  loadState().then(() => {
                    if (workbookRef.current && workbookData) {
                      workbookRef.current.updateSheet(workbookData);
                    }
                  });
                }
              }
              updateRevision(msg.revision);
            } else if (msg.type === 'reset') {
              loadState().then(() => {
                if (workbookRef.current) {
                  workbookRef.current.updateSheet(workbookData);
                }
              });
              updateRevision(msg.revision);
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
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Op batcher ────────────────────────────────────────────────────
  const batcherRef = useRef(null);

  const handleOp = useCallback((ops) => {
    if (!batcherRef.current) return;
    batcherRef.current.push(ops);
  }, []);

  const commitOps = useCallback(async (ops) => {
    if (!ops.length) return;
    setSyncStatus('saving');

    const snapshot = workbookRef.current?.getAllSheets?.() ?? undefined;

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
    } catch (err) {
      if (err.response?.status === 409) {
        const { revision: serverRev, workbook_data: serverSheet } = err.response.data;
        updateRevision(serverRev);
        setSyncStatus('conflict');
        setConflictMessage('다른 사용자가 동시에 편집했습니다. 최신 버전으로 복원되었습니다.');
        if (workbookRef.current && serverSheet) {
          workbookRef.current.updateSheet(serverSheet);
          setWorkbookData(serverSheet);
        }
      } else {
        setSyncStatus('error');
        console.error('[peLogSheet] submitOps failed', err);
      }
    }
  }, [updateRevision, workbookRef]);

  useEffect(() => {
    batcherRef.current = new OpBatcher({
      flushFn: commitOps,
      debounceMs: 300,
    });
    return () => batcherRef.current?.cancel();
  }, [commitOps]);

  // ── Reset from CSV ────────────────────────────────────────────────
  const resetFromSource = useCallback(async () => {
    try {
      const result = await peLogSheetApi.resetFromSource();
      await loadState();
      if (workbookRef.current) {
        const latest = await peLogSheetApi.getState();
        workbookRef.current.updateSheet(latest.workbook_data);
      }
      updateRevision(result.revision);
    } catch (err) {
      console.error('[peLogSheet] resetFromSource failed', err);
    }
  }, [loadState, updateRevision, workbookRef]);

  return {
    workbookData,
    revision,
    syncStatus,
    conflictMessage,
    dismissConflict: () => { setSyncStatus('idle'); setConflictMessage(null); },
    handleOp,
    resetFromSource,
  };
}
