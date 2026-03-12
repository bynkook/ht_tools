from datetime import timedelta

from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from .models import Board, BoardModerator, BoardPost, build_board_slug


class BoardPermissionTests(APITestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(username='admin_user', password='password123', is_staff=True)
        self.moderator_user = User.objects.create_user(username='moderator_user', password='password123')
        self.regular_user = User.objects.create_user(username='regular_user', password='password123')
        self.board = Board.objects.create(name='dashboardBoardTest', description='Dashboard board')
        BoardModerator.objects.create(board=self.board, user=self.moderator_user)

    def _authenticate(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

    def test_build_board_slug(self):
        self.assertEqual(build_board_slug('dashboardList'), 'dashboard-list')

    def test_regular_user_cannot_create_post(self):
        self._authenticate(self.regular_user)
        response = self.client.post(
            reverse('board-post-list-create', kwargs={'slug': self.board.slug}),
            {'title': 'Unauthorized', 'body_markdown': 'No access'},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_moderator_can_create_post_when_allowed(self):
        self._authenticate(self.moderator_user)
        response = self.client.post(
            reverse('board-post-list-create', kwargs={'slug': self.board.slug}),
            {'title': 'Allowed', 'body_markdown': 'Moderator content'},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['title'], 'Allowed')

    def test_moderator_cannot_create_when_board_disallows_create(self):
        self.board.allow_create = False
        self.board.save(update_fields=['allow_create', 'updated_at'])
        self._authenticate(self.moderator_user)
        response = self.client.post(
            reverse('board-post-list-create', kwargs={'slug': self.board.slug}),
            {'title': 'Blocked', 'body_markdown': 'Moderator content'},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_create_even_when_board_disallows_create(self):
        self.board.allow_create = False
        self.board.save(update_fields=['allow_create', 'updated_at'])
        self._authenticate(self.admin_user)
        response = self.client.post(
            reverse('board-post-list-create', kwargs={'slug': self.board.slug}),
            {'title': 'Admin override', 'body_markdown': 'Admin content'},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_posts_are_sorted_by_latest_created_first(self):
        self._authenticate(self.moderator_user)
        first_response = self.client.post(
            reverse('board-post-list-create', kwargs={'slug': self.board.slug}),
            {'title': 'First', 'body_markdown': 'First content'},
        )
        self.assertEqual(first_response.status_code, status.HTTP_201_CREATED)

        second_response = self.client.post(
            reverse('board-post-list-create', kwargs={'slug': self.board.slug}),
            {'title': 'Second', 'body_markdown': 'Second content'},
        )
        self.assertEqual(second_response.status_code, status.HTTP_201_CREATED)

        response = self.client.get(reverse('board-detail', kwargs={'slug': self.board.slug}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([post['title'] for post in response.data['posts'][:2]], ['Second', 'First'])

    def test_updated_post_moves_to_top(self):
        first_post = BoardPost.objects.create(
            board=self.board,
            author=self.moderator_user,
            title='Older',
            body_markdown='Older content',
        )
        second_post = BoardPost.objects.create(
            board=self.board,
            author=self.moderator_user,
            title='Newer',
            body_markdown='Newer content',
        )
        BoardPost.objects.filter(id=first_post.id).update(updated_at=timezone.now() + timedelta(minutes=1))

        self._authenticate(self.regular_user)
        response = self.client.get(reverse('board-detail', kwargs={'slug': self.board.slug}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([post['title'] for post in response.data['posts'][:2]], ['Older', 'Newer'])
