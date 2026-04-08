import React, { useState, useRef, useEffect } from 'react';
import { Send, StopCircle } from 'lucide-react';
import TemplateButton from './TemplateButton';
import useInputFocusRestore from '../../../hooks/useInputFocusRestore';

/**
 * Input component for Model Chat (FabriX Chat)
 * Simplified version without file upload - Model Chat API doesn't support file attachments
 */
const InputBox = ({
  onSend,
  isLoading,
  isBusy = isLoading,
  onStop,
  sessionId = null,
  resetVersion = 0,
}) => {
  const [text, setText] = useState('');
  const [isTemplateActive, setIsTemplateActive] = useState(false);
  const composerRef = useRef(null);
  const textareaRef = useRef(null);
  const historyRef    = useRef([]);  // 최근 5개 전송 메시지 (최신=index 0)
  const historyIdxRef = useRef(-1);  // 탐색 위치 (-1: 탐색 중 아님)
  const draftRef      = useRef('');  // 탐색 시작 전 입력값 보존
  const {
    inputFocusProps,
    keepFocusOnPointerDown,
    requestRestoreFocus,
  } = useInputFocusRestore({
    inputRef: textareaRef,
    scopeRef: composerRef,
    isBusy,
  });

  useEffect(() => {
    setText('');
    setIsTemplateActive(false);
    historyRef.current = [];
    historyIdxRef.current = -1;
    draftRef.current = '';
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }, [resetVersion, sessionId]);

  // Auto-resize textarea
  useEffect(() => {
    const ta = textareaRef.current;
    if (ta) {
      ta.style.height = 'auto';
      ta.style.height = Math.min(ta.scrollHeight, 200) + 'px';
    }
  }, [text]);

  const handleSend = async () => {
    if (!text.trim() || isBusy) return;

    const message = text.trim();
    if (historyRef.current[0] !== message) {
      historyRef.current = [message, ...historyRef.current].slice(0, 5);
    }
    historyIdxRef.current = -1;
    setText('');
    setIsTemplateActive(false);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }

    try {
      const result = onSend(message);
      if (result && typeof result.then === 'function') {
        await result;
      }
    } finally {
      requestRestoreFocus();
    }
  };

  const handleKeyDown = (e) => {
    if (e.nativeEvent?.isComposing) return;
    if (e.key === 'ArrowUp') {
      const ta = textareaRef.current;
      const onFirstLine = !text.includes('\n') ||
        (ta && ta.selectionStart <= text.indexOf('\n'));
      if (onFirstLine && historyRef.current.length > 0) {
        e.preventDefault();
        if (historyIdxRef.current === -1) draftRef.current = text;
        historyIdxRef.current = Math.min(historyIdxRef.current + 1, historyRef.current.length - 1);
        setText(historyRef.current[historyIdxRef.current]);
        return;
      }
    }
    if (e.key === 'ArrowDown' && historyIdxRef.current >= 0) {
      e.preventDefault();
      historyIdxRef.current -= 1;
      setText(historyIdxRef.current === -1 ? draftRef.current : historyRef.current[historyIdxRef.current]);
      return;
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleTemplateSelect = (content) => {
    const newText = content + '\n';
    setText(newText);
    setIsTemplateActive(true);
  };

  const handleTemplateClear = () => {
    setText('');
    setIsTemplateActive(false);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  return (
    <div className="w-full">
      <div
        ref={composerRef}
        className="flex flex-col bg-white border border-[var(--border-color)] rounded-2xl p-1 shadow-md hover:shadow-md focus-within:shadow-md transition-all w-full"
      >
        {/* Text Input */}
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => { setText(e.target.value); historyIdxRef.current = -1; if (isTemplateActive) setIsTemplateActive(false); }}
          onKeyDown={handleKeyDown}
          {...inputFocusProps}
          placeholder="Message FabriX Chat..."
          rows={1}
          readOnly={isLoading}
          aria-busy={isLoading}
          className="bg-transparent text-sm text-[var(--text-primary)] placeholder:text-gray-400 px-4 py-3 resize-none focus:outline-none w-full"
        />

        {/* Toolbar row: Template (left) + Send/Stop (right) */}
        <div className="flex items-center justify-between px-2 pt-1 pb-2">
          <TemplateButton
            onSelect={handleTemplateSelect}
            disabled={isBusy}
            isActive={isTemplateActive}
            onClear={handleTemplateClear}
            onPreserveInputPointerDown={keepFocusOnPointerDown}
          />
          {/* Send / Stop Button */}
          {isLoading ? (
            <button
              onMouseDown={keepFocusOnPointerDown}
              onClick={onStop}
              className="flex items-center justify-center w-10 h-10 bg-red-500 text-white rounded-lg hover:bg-red-600 transition-all hover:scale-105 active:scale-95"
              title="Stop generating"
            >
              <StopCircle size={18} />
            </button>
          ) : (
            <button
              onMouseDown={keepFocusOnPointerDown}
              onClick={handleSend}
              disabled={!text.trim() || isBusy}
              className="flex items-center justify-center w-10 h-10 bg-gradient-to-r from-cyan-500 to-blue-500 text-white rounded-lg disabled:opacity-40 disabled:cursor-not-allowed hover:shadow-lg hover:scale-105 active:scale-95 transition-all"
              title="Send message"
            >
              <Send size={18} />
            </button>
          )}
        </div>
      </div>
      <div className="text-center mt-3 text-xs text-[var(--text-placeholder)] font-medium">
        FabriX can make mistakes. Please verify important information.
      </div>
    </div>
  );
};

export default InputBox;
