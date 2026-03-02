import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useSearchParams, useNavigate, useLocation } from 'react-router-dom';
import { fetchEventSource } from '@microsoft/fetch-event-source';
import { Sparkles, AlertCircle, CheckCircle } from 'lucide-react';

import ChatBubble from './components/ChatBubble';
import InputBox from './components/InputBox';
import { modelChatApi, memoryApi } from '../../api/djangoApi';
import { getFastApiUrl } from '../../api/axiosConfig';

// 대화 이력 제한: 최근 5턴 (10개 메시지)
const MAX_HISTORY_TURNS = 5;

/**
 * 대화 이력을 FabriX API contents 배열 형식으로 변환
 * FabriX API 규칙: [user1, ai1, user2, ai2, ..., 현재입력]
 * @param {Array} messages - 현재 세션의 메시지 배열 [{role, content}, ...]
 * @param {string} newUserText - 새로 입력한 사용자 메시지
 * @returns {Array<string>} contents 배열
 */
const buildContentsArray = (messages, newUserText) => {
  // 기존 메시지 중 user와 assistant만 필터링 (system 메시지 제외)
  const validMessages = messages.filter(m => m.role === 'user' || m.role === 'assistant');
  const historyContents = validMessages.map(m => m.content);
  
  // 최근 N턴으로 제한 (1턴 = user + assistant = 2개 메시지)
  const maxMessages = MAX_HISTORY_TURNS * 2;
  const trimmedHistory = historyContents.slice(-maxMessages);
  
  // 새 사용자 메시지 추가
  const contents = [...trimmedHistory, newUserText];
  
  return contents;
};

/**
 * FabriX Chat - Model 기반 채팅 페이지
 * AgentChat과 동일한 구조를 사용하여 안정성 확보
 */
