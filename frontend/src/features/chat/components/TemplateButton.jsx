import React, { useState, useRef, useEffect } from 'react';
import { ChevronUp, X } from 'lucide-react';
import templates from '../template/chat_templates.json';

/**
 * Template button for FabriX Chat input box.
 * Displays a popup list of 20 preset prompt templates above the button.
 * Clicking a template calls onSelect(content) and closes the popup.
 * When a template is active, shows an × button to clear the textarea.
 */
const TemplateButton = ({
  onSelect,
  disabled,
  isActive,
  onClear,
  onPreserveInputPointerDown,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const wrapperRef = useRef(null);

  // Close popup when clicking outside
  useEffect(() => {
    if (!isOpen) return;
    const handleOutsideClick = (e) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, [isOpen]);

  const handleSelect = (content) => {
    onSelect(content);
    setIsOpen(false);
  };

  return (
    <div ref={wrapperRef} className="relative">
      {/* Popup list — appears above the button */}
      {isOpen && (
        <div className="absolute bottom-full left-0 mb-2 w-64 bg-[var(--bg-primary)] border border-[var(--border-color)] rounded-xl shadow-xl z-50 overflow-hidden">
          {/* Template list — shows ~5 items, rest scrollable */}
          <ul className="max-h-[180px] overflow-y-auto py-1">
            {templates.map((tpl) => (
              <li key={tpl.id}>
                <button
                  className="w-full text-left px-3 py-1.5 text-xs text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors"
                  onMouseDown={(e) => {
                    onPreserveInputPointerDown?.(e);
                    handleSelect(tpl.content);
                  }}
                >
                  {tpl.title}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Trigger button */}
      <div className={`flex items-center border rounded-lg transition-colors
        ${disabled ? 'opacity-40 cursor-not-allowed' : ''}
        ${isOpen
          ? 'border-[var(--text-secondary)] bg-[var(--input-template-bg)]'
          : isActive
            ? 'border-[var(--text-secondary)] bg-[var(--input-template-bg)]'
            : 'border-[var(--border-color)] bg-[var(--input-template-bg)] hover:bg-[var(--input-template-bg)] hover:border-[var(--text-secondary)]'
        }`}
      >
        <button
          type="button"
          disabled={disabled}
          onMouseDown={onPreserveInputPointerDown}
          onClick={() => !disabled && setIsOpen((prev) => !prev)}
          className={`flex items-center gap-1 pl-4 pr-3 py-1 text-sm font-medium transition-colors disabled:cursor-not-allowed
            ${isOpen || isActive ? 'text-[var(--text-primary)]' : 'text-[var(--text-secondary)]'}`}
          title="Insert a template prompt"
        >
          Template
          <ChevronUp
            size={14}
            className={`transition-transform duration-200 ${isOpen ? 'rotate-0' : 'rotate-180'}`}
          />
        </button>
        {/* Clear button — only shown when a template is active */}
        {isActive && (
          <button
            type="button"
            onMouseDown={(e) => {
              onPreserveInputPointerDown?.(e);
              onClear();
            }}
            className="pr-3 py-1 text-[var(--text-secondary)] hover:text-red-500 transition-colors"
            title="Clear inserted template"
          >
            <X size={14} />
          </button>
        )}
      </div>
    </div>
  );
};

export default TemplateButton;
