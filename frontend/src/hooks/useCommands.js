import { useState, useCallback } from 'react';
import { dashboardLinksApi, memoryApi } from '../api/djangoApi';

/**
 * 자연어 → 커맨드 매핑 패턴
 * { patterns: RegExp[], command: string }
 */
const NATURAL_LANGUAGE_PATTERNS = [
  {
    patterns: [
      /태블로.*대시보드/i,
      /tableau.*dashboard/i,
      /대시보드.*목록/i,
      /대시보드.*링크/i,
      /대시보드.*보여/i,
    ],
    command: '/dashboard'
  },
  // 추후 다른 커맨드 패턴 추가 가능
];

/**
 * 자연어 입력에서 커맨드 감지
 * @param {string} text - 사용자 입력
 * @returns {string|null} - 매칭된 커맨드 또는 null
 */
export const detectNaturalLanguageCommand = (text) => {
  const normalized = text.trim();
  for (const { patterns, command } of NATURAL_LANGUAGE_PATTERNS) {
    if (patterns.some(pattern => pattern.test(normalized))) {
      return command;
    }
  }
  return null;
};

/**
 * Chat 커맨드 처리를 위한 커스텀 훅
 * "/" 로 시작하는 커맨드들을 파싱하고 실행한다.
 * 
 * 지원 커맨드:
 * - /memory save|load|delete|list|clear "이름"
 * - /dashboard
 * 
 * @param {Object} params
 * @param {Array} params.messages - 현재 메시지 배열
 * @param {Function} params.setMessages - 메시지 상태 setter
 * @param {Function} params.setError - 에러 메시지 setter
 * @param {Function} params.setSuccessMessage - 성공 메시지 setter
 * @param {string} params.currentSessionId - 현재 세션 ID
 * @returns {{ executeCommand: Function, isCommandLoading: boolean }}
 */
