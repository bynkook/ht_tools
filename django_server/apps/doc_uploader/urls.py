from django.urls import path

from . import views

urlpatterns = [
    # 작업 목록 (GET)
    path('jobs/', views.JobListView.as_view(), name='doc-job-list'),
    # 내부 작업 생성 (FastAPI → Django, X-Internal-Secret 인증)
    path('jobs/internal/', views.JobInternalCreateView.as_view(), name='doc-job-internal-create'),
    # FastAPI 시작 시 working job 초기화 (X-Internal-Secret 인증)
    path('jobs/startup-reset/', views.JobStartupResetView.as_view(), name='doc-job-startup-reset'),
    # FastAPI 변환 완료 콜백 (callback_token으로만 보안, 일반 Auth 없음)
    path('jobs/callback/<uuid:token>/', views.JobCallbackView.as_view(), name='doc-job-callback'),
    # 카테고리 목록 조회 (GET) + 생성 (POST)
    path('categories/', views.CategoryListCreateView.as_view(), name='doc-category-list-create'),
    # 카테고리 이름 변경 (PATCH)
    path('categories/<str:name>/', views.CategoryRenameView.as_view(), name='doc-category-rename'),
]
