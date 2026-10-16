from django.urls import path

from apps.reports.views import sheets_status

app_name = 'reports'

urlpatterns = [
    path('sheets/', sheets_status, name='sheets_status'),
]
