import React from 'react';

export default function ActiveUsersBadge({ activeUsers }) {
  if (!activeUsers?.length) {
    return (
      <div className="flex items-center gap-2 text-xs text-gray-400">
        <span>작업자 없음</span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 min-w-0">
      <span className="text-xs font-medium text-gray-500 shrink-0">작업 중</span>
      <div className="flex items-center gap-1.5 min-w-0 overflow-hidden">
        {activeUsers.map((user) => (
          <span
            key={user.username}
            className="px-2 py-0.5 rounded-full bg-sky-50 text-sky-700 border border-sky-200 text-xs truncate max-w-28"
            title={user.display_name || user.username}
          >
            {user.display_name || user.username}
          </span>
        ))}
      </div>
    </div>
  );
}
