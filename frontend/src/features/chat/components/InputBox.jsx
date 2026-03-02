import React, { useState, useRef, useEffect } from 'react';
import { Send, StopCircle } from 'lucide-react';
import useInputFocusRestore from '../../../hooks/useInputFocusRestore';

/**
 * Input component for Model Chat (FabriX Chat)
 * Simplified version without file upload - Model Chat API doesn't support file attachments
 */
const InputBox = ({ onSend, isLoading, onStop }) => {
  const [text, setText] = useState('');
  const textareaRef = useRef(null);
  const { requestRestoreFocus } = useInputFocusRestore({
    inputRef: textareaRef,
    isLoading,
  });

  // Auto-resize textarea
  useEffect(() => {
    const ta = textareaRef.current;
    if (ta) {
      ta.style.height = 'auto';
      ta.style.height = Math.min(ta.scrollHeight, 200) + 'px';
    }
  }, [text]);

  const handleSend = async (trigger = 'mouse') => {
    if (!text.trim() || isLoading) return;

    const shouldRestore = trigger === 'keyboard';
    const message = text.trim();

    setText('');
    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }

    try {
      const result = onSend(message);
      if (result && typeof result.then === 'function') {
        await result;
      }
    } finally {
      if (shouldRestore) {
        requestRestoreFocus();
      }
    }
  };

  const handleKeyDown = (e) => {
    if (e.nativeEvent?.isComposing) return;
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend('keyboard');
    }
  };

  return (
    <div className="w-full">
      <div className="relative flex items-end gap-2 bg-white border border-[var(--border-color)] rounded-2xl p-1 shadow-md hover:shadow-md focus-within:shadow-md transition-all w-full">
        {/* Text Input */}
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Message FabriX Chat..."
          rows={1}
          readOnly={isLoading}
          aria-busy={isLoading}
          className="flex-1 bg-transparent text-sm text-[var(--text-primary)] placeholder:text-gray-400 px-4 py-3.5 pr-16 resize-none focus:outline-none"
        />

        {/* Action Buttons - Positioned absolutely to the right */}
        <div className="absolute right-2 bottom-2 flex items-center gap-2">
          {/* Send / Stop Button */}
          {isLoading ? (
            <button
              onClick={onStop}
              className="flex items-center justify-center w-10 h-10 bg-red-500 text-white rounded-xl hover:bg-red-600 transition-all hover:scale-105 active:scale-95"
              title="Stop generating"
            >
              <StopCircle size={20} />
            </button>
          ) : (
            <button
              onClick={() => handleSend('mouse')}
              disabled={!text.trim()}
              className="flex items-center justify-center w-10 h-10 bg-gradient-to-r from-cyan-500 to-blue-500 text-white rounded-xl disabled:opacity-40 disabled:cursor-not-allowed hover:shadow-lg hover:scale-105 active:scale-95 transition-all"
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
