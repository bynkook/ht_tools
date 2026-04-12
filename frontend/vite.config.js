import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'node',
    include: ['src/**/*.test.js', 'src/**/*.test.jsx'],
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
    // React 버전 충돌 방지 - 모든 의존성이 동일한 React 인스턴스를 사용하도록 강제
    dedupe: ['react', 'react-dom'],
  },
  optimizeDeps: {
    include: ['react', 'react-dom'],
    // graphic-walker는 patch-package로 직접 수정된 번들(es.js)을 사용함.
    // Vite의 dep 최적화(캐싱)에서 제외하여 패치 내용이 항상 직접 반영되도록 함.
    // 재시작 시 캐시 무효화로 패치 효과가 사라지는 문제 방지.
    exclude: ['@kanaries/graphic-walker'],
  },
  server: {
    // 사내망 배포(Service Mode)를 위해 0.0.0.0 개방
    host: '0.0.0.0',
    port: 5173,  // 통일된 포트 번호
    
    // [추가됨] 서버 시작 시 브라우저 자동 실행
    open: true, 

    // 개발 편의를 위한 프록시 설정 (선택 사항)
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    }
  }
})