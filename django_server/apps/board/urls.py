from django.urls import path

from .views import BoardDetailView, BoardListView, BoardPostDetailView, BoardPostListCreateView


urlpatterns = [
    path('boards/', BoardListView.as_view(), name='board-list'),
    path('boards/<slug:slug>/', BoardDetailView.as_view(), name='board-detail'),
    path('boards/<slug:slug>/posts/', BoardPostListCreateView.as_view(), name='board-post-list-create'),
    path('posts/<int:post_id>/', BoardPostDetailView.as_view(), name='board-post-detail'),
]
