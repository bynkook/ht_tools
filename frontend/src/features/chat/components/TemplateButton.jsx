import React, { useState, useRef, useEffect } from 'react';
import { ChevronUp, X } from 'lucide-react';
import templates from '../data/chat_templates.json';

/**
 * Template button for FabriX Chat input box.
 * Displays a popup list of 20 preset prompt templates above the button.
 * Clicking a template calls onSelect(content) and closes the popup.
 * When a template is active, shows an × button to clear the textarea.
 */
const TemplateButton = ({ onSelect, disabled, isActive, onClear }) => {
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
        <div className="absolute bottom-full left-0 mb-2 w-64 bg-white border border-[var(--border-color)] rounded-xl shadow-xl z-50 overflow-hidden">
          {/* Template list — shows ~5 items, rest scrollable */}
          <ul className="max-h-[180px] overflow-y-auto py-1">
            {templates.map((tpl) => (
              <li key={tpl.id}>
                <button
                  className="w-full text-left px-3 py-1.5 text-xs text-[var(--text-primary)] hover:bg-cyan-50 hover:text-cyan-700 transition-colors"
                  /* Use onMouseDown + preventDefault to prevent textarea blur before selection */
                  onMouseDown={(e) => {
                    e.preventDefault();
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
          ? 'border-cyan-400 bg-cyan-50'
          : isActive
            ? 'border-cyan-300 bg-cyan-50'
            : 'border-gray-400 bg-white hover:bg-gray-50 hover:border-gray-800'
        }`}
      >
        <button
          type="button"
          disabled={disabled}
          onClick={() => !disabled && setIsOpen((prev) => !prev)}
          className={`flex items-center gap-1 pl-4 pr-3 py-1 text-sm font-medium transition-colors disabled:cursor-not-allowed
            ${isOpen || isActive ? 'text-cyan-600' : 'text-[var(--text-secondary)]'}`}
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
              e.preventDefault();
              onClear();
            }}
            className="pr-3 py-1 text-cyan-500 hover:text-red-500 transition-colors"
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
