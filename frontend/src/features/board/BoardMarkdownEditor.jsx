import React from 'react';
import MDEditor from '@uiw/react-md-editor';
import '@uiw/react-md-editor/markdown-editor.css';
import '@uiw/react-markdown-preview/markdown.css';

import '../../styles/BoardEditor.css';


const previewComponents = {
  a: ({ href, children, ...props }) => (
    <a
      {...props}
      href={href}
      target="_blank"
      rel="noreferrer"
    >
      {children}
    </a>
  ),
};

const BoardMarkdownEditor = ({ value, onChange, placeholder }) => (
  <div data-color-mode="dark" className="board-md-editor overflow-hidden rounded-[20px] bg-transparent">
    <MDEditor
      value={value}
      onChange={(nextValue) => onChange(nextValue ?? '')}
      preview="edit"
      visibleDragbar={false}
      height={280}
      defaultTabEnable={false}
      previewOptions={{
        skipHtml: true,
        components: previewComponents,
      }}
      textareaProps={{
        placeholder,
      }}
    />
  </div>
);

export default BoardMarkdownEditor;