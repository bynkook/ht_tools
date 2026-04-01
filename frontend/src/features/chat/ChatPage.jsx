import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useSearchParams, useNavigate, useLocation } from 'react-router-dom';
import { fetchEventSource } from '@microsoft/fetch-event-source';
import { Sparkles, AlertCircle, CheckCircle } from 'lucide-react';

import ChatBubble from './components/ChatBubble';
import InputBox from './components/InputBox';
import { modelChatApi } from '../../api/djangoApi';
import { getFastApiUrl } from '../../api/axiosConfig';
import { mcpRagApi } from '../../api/fastapiApi';
import { useCommands, detectNaturalLanguageCommand, parseAtMentions, stripAtMentions, resolveAtMentions } from '../../hooks/useCommands';

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
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [successMessage, setSuccessMessage] = useState(null);
 
  const abortControllerRef = useRef(null);
  const messagesEndRef = useRef(null);
  const assistantSavedRef = useRef(false);
  const errorTimerRef = useRef(null); // 429 배너 자동 닫기 타이머 ID
  const currentStreamingMsgRef = useRef(""); // 현재 스트리밍 중인 메시지 추적용
  const activeSessionIdRef = useRef(currentSessionId);
  const pendingBootstrapSessionIdRef = useRef(null);

  useEffect(() => {
    activeSessionIdRef.current = currentSessionId;
  }, [currentSessionId]);

  const ensureSession = useCallback(async (seedText) => {
    if (activeSessionIdRef.current) {
      return activeSessionIdRef.current;
    }

    if (!selectedModelId) {
      setError("Please select a model first.");
      return null;
    }

    const title = seedText ? seedText.slice(0, 30) : "New Conversation";
    const newSession = await modelChatApi.createSession(selectedModelId, title);
    activeSessionIdRef.current = String(newSession.id);
    pendingBootstrapSessionIdRef.current = String(newSession.id);
    navigate(`/chat?session_id=${newSession.id}`, { replace: true, state: { skipLoad: true } });
    window.dispatchEvent(new Event('session-created'));
    return String(newSession.id);
  }, [navigate, selectedModelId]);

  // 커맨드 처리 훅
  const { executeCommand, isCommandLoading, activeCategory, ragEnabled, ragCacheRef, resetCommandState } = useCommands({
    messages,
    setMessages,
    setError,
    setSuccessMessage,
    currentSessionId,
    ensureSession,
  });

  // Model 선택 이벤트 핸들러 (최상위 레벨에서 선언)
  const handleModelSelected = useCallback((e) => {
    setSelectedModelId(e.detail.modelId);
  }, []);

  // Model 선택 이벤트 수신 (ChatMainLayout → Sidebar에서 dispatch)
  useEffect(() => {
    window.addEventListener('model-selected', handleModelSelected);
    return () => window.removeEventListener('model-selected', handleModelSelected);
  }, [handleModelSelected]);

  // New Chat 이벤트 수신: null→null 세션 전환 및 스트리밍 중 New Chat 처리
  // currentSessionId 의존 useEffect는 null→null 변화를 감지하지 못하므로 이벤트 패턴 사용
  useEffect(() => {
    const onNewChatRequested = () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
      setIsLoading(false);
      setMessages([]);
      setError(null);
      setSuccessMessage(null);
      resetCommandState();
      assistantSavedRef.current = false;
      currentStreamingMsgRef.current = '';
      activeSessionIdRef.current = null;
      pendingBootstrapSessionIdRef.current = null;
    };
    window.addEventListener('new-chat-requested', onNewChatRequested);
    return () => window.removeEventListener('new-chat-requested', onNewChatRequested);
  }, [resetCommandState]);

  // --- Session Load ---
  // 핵심: 사이드바에서 세션 클릭 시에만 loadHistory 실행
  // 새 세션 생성 직후에는 location.state.skipLoad를 통해 스킵
  useEffect(() => {
    // 세션 전환 시 진행 중인 스트림 중단 (Race Condition 방지)
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setIsLoading(false);
    }
    if (currentSessionId) {
      if (location.state?.skipLoad) {
        // state를 초기화하여 새로고침 시에는 정상 로드되도록 함
        navigate(`/chat?session_id=${currentSessionId}`, { replace: true, state: {} });
        return;
      }

      if (pendingBootstrapSessionIdRef.current === currentSessionId) {
        pendingBootstrapSessionIdRef.current = null;
        return;
      }

      resetCommandState();
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
      activeSessionIdRef.current = null;
      pendingBootstrapSessionIdRef.current = null;
      resetCommandState();
      setMessages([]);
    }
  }, [currentSessionId, resetCommandState]);

  // --- Scroll ---
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // --- Handlers (Send & Stop) ---
  const handleSend = async (text) => {
    if (isLoading || isCommandLoading) return;

    // 커맨드 감지: / 로 시작하는 모든 입력은 커맨드로 인식
    if (text.startsWith('/')) {
      const result = await executeCommand(text, { originalText: text });
      if (result.handled) return;
    }

    // 자연어 커맨드 감지 ("태블로 대시보드 목록" 등)
    const detectedCommand = detectNaturalLanguageCommand(text);
    if (detectedCommand) {
      const result = await executeCommand(detectedCommand, { originalText: text });
      if (result.handled) return;
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
      const sessionId = await ensureSession(text);
      if (!sessionId) {
        setIsLoading(false);
        setMessages(prev => prev.slice(0, -1));
        return;
      }

      await modelChatApi.saveMessage(sessionId, 'user', userMsg.content);
      setMessages(prev => [...prev, { role: 'assistant', content: '', isRag: ragEnabled && !!activeCategory, ragCategory: activeCategory }]);
      assistantSavedRef.current = false;
      currentStreamingMsgRef.current = "";
     
      abortControllerRef.current = new AbortController();
      let accumulatedAnswer = "";

      const token = sessionStorage.getItem('authToken');

      // ===== @<파일명> mention 전처리 =====
      const mentions = parseAtMentions(text);
      let atMentionSystemPrompt = null;
      if (mentions.length > 0) {
        const cleanQuery = stripAtMentions(text);
        try {
          const { resolved, errors } = await resolveAtMentions(mentions, cleanQuery, activeCategory);
          if (errors.length > 0) {
            setError(`파일을 찾을 수 없습니다: ${errors.map(e => `@"${e}"`).join(', ')}`);
            if (resolved.length === 0) {
              setIsLoading(false);
              setMessages(prev => prev.slice(0, -1)); // 추가한 userMsg 되돌리기
              return;
            }
          }
          if (resolved.length === 1 && resolved[0].system_prompt) {
            atMentionSystemPrompt = resolved[0].system_prompt;
          } else if (resolved.length > 1) {
            const allBlocks = resolved
              .flatMap(({ filename, snippets }) =>
                snippets.map(s => `📄 **파일: ${filename}**\n\n${s.snippet}`)
              )
              .join('\n\n---\n\n');
            if (allBlocks) {
              atMentionSystemPrompt =
                `당신은 사내 문서 기반 질문 답변 어시스턴트입니다.\n` +
                `아래 참고 문서를 바탕으로 사용자의 질문에 답하세요.\n` +
                `참고 문서에 없는 내용은 '제공된 문서에서 찾을 수 없습니다'라고 솔직하게 답하세요.\n\n` +
                `=== 참고 문서 ===\n\n${allBlocks}\n\n==================`;
            }
          }
        } catch (e) {
          console.warn('@mention 해석 실패 — 일반 채팅으로 진행:', e);
        }
      }
      // =====================================

      // ===== RAG 전처리 (세션 캐시 포함) — @mention 있으면 건너뜀 =====
      let ragSystemPrompt = null;
      if (!atMentionSystemPrompt && ragEnabled) {
        try {
          const now = Date.now();
          const cache = ragCacheRef.current;
          const RAG_CACHE_TTL_MS = 5 * 60 * 1000; // 5분
          const cacheHit = cache &&
            cache.query === text &&
            cache.category === (activeCategory ?? null) &&
            (now - cache.cachedAt) < RAG_CACHE_TTL_MS;

          if (cacheHit) {
            ragSystemPrompt = cache.systemPrompt;
          } else {
            const ragRes = await mcpRagApi.search({
              query: text,
              category: activeCategory ?? undefined,
            });
            if (ragRes.data?.success && ragRes.data?.system_prompt) {
              ragSystemPrompt = ragRes.data.system_prompt;
              ragCacheRef.current = {
                query: text,
                category: activeCategory ?? null,
                systemPrompt: ragSystemPrompt,
                cachedAt: now,
              };
            }
          }
        } catch (e) {
          console.warn('RAG 검색 실패 — 일반 채팅으로 진행:', e);
        }
      }
      // ========================================

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
          isStream: true,
          ...(atMentionSystemPrompt
            ? { systemPrompt: atMentionSystemPrompt }
            : ragSystemPrompt ? { systemPrompt: ragSystemPrompt } : {}),
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
      if (activeSessionIdRef.current && currentStreamingMsgRef.current) {
        persistAssistantMessageOnce(activeSessionIdRef.current, currentStreamingMsgRef.current)
          .catch(() => setError("응답 저장 중 오류가 발생했습니다. 다시 시도해주세요."));
      }
      abortControllerRef.current = null;
      setIsLoading(false);
    }
  }, [persistAssistantMessageOnce]);

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
          {/* RAG 모드 배지 */}
          {ragEnabled && (
            <div className="flex items-center gap-2 mb-2 px-1">
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-cyan-100 text-cyan-700 text-xs font-medium dark:bg-cyan-900/40 dark:text-cyan-300">
                📚 RAG
                {activeCategory && <span className="opacity-70">· {activeCategory}</span>}
              </span>
              <span className="text-xs text-[var(--text-secondary)]">
                질문 시 문서를 자동 검색합니다
              </span>
            </div>
          )}
          <InputBox key={currentSessionId ?? 'new'} onSend={handleSend} isLoading={isLoading} onStop={handleStop} />
        </div>
      </div>
    </div>
  );
};

export default ChatPage;
