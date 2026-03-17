import os
import re

from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils.text import slugify


_CAMEL_BOUNDARY_RE = re.compile(r'(?<=[a-z0-9])(?=[A-Z])')
_SEPARATOR_RE = re.compile(r'[-_\s]+')


def _normalize_name_parts(value):
    separated = _CAMEL_BOUNDARY_RE.sub(' ', value or '')
    separated = _SEPARATOR_RE.sub(' ', separated).strip()
    return [part for part in separated.split(' ') if part]


def build_board_slug(name):
    parts = _normalize_name_parts(name)
    return slugify('-'.join(parts))


def build_board_title(name):
    parts = _normalize_name_parts(name)
    if not parts:
        return ''
    return ' '.join(part.capitalize() for part in parts)


def post_image_upload_path(instance, filename):
    _, extension = os.path.splitext(filename)
    safe_extension = extension.lower() or '.bin'
    return f'board/{instance.post.board.slug}/{instance.post_id}/{instance.sort_order}{safe_extension}'


def board_header_upload_path(instance, filename):
    _, extension = os.path.splitext(filename)
    safe_extension = extension.lower() or '.bin'
    return f'board/{instance.slug}/header{safe_extension}'


BOARD_STYLE_TILE = 'tile'
BOARD_STYLE_REDDIT = 'reddit'
BOARD_STYLE_CHOICES = [
    (BOARD_STYLE_TILE, '타일형'),
    (BOARD_STYLE_REDDIT, 'Reddit형'),
]


class Board(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, db_index=True)
    title_display = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True, default='')
    header_background_image = models.FileField(upload_to=board_header_upload_path, blank=True, null=True)
    board_style = models.CharField(max_length=20, choices=BOARD_STYLE_CHOICES, default=BOARD_STYLE_TILE)
    is_active = models.BooleanField(default=True)
    allow_create = models.BooleanField(default=True)
    allow_update = models.BooleanField(default=True)
    allow_delete = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ['title_display', 'name']
        verbose_name = 'Board'
        verbose_name_plural = 'Boards'

    def save(self, *args, **kwargs):
        self.slug = build_board_slug(self.name)
        if not self.title_display:
            self.title_display = build_board_title(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title_display or self.name


class BoardModerator(models.Model):
    board = models.ForeignKey(Board, on_delete=models.CASCADE, related_name='moderatorships')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='board_moderatorships')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('board', 'user')]
        ordering = ['board__title_display', 'user__username']
        verbose_name = 'Board Moderator'
        verbose_name_plural = 'Board Moderators'

    def __str__(self):
        return f'{self.board.slug} :: {self.user.username}'


class BoardPost(models.Model):
    board = models.ForeignKey(Board, on_delete=models.CASCADE, related_name='posts')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='board_posts')
    title = models.CharField(max_length=200)
    body_markdown = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ['-updated_at', '-created_at', '-id']
        indexes = [
            models.Index(fields=['board', '-updated_at']),
            models.Index(fields=['board', '-created_at']),
        ]
        verbose_name = 'Board Post'
        verbose_name_plural = 'Board Posts'

    def __str__(self):
        return f'{self.board.slug} :: {self.title}'

    @property
    def preview_image(self):
        if hasattr(self, '_prefetched_objects_cache') and 'images' in self._prefetched_objects_cache:
            images = self._prefetched_objects_cache['images']
            return images[0] if images else None
        return self.images.order_by('sort_order', 'id').first()


class BoardPostImage(models.Model):
    post = models.ForeignKey(BoardPost, on_delete=models.CASCADE, related_name='images')
    image = models.FileField(upload_to=post_image_upload_path)
    sort_order = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    alt_text = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['sort_order', 'id']
        verbose_name = 'Board Post Image'
        verbose_name_plural = 'Board Post Images'

    def __str__(self):
        return f'{self.post.title} :: {self.image.name}'


@receiver(post_delete, sender=BoardPostImage)
def delete_board_post_image_file(sender, instance, **kwargs):
    if instance.image:
        instance.image.delete(save=False)


@receiver(post_delete, sender=Board)
def delete_board_header_file(sender, instance, **kwargs):
    if instance.header_background_image:
        instance.header_background_image.delete(save=False)


class BoardPostComment(models.Model):
    post = models.ForeignKey(BoardPost, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='board_comments')
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['post', 'created_at']),
        ]
        verbose_name = 'Board Post Comment'
        verbose_name_plural = 'Board Post Comments'

    def __str__(self):
        return f'{self.post.title} :: {self.author.username} :: {self.body[:40]}'
