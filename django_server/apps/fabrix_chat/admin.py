from django.contrib import admin
from django.db.models import Count
from .models import ChatSession, ChatMessage


class ChatMessageInline(admin.TabularInline):
    """ChatSession 상세 페이지에서 메시지를 함께 표시"""
    model = ChatMessage
    extra = 0
    fields = ('role', 'content', 'created_at')
    readonly_fields = ('created_at',)
    can_delete = True
    
    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    """FabriX Chat 대화 세션 관리"""
    list_display = ('id', 'title', 'user', 'model_id', 'message_count', 'created_at', 'updated_at')
    list_filter = ('created_at', 'updated_at', 'user')
    search_fields = ('title', 'user__username', 'model_id')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'created_at'
    
    inlines = [ChatMessageInline]
    
    fieldsets = (
        ('기본 정보', {
            'fields': ('user', 'model_id', 'title')
        }),
        ('타임스탬프', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def message_count(self, obj):
        """메시지 개수 표시"""
        return getattr(obj, 'message_count_annotated', obj.messages.count())
    message_count.short_description = '메시지 수'
    message_count.admin_order_field = 'message_count_annotated'
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('user').annotate(
            message_count_annotated=Count('messages')
        )


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    """FabriX Chat 개별 메시지 관리"""
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
        return obj.session.title
    session_title.short_description = '대화 세션'
    
    def content_preview(self, obj):
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    content_preview.short_description = '내용 미리보기'
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('session', 'session__user')
