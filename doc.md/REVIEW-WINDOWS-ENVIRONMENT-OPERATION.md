# REVIEW: Windows 환경 운영 적합성 점검

작성일: 2026-02-20  
대상 저장소: `django_dev` (`feature/add-general-chat`)

## 1) 점검 목적
현재 프로젝트가 **Windows 환경 운영 전제**에 맞게 구현되어 있는지 확인하고,
운영 안정성을 높이기 위한 보완점을 정리한다.

---

## 2) 종합 결론
- 현재 코드는 **Windows 단일 서버/단일 워커 운영** 기준으로는 전반적으로 적합하다.
- 다만 **장기 상시 운영(서비스 운영 수준)** 기준에서는 몇 가지 개발 편의 설정을 운영형으로 전환할 필요가 있다.

---

## 3) 운영 적합 항목 (확인됨)

### 3.1 Windows 전제와 아키텍처 일치
- 실행/운영 스크립트가 Windows 배치 파일 중심으로 제공됨.
- 단일 프로세스/단일 워커 전제가 문서 및 구현과 일치함.

관련 파일:
- `run_project.bat`
- `service_project.bat`
- `.github/copilot-instructions.md`

### 3.2 SQLite 운영 안정성 고려
- SQLite WAL 기반 운영 구조를 사용.
- DB 연결 옵션(`CONN_MAX_AGE=0`, timeout 등)으로 잠금/동시성 리스크를 완화하도록 구성됨.

관련 파일:
- `django_server/config/settings.py`

### 3.3 FastAPI 외부 HTTP 호출 안정성
- 공유 `httpx.AsyncClient` 사용 원칙이 반영되어 있으며,
  timeout/limits/retry 관련 운영 고려가 존재함.

관련 파일:
- `ai_gateway/main.py`
- `django_server/config/settings.py`
- `.github/copilot-instructions.md`

### 3.4 Windows 인코딩 대응 로깅
- cp949 환경에서 발생 가능한 로깅 인코딩 이슈 대응 코드가 반영됨.

관련 파일:
- `django_server/apps/fabrix_chat/views.py`
- `django_server/apps/fabrix_agent_chat/views.py`

### 3.5 Data Explorer 안전성/운영성
- 예외 체계(세션 만료/타임아웃/동시성 충돌) 정의.
- SQL 검증(SELECT-only + 금지 패턴) 및 projection 기반 실행 경로 유지.
- 운영 환경에서 에러 메시지 sanitize 정책이 문서화/구현되어 있음.

관련 파일:
- `django_server/apps/data_explorer/exceptions.py`
- `django_server/apps/data_explorer/utils.py`
- `django_server/apps/data_explorer/views.py`

### 3.6 마이그레이션 운영 절차
- 백업 후 마이그레이션/검증 흐름이 스크립트화되어 운영 안전성이 높음.

관련 파일:
- `migrate_db.bat`
- `README.md`

---

## 4) 운영 보완 필요 항목 (중요)

### 4.1 `--reload` 운영 비권장
- 개발 편의 기능으로 운영 환경에서는 불필요한 재기동/감시 오버헤드가 발생할 수 있음.
- 운영 스크립트에서는 `--reload` 제거 권장.

### 4.2 Django `runserver`의 운영 한계
- `runserver`는 개발용 서버이므로 장기 운영에는 부적합.
- Windows 서비스(예: NSSM/작업 스케줄러/SCM 연계) 기반으로 WSGI/ASGI 서버 실행 구조 전환 권장.

### 4.3 Rate limiter 확장성 주의
- 현재 limiter는 단일 워커 전제에서는 유효.
- 추후 멀티 워커/멀티 인스턴스 확장 시 상태 공유 전략(예: 외부 저장소 기반) 필요.

관련 파일:
- `ai_gateway/services/rate_limiter.py`

---

## 5) 권장 조치 (우선순위)

### P1 (즉시)
1. 운영 실행 스크립트에서 개발 옵션(`--reload`) 제거.
2. 운영 가이드에 개발 모드/운영 모드 실행 방법을 명확히 분리 기재.

### P2 (단기)
3. Django/FastAPI 프로세스를 Windows 서비스 방식으로 관리하도록 정리
   (자동 재시작, 로그 경로 분리, 종료 시그널 처리 포함).
4. 장애 대응 체크리스트(429, SSE 중단, SQLite lock)를 운영 문서에 간단 SOP로 추가.

### P3 (확장 대비)
5. 멀티 워커 확장 계획 수립 시 limiter 상태 공유 방식과 SQLite 대체 DB 전략(필요 시)을 함께 검토.

---

## 6) 최종 판단
현 상태는 **사내 Windows 기반 단일 운영 환경**에 충분히 적합하다.  
다만 **운영 성숙도 향상**을 위해서는 개발 편의 설정 제거, 서비스 실행 체계 고도화,
확장 시나리오 대비(리미터/DB) 항목을 순차 반영하는 것이 바람직하다.
