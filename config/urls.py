"""
FactoryOps Main URL Configuration
"""

from pathlib import Path

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import FileResponse, Http404
from django.urls import include, path
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET

handler403 = 'django.views.defaults.permission_denied'

admin.site.site_header = 'FactoryOps Administration'
admin.site.site_title = 'FactoryOps'
admin.site.index_title = 'Production & Inventory Intelligence'


@require_GET
@cache_control(max_age=86400, public=True)
def favicon(request):
    path = Path(settings.BASE_DIR) / 'static' / 'img' / 'favicon' / 'favicon.ico'
    if not path.is_file():
        raise Http404
    return FileResponse(path.open('rb'), content_type='image/x-icon')


urlpatterns = [
    path('favicon.ico', favicon, name='favicon'),
    path('admin/', admin.site.urls),
    path('accounts/', include('apps.accounts.urls', namespace='accounts')),
    path('factories/', include('apps.factories.urls', namespace='factories')),
    path('', include('apps.dashboard.urls', namespace='dashboard')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
