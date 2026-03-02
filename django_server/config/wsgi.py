import os
from django.core.wsgi import get_wsgi_application

# settings.py의 위치를 지정합니다 (config.settings)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_wsgi_application()