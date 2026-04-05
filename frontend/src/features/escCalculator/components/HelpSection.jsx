import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ChevronDown, ChevronRight } from 'lucide-react';

const HELP_CONTENT = `# 「ESC(물가변동)」비용 산출 세부기준

---

□ **금액산정 기준**　　[ ESC = 물가변동대상금액 **[A]** × 잔여기성률 **[B]** × 물가변동률 **[C]** ]

---

**1) '물가변동대상금액[A]'** 이란, 정산내역서상 ESC(물가변동) 산정 대상품목의 자재비[A1]와 노무비[A2]의 합을 말한다.

**2) '잔여기성률[B]'** 이란, 정산금액 대비 월별 기집행된 기성금액을 제외한 잔여 기성금액의 비율을 말한다.

**3) '물가변동률[C]'** 이란, 자재비 물가변동률[C1] 과 노무비 물가변동률[C2] 의 합을 말한다.

**3.1) '자재비 물가변동률[C1]'** 이란, '물가지수 변동률[D1]' 에 '물가변동대상금액[A]' 中 '자재비[A1]' 가 차지하는 비중을 곱하여 산정한다.

> **산출식** : 자재비 물가변동률[C1] = 물가지수 변동률 × ( 자재비 물가변동대상금액[A1] ÷ 총 물가변동대상금액[A] )

- '물가지수 변동률' 이란, '생산자물가지수의 월별 변동률'을 말한다. (해당월의 생산자물가지수 ÷ 전월의 생산자물가지수)
- '생산자물가지수' 란, 한국은행에서 매월 발표하는 지수를 말하며, 품목은 **'공산품'** 을 기준으로 적용한다.

**3.2) '노무비 물가변동률[C2]'** 이란, '노임단가 변동률[D2]' 에 '물가변동대상금액[A]' 중 '노무비[A2]' 가 차지하는 비중을 곱하여 산정한다.

> **산출식** : 노무비 물가변동률[C2] = 노임단가 변동률 × ( 노무비 물가변동대상금액[A2] ÷ 총 물가변동대상금액[A] )

- '노임단가 변동률' 이란, 시중노임단가의 월별 변동률을 말한다. (해당월의 시중노임단가 ÷ 전월의 시중노임단가)
- '시중노임단가' 란, 대한건설협회에서 연 2회 발표하는 지수를 말하며, 직종은 **'일반공사직종'** 을 기준으로 적용한다.

---

※ **기타 용어정의**

- **'기준시점'** 이란, 1차 조정 시에는 계약체결일(우선시공작업지시서발행일), 2차 이상의 조정 시에는 직전 조정일을 말한다.
- **'조정시점'** 이란, 착공일로부터 90일 이상 경과(91번째 날부터 가능)하고 동시에 물가변동률이 3% 이상 증감된 시점을 말한다.
- 선금을 지급한 경우에는 다음 산식에 의거하여 공제금액을 산정하여야 한다.  
  **[ 공제금액 = 물가변동적용대가 × 지수조정률 × 선금금률 ]**
`;

export default function HelpSection() {
  const [open, setOpen] = useState(false);
  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <button
        className="w-full flex items-center gap-2 px-4 py-3 bg-gray-50 hover:bg-gray-100 transition-colors"
        onClick={() => setOpen(v => !v)}
      >
        {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        <span className="text-sm font-semibold text-gray-700">📖 세부기준 도움말</span>
        <span className="ml-auto text-xs text-gray-400">클릭하여 {open ? '닫기' : '펼치기'}</span>
      </button>
      {open && (
        <div className="p-4 prose prose-sm max-w-none text-gray-700 bg-white">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{HELP_CONTENT}</ReactMarkdown>
        </div>
      )}
    </div>
  );
}
