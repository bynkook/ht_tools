import React from 'react';
import { X, HelpCircle } from 'lucide-react';

const CATEGORIES = [
  { name: '장애', desc: '시스템 또는 서비스 이상으로 업무가 중단된 경우' },
  { name: '오류', desc: '기능은 동작하나 결과가 잘못 출력되는 경우' },
  { name: '성능', desc: '응답 지연, 타임아웃 등 성능 관련 이슈' },
  { name: '데이터', desc: '데이터 불일치, 누락, 정합성 문제' },
  { name: '기능개선', desc: '기존 기능의 개선 또는 변경 요청' },
  { name: '신규개발', desc: '현재 미구현된 새 기능 개발 요청' },
  { name: '문의', desc: '시스템 사용법, 정책 등 단순 문의' },
  { name: '배포', desc: '소스 배포 또는 환경 설정 관련 작업' },
  { name: '보안', desc: '보안 취약점, 접근제어 관련 이슈' },
  { name: '인프라', desc: '서버, 네트워크, OS 등 인프라 관련 이슈' },
  { name: '기타', desc: '위 분류에 해당하지 않는 기타 사항' },
];

export default function HelpModal({ onClose }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-lg mx-4 overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 bg-teal-600 text-white">
          <div className="flex items-center gap-2">
            <HelpCircle size={18} />
            <h2 className="font-semibold text-base">유형 분류 기준</h2>
          </div>
          <button
            onClick={onClose}
            className="text-teal-100 hover:text-white transition-colors"
            aria-label="닫기"
          >
            <X size={18} />
          </button>
        </div>

        <div className="px-6 py-4 max-h-[70vh] overflow-y-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-gray-200 text-gray-500">
                <th className="text-left py-2 pr-4 font-medium w-28">유형</th>
                <th className="text-left py-2 font-medium">설명</th>
              </tr>
            </thead>
            <tbody>
              {CATEGORIES.map(({ name, desc }) => (
                <tr key={name} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="py-2 pr-4">
                    <span className="inline-block bg-teal-50 text-teal-700 rounded px-2 py-0.5 text-xs font-semibold">
                      {name}
                    </span>
                  </td>
                  <td className="py-2 text-gray-700">{desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="px-6 py-3 border-t border-gray-100 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-1.5 text-sm bg-teal-600 text-white rounded-lg hover:bg-teal-700 transition-colors"
          >
            닫기
          </button>
        </div>
      </div>
    </div>
  );
}
