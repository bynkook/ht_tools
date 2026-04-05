# Offline Safe Ops Checklist (Chat/Agent)

본 문서는 Windows 단일 워커 + 로컬 개발 환경에서
안전하게 운영 개선(1,2,3,4)을 적용하기 위한 체크리스트입니다.

## 최종 권고 반영 상태

- 적용 유지: 1, 3, 4
- 적용 유지하되 확장 금지: 2 (현재 수준에서 운영 검증만 수행)
- 취소 대상: 없음
- 단, 2번의 추가 강화(더 엄격한 제한/추가 계층 제한)는 온라인 재검증 전 보류


## 0) 적용 원칙 (필수)

- 프론트엔드가 기대하는 SSE/429 응답 계약은 변경 금지
- 대규모 리팩터링 금지 (최소 수정)
- 변경 예산 초과 시 즉시 중단
  - 파일 2개 초과 또는 코드 80 LOC 초과 예상 시 중단

---


## 1) 응답 프로토콜 불변 원칙 고정


### 1-1. 불변 계약 (Do Not Change)

- SSE Content-Type: `text/event-stream`
- SSE payload envelope: `data: {...}\n\n`
- CHUNK 누적 키 호환 유지
  - `event_status` / `eventStatus`
  - `finish_reason` / `finishReason`
- 429 에러 구조 유지
  - `detail.message`
  - `detail.retry_after`
  - `Retry-After`, `X-RateLimit-*` 헤더


### 1-2. 오프라인 실행 명령

1. `run_project.bat` 실행
2. FabriX upstream 연결이 가능한 개발환경에서 브라우저 `/chat`, `/agent-chat` 각각 3회 송신 + 1회 Stop
3. upstream 연결이 불가한 개발환경이라면 송신 검증은 건너뛰고 페이지 로드/네비게이션/히스토리 진입까지만 확인


### 1-3. 통과 기준

- 스트리밍 시작/종료가 정상
- Stop 후 로딩 해제 정상
- 429/에러 배너 문구 파싱이 깨지지 않음
- 응답 저장 중복/유실 재현 없음


### 1-4. 온라인 전환 후 재검증

- 실제 FabriX의 `Retry-After` 반영 정확도
- 실제 upstream 429/5xx에서 프론트 안내 문구 정합성

---


## 2) httpx 연결풀 상한 보수적 적용


### 2-1. 적용 내용

- FastAPI shared AsyncClient에 limits/timeout 명시
- 기본값은 보수적으로 유지
  - max connections: 100
  - keepalive connections: 20
  - keepalive expiry: 30s
  - timeout(connect/read/write/pool): 10/60/60/5s
- 2번 항목은 **동결(Frozen Scope)**
  - 허용: 운영 검증, 로그 관찰, 문서 보완
  - 금지: 제한값 추가 강화, 새 제한 계층 도입, 스트리밍 경로 정책 변경


### 2-2. 오프라인 실행 명령

1. `run_project.bat`
2. FabriX upstream 연결이 가능한 개발환경에서 `/chat`, `/agent-chat` 탭 2~3개에서 연속 송신
3. `http://127.0.0.1:8001/chat-messages/rate-limit-status`
4. `http://127.0.0.1:8001/agent-messages/rate-limit-status`


### 2-3. 통과 기준

- 연결/타임아웃 오류 로그 급증 없음
- 스트림 시작 지연이 기존 대비 악화되지 않음


### 2-4. 온라인 전환 후 재검증

- 실트래픽에서 pool timeout 발생률
- 동시 사용자 증가 시 지연/오류율

---


## 3) 운영 복구체계 + 런북 최소강화


### 3-1. 복구 시나리오

- FastAPI 프로세스 다운
- Django 프로세스 다운
- 포트 충돌(8000/8001/5173)


### 3-2. 오프라인 실행 명령

1. 실행 중 FastAPI 창 강제 종료
2. FastAPI만 재시작
3. `/chat`, `/agent-chat` 재접속 및 1회 송신
4. Django도 동일 절차 반복


### 3-3. 통과 기준

- 런북 절차만으로 5~10분 내 복구 가능
- 복구 후 기본 송수신 정상


### 3-4. 온라인 전환 후 재검증

- 사내망 클라이언트 재접속 성공률
- 운영자 교대 시 런북 재현성

---


## 4) 지표 임계치·알람 후행적용


### 4-1. 지표

- `429_rate` (분당 429 비율)
- `queue_depth` / `queue_depth_peak`
- `p95_latency`
- `upstream_5xx`


### 4-2. 임계치(초안)

- Warning
  - `429_rate >= 5%` (3분 연속)
  - `queue_depth_peak >= 5`
  - `p95_latency >= 8s`
- Critical
  - `429_rate >= 15%` (3분 연속)
  - `queue_depth_peak >= 10`
  - `p95_latency >= 15s`
  - `upstream_5xx >= 5/min`


### 4-3. 오프라인 실행

- 개발 환경에서 `rate-limit-status` 응답 값 관찰
- 임계치 초과 시 운영 액션 수행 여부 점검


### 4-4. 통과 기준

- Warning/Critical 기준 + 대응 액션(누가/무엇을) 문서화 완료


### 4-5. 온라인 전환 후 재검증

- 실제 트래픽 분포 기반 임계치 재조정
- 오탐/미탐 비율 확인 후 튜닝

---


## 변경 중단 규칙 (즉시)

- 프론트 이벤트 흐름(onopen/onmessage/onclose/stop) 변경 필요 시 중단
- 429 응답 바디/헤더 포맷 변경 필요 시 중단
- 변경 예산(파일 수/LOC) 초과 시 중단
