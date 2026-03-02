import axios from 'axios';

// --- Dynamic Host Configuration ---
// 배포 시 localhost가 아닌 실제 접속 IP(window.location.hostname)를 사용합니다.
const getBaseUrl = (port) => {
  const protocol = window.location.protocol; // 'http:'
  const hostname = window.location.hostname; // 'localhost' or '192.168.x.x'
  return `${protocol}//${hostname}:${port}`;
};

// 1. Django Client (Port 8000) - 데이터 및 인증 관리
export const djangoClient = axios.create({
  baseURL: getBaseUrl(8000),
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,
});

// [수정] localStorage -> sessionStorage로 변경
djangoClient.interceptors.request.use(
  (config) => {
    const token = sessionStorage.getItem('authToken'); 
    if (token) {
      config.headers['Authorization'] = `Token ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// 2. FastAPI Client (Port 8001) - AI 스트리밍 및 프록시
export const fastApiClient = axios.create({
  baseURL: getBaseUrl(8001),
  headers: {
    'Content-Type': 'application/json',
  },
});

// FastAPI 요청에도 Django 토큰 포함 (Security)
fastApiClient.interceptors.request.use(
  (config) => {
    const token = sessionStorage.getItem('authToken'); 
    if (token) {
      config.headers['Authorization'] = `Token ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// --- Helper for SSE URL ---
// EventSource는 axios를 쓰지 않으므로 URL 생성 헬퍼가 필요함
export const getFastApiUrl = (endpoint) => {
  const baseUrl = getBaseUrl(8001);
  return `${baseUrl}${endpoint}`;
};