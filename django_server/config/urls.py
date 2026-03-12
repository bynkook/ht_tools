from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from apps.core.admin_views import UsageStatsView

urlpatterns = [
    path('admin/usage-stats/', UsageStatsView.as_view(), name='admin-usage-stats'),
    path('admin/', admin.site.urls),
    
    # [수정] 루트 접속 시 /admin/ 으로 리다이렉트 (404 에러 방지)
    path('', RedirectView.as_view(url='/admin/')), 
    
    # API URLs
    # Authentication (전역)
    path('api/auth/', include('apps.authentication.urls')),
    
    # Feature Apps
    path('api/agent-chat/', include('apps.fabrix_agent_chat.urls')),  # FabriX Agent Chat
    path('api/chat/', include('apps.fabrix_chat.urls')),              # FabriX Chat
    path('api/image-inspector/', include('apps.image_inspector.urls')),
    path('api/data-explorer/', include('apps.data_explorer.urls')),
    path('api/settings/', include('apps.user_settings.urls')),
    path('api/board/', include('apps.board.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)