export const useCommands = ({
  messages,
  setMessages,
  setError,
  setSuccessMessage,
  currentSessionId
}) => {
  const [isCommandLoading, setIsCommandLoading] = useState(false);

  // ===== Memory Command Handlers =====

  const handleMemorySave = useCallback(async (name) => {
    if (!currentSessionId) {
      setError('세션을 먼저 생성한 후 스냅샷을 저장해주세요.');
      return;
    }
    setIsCommandLoading(true);
    try {
      const snapshotMessages = messages.filter(m => m.role !== 'system');
      if (snapshotMessages.length === 0) {
        setError('저장할 대화 내용이 없습니다.');
        return;
      }
      await memoryApi.saveSnapshot(currentSessionId, name, snapshotMessages);
      setSuccessMessage(`메모리 저장 완료: "${name}" (${snapshotMessages.length}개 메시지)`);
    } catch (err) {
      if (err.response?.data?.error?.includes('이미 존재')) {
        setError(`스냅샷 "${name}"이(가) 이미 존재합니다. 다른 이름을 사용해주세요.`);
      } else {
        setError('스냅샷 저장에 실패했습니다: ' + (err.response?.data?.error || err.message || '알 수 없는 오류'));
      }
    } finally {
      setIsCommandLoading(false);
    }
  }, [currentSessionId, messages, setError, setSuccessMessage]);

  const handleMemoryLoad = useCallback(async (name) => {
    if (!currentSessionId) {
      setError('세션을 먼저 생성한 후 스냅샷을 로드해주세요.');
      return;
    }
    setIsCommandLoading(true);
    try {
      const snapshot = await memoryApi.getSnapshotByName(currentSessionId, name);
      if (!snapshot) {
        setError(`스냅샷 "${name}"을(를) 찾을 수 없습니다.`);
        return;
      }
      const restoredMessages = snapshot.snapshot_data?.messages || [];
      if (restoredMessages.length === 0) {
        setError(`스냅샷 "${name}"에 저장된 메시지가 없습니다.`);
        return;
      }
      setMessages(restoredMessages);
      setSuccessMessage(`메모리 로드 완료: "${name}" (${restoredMessages.length}개 메시지, ${new Date(snapshot.created_at).toLocaleString('ko-KR')})`);
    } catch (err) {
      setError('스냅샷 로드에 실패했습니다: ' + (err.message || '알 수 없는 오류'));
    } finally {
      setIsCommandLoading(false);
    }
  }, [currentSessionId, setMessages, setError, setSuccessMessage]);

  const handleMemoryList = useCallback(async () => {
    if (!currentSessionId) {
      setError('세션을 먼저 생성한 후 목록을 조회해주세요.');
      return;
    }
    setIsCommandLoading(true);
    try {
      const snapshots = await memoryApi.listSnapshots(currentSessionId);
      if (snapshots.length === 0) {
        setMessages(prev => [...prev, { role: 'system', content: '저장된 스냅샷이 없습니다.' }]);
      } else {
        const listText = snapshots.map((s, i) =>
          `${i + 1}. "${s.name}" (${new Date(s.created_at).toLocaleString('ko-KR')})`
        ).join('\n');
        setMessages(prev => [...prev, {
          role: 'system',
          content: `저장된 스냅샷 (${snapshots.length}개):\n${listText}`
        }]);
      }
    } catch (err) {
      setError('스냅샷 목록 조회에 실패했습니다: ' + (err.message || '알 수 없는 오류'));
    } finally {
      setIsCommandLoading(false);
    }
  }, [currentSessionId, setMessages, setError]);

  const handleMemoryClear = useCallback(async () => {
    if (!currentSessionId) {
      setError('세션을 먼저 생성한 후 스냅샷을 삭제해주세요.');
      return;
    }
    setIsCommandLoading(true);
    try {
      const result = await memoryApi.clearSnapshots(currentSessionId);
      setSuccessMessage(`메모리 초기화 완료: ${result.deleted}개의 스냅샷 삭제`);
    } catch (err) {
      setError('스냅샷 삭제에 실패했습니다: ' + (err.message || '알 수 없는 오류'));
    } finally {
      setIsCommandLoading(false);
    }
  }, [currentSessionId, setError, setSuccessMessage]);

  const handleMemoryDelete = useCallback(async (name) => {
    if (!currentSessionId) {
      setError('세션을 먼저 생성한 후 스냅샷을 삭제해주세요.');
      return;
    }
    setIsCommandLoading(true);
    try {
      const result = await memoryApi.deleteSnapshotByName(currentSessionId, name);
      if (!result) {
        setError(`스냅샷 "${name}"을(를) 찾을 수 없습니다.`);
      } else {
        setSuccessMessage(`스냅샷 "${name}" 삭제 완료`);
      }
    } catch (err) {
      setError('스냅샷 삭제에 실패했습니다: ' + (err.message || '알 수 없는 오류'));
    } finally {
      setIsCommandLoading(false);
    }
  }, [currentSessionId, setError, setSuccessMessage]);

  const handleMemoryCommand = useCallback(async (command) => {
    if (command.startsWith('/memory save ')) {
      const name = command.replace('/memory save ', '').trim().replace(/^["']|["']$/g, '');
      if (!name) { setError('스냅샷 이름을 입력해주세요. 예: /memory save "이름"'); return; }
      await handleMemorySave(name);
      return;
    }
    if (command.startsWith('/memory load ')) {
      const name = command.replace('/memory load ', '').trim().replace(/^["']|["']$/g, '');
      if (!name) { setError('스냅샷 이름을 입력해주세요. 예: /memory load "이름"'); return; }
      await handleMemoryLoad(name);
      return;
    }
    if (command.startsWith('/memory delete ')) {
      const name = command.replace('/memory delete ', '').trim().replace(/^["']|["']$/g, '');
      if (!name) { setError('스냅샷 이름을 입력해주세요. 예: /memory delete "이름"'); return; }
      await handleMemoryDelete(name);
      return;
    }
    if (command === '/memory list') {
      await handleMemoryList();
      return;
    }
    if (command === '/memory clear') {
      await handleMemoryClear();
      return;
    }
    if (command === '/memory') {
      setError('사용법: /memory [save|load|delete|list|clear] "이름"');
      return;
    }
    setError('알 수 없는 /memory 커맨드입니다. 사용 가능한 커맨드: save, load, delete, list, clear');
  }, [handleMemorySave, handleMemoryLoad, handleMemoryDelete, handleMemoryList, handleMemoryClear, setError]);

  // ===== Dashboard Command Handler =====

  const handleDashboardCommand = useCallback(async () => {
    setIsCommandLoading(true);
    try {
      const dashboards = await dashboardLinksApi.list();

      if (!dashboards || dashboards.length === 0) {
        setError('등록된 대시보드가 없습니다.');
        return;
      }

      const tableHeader = '| No | 대시보드 | 링크 | 설명 |';
      const tableDivider = '|:---:|:---|:---:|:---|';
      const tableRows = dashboards.map((dashboard, index) =>
        `| ${dashboard.id ?? index + 1} | ${dashboard.dashboard_name} | [${dashboard.linkname}](${dashboard.url}) | ${dashboard.desc} |`
      ).join('\n');

      const markdownTable = `📊 **Tableau 대시보드 목록**\n\n${tableHeader}\n${tableDivider}\n${tableRows}`;

      setMessages(prev => [...prev, {
        role: 'assistant',
        content: markdownTable
      }]);
    } catch (err) {
      setError('대시보드 목록 조회에 실패했습니다: ' + (err.message || '알 수 없는 오류'));
    } finally {
      setIsCommandLoading(false);
    }
  }, [setError, setMessages]);

  // ===== Command Dispatcher =====

  /**
   * 커맨드를 파싱하고 적절한 핸들러를 실행
   * @param {string} text - "/" 로 시작하는 커맨드 문자열
   * @returns {{ handled: boolean }} - 커맨드가 처리되었는지 여부
   */
  const executeCommand = useCallback(async (text) => {
    setSuccessMessage(null);
    setError(null);

    // /memory 커맨드
    if (text.startsWith('/memory')) {
      await handleMemoryCommand(text);
      return { handled: true };
    }

    // /dashboard 커맨드
    if (text === '/dashboard' || text === '/dashboard list') {
      await handleDashboardCommand();
      return { handled: true };
    }

    // 알 수 없는 커맨드
    setError(`알 수 없는 커맨드입니다: "${text.split(' ')[0]}"`);
    return { handled: true };
  }, [handleMemoryCommand, handleDashboardCommand, setError, setSuccessMessage]);

  return {
    executeCommand,
    isCommandLoading
  };
};
