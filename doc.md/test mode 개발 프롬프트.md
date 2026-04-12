# fabrix chat 의 generic mcp host 로의 전환 이후에 test mode 를 구현

## AGENTS.md 

You are an expert full-stack architect and MCP (Model Context Protocol) specialist.

You must follow the official MCP specification strictly (latest version 2025-11-25):
https://modelcontextprotocol.io/specification/2025-11-25

and all official SDK patterns.

### Reference Projects & Source Code (반드시 공부하고 참조하라)

아래 프로젝트들의 소스코드와 아키텍처를 철저히 분석해서 설계에 반영:

	1. mark3labs/mcphost (https://github.com/mark3labs/mcphost)
		→ 가장 유사한 universal MCP Host (CLI 기반). Go로 구현되었으나 아키텍처가 완벽한 참고 대상.
		- Multiple MCP 서버 관리 (stdio + streamable HTTP)
		- Debug mode + Hooks (PreToolUse, PostToolUse, UserPromptSubmit) → MCP 쿼리/응답 상세 로깅
		- Non-interactive / Script mode → Test Mode simulation에 직접 참조
		- Config 파일(.mcphost.yml)과 env var 처리 패턴

	2. OpenAgentPlatform/Dive (https://github.com/OpenAgentPlatform/Dive)
		→ Desktop MCP Host with 실제 Chat UI. Electron/Tauri + TypeScript.
		- Chat interface + system messages/custom instructions
		- Granular tool control, stdio/SSE 지원
		- Local LLM (Ollama) 지원 → offline Test Mode 참고

	3. Official Quickstart Resources (https://github.com/modelcontextprotocol/quickstart-resources)
		→ Python/TS client 예제 (mcp-client-python, mcp-client-typescript)

	4. MCP Inspector (https://github.com/modelcontextprotocol/inspector)
		→ MCP 서버 테스트/디버깅용 React UI → Test Mode에서 상세 system message 출력 스타일 참고

	5. Official SDKs (강력 추천 사용):
		- Python SDK: https://github.com/modelcontextprotocol/python-sdk (ClientSession, transport 등 가장 완성도 높음)
		- TypeScript SDK: https://github.com/modelcontextprotocol/typescript-sdk

Test Mode 구현 시 반드시 위 프로젝트들의 debug/logging/hooks/non-interactive 패턴을 참고해서 구현하라.





## test mode 개발 계획서 작성용 프롬프트

### Project Overview

나는 간단하고 범용적인 MCP Host 채팅 앱을 만들고 있다.
- Host는 외부 LLM (OpenAI, Anthropic, Groq 등) API를 호출해서 채팅 + tool-calling을 담당
- 여러 MCP Server (local/remote)를 동시에 연결해서 tools/resources/prompts 사용
- MCP 표준 흐름 (capability discovery → tool list → call 등)을 최대한 준수

### Development Environment Constraint

개발 환경은 보안 때문에 완전 오프라인이라 외부 LLM API 호출이 불가능하다.
따라서 Test Mode가 반드시 필요하며, MCP 부분만 완벽히 테스트할 수 있어야 한다.

#### Test Mode Requirements (최우선)

1. Toggle
	secrets.toml 또는 .env 파일에 MCP_TEST_MODE=true 또는 환경변수로 ON/OFF 가능

2. Chat UI에서의 동작
	사용자 채팅은 정상 작동
	모든 MCP 활동은 System Message로 채팅창 상단에 표시 (회색 배경 + [MCP-TEST] 또는 [SYSTEM] prefix)
	표시 내용 (순서대로):
		- 각 MCP Server 연결 상태 (stdio / https 성공/실패)
		- Capability discovery 결과 (tools/resources/prompts 목록)
		- 사용자 메시지 도착 시:
			- “Simulating LLM tool decision...”
			- 실제 MCP 서버로 보낸 JSON-RPC 요청 (전체 payload 또는 method+params)
			- MCP 서버로부터 받은 응답 (전체 또는 summary + raw)
			- 최종으로 LLM에 전달될 aggregated context (실제 LLM 호출은 안 함)

3. Simulation Logic
	- Test Mode에서는 절대 외부 LLM API 호출 금지
	- 간단한 deterministic mock (keyword matching 또는 미리 정의된 mock scenario JSON 파일)으로 tool 선택 및 호출 시뮬레이션

4. MCP 표준 완전 준수
	-JSON-RPC 2.0 메시지 형식, Initialize, ListCapabilities, CallTool 등 공식 메서드 사용
	-stdio + Streamable HTTP transport 모두 지원
	-Client capability negotiation 및 session 관리

### Deliverables

아래 정확한 섹션 순서로 완전한 설계 문서를 작성해 주세요:

1. High-level Architecture Diagram (Mermaid 또는 ASCII) – Host ↔ MCP Client(s) ↔ Server(s) + Test Mode bypass 표시

2. Config & Test Mode Flag Design

3. Normal Mode vs Test Mode Core Flow (step-by-step 비교 테이블)

4. Test Mode 구현 상세 계획
	- 어디에 로직을 넣을지 (middleware? 별도 TestHost class? decorator?)
	- LLM API 호출 interception 방법
	- Chat UI에 system message 주입 방법 (React/Vue/Svelte/Tauri/Electron 모두 고려, framework-agnostic interface 제공)
	- mark3labs/mcphost의 hooks와 Dive의 system message 패턴 참고 설명

5. 추천 Code Structure (폴더 레이아웃 + 핵심 파일/클래스)
	Python 또는 TypeScript 중 더 적합한 언어 하나를 선택해서 제안 (이유 설명)
	
6. Sample Code Snippets (선택한 언어로 핵심 모듈 3~4개 제공 – Test Mode 핵심 포함)

7. Best Practices & Edge Cases (MCP spec 준수 + 보안 + maintainability)

8. 시스템 메시지 채팅창 화면 출력 UI/UX design
	- 현재 react 로 구현된 Chat Page 는 시스템 메시지를 대화 영역 중앙에 버블로 출력하고 있음
	→ 이것을 professional coding style logger 출력 스타일로 변경
	- 시스템 메시지 출력 디자인은 test mode, operation mode 모두 동일하게 적용되는 전역(global) 설정이다.

## 추가 지시

- 전체 앱은 “simple universal MCP host”이므로 최대한 간단하게 유지
- Production 코드와 Test Mode 코드를 완전히 분리 (Test Mode ON일 때만 동작)
- 코드에 주석으로 “why this decision was made for Test Mode” 명시
- 공식 SDK를 최대한 활용 (직접 wheel reinvention 금지)


이제 바로 위 섹션 순서대로 완전한 설계 문서를 출력해 주세요. 인사말 없이 바로 시작.

프롬프트 끝