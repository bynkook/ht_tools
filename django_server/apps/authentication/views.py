import logging
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from rest_framework import status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.authtoken.models import Token
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, logout as auth_logout

logger = logging.getLogger(__name__)
ALLOWED_SIGNUP_EMAIL_DOMAIN = '@samsung.com'


class SignUpView(APIView):
    """회원가입 API"""
    authentication_classes = []  # 토큰 발급 엔드포인트: 세션 인증/CSRF 검증 불필요
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        email = request.data.get('email')
        auth_key = request.data.get('auth_key')
        recovery_pin = request.data.get('recovery_pin')

        if not all([username, password, email, auth_key, recovery_pin]):
            return Response({'error': 'All fields are required.'}, status=status.HTTP_400_BAD_REQUEST)

        email_normalized = str(email).strip().lower()

        try:
            validate_email(email_normalized)
        except ValidationError:
            return Response({'error': 'Invalid email format.'}, status=status.HTTP_400_BAD_REQUEST)

        if not email_normalized.endswith(ALLOWED_SIGNUP_EMAIL_DOMAIN):
            return Response({'error': 'Only @samsung.com email addresses are allowed.'}, status=status.HTTP_400_BAD_REQUEST)

        # Admin Key 검증
        expected_key = getattr(settings, 'ADMIN_SIGNUP_KEY', '')
        
        # 타입 통일 및 공백 제거 후 비교
        received_key = str(auth_key).strip() if auth_key else ''
        expected_key_str = str(expected_key).strip()
        
        # 개발 환경에서 디버그 로그 출력
        if settings.DEBUG:
            logger.debug(f"[Signup Debug] Auth Key Match: {received_key == expected_key_str}")
        
        if received_key != expected_key_str:
            return Response({'error': 'Invalid Auth Key.'}, status=status.HTTP_403_FORBIDDEN)

        # 사용자 중복 검증
        if User.objects.filter(username=username).exists():
            return Response({'error': 'Username already exists.'}, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(email__iexact=email_normalized).exists():
            return Response({'error': 'Email already exists.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # 트랜잭션으로 원자성 보장
            with transaction.atomic():
                user = User.objects.create_user(username=username, email=email_normalized, password=password)
                user.is_active = True
                user.save()
                
                # UserProfile 생성 및 PIN 저장
                from .models import UserProfile
                UserProfile.objects.create(user=user, recovery_pin=recovery_pin)

                # 새 사용자이므로 토큰 생성
                token = Token.objects.create(user=user)
            
            logger.info(f"New user created: {username}")
            return Response({
                'message': 'Signup successful.',
                'token': token.key,
                'user_id': user.pk,
                'username': user.username,
                'email': user.email
            }, status=status.HTTP_201_CREATED)
        except Exception as e:
            logger.error(f"Signup failed for {username}: {e}", exc_info=True)
            return Response({'error': f'Signup failed: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class LoginView(APIView):
    """로그인 API"""
    authentication_classes = []  # 토큰 발급 엔드포인트: 세션 인증/CSRF 검증 불필요
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        
        logger.info(f"[Login Request] Username: '{username}'")
        
        # 입력값 검증
        if not username or not password:
            return Response(
                {'error': 'Username and password are required.'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # 디버그: 사용자 존재 여부 확인
        if settings.DEBUG:
            try:
                user_exists = User.objects.filter(username=username).exists()
                logger.debug(f"[Login Debug] Username '{username}' exists: {user_exists}")
                if user_exists:
                    user_obj = User.objects.get(username=username)
                    logger.debug(f"[Login Debug] User details - Active: {user_obj.is_active}")
            except Exception as e:
                logger.debug(f"[Login Debug] Error checking user: {e}")
        
        user = authenticate(username=username, password=password)
        
        if user:
            # 계정 활성화 상태 확인
            if not user.is_active:
                logger.warning(f"[Login] User '{username}' is not active")
                return Response(
                    {'error': 'Account is disabled.'}, 
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Token 인증 사용
            token, created = Token.objects.get_or_create(user=user)
            logger.info(f"[Login Success] User '{username}' logged in successfully")
            
            return Response({
                'token': token.key,
                'user_id': user.pk,
                'username': user.username,
                'email': user.email,
                'is_staff': user.is_staff,
            })
        
        logger.warning(f"[Login Failed] Authentication failed for username '{username}'")
        return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)


class LogoutView(APIView):
    """로그아웃 API"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            # DRF Token 삭제 → 재로그인 강제
            request.user.auth_token.delete()
        except Token.DoesNotExist:
            pass  # 이미 삭제된 토큰은 무시

        # Django 세션 로그아웃 (Admin 패널 사용 등으로 세션이 생긴 경우 정리)
        auth_logout(request)

        logger.info(f"[Logout] User '{request.user.username}' logged out successfully")
        return Response({'message': 'Logged out successfully'}, status=status.HTTP_200_OK)


class UserProfileView(APIView):
    """사용자 프로필 조회 및 수정 API"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        # UserProfile이 없는 기존 사용자를 위해 get_or_create 사용
        from .models import UserProfile
        profile, _ = UserProfile.objects.get_or_create(user=user)
        
        return Response({
            'user_id': user.id,
            'username': user.username,
            'email': user.email,
            'is_staff': user.is_staff,
            'date_joined': user.date_joined,
            'has_recovery_pin': bool(profile.recovery_pin),
        })
        
    def patch(self, request):
        user = request.user
        new_password = request.data.get('new_password')
        new_pin = request.data.get('new_pin')
        
        if not new_password and not new_pin:
            return Response({'error': 'No data provided to update.'}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            with transaction.atomic():
                if new_password:
                    user.set_password(new_password)
                    user.save()
                    
                if new_pin:
                    from .models import UserProfile
                    profile, _ = UserProfile.objects.get_or_create(user=user)
                    profile.recovery_pin = new_pin
                    profile.save()
                    
            return Response({'message': 'Profile updated successfully.'}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Profile update failed for {user.username}: {e}", exc_info=True)
            return Response({'error': 'Failed to update profile.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class PasswordResetView(APIView):
    """비밀번호 초기화 API (로그인 전)"""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        username = request.data.get('username')
        recovery_pin = request.data.get('recovery_pin')
        new_password = request.data.get('new_password')
        
        if not all([username, recovery_pin, new_password]):
            return Response({'error': 'All fields are required.'}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            user = User.objects.get(username=username)
            from .models import UserProfile
            profile = UserProfile.objects.get(user=user)
            
            if not profile.recovery_pin or profile.recovery_pin != recovery_pin:
                return Response({'error': 'Invalid recovery PIN.'}, status=status.HTTP_403_FORBIDDEN)
                
            user.set_password(new_password)
            user.save()
            
            logger.info(f"Password reset successful for user: {username}")
            return Response({'message': 'Password reset successful.'}, status=status.HTTP_200_OK)
            
        except User.DoesNotExist:
            return Response({'error': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)
        except UserProfile.DoesNotExist:
            return Response({'error': 'Recovery PIN not set for this user.'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Password reset failed for {username}: {e}", exc_info=True)
            return Response({'error': 'Failed to reset password.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