const ChatPage = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const currentSessionId = searchParams.get('session_id');

  const [messages, setMessages] = useState([]);
  const [selectedModelId, setSelectedModelId] = useState('');
  const [selectedModel, setSelectedModel] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [successMessage, setSuccessMessage] = useState(null);
 
  const abortControllerRef = useRef(null);
  const messagesEndRef = useRef(null);
  const assistantSavedRef = useRef(false);
  const errorTimerRef = useRef(null); // 429 배너 자동 닫기 타이머 ID
  const currentStreamingMsgRef = useRef(""); // 현재 스트리밍 중인 메시지 추적용

  // Model 선택 이벤트 핸들러 (최상위 레벨에서 선언)
  const handleModelSelected = useCallback((e) => {
    setSelectedModelId(e.detail.modelId);
    setSelectedModel(e.detail.model);
  }, []);

  // Model 선택 이벤트 수신 (ChatMainLayout → Sidebar에서 dispatch)
  useEffect(() => {
    window.addEventListener('model-selected', handleModelSelected);
    return () => window.removeEventListener('model-selected', handleModelSelected);
  }, [handleModelSelected]);

  // --- Session Load ---
  // 핵심: 사이드바에서 세션 클릭 시에만 loadHistory 실행
  // 새 세션 생성 직후에는 location.state.skipLoad를 통해 스킵
  useEffect(() => {
    if (currentSessionId) {
      if (location.state?.skipLoad) {
        // state를 초기화하여 새로고침 시에는 정상 로드되도록 함
        navigate(`/chat?session_id=${currentSessionId}`, { replace: true, state: {} });
        return;
      }
      
      const loadHistory = async () => {
        setIsLoading(true);
        try {
          const data = await modelChatApi.getSessionDetail(currentSessionId);
          setMessages(data.messages || []);
          if (data.model_id) setSelectedModelId(data.model_id);
        } catch (err) { /* Ignore error - deleted session etc */ }
        finally { setIsLoading(false); }
      };
      loadHistory();
    } else {
      setMessages([]);
    }
  }, [currentSessionId]);

  // --- Scroll ---
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // ===== Memory Command Handlers =====

  const handleMemoryCommand = async (command) => {
    setSuccessMessage(null);
    setError(null);

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
  };

  const handleMemorySave = async (name) => {
    if (!currentSessionId) {
      setError('세션을 먼저 생성한 후 스냅샷을 저장해주세요.');
      return;
    }
    setIsLoading(true);
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
      setIsLoading(false);
    }
  };

  const handleMemoryLoad = async (name) => {
    if (!currentSessionId) {
      setError('세션을 먼저 생성한 후 스냅샷을 로드해주세요.');
      return;
    }
    setIsLoading(true);
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
      setIsLoading(false);
    }
  };

  const handleMemoryList = async () => {
    if (!currentSessionId) {
      setError('세션을 먼저 생성한 후 목록을 조회해주세요.');
      return;
    }
    setIsLoading(true);
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
      setIsLoading(false);
    }
  };

  const handleMemoryClear = async () => {
    if (!currentSessionId) {
      setError('세션을 먼저 생성한 후 스냅샷을 삭제해주세요.');
      return;
    }
    setIsLoading(true);
    try {
      const result = await memoryApi.clearSnapshots(currentSessionId);
      setSuccessMessage(`메모리 초기화 완료: ${result.deleted}개의 스냅샷 삭제`);
    } catch (err) {
      setError('스냅샷 삭제에 실패했습니다: ' + (err.message || '알 수 없는 오류'));
    } finally {
      setIsLoading(false);
    }
  };

  const handleMemoryDelete = async (name) => {
    if (!currentSessionId) {
      setError('세션을 먼저 생성한 후 스냅샷을 삭제해주세요.');
      return;
    }
    setIsLoading(true);
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
      setIsLoading(false);
    }
  };

  // --- Handlers (Send & Stop) ---
  const handleSend = async (text) => {
    if (isLoading) return;

    // 커맨드 감지: / 로 시작하는 모든 입력은 커맨드로 인식
    if (text.startsWith('/')) {
      setSuccessMessage(null);
      setError(null);

      if (text.startsWith('/memory')) {
        await handleMemoryCommand(text);
        return;
      }

      setError(`알 수 없는 커맨드입니다: "${text.split(' ')[0]}"`);
      return;
    }

    if (!selectedModelId) {
      setError("Please select a model first.");
      return;
    }
    
    setError(null);
    setSuccessMessage(null);
    setIsLoading(true);

    const userMsg = { role: 'user', content: text };
    setMessages(prev => [...prev, userMsg]);

    try {
      let sessionId = currentSessionId;
      if (!sessionId) {
        const title = text ? text.slice(0, 30) : "New Conversation";
        const newSession = await modelChatApi.createSession(selectedModelId, title);
        sessionId = newSession.id;
        
        // 새 세션 생성 시 location.state에 skipLoad 플래그 전달 (ref 해킹 대체)
        navigate(`/chat?session_id=${sessionId}`, { replace: true, state: { skipLoad: true } });
        // 사이드바 갱신 이벤트 트리거
        window.dispatchEvent(new Event('session-created'));
      }

      await modelChatApi.saveMessage(sessionId, 'user', userMsg.content);
      setMessages(prev => [...prev, { role: 'assistant', content: '' }]);
      assistantSavedRef.current = false;
      currentStreamingMsgRef.current = "";
     
      abortControllerRef.current = new AbortController();
      let accumulatedAnswer = "";

      const token = sessionStorage.getItem('authToken');

      // 대화 이력 기반 contents 배열 구성
      const contentsArray = buildContentsArray(
        messages.filter(m => m.role !== undefined && m.content),
        text
      );
      
      await fetchEventSource(getFastApiUrl('/chat-messages'), {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': `Token ${token}`
        },
        body: JSON.stringify({ 
          modelIds: [selectedModelId],
          contents: contentsArray,
          isStream: true 
        }),
        signal: abortControllerRef.current.signal,
        async onopen(response) {
          // Rate Limit 에러 처리 (HTTP 429)
          if (response.status === 429) {
            let retryAfter = 30;
            let errorMessage = "요청이 너무 많습니다.";
            try {
              const errorBody = await response.json();
              if (errorBody.detail?.retry_after) {
                retryAfter = Math.ceil(errorBody.detail.retry_after);
              }
              if (errorBody.detail?.message) {
                errorMessage = errorBody.detail.message;
              }
            } catch (e) {
              // ignore parse error
            }
            throw new Error(`RATE_LIMIT:${retryAfter}:${errorMessage}`);
          }

          if (response.ok && response.headers.get('content-type')?.includes('text/event-stream')) {
            return; // success
          } else {
            throw new Error(`Invalid response: ${response.status}`);
          }
        },
        onmessage(ev) {
          try {
            if (!ev.data) {
              return;
            }
            
            const trimmedData = ev.data.trim();
            if (!trimmedData) {
              return;
            }
            
            try {
              const parsed = JSON.parse(trimmedData);
              // 방어적 코딩: 스네이크케이스 / 카멜케이스 모두 처리
              const eventStatus = parsed.event_status ?? parsed.eventStatus;
              const filterBlockReason = parsed.filter_block_reason ?? parsed.filterBlockReason;
              
              if (parsed.error) {
                setError(`API Error: ${parsed.error}`);
                return;
              }
              
              // 필터 차단 확인 (FabriX Chat API 응답 구조 기반)
              // - filter_block_reason: null → 정상 (필터 정보 없음)
              // - filter_block_reason.result_code: "FR-200" → 정상 (Filter Result 200 = 통과)
              // - filter_block_reason.message: "The content was passed" → 정상 (통과)
              // - 실제 차단 시에만 다른 result_code와 차단 메시지가 반환됨
              if (filterBlockReason && filterBlockReason !== null) {
                const resultCode = filterBlockReason.result_code || filterBlockReason.resultCode || '';
                const message = filterBlockReason.message || '';
                
                // FR-200 = 필터 통과, "passed"/"allowed" = 통과됨
                const isFilterPassed = resultCode === 'FR-200' 
                  || message.toLowerCase().includes('passed')
                  || message.toLowerCase().includes('allowed');
                
                // 통과가 아니고, 실제 차단 메시지가 있는 경우만 에러 표시
                if (!isFilterPassed) {
                  // 차단 메시지 추출 (ko, en, message 순서로 확인)
                  const blockReason = filterBlockReason.ko || filterBlockReason.en || message;
                  if (blockReason) {
                    setError(`응답이 필터링되었습니다: ${blockReason}`);
                    return;
                  }
                }
              }
              
              // CHUNK 이벤트의 content만 사용자 응답으로 누적
              if (eventStatus === 'CHUNK') {
                const content = parsed.content;
                if (content !== null && content !== undefined) {
                  const contentStr = String(content);
                  if (contentStr) {
                    accumulatedAnswer += contentStr;
                    currentStreamingMsgRef.current = accumulatedAnswer;
                    updateLastMessage(accumulatedAnswer);
                  }
                }
              }
            } catch (jsonErr) {
              // JSON 파싱 실패 - 무시 (잘못된 데이터)
            }
          } catch (e) {
            // SSE parse error - ignore
          }
        },
        onerror(err) {
          if (err.message?.startsWith('RATE_LIMIT:')) {
            throw err;
          }
          setError("연결 오류가 발생했습니다. 다시 시도해주세요.");
          setIsLoading(false);
          throw err;
        },
        async onclose() {
          try {
            await persistAssistantMessageOnce(sessionId, accumulatedAnswer);
          } catch (saveErr) {
            setError("응답 저장 중 오류가 발생했습니다. 다시 시도해주세요.");
          }
          abortControllerRef.current = null;
          setIsLoading(false);
        }
      });
    } catch (err) {
      if (err.message?.startsWith('RATE_LIMIT:')) {
        const parts = err.message.split(':');
        const retryAfter = parseInt(parts[1], 10) || 30;
        const message = parts.slice(2).join(':') || "요청이 너무 많습니다.";
        setError(`${message} (약 ${retryAfter}초 후 다시 시도해주세요)`);
        // 429 전용: Retry-After 시간 후 배너 자동 닫기
        if (errorTimerRef.current) clearTimeout(errorTimerRef.current);
        errorTimerRef.current = setTimeout(() => setError(null), retryAfter * 1000);
      } else {
        setError("메시지 전송 중 오류가 발생했습니다.");
      }
      setIsLoading(false);
    }
  };

  const updateLastMessage = useCallback((content) => {
    setMessages(prev => {
      if (prev.length === 0) return prev;
      const newHistory = [...prev];
      const last = newHistory[newHistory.length - 1];
      newHistory[newHistory.length - 1] = { ...last, content };
      return newHistory;
    });
  }, []);

  const persistAssistantMessageOnce = useCallback(async (sessionId, content) => {
    const normalizedContent = (content || '').trim();
    if (!sessionId || !normalizedContent || assistantSavedRef.current) {
      return;
    }

    assistantSavedRef.current = true;
    try {
      await modelChatApi.saveMessage(sessionId, 'assistant', normalizedContent);
    } catch (saveError) {
      assistantSavedRef.current = false;
      throw saveError;
    }
  }, []);

  const handleStop = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      // messages 배열 대신 ref를 사용하여 클로저 문제 및 불필요한 리렌더링 방지
      if (currentSessionId && currentStreamingMsgRef.current) {
        persistAssistantMessageOnce(currentSessionId, currentStreamingMsgRef.current)
          .catch(() => setError("응답 저장 중 오류가 발생했습니다. 다시 시도해주세요."));
      }
      abortControllerRef.current = null;
      setIsLoading(false);
    }
  }, [currentSessionId, persistAssistantMessageOnce]);

  return (
    <div className="flex flex-col h-full bg-[var(--bg-primary)]">
      {/* Success Display - Top of Page */}
      {successMessage && (
        <div className="flex-shrink-0 bg-green-50 text-green-600 px-4 py-3 text-sm flex items-center gap-2 border-b border-green-100 z-50">
          <CheckCircle size={16} />
          {successMessage}
          <button
            onClick={() => setSuccessMessage(null)}
            className="ml-auto text-xs hover:underline"
          >
            닫기
          </button>
        </div>
      )}

      {/* Error Display - Top of Page */}
      {error && (
        <div className="flex-shrink-0 bg-red-50 text-red-600 px-4 py-3 text-sm flex items-center gap-2 border-b border-red-100 z-50">
          <AlertCircle size={16} />
          {error}
          <button 
            onClick={() => setError(null)} 
            className="ml-auto text-xs hover:underline"
          >
            닫기
          </button>
        </div>
      )}

      {/* Chat Area */}
      <div className="flex-1 overflow-y-auto px-4 py-8 custom-scrollbar scroll-smooth">
        <div className="max-w-3xl mx-auto flex flex-col gap-6">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-[50vh] text-center animate-fade-in-up">
              <div className="w-16 h-16 bg-gradient-to-tr from-cyan-500 to-blue-500 rounded-2xl flex items-center justify-center shadow-lg mb-6 text-white">
                <Sparkles size={32} />
              </div>
              <h2 className="text-2xl font-bold text-[var(--text-primary)] mb-2">How can I help you today?</h2>
              <p className="text-[var(--text-secondary)] max-w-md leading-relaxed">
                Select a model from the sidebar and start a conversation.
              </p>
            </div>
          ) : (
            messages.map((msg, idx) => (
              <ChatBubble
                key={idx}
                message={msg}
                isStreaming={isLoading && idx === messages.length - 1 && msg.role === 'assistant'}
              />
            ))
          )}
          <div ref={messagesEndRef} className="h-4" />
        </div>
      </div>

      {/* Input Area */}
      <div className="flex-shrink-0 bg-[var(--bg-primary)] p-4 pb-6">
        <div className="max-w-3xl mx-auto">
          <InputBox onSend={handleSend} isLoading={isLoading} onStop={handleStop} />
        </div>
      </div>
    </div>
  );
};

export default ChatPage;
