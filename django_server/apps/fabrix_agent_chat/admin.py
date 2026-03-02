from django.contrib import admin
from django.db.models import Count
from .models import ChatSession, ChatMessage

# --- ChatMessage Inline ---
class ChatMessageInline(admin.TabularInline):
    """
    ChatSession 상세 페이지에서 메시지를 함께 표시
    """
    model = ChatMessage
    extra = 0  # 빈 폼 개수 (0으로 설정하여 기존 데이터만 표시)
    fields = ('role', 'content', 'created_at')
    readonly_fields = ('created_at',)
    can_delete = True
    
    def has_add_permission(self, request, obj=None):
        # Admin에서 직접 메시지 추가는 비활성화 (API로만 추가)
        return False


# --- ChatSession Admin ---
@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    """
    대화 세션 관리
    """
    list_display = ('id', 'title', 'user', 'agent_id', 'message_count', 'created_at', 'updated_at')
    list_filter = ('created_at', 'updated_at', 'user')
    search_fields = ('title', 'user__username', 'agent_id')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'created_at'
    
    inlines = [ChatMessageInline]
    
    fieldsets = (
        ('기본 정보', {
            'fields': ('user', 'agent_id', 'title')
        }),
        ('타임스탬프', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)  # 기본적으로 접혀있음
        }),
    )
    
    def message_count(self, obj):
        """메시지 개수 표시 (annotate로 최적화)"""
        # Use annotated count if available, otherwise fallback to query
        return getattr(obj, 'message_count_annotated', obj.messages.count())
    message_count.short_description = '메시지 수'
    message_count.admin_order_field = 'message_count_annotated'
    
    def get_queryset(self, request):
        """쿼리 최적화: user 정보를 함께 가져오고 메시지 수를 annotation으로 계산"""
        qs = super().get_queryset(request)
        return qs.select_related('user').annotate(
            message_count_annotated=Count('messages')
        )


# --- ChatMessage Admin ---
@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    """
    개별 메시지 관리
    """
    list_display = ('id', 'session_title', 'role', 'content_preview', 'created_at')
    list_filter = ('role', 'created_at', 'session__user')
    search_fields = ('content', 'session__title', 'session__user__username')
    readonly_fields = ('created_at',)
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('메시지 정보', {
            'fields': ('session', 'role', 'content')
        }),
        ('타임스탬프', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def session_title(self, obj):
        """세션 제목 표시"""
        return obj.session.title
    session_title.short_description = '대화 세션'
    
    def content_preview(self, obj):
        """내용 미리보기 (50자)"""
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    content_preview.short_description = '내용 미리보기'
    
    def get_queryset(self, request):
        """쿼리 최적화: session과 user 정보를 함께 가져옴"""
        qs = super().get_queryset(request)
        return qs.select_related('session', 'session__user')


# --- Django User Admin 커스터마이징 (선택사항) ---
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

# 기존 User Admin을 언레지스터하고 다시 등록 (커스터마이징)
admin.site.unregister(User)

@admin.register(User)
class CustomUserAdmin(BaseUserAdmin):
    """
    사용자 관리에 채팅 세션 수 추가
    """
    list_display = ('username', 'email', 'first_name', 'last_name', 'session_count', 'is_staff', 'date_joined')
    
    def session_count(self, obj):
        """사용자의 총 세션 수 (annotate로 최적화)"""
        # Use annotated count if available, otherwise fallback to query
        return getattr(obj, 'session_count_annotated', obj.sessions.count())
    session_count.short_description = '대화 세션 수'
    session_count.admin_order_field = 'session_count_annotated'
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(session_count_annotated=Count('sessions'))