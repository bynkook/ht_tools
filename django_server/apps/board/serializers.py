import re

from rest_framework import serializers

from .models import Board, BoardPost, BoardPostComment, BoardPostImage
from .permissions import get_board_permission_flags


_MARKDOWN_SYMBOL_RE = re.compile(r'[#>*_`~\[\]\(\)!-]')


class BoardPostImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = BoardPostImage
        fields = ['id', 'image_url', 'alt_text', 'sort_order']

    def get_image_url(self, obj):
        request = self.context.get('request')
        if not obj.image:
            return ''
        if request:
            return request.build_absolute_uri(obj.image.url)
        return obj.image.url


class BoardSerializer(serializers.ModelSerializer):
    permissions = serializers.SerializerMethodField()
    moderator_user_ids = serializers.SerializerMethodField()
    header_image_url = serializers.SerializerMethodField()

    class Meta:
        model = Board
        fields = [
            'id',
            'name',
            'slug',
            'title_display',
            'description',
            'header_image_url',
            'board_style',
            'is_active',
            'allow_create',
            'allow_update',
            'allow_delete',
            'permissions',
            'moderator_user_ids',
        ]

    def get_header_image_url(self, obj):
        request = self.context.get('request')
        if not obj.header_background_image:
            return ''
        if request:
            return request.build_absolute_uri(obj.header_background_image.url)
        return obj.header_background_image.url

    def get_permissions(self, obj):
        request = self.context.get('request')
        user = request.user if request else None
        return get_board_permission_flags(user, obj)

    def get_moderator_user_ids(self, obj):
        request = self.context.get('request')
        if not request or not request.user or not request.user.is_authenticated:
            return []
        flags = get_board_permission_flags(request.user, obj)
        if not flags['is_admin']:
            return []
        return list(obj.moderatorships.values_list('user_id', flat=True))


class BoardPostListSerializer(serializers.ModelSerializer):
    author_username = serializers.CharField(source='author.username', read_only=True)
    preview_image_url = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()
    excerpt = serializers.SerializerMethodField()
    image_count = serializers.SerializerMethodField()
    comment_count = serializers.SerializerMethodField()

    class Meta:
        model = BoardPost
        fields = [
            'id',
            'title',
            'excerpt',
            'author_username',
            'preview_image_url',
            'image_count',
            'comment_count',
            'created_at',
            'updated_at',
            'can_edit',
            'can_delete',
        ]

    def _get_board_permissions(self, obj):
        permissions = self.context.get('board_permissions')
        if permissions is not None:
            return permissions
        request = self.context.get('request')
        user = request.user if request else None
        return get_board_permission_flags(user, obj.board)

    def get_preview_image_url(self, obj):
        preview = obj.preview_image
        if not preview or not preview.image:
            return ''
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(preview.image.url)
        return preview.image.url

    def get_can_edit(self, obj):
        return self._get_board_permissions(obj)['can_update']

    def get_can_delete(self, obj):
        return self._get_board_permissions(obj)['can_delete']

    def get_excerpt(self, obj):
        cleaned = _MARKDOWN_SYMBOL_RE.sub(' ', obj.body_markdown or '')
        cleaned = ' '.join(cleaned.split())
        if len(cleaned) <= 140:
            return cleaned
        return f'{cleaned[:137]}...'

    def get_image_count(self, obj):
        if hasattr(obj, '_prefetched_objects_cache') and 'images' in obj._prefetched_objects_cache:
            return len(obj._prefetched_objects_cache['images'])
        return obj.images.count()

    def get_comment_count(self, obj):
        if hasattr(obj, '_prefetched_objects_cache') and 'comments' in obj._prefetched_objects_cache:
            return len(obj._prefetched_objects_cache['comments'])
        return obj.comments.count()


class BoardPostDetailSerializer(BoardPostListSerializer):
    images = BoardPostImageSerializer(many=True, read_only=True)

    class Meta:
        model = BoardPost
        fields = [
            'id',
            'board',
            'title',
            'excerpt',
            'body_markdown',
            'author_username',
            'preview_image_url',
            'image_count',
            'comment_count',
            'images',
            'created_at',
            'updated_at',
            'can_edit',
            'can_delete',
        ]
        read_only_fields = ['board']


class BoardPostWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = BoardPost
        fields = ['title', 'body_markdown']

    def validate_title(self, value):
        stripped = value.strip()
        if not stripped:
            raise serializers.ValidationError('제목을 입력하세요.')
        return stripped

    def validate_body_markdown(self, value):
        stripped = value.strip()
        if not stripped:
            raise serializers.ValidationError('본문을 입력하세요.')
        return stripped


class BoardPostCommentSerializer(serializers.ModelSerializer):
    author_username = serializers.CharField(source='author.username', read_only=True)
    can_edit = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()

    class Meta:
        model = BoardPostComment
        fields = ['id', 'author_username', 'body', 'created_at', 'updated_at', 'can_edit', 'can_delete']

    def _is_owner_or_admin(self, obj):
        request = self.context.get('request')
        if not request or not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_staff or request.user.is_superuser:
            return True
        return obj.author_id == request.user.id

    def get_can_edit(self, obj):
        return self._is_owner_or_admin(obj)

    def get_can_delete(self, obj):
        return self._is_owner_or_admin(obj)
