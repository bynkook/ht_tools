import React, { useState, useRef, useEffect } from 'react';
import { Send, StopCircle } from 'lucide-react';
import useInputFocusRestore from '../../../hooks/useInputFocusRestore';
import TemplateButton from './TemplateButton';

/**
 * Input component for Model Chat (FabriX Chat)
 * Simplified version without file upload - Model Chat API doesn't support file attachments
 */
const InputBox = ({ onSend, isLoading, onStop }) => {
  const [text, setText] = useState('');
  const [isTemplateActive, setIsTemplateActive] = useState(false);
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
    setIsTemplateActive(false);
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

  const handleTemplateSelect = (content) => {
    const newText = content + '\n';
    setText(newText);
    setIsTemplateActive(true);
    // Restore focus and move cursor to end after render
    requestAnimationFrame(() => {
      if (textareaRef.current) {
        textareaRef.current.focus();
        const len = newText.length;
        textareaRef.current.setSelectionRange(len, len);
      }
    });
  };

  const handleTemplateClear = () => {
    setText('');
    setIsTemplateActive(false);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.focus();
    }
  };

  return (
    <div className="w-full">
      <div className="flex flex-col bg-white border border-[var(--border-color)] rounded-2xl p-1 shadow-md hover:shadow-md focus-within:shadow-md transition-all w-full">
        {/* Text Input */}
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => { setText(e.target.value); if (isTemplateActive) setIsTemplateActive(false); }}
          onKeyDown={handleKeyDown}
          placeholder="Message FabriX Chat..."
          rows={1}
          readOnly={isLoading}
          aria-busy={isLoading}
          className="bg-transparent text-xs text-[var(--text-primary)] placeholder:text-gray-400 px-4 py-3 resize-none focus:outline-none w-full"
        />

        {/* Toolbar row: Template (left) + Send/Stop (right) */}
        <div className="flex items-center justify-between px-2 py-2">
          <TemplateButton
            onSelect={handleTemplateSelect}
            disabled={isLoading}
            isActive={isTemplateActive}
            onClear={handleTemplateClear}
          />
          {/* Send / Stop Button */}
          {isLoading ? (
            <button
              onClick={onStop}
              className="flex items-center justify-center w-8 h-8 bg-red-500 text-white rounded-lg hover:bg-red-600 transition-all hover:scale-105 active:scale-95"
              title="Stop generating"
            >
              <StopCircle size={16} />
            </button>
          ) : (
            <button
              onClick={() => handleSend('mouse')}
              disabled={!text.trim()}
              className="flex items-center justify-center w-8 h-8 bg-gradient-to-r from-cyan-500 to-blue-500 text-white rounded-lg disabled:opacity-40 disabled:cursor-not-allowed hover:shadow-lg hover:scale-105 active:scale-95 transition-all"
              title="Send message"
            >
              <Send size={15} />
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
