# Potential Issues Fix Summary (2026-02-06)

내부망 FabriX API 연동을 대비하여 식별된 잠재적인 백엔드 및 프론트엔드 연동 문제를 수정하였습니다.

## 1. AI Gateway (FastAPI) 수정
- **파일:** `ai_gateway/routers/chat.py`
- **내용:** `chat_with_file` (파일 분석) 엔드포인트에서 `contents` 필드 전송 방식을 단일 문자열에서 리스트(`List[str]`) 형태로 변경하였습니다.
- **이유:** FabriX OpenAPI 명세서에 따라 파일 업로드 시에도 메시지 내용은 리스트 형태를 유지해야 함을 확인하였습니다.

## 2. 프론트엔드 API 호출 경로 수정
- **파일:** `frontend/src/api/fastapiApi.js`
- **내용:** `getAgents` 함수의 호출 경로에 누락된 라우터 프리픽스 `/agent-messages`를 추가하였습니다.
- **수정 전:** `/agents`
- **수정 후:** `/agent-messages/agents`
- **이유:** FastAPI 서버의 `chat_router`가 `/agent-messages` 프리픽스로 등록되어 있어 발생하던 404 잠재 오류를 해결하였습니다.

## 3. Django 백엔드 프록시 로직 최적화
- **파일:** `django_server/apps/fabrix_agent_chat/views.py`
- **내용:** `AgentListView` 내의 HTTP 요청 파라미터(`limit: 100`) 설정을 변수화하여 중복 코드를 제거하고 가독성을 개선하였습니다.
- **이유:** 코드 유지보수성을 높이고 UI에서 요구하는 에이전트 목록 개수를 안정적으로 반환하기 위함입니다.

## 결과
위 수정을 통해 내부 네트워크 환경에서 실제 FabriX LLM 서버와 통신할 때 발생할 수 있는 데이터 규격 불일치 및 경로 오류를 사전에 차단하였습니다.
