"""
Django Management Command: FabriX Agent Chat 샘플 대화 이력 생성

이 명령어는 FabriX Agent Chat 세션/히스토리 UI와 대화 이력 적재 상태를 확인하기 위한
샘플 대화 데이터를 생성합니다.

【주요 기능】
- 지정된 사용자의 FabriX Agent Chat 세션에 샘플 대화 이력 자동 생성
- 최대 12턴의 다양한 주제 대화 (파일 분석, 지식 베이스, RAG 기능 등)
- 세션 목록, 히스토리 렌더링, 이전 대화 맥락 재진입 점검에 활용 가능
"""
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from apps.fabrix_agent_chat.models import ChatSession, ChatMessage


class Command(BaseCommand):
    help = (
        'FabriX Agent Chat 샘플 대화 이력 생성\n'
        '사용 예: python manage.py load_test_agent_chat --username=사용자명 --turns=5'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--username',
            type=str,
            default='admin',
            help='대화 세션을 생성할 사용자 이름 (기본값: admin)'
        )
        parser.add_argument(
            '--turns',
            type=int,
            default=5,
            help='생성할 대화 턴 수 (기본값: 5)'
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='기존 테스트 세션 삭제 후 생성'
        )
        parser.add_argument(
            '--agent-id',
            type=str,
            default='sample-agent-history',
            help='세션에 저장할 agent_id (기본값: sample-agent-history)'
        )

    def handle(self, *args, **options):
        """
        대화 이력 생성 메인 로직
        
        실행 순서:
        1. 사용자 계정 확인
        2. [optional] 기존 테스트 세션 삭제
        3. 새 ChatSession 생성
        4. 샘플 대화 12턴 중 지정된 수만큼 ChatMessage 생성
        5. 웹 UI 접속 URL 출력
        """
        username = options['username']
        turns = options['turns']
        clear = options['clear']
        agent_id = options['agent_id']

        # 사용자 확인
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f'사용자 "{username}"을(를) 찾을 수 없습니다.')

        # 기존 테스트 세션 삭제
        if clear:
            deleted_count, _ = ChatSession.objects.filter(
                user=user,
                title__startswith='[Test]'
            ).delete()
            self.stdout.write(f'기존 테스트 세션 {deleted_count}개 삭제됨')

        # 테스트 세션 생성
        session = ChatSession.objects.create(
            user=user,
            agent_id=agent_id,
            title=f'[Test] Agent 대화 이력 테스트 ({turns}턴)'
        )
        self.stdout.write(f'세션 생성됨: ID={session.id}')

        # 샘플 대화 데이터 (12턴)
        # 주제: 파일 분석 → 데이터 전처리 → RAG 검색 → 지식 베이스 → Agent 기능 → 히스토리 재확인
        # 대화 이력 컨텍스트 기능 검증을 위해 Agent Chat 특성에 맞는 주제와 참조 질문 포함
        sample_conversations = [
            ("data.csv 파일을 분석해줘", 
             "CSV 파일을 분석했습니다. 총 1,000행, 15개 컬럼입니다. 주요 컬럼: id, name, age, salary, department. 일부 Missing 값이 발견되었습니다."),
            ("Missing 값 처리는 어떻게 하나요?", 
             "Missing 값 처리 방법: 1) 삭제 - dropna() 2) 평균값 대체 - fillna(mean) 3) 중앙값 대체 - fillna(median) 4) 전후 값 보간 - interpolate()"),
            ("방금 분석한 데이터의 salary 컬럼 통계 알려줘", 
             "salary 통계: 평균 5,500만원, 중앙값 4,800만원, 최소 2,000만원, 최대 12,000만원, 표준편차 2,300만원. 상위 10%는 8,000만원 이상입니다."),
            ("지식 베이스에서 데이터 전처리 관련 문서 찾아줘", 
             "지식 베이스 검색 완료. 3개 문서 발견: 1) 'Data Preprocessing Guide' (relevance: 0.95) 2) 'ML Pipeline Best Practices' (0.87) 3) 'Feature Engineering' (0.82)"),
            ("첫 번째 문서 요약해줘", 
             "'Data Preprocessing Guide' 요약: 데이터 정제 → Missing 값 처리 → 이상치 제거 → 정규화/표준화 → 범주형 인코딩. 전체 ML 프로젝트의 70% 시간 소요됩니다."),
            ("RAG 기능은 어떻게 작동하나요?", 
             "RAG(Retrieval-Augmented Generation) 동작: 1) 벡터 임베딩으로 문서 인덱싱 2) 질문과 유사도 높은 문서 검색 3) 검색 결과를 LLM에 컨텍스트로 제공 4) 정확한 응답 생성"),
            ("우리 Agent는 어떤 도구를 사용할 수 있나요?", 
             "FabriX Agent 도구: 1) 파일 분석 (CSV, PDF, 이미지) 2) 지식 베이스 검색 (RAG) 3) 코드 실행 (Python) 4) 웹 검색 5) API 호출. 각 도구는 필요 시 자동 선택됩니다."),
            ("파일 첨부는 어떻게 하나요?", 
             "파일 첨부 방법: 1) 입력창 클릭 아이콘 선택 2) 파일 선택 (최대 10MB) 3) 질문과 함께 전송. 지원 형식: PDF, CSV, TXT, PNG, JPG, DOCX 등."),
            ("이전에 말한 salary 통계와 전처리 가이드를 결합해서 설명해줘", 
             "salary 데이터 전처리 예시: 1) Missing 값 14건 → 평균값(5,500만원) 대체 2) 이상치 3건(20억 이상) 제거 3) 로그 변환으로 정규 분포 변환 4) MinMaxScaler로 [0,1] 정규화"),
            ("오늘 대화 내용 전체 요약해줘", 
             "오늘 대화 요약: 1) CSV 파일 분석(1,000행) 2) Missing 값 처리 방법 3) salary 통계(평균 5,500만원) 4) RAG/지식 베이스 검색 5) Agent 도구 소개. 데이터 분석 전체 워크플로우를 다뤘습니다."),
            ("고마워요!", 
             "천만에요! Agent 기능을 계속 탐색해보세요. 파일 분석이나 지식 검색이 필요하면 언제든 도움 드리겠습니다! 🤖"),
            ("마지막으로, 오늘 분석 흐름을 한 번만 더 요약해줘.", 
             "오늘 분석 흐름 요약: 1) CSV 구조 확인 2) Missing 값 처리 3) salary 통계 검토 4) 지식 베이스/RAG 설명 5) Agent 도구 활용 방식 확인입니다."),
        ]

        # 지정된 턴 수만큼 대화 생성 (최대 12턴)
        # 각 턴은 user 메시지 + assistant 메시지 쌍으로 구성
        for i in range(min(turns, len(sample_conversations))):
            user_content, assistant_content = sample_conversations[i]
            
            ChatMessage.objects.create(
                session=session,
                role='user',
                content=user_content
            )
            ChatMessage.objects.create(
                session=session,
                role='assistant',
                content=assistant_content
            )
            self.stdout.write(f'  턴 {i+1}: "{user_content[:30]}..."')

        self.stdout.write(self.style.SUCCESS(
            f'\n✅ 테스트 대화 생성 완료!\n'
             f'   세션 ID: {session.id}\n'
             f'   사용자: {username}\n'
             f'   agent_id: {agent_id}\n'
             f'   대화 턴: {min(turns, len(sample_conversations))}턴 '
             f'(총 {min(turns, len(sample_conversations)) * 2}개 메시지)\n'
             f'\n'
             f'【다음 단계】\n'
             f'1. 서버 시작: run_project.bat 실행\n'
             f'2. 브라우저 접속: http://localhost:5173/agent-chat?session_id={session.id}\n'
             f'3. 필요 시 사이드바에서 실제 Agent를 다시 선택\n'
             f'4. 후속 질문을 보내고 이전 대화 맥락이 자연스럽게 이어지는지 확인'
        ))
