import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchEventSource } from '@microsoft/fetch-event-source';
import { peLogSheetApi } from '../../../api/djangoApi';
import { useWorkbookNavigation } from './useWorkbookNavigation';
import { OpBatcher } from '../utils/opBatcher';

const CLIENT_ID = `client_${Math.random().toString(36).slice(2, 10)}`;
const PRESENCE_HEARTBEAT_INTERVAL_MS = 3000;
// Phase-1 soft-lock contract placeholder: server-issued cell locks live for 30s,
// and the active editor refreshes them every 8s while `.luckysheet-cell-input`
// remains focused. These constants are documentation/integration anchors only in
// this task; lock acquisition/release wiring lands in a later task.
const CELL_LOCK_TTL_SECONDS = 30;
const CELL_LOCK_HEARTBEAT_INTERVAL_MS = 8000;
const CELL_LOCK_TTL_MS = CELL_LOCK_TTL_SECONDS * 1000;

/**
 * usePeLogSheet
 *
 * Manages:
 *  - Initial state load
 *  - SSE subscription for remote edits
 *  - Op batching + server commit
 *  - Conflict detection → authoritative state reload
 *
 * Cell soft-lock policy contract for the PE log sheet feature:
 *  - Only one active text-edit cell per client may hold a lock at a time.
 *  - Lock ownership is tied to actual `.luckysheet-cell-input` focus, never to
 *    bare selection state or `afterCellMouseDown`.
 *  - Trailing users are allowed to type locally, but are blocked only when they
 *    attempt to save/commit; edit-start itself does not warn or hard-block.
 *  - The leading user never sees a warning for the cell they already own.
 *  - A trailing user's temporary draft is cancelled/cleared by restoring the
 *    authoritative server workbook after a save-time lock conflict.
 *  - `conflict_type = "cell-lock"` is reserved for this save-time lock branch
 *    and stays distinct from existing `"cell-edit"` and `"structural"`
 *    revision-gap conflicts.
 *  - FortuneSheet 1.0.4 exposes no reliable native edit-start hook, so phase-1
 *    integrates conservatively via DOM/input focus boundaries without patching
 *    or monkey-patching the library.
 *  - Lock TTL is 60 seconds and the planned heartbeat interval is 15 seconds.
 *  - Phase-1 scope is a single active text-edit cell only; multi-cell paste and
 *    structural operations remain outside the lock system.
 */
