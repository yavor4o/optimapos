# optimapos/urls.py
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

from optimapos import settings

urlpatterns = [
    path('admin/', admin.site.urls),
    path('purchases/', include('purchases.urls')),
    path('nomenclatures/', include('nomenclatures.urls')),
]

if settings.DEBUG:  # Само в режим на разработка
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)