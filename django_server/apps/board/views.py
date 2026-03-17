import json
import os

from django.db import transaction
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Board, BoardPost, BoardPostComment, BoardPostImage
from .permissions import get_board_permission_flags
from .serializers import BoardPostCommentSerializer, BoardPostDetailSerializer, BoardPostListSerializer, BoardPostWriteSerializer, BoardSerializer


ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
MAX_POST_IMAGES = 6
MAX_IMAGE_BYTES = 10 * 1024 * 1024


def _board_queryset():
    return Board.objects.prefetch_related('moderatorships')


def _post_queryset():
    image_prefetch = Prefetch('images', queryset=BoardPostImage.objects.order_by('sort_order', 'id'))
    return BoardPost.objects.select_related('board', 'author').prefetch_related(image_prefetch)


def _parse_retained_image_ids(raw_value):
    if raw_value in (None, '', []):
        return set()
    if isinstance(raw_value, list):
        return {int(value) for value in raw_value}
    if isinstance(raw_value, str):
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError:
            raise ValueError('retained_image_ids 형식이 올바르지 않습니다.')
        if not isinstance(parsed, list):
            raise ValueError('retained_image_ids 형식이 올바르지 않습니다.')
        return {int(value) for value in parsed}
    raise ValueError('retained_image_ids 형식이 올바르지 않습니다.')


def _validate_uploaded_images(images, existing_count=0):
    if existing_count + len(images) > MAX_POST_IMAGES:
        raise ValueError(f'이미지는 최대 {MAX_POST_IMAGES}개까지 업로드할 수 있습니다.')

    for image in images:
        extension = os.path.splitext(image.name)[1].lower()
        if extension not in ALLOWED_IMAGE_EXTENSIONS:
            raise ValueError('jpg, jpeg, png, gif, webp 형식만 업로드할 수 있습니다.')
        if image.size > MAX_IMAGE_BYTES:
            raise ValueError('개별 이미지 크기는 10MB를 초과할 수 없습니다.')


def _sync_post_images(post, retained_image_ids, new_images):
    existing_images = list(post.images.all())
    existing_ids = {image.id for image in existing_images}

    invalid_retained_ids = retained_image_ids - existing_ids
    if invalid_retained_ids:
        raise ValueError('유효하지 않은 이미지 참조가 포함되어 있습니다.')

    _validate_uploaded_images(new_images, existing_count=len(retained_image_ids))

    for image in existing_images:
        if image.id not in retained_image_ids:
            image.delete()

    sort_order = post.images.count()
    for image in new_images:
        BoardPostImage.objects.create(post=post, image=image, sort_order=sort_order)
        sort_order += 1


def _require_permission(user, board, permission_key):
    flags = get_board_permission_flags(user, board)
    if not flags.get(permission_key):
        return None, Response({'error': '권한이 없습니다.'}, status=status.HTTP_403_FORBIDDEN)
    return flags, None


class BoardListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        queryset = _board_queryset()
        if not (request.user.is_staff or request.user.is_superuser):
            queryset = queryset.filter(is_active=True)
        serializer = BoardSerializer(queryset, many=True, context={'request': request})
        return Response({'boards': serializer.data}, status=status.HTTP_200_OK)


class BoardDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, slug):
        board = get_object_or_404(_board_queryset(), slug=slug)
        if not board.is_active and not (request.user.is_staff or request.user.is_superuser):
            return Response({'error': '비활성화된 게시판입니다.'}, status=status.HTTP_404_NOT_FOUND)

        posts = _post_queryset().filter(board=board)
        board_permissions = get_board_permission_flags(request.user, board)
        board_serializer = BoardSerializer(board, context={'request': request})
        post_serializer = BoardPostListSerializer(
            posts,
            many=True,
            context={'request': request, 'board_permissions': board_permissions},
        )
        return Response({
            'board': board_serializer.data,
            'posts': post_serializer.data,
        }, status=status.HTTP_200_OK)


class BoardPostListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request, slug):
        board = get_object_or_404(_board_queryset(), slug=slug)
        if not board.is_active and not (request.user.is_staff or request.user.is_superuser):
            return Response({'error': '비활성화된 게시판입니다.'}, status=status.HTTP_404_NOT_FOUND)
        posts = _post_queryset().filter(board=board)
        board_permissions = get_board_permission_flags(request.user, board)
        serializer = BoardPostListSerializer(
            posts,
            many=True,
            context={'request': request, 'board_permissions': board_permissions},
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, slug):
        board = get_object_or_404(_board_queryset(), slug=slug)
        _, error_response = _require_permission(request.user, board, 'can_create')
        if error_response:
            return error_response

        serializer = BoardPostWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        images = request.FILES.getlist('images')
        try:
            _validate_uploaded_images(images)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            post = serializer.save(board=board, author=request.user)
            for sort_order, image in enumerate(images):
                BoardPostImage.objects.create(post=post, image=image, sort_order=sort_order)

        detail_serializer = BoardPostDetailSerializer(post, context={'request': request})
        return Response(detail_serializer.data, status=status.HTTP_201_CREATED)


class BoardPostDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_object(self, post_id):
        return get_object_or_404(_post_queryset(), id=post_id)

    def get(self, request, post_id):
        post = self.get_object(post_id)
        if not post.board.is_active and not (request.user.is_staff or request.user.is_superuser):
            return Response({'error': '비활성화된 게시판입니다.'}, status=status.HTTP_404_NOT_FOUND)
        board_permissions = get_board_permission_flags(request.user, post.board)
        serializer = BoardPostDetailSerializer(
            post,
            context={'request': request, 'board_permissions': board_permissions},
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request, post_id):
        post = self.get_object(post_id)
        _, error_response = _require_permission(request.user, post.board, 'can_update')
        if error_response:
            return error_response

        serializer = BoardPostWriteSerializer(post, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        images = request.FILES.getlist('images')
        try:
            retained_image_ids = _parse_retained_image_ids(request.data.get('retained_image_ids', '[]'))
            with transaction.atomic():
                post = serializer.save()
                _sync_post_images(post, retained_image_ids, images)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        refreshed_post = self.get_object(post_id)
        detail_serializer = BoardPostDetailSerializer(refreshed_post, context={'request': request})
        return Response(detail_serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, post_id):
        post = self.get_object(post_id)
        _, error_response = _require_permission(request.user, post.board, 'can_delete')
        if error_response:
            return error_response

        with transaction.atomic():
            post.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class BoardPostCommentListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, post_id):
        post = get_object_or_404(BoardPost.objects.select_related('board'), id=post_id)
        if not post.board.is_active and not (request.user.is_staff or request.user.is_superuser):
            return Response({'error': '비활성화된 게시판입니다.'}, status=status.HTTP_404_NOT_FOUND)
        comments = post.comments.select_related('author').order_by('created_at')
        serializer = BoardPostCommentSerializer(comments, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, post_id):
        post = get_object_or_404(BoardPost.objects.select_related('board'), id=post_id)
        if not post.board.is_active:
            return Response({'error': '비활성화된 게시판입니다.'}, status=status.HTTP_403_FORBIDDEN)
        body = request.data.get('body', '').strip()
        if not body:
            return Response({'error': '댓글을 입력하세요.'}, status=status.HTTP_400_BAD_REQUEST)
        comment = BoardPostComment.objects.create(post=post, author=request.user, body=body)
        serializer = BoardPostCommentSerializer(comment, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class BoardPostCommentDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _get_comment(self, comment_id):
        return get_object_or_404(
            BoardPostComment.objects.select_related('post__board', 'author'),
            id=comment_id,
        )

    def _check_permission(self, request, comment):
        is_owner = comment.author_id == request.user.id
        is_admin = request.user.is_staff or request.user.is_superuser
        if not (is_owner or is_admin):
            return Response({'error': '권한이 없습니다.'}, status=status.HTTP_403_FORBIDDEN)
        return None

    def patch(self, request, comment_id):
        comment = self._get_comment(comment_id)
        error_response = self._check_permission(request, comment)
        if error_response:
            return error_response
        body = request.data.get('body', '').strip()
        if not body:
            return Response({'error': '댓글을 입력하세요.'}, status=status.HTTP_400_BAD_REQUEST)
        comment.body = body
        comment.save(update_fields=['body', 'updated_at'])
        serializer = BoardPostCommentSerializer(comment, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, comment_id):
        comment = self._get_comment(comment_id)
        error_response = self._check_permission(request, comment)
        if error_response:
            return error_response
        comment.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