export function usePeLogSheet(workbookRef) {
  const [workbookData, setWorkbookData] = useState(null);
  const [workbookRenderKey, setWorkbookRenderKey] = useState(0);
  const [revision, setRevision] = useState(0);
  const [syncStatus, setSyncStatus] = useState('idle'); // idle | saving | conflict | error
  const [conflictMessage, setConflictMessage] = useState(null);
  const [conflictState, setConflictState] = useState(null);
  const [activeUsers, setActiveUsers] = useState([]);

  const revisionRef = useRef(0);
  const workbookDataRef = useRef(null);
  const activeUsersRef = useRef([]);
  const pendingJoinedUserRef = useRef(null);
  const activeCellLockRef = useRef(null);
  const cellLockConflictOwnerRef = useRef(null);
  const [activeCellLockVersion, setActiveCellLockVersion] = useState(0);

  const normalizePresenceUsers = useCallback((users) => {
    if (!Array.isArray(users)) {
      return [];
    }

    return users
      .filter((user) => user?.username)
      .map((user) => ({
        username: user.username,
        display_name: user.display_name ?? user.username,
      }));
  }, []);

  const mergePresenceUsers = useCallback((users, joinedUser) => {
    const normalizedUsers = normalizePresenceUsers(users);
    if (!joinedUser?.username) {
      return normalizedUsers;
    }

    const nextUsers = normalizedUsers.filter((user) => user.username !== joinedUser.username);
    nextUsers.push(joinedUser);
    return nextUsers;
  }, [normalizePresenceUsers]);

  const applyPresenceUsers = useCallback((users) => {
    const normalizedUsers = normalizePresenceUsers(users);
    activeUsersRef.current = normalizedUsers;
    setActiveUsers(normalizedUsers);
  }, [normalizePresenceUsers]);

  const applyPresenceSnapshot = useCallback((users) => {
    const normalizedUsers = normalizePresenceUsers(users);
    const pendingJoinedUser = pendingJoinedUserRef.current;
    if (!pendingJoinedUser) {
      pendingJoinedUserRef.current = null;
      applyPresenceUsers(normalizedUsers);
      return;
    }

    const includesPendingUser = normalizedUsers.some(
      (user) => user?.username === pendingJoinedUser.username,
    );
    if (includesPendingUser) {
      pendingJoinedUserRef.current = null;
      applyPresenceUsers(normalizedUsers);
      return;
    }

    applyPresenceUsers(mergePresenceUsers(normalizedUsers, pendingJoinedUser));
  }, [applyPresenceUsers, mergePresenceUsers, normalizePresenceUsers]);

  const applyJoinPresence = useCallback((users, joinedUser) => {
    const normalizedUsers = normalizePresenceUsers(users);
    const normalizedJoinedUser = joinedUser && joinedUser.username
      ? {
          username: joinedUser.username,
          display_name: joinedUser.display_name ?? joinedUser.username,
        }
      : null;

    if (normalizedJoinedUser) {
      pendingJoinedUserRef.current = normalizedJoinedUser;
      applyPresenceUsers(mergePresenceUsers(normalizedUsers, normalizedJoinedUser));
    } else {
      pendingJoinedUserRef.current = null;
      applyPresenceUsers(normalizedUsers);
    }
  }, [applyPresenceUsers, mergePresenceUsers, normalizePresenceUsers]);

  const updateRevision = useCallback((rev) => {
    setRevision(rev);
    revisionRef.current = rev;
  }, []);

  const syncActiveCellLock = useCallback((nextLock) => {
    activeCellLockRef.current = nextLock;
    setActiveCellLockVersion((current) => current + 1);
  }, []);

  const clearActiveCellLock = useCallback(() => {
    activeCellLockRef.current = null;
    setActiveCellLockVersion((current) => current + 1);
  }, []);

  const releaseActiveCellLock = useCallback(async (lock = activeCellLockRef.current) => {
    if (!lock) {
      return;
    }

    try {
      console.log('[peLogSheet] releasing cell lock', lock);
      await peLogSheetApi.releaseCellLock({
        client_id: CLIENT_ID,
        ...lock,
      });
    } catch (err) {
      console.warn('[peLogSheet] releaseCellLock failed', err);
    } finally {
      if (activeCellLockRef.current && activeCellLockRef.current.sheet_id === lock.sheet_id && activeCellLockRef.current.row === lock.row && activeCellLockRef.current.column === lock.column) {
        clearActiveCellLock();
      }
    }
  }, [clearActiveCellLock]);

  const releaseActiveCellLockBeforeUnload = useCallback((lock = activeCellLockRef.current) => {
    if (!lock) {
      return;
    }

    try {
      const releaseUrl = `${window.location.protocol}//${window.location.hostname}:8000/api/pe-log-sheet/cell-lock/release/`;
      const xhr = new XMLHttpRequest();
      xhr.open('POST', releaseUrl, false);
      xhr.setRequestHeader('Content-Type', 'application/json');

      const token = sessionStorage.getItem('authToken');
      if (token) {
        xhr.setRequestHeader('Authorization', `Token ${token}`);
      }

      xhr.send(JSON.stringify({
        client_id: CLIENT_ID,
        ...lock,
      }));
    } catch (err) {
      console.warn('[peLogSheet] beforeunload cell lock release failed', err);
    }
  }, []);

  const handleCellEditStart = useCallback(async (sheet_id, row, column) => {
    const nextLock = { sheet_id, row, column };
    const currentLock = activeCellLockRef.current;

    if (currentLock && currentLock.sheet_id === sheet_id && currentLock.row === row && currentLock.column === column) {
      console.log('[peLogSheet] cell lock already held for active edit', nextLock);
      return;
    }

    if (currentLock) {
      console.log('[peLogSheet] releasing previous cell lock before new edit', currentLock);
      await releaseActiveCellLock(currentLock);
    }

    try {
      console.log('[peLogSheet] acquiring cell lock', nextLock);
      console.log('[peLogSheet] cell lock timing', {
        ttlMs: CELL_LOCK_TTL_MS,
        heartbeatMs: CELL_LOCK_HEARTBEAT_INTERVAL_MS,
      });
      const response = await peLogSheetApi.acquireCellLock({
        client_id: CLIENT_ID,
        sheet_id,
        row,
        column,
      });

      if (response?.is_new || response?.lock?.client_id === CLIENT_ID) {
        syncActiveCellLock(nextLock);
        cellLockConflictOwnerRef.current = null;
        return;
      }

      if (response?.conflict_type === 'cell-lock') {
        cellLockConflictOwnerRef.current = response.lock_owner ?? response.lock ?? null;
        console.log('[peLogSheet] cell lock conflict captured for later UX', cellLockConflictOwnerRef.current);
      }
    } catch (err) {
      console.warn('[peLogSheet] acquireCellLock failed', err);
    }
  }, [releaseActiveCellLock, syncActiveCellLock]);

  const handleCellEditEnd = useCallback(async () => {
    const currentLock = activeCellLockRef.current;
    if (!currentLock) {
      return;
    }

    clearActiveCellLock();
    await releaseActiveCellLock(currentLock);
  }, [clearActiveCellLock, releaseActiveCellLock]);

  useWorkbookNavigation(workbookRef, null, {
    onCellEditStart: handleCellEditStart,
    onCellEditEnd: handleCellEditEnd,
  });

  const replaceWorkbookData = useCallback((nextWorkbookData) => {
    // Deep clone to avoid Immer proxy conflicts inside FortuneSheet
    const cloned = structuredClone(nextWorkbookData);
    setWorkbookData(cloned);
    workbookDataRef.current = cloned;

    if (workbookRef.current?.updateSheet) {
      try {
        workbookRef.current.updateSheet(cloned);
        return;
      } catch (err) {
        console.warn('[peLogSheet] updateSheet failed, remounting workbook', err);
      }
    }

    setWorkbookRenderKey((currentKey) => currentKey + 1);
  }, [workbookRef]);

  const handleChange = useCallback((nextWorkbookData) => {
    // Deep clone to avoid Immer proxy leaking into our state
    const cloned = structuredClone(nextWorkbookData);
    setWorkbookData(cloned);
    workbookDataRef.current = cloned;
  }, []);

  // ── Initial load ──────────────────────────────────────────────────
  const loadState = useCallback(async () => {
    try {
      const data = await peLogSheetApi.getState();
      replaceWorkbookData(data.workbook_data);
      updateRevision(data.revision);
      return data;
    } catch (err) {
      console.error('[peLogSheet] loadState failed', err);
      return null;
    }
  }, [replaceWorkbookData, updateRevision]);

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
              applyPresenceSnapshot(msg.active_users);
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
  }, [applyPresenceSnapshot, loadState, workbookRef]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const token = sessionStorage.getItem('authToken');
    if (!token) return;

    let heartbeatId = null;

    const join = async () => {
      try {
        const result = await peLogSheetApi.joinPresence(CLIENT_ID);
        applyJoinPresence(result.active_users, result.joined_user);
      } catch (err) {
        console.error('[peLogSheet] presence join failed', err);
      }
    };

    join();

    heartbeatId = window.setInterval(() => {
      peLogSheetApi.heartbeatPresence(CLIENT_ID).catch((err) => {
        console.warn('[peLogSheet] presence heartbeat failed', err);
      });
    }, PRESENCE_HEARTBEAT_INTERVAL_MS);

    return () => {
      if (heartbeatId) {
        window.clearInterval(heartbeatId);
      }
      pendingJoinedUserRef.current = null;
      peLogSheetApi.leavePresence(CLIENT_ID).catch(() => {});
    };
  }, [applyJoinPresence]);

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
    const hasStructural = ops.some((op) => ['insertRowCol', 'deleteRowCol', 'addSheet', 'deleteSheet'].includes(op.op));
    console.log('[peLogSheet] commitOps:', {
      base_revision: revisionRef.current,
      ops_count: ops.length,
      has_structural: hasStructural,
      op_types: [...new Set(ops.map((o) => o.op))],
    });

    try {
      const result = await peLogSheetApi.submitOps({
        base_revision: revisionRef.current,
        ops,
        snapshot,
        client_id: CLIENT_ID,
      });
      console.log('[peLogSheet] commitOps success:', { new_revision: result.new_revision });
      updateRevision(result.new_revision);
      setSyncStatus('idle');
      setConflictMessage(null);
      setConflictState(null);
    } catch (err) {
      console.error('[peLogSheet] commitOps error:', err.response?.status, err.response?.data);
if (err.response?.status === 409) {
        batcherRef.current?.cancel();
        const conflictType = err.response.data?.conflict_type;

        if (conflictType === 'cell-lock') {
          // ── Cell-lock conflict (save-time lock collision) ──────────────
          // Another user holds an active lock on the same cell.
          // The trailing user's draft is cancelled/cleared by restoring
          // the authoritative server workbook. Retry is disabled because
          // the lock owner must finish first.
          // ────────────────────────────────────────────────────────────────
          const {
            revision: serverRev,
            workbook_data: serverSheet,
            locked_cell,
            lock_owner,
          } = err.response.data;
          updateRevision(serverRev);
          setSyncStatus('conflict');
          setConflictMessage('다른 사용자가 같은 셀을 편집 중입니다. 최신 버전으로 복원되었습니다.');
          setConflictState({
            conflicts: locked_cell
              ? [{ ...locked_cell, conflict_type: 'cell-lock', lock_owner: lock_owner ?? null }]
              : [],
            hasStructuralConflict: false,
            isPasteConflict: false,
            canRetry: false,
            isCellLockConflict: true,
          });
          if (serverSheet) {
            replaceWorkbookData(serverSheet);
          }
        } else {
          // ── Revision-gap conflict (cell-edit / structural) ─────────────
          const {
            revision: serverRev,
            workbook_data: serverSheet,
            conflicts = [],
          } = err.response.data;
          updateRevision(serverRev);
          setSyncStatus('conflict');
          const hasStructuralConflict = conflicts.some((conflict) => conflict?.conflict_type === 'structural');
          const isPasteConflict = !hasStructuralConflict && conflicts.length > 1;
          setConflictMessage(
            hasStructuralConflict
              ? '다른 사용자가 시트 구조를 먼저 변경했습니다. 최신 구조로 복원되었습니다.'
              : isPasteConflict
                ? `동시 편집 충돌로 붙여넣기 작업이 취소되었습니다. 충돌 셀 ${conflicts.length}개를 확인하세요.`
                : '다른 사용자가 같은 셀을 먼저 수정했습니다. 최신 버전으로 복원되었습니다.'
          );
          setConflictState({
            conflicts,
            hasStructuralConflict,
            isPasteConflict,
            canRetry: !hasStructuralConflict && conflicts.length === 1 && conflicts[0]?.conflict_type === 'cell-edit' && !isPasteConflict,
          });
          if (serverSheet) {
            replaceWorkbookData(serverSheet);
          }
        }
      } else {
        setSyncStatus('error');
        console.error('[peLogSheet] submitOps failed', err);
      }
    }
  }, [replaceWorkbookData, updateRevision]);

  useEffect(() => {
    batcherRef.current = new OpBatcher({
      flushFn: commitOps,
      debounceMs: 300,
    });
    return () => batcherRef.current?.cancel();
  }, [commitOps]);

  useEffect(() => {
    const handleBeforeUnload = () => {
      releaseActiveCellLockBeforeUnload();
    };

    window.addEventListener('beforeunload', handleBeforeUnload);

    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
      void releaseActiveCellLock();
    };
  }, [releaseActiveCellLock, releaseActiveCellLockBeforeUnload]);

  useEffect(() => {
    const currentLock = activeCellLockRef.current;
    if (!currentLock) {
      return undefined;
    }

    const heartbeatId = window.setInterval(async () => {
      const lock = activeCellLockRef.current;
      if (!lock) {
        return;
      }

      try {
        console.log('[peLogSheet] cell lock heartbeat', lock);
        const response = await peLogSheetApi.heartbeatCellLock({
          client_id: CLIENT_ID,
          ...lock,
        });

        if (response?.refreshed === false) {
          console.log('[peLogSheet] cell lock heartbeat lost ownership', lock);
          clearActiveCellLock();
        }
      } catch (err) {
        console.warn('[peLogSheet] heartbeatCellLock failed', err);
      }
    }, CELL_LOCK_HEARTBEAT_INTERVAL_MS);

    return () => {
      window.clearInterval(heartbeatId);
    };
  }, [activeCellLockVersion, clearActiveCellLock]);

  const uploadCsv = useCallback(async (file) => {
    batcherRef.current?.cancel();
    try {
      const result = await peLogSheetApi.uploadCsv(file);
      // Force full remount to clear FortuneSheet internal state (column widths, etc.)
      const cloned = structuredClone(result.workbook_data);
      setWorkbookData(cloned);
      workbookDataRef.current = cloned;
      setWorkbookRenderKey((k) => k + 1);
      updateRevision(result.revision);
      setSyncStatus('idle');
      setConflictMessage(null);
      return result;
    } catch (err) {
      setSyncStatus('error');
      console.error('[peLogSheet] uploadCsv failed', err);
      throw err;
    }
  }, [updateRevision]);

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
    workbookRenderKey,
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
