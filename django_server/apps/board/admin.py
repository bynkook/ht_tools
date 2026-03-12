from django.contrib import admin
from django.db.models import Count

from .models import Board, BoardModerator, BoardPost, BoardPostImage


class BoardModeratorInline(admin.TabularInline):
    model = BoardModerator
    extra = 1
    autocomplete_fields = ['user']


class BoardPostImageInline(admin.TabularInline):
    model = BoardPostImage
    extra = 1
    fields = ['image', 'alt_text', 'sort_order', 'created_at']
    readonly_fields = ['created_at']


@admin.register(Board)
class BoardAdmin(admin.ModelAdmin):
    list_display = [
        'title_display',
        'name',
        'slug',
        'is_active',
        'allow_create',
        'allow_update',
        'allow_delete',
        'moderator_count',
        'post_count',
        'updated_at',
    ]
    list_filter = ['is_active', 'allow_create', 'allow_update', 'allow_delete', 'created_at']
    search_fields = ['name', 'slug', 'title_display', 'description']
    readonly_fields = ['slug', 'created_at', 'updated_at']
    inlines = [BoardModeratorInline]

    fieldsets = (
        ('기본 정보', {'fields': ('name', 'slug', 'title_display', 'description', 'header_background_image')}),
        ('정책', {'fields': ('is_active', 'allow_create', 'allow_update', 'allow_delete')}),
        ('타임스탬프', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            moderator_count_annotated=Count('moderatorships', distinct=True),
            post_count_annotated=Count('posts', distinct=True),
        )

    def moderator_count(self, obj):
        return getattr(obj, 'moderator_count_annotated', obj.moderatorships.count())

    def post_count(self, obj):
        return getattr(obj, 'post_count_annotated', obj.posts.count())


@admin.register(BoardModerator)
class BoardModeratorAdmin(admin.ModelAdmin):
    list_display = ['board', 'user', 'created_at']
    list_filter = ['board', 'created_at']
    search_fields = ['board__name', 'board__slug', 'user__username', 'user__email']
    autocomplete_fields = ['board', 'user']


@admin.register(BoardPost)
class BoardPostAdmin(admin.ModelAdmin):
    list_display = ['title', 'board', 'author', 'image_count', 'updated_at']
    list_filter = ['board', 'author', 'created_at', 'updated_at']
    search_fields = ['title', 'body_markdown', 'board__name', 'author__username']
    readonly_fields = ['created_at', 'updated_at']
    autocomplete_fields = ['board', 'author']
    inlines = [BoardPostImageInline]

    fieldsets = (
        ('게시글', {'fields': ('board', 'author', 'title', 'body_markdown')}),
        ('타임스탬프', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('board', 'author').annotate(
            image_count_annotated=Count('images', distinct=True)
        )

    def image_count(self, obj):
        return getattr(obj, 'image_count_annotated', obj.images.count())


@admin.register(BoardPostImage)
class BoardPostImageAdmin(admin.ModelAdmin):
    list_display = ['post', 'sort_order', 'created_at']
    list_filter = ['post__board', 'created_at']
    search_fields = ['post__title', 'post__board__name', 'alt_text']
    autocomplete_fields = ['post']
