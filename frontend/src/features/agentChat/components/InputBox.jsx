import React, { useState, useRef, useEffect } from 'react';
import { Paperclip, Square, X, ArrowUp } from 'lucide-react';
import useInputFocusRestore from '../../../hooks/useInputFocusRestore';

const InputBox = ({
  onSend,
  isLoading,
  isBusy = isLoading,
  onStop,
  sessionId = null,
  resetVersion = 0,
}) => {
  const [message, setMessage] = useState('');
  const [selectedFile, setSelectedFile] = useState(null);
  const composerRef = useRef(null);
  const fileInputRef = useRef(null);
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
    setMessage('');
    setSelectedFile(null);
    historyRef.current = [];
    historyIdxRef.current = -1;
    draftRef.current = '';
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }, [resetVersion, sessionId]);

  const handleSend = async () => {
    if ((!message.trim() && !selectedFile) || isBusy) return;
    const messageToSend = message;
    const fileToSend = selectedFile;

    if (messageToSend.trim() && historyRef.current[0] !== messageToSend.trim()) {
      historyRef.current = [messageToSend.trim(), ...historyRef.current].slice(0, 5);
    }
    historyIdxRef.current = -1;
    setMessage('');
    setSelectedFile(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
    if (textareaRef.current) textareaRef.current.style.height = 'auto';

    try {
      const result = onSend(messageToSend, fileToSend);
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
      const onFirstLine = !message.includes('\n') ||
        (ta && ta.selectionStart <= message.indexOf('\n'));
      if (onFirstLine && historyRef.current.length > 0) {
        e.preventDefault();
        if (historyIdxRef.current === -1) draftRef.current = message;
        historyIdxRef.current = Math.min(historyIdxRef.current + 1, historyRef.current.length - 1);
        setMessage(historyRef.current[historyIdxRef.current]);
        return;
      }
    }
    if (e.key === 'ArrowDown' && historyIdxRef.current >= 0) {
      e.preventDefault();
      historyIdxRef.current -= 1;
      setMessage(historyIdxRef.current === -1 ? draftRef.current : historyRef.current[historyIdxRef.current]);
      return;
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
        handleSend();
    }
  };

  const handleFileChange = (e) => {
    if (e.target.files?.[0]) setSelectedFile(e.target.files[0]);
  };

  const handleInput = (e) => {
    const target = e.target;
    target.style.height = 'auto';
    target.style.height = `${Math.min(target.scrollHeight, 200)}px`;
    historyIdxRef.current = -1;
    setMessage(target.value);
  };

  return (
    <div className="w-full">
      {/* File Preview */}
      {selectedFile && (
        <div className="flex items-center gap-2 mb-2 p-2 px-3 bg-white border border-[var(--border-color)] rounded-xl w-fit shadow-sm animate-slide-up">
          <div className="p-1.5 bg-gray-100 rounded-lg">
            <Paperclip size={14} className="text-gray-500" />
          </div>
          <span className="text-sm text-[var(--text-primary)] max-w-[200px] truncate font-medium">
            {selectedFile.name}
          </span>
          <button
            onMouseDown={keepFocusOnPointerDown}
            onClick={() => setSelectedFile(null)}
            className="text-gray-400 hover:text-red-500 ml-1 transition-colors"
          >
            <X size={16} />
          </button>
        </div>
      )}

      {/* Main Input Container */}
      <div
        ref={composerRef}
        className="relative flex items-end gap-2 bg-white border border-[var(--border-color)] rounded-2xl p-1 shadow-md hover:shadow-md focus-within:shadow-md transition-all w-full"
      >
       
        {/* File Button */}
        <button
          onMouseDown={keepFocusOnPointerDown}
          onClick={() => fileInputRef.current?.click()}
          className="p-3 text-[var(--text-secondary)] hover:text-[var(--accent-color)] hover:bg-blue-50 rounded-full transition-colors flex-shrink-0 mb-0.5"
          disabled={isBusy}
          title="Attach file"
        >
          <Paperclip size={20} />
        </button>
        <input type="file" ref={fileInputRef} onChange={handleFileChange} className="hidden" />

        {/* Textarea */}
        <textarea
          ref={textareaRef}
          value={message}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          {...inputFocusProps}
          placeholder="Message FabriX Agent..."
          rows={1}
          readOnly={isLoading}
          aria-busy={isLoading}
          className="flex-1 max-w-full min-w-0 bg-transparent text-sm text-[var(--text-primary)] resize-none outline-none py-3.5 max-h-[200px] custom-scrollbar placeholder:text-gray-400 leading-relaxed"
        />

        {/* Send/Stop Button */}
        <div className="mb-1 mr-1">
            {isLoading ? (
            <button
                onMouseDown={keepFocusOnPointerDown}
                onClick={onStop}
                className="p-2.5 bg-[var(--text-primary)] text-white rounded-full hover:opacity-80 transition-all shadow-md"
                title="Stop"
            >
                <Square size={16} fill="currentColor" />
            </button>
            ) : (
            <button
              onMouseDown={keepFocusOnPointerDown}
              onClick={handleSend}
                disabled={(!message.trim() && !selectedFile) || isBusy}
                className={`
                p-2.5 rounded-full transition-all shadow-md
                ${((!message.trim() && !selectedFile) || isBusy)
                    ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                    : 'bg-[var(--accent-color)] text-white hover:bg-[var(--accent-hover)] hover:scale-105 active:scale-95'}
                `}
                title="Send"
            >
                <ArrowUp size={20} strokeWidth={3} />
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
