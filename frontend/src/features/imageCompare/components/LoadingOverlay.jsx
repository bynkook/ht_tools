import React from 'react';
import { Loader2 } from 'lucide-react';

const LoadingOverlay = ({ message = "이미지를 처리하고 있습니다..." }) => {
  return (
    <div className="absolute inset-0 bg-white/90 backdrop-blur-sm flex items-center justify-center z-50 rounded-lg">
      <div className="text-center">
        <Loader2 className="animate-spin mx-auto mb-4 text-blue-500" size={40} />
        <p className="text-sm font-medium text-[var(--text-primary)] mb-2">
          {message}
        </p>
        <p className="text-xs text-gray-500 max-w-xs">
          대용량 파일의 경우 최대 30초가 소요될 수 있습니다.
        </p>
      </div>
    </div>
  );
};

export default LoadingOverlay;
