"""
Django Management Command: FabriX Chat 샘플 대화 이력 생성

이 명령어는 FabriX Chat 세션/히스토리 UI와 대화 이력 적재 상태를 확인하기 위한
샘플 대화 데이터를 생성합니다.

【주요 기능】
- 지정된 사용자의 FabriX Chat 세션에 샘플 대화 이력 자동 생성
- 최대 12턴의 다양한 주제 대화 (날씨, Python, React, Django/FastAPI 등)
- 세션 목록, 히스토리 렌더링, 이전 대화 맥락 재진입 점검에 활용 가능
"""
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.conf import settings
from apps.fabrix_chat.models import ChatSession, ChatMessage


class Command(BaseCommand):
    help = (
        'FabriX Chat 샘플 대화 이력 생성\n'
        '사용 예: python manage.py load_test_chat --username=사용자명 --turns=5'
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
            '--model-id',
            type=str,
            default='',
            help='세션에 저장할 model_id (미지정 시 secrets.toml의 기본 FabriX model_id 사용)'
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
        model_id = options['model_id'] or getattr(settings, 'FABRIX_CHAT_API_CONFIG', {}).get('model_id') or 'sample-history-model'

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
            model_id=model_id,
            title=f'[Test] 대화 이력 테스트 ({turns}턴)'
        )
        self.stdout.write(f'세션 생성됨: ID={session.id}')

        # 샘플 대화 데이터 (12턴)
        # 주제: 날씨 → Python → React 19 → Django/FastAPI → 요약/히스토리 재확인
        # 대화 이력 컨텍스트 기능 검증을 위해 다양한 주제와 참조 질문 포함
        sample_conversations = [
            ("안녕하세요, 오늘 날씨가 어떤가요?", 
             "안녕하세요! 오늘 서울 날씨는 맑고 기온은 15도입니다. 야외 활동하기 좋은 날씨네요."),
            ("그렇군요. Python에서 리스트 컴프리헨션 사용법 알려주세요.", 
             "리스트 컴프리헨션은 [표현식 for 항목 in 반복가능객체] 형식입니다. 예: [x**2 for x in range(10)]"),
            ("방금 설명한 예제를 좀 더 자세히 설명해줄 수 있나요?", 
             "물론이죠! [x**2 for x in range(10)]는 0부터 9까지 각 숫자의 제곱을 리스트로 만듭니다. 결과는 [0, 1, 4, 9, 16, 25, 36, 49, 64, 81]입니다."),
            ("필터링도 추가할 수 있나요?", 
             "네! if 조건을 추가할 수 있습니다. 예: [x**2 for x in range(10) if x % 2 == 0]은 짝수만 제곱합니다."),
            ("지금까지 설명한 내용을 요약해주세요.", 
             "요약: 1) 날씨 - 서울 맑음 15도 2) 리스트 컴프리헨션 기본 문법 3) range(10) 제곱 예제 4) if 조건 필터링. 추가 질문 있으시면 말씀해주세요!"),
            ("React 19의 새로운 기능은 뭐가 있나요?", 
             "React 19의 주요 기능: 1) Actions - 폼 처리 간소화 2) use() 훅 - Promise/Context 직접 사용 3) Document Metadata 지원 4) Asset Loading 최적화 등이 있습니다."),
            ("use() 훅에 대해 더 자세히 알려주세요.", 
             "use() 훅은 컴포넌트 내에서 Promise나 Context를 직접 읽을 수 있게 해줍니다. Suspense와 함께 사용하면 데이터 로딩 상태를 선언적으로 처리할 수 있습니다."),
            ("Django와 FastAPI 차이점은?", 
             "Django는 풀스택 동기 프레임워크(ORM, Admin 포함), FastAPI는 비동기 API 특화 프레임워크입니다. Django는 전통적 웹앱, FastAPI는 고성능 API에 적합합니다."),
            ("우리 프로젝트는 왜 둘 다 쓰나요?", 
             "하이브리드 아키텍처입니다. Django는 사용자 인증/DB 관리, FastAPI는 SSE 스트리밍/외부 API 프록시 담당. 각 프레임워크의 장점을 활용합니다."),
            ("오늘 대화 내용 전체 요약해줘.", 
             "오늘 대화 요약: 1) 날씨 정보 2) Python 리스트 컴프리헨션 3) React 19 신기능(use 훅) 4) Django vs FastAPI 비교. 다양한 기술 주제를 다뤘습니다!"),
            ("고마워요!", 
             "천만에요! 언제든 질문해주세요. 좋은 하루 보내세요! 🙂"),
            ("마지막으로 하나만 더, 오늘 대화 핵심만 짧게 다시 정리해줘.", 
             "오늘 대화 핵심: 1) 날씨 정보 2) Python 리스트 컴프리헨션 3) React 19 use() 훅 4) Django와 FastAPI 역할 분담입니다."),
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
             f'   model_id: {model_id}\n'
             f'   대화 턴: {min(turns, len(sample_conversations))}턴 '
             f'(총 {min(turns, len(sample_conversations)) * 2}개 메시지)\n'
             f'\n'
             f'【다음 단계】\n'
             f'1. 서버 시작: run_project.bat 실행\n'
             f'2. 브라우저 접속: http://localhost:5173/chat?session_id={session.id}\n'
             f'3. 필요 시 사이드바에서 실제 FabriX 모델을 선택\n'
             f'4. 후속 질문을 보내고 이전 대화 맥락이 자연스럽게 이어지는지 확인'
        ))
