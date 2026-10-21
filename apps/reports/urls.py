from django.urls import path

from apps.reports.views import sheets_status
"""
FactoryOps reports — URL configuration.
"""

from django.urls import path

from . import views

app_name = 'reports'

urlpatterns = [
    path('sheets/', sheets_status, name='sheets_status'),
    path('production/', views.production_summary_view, name='production_summary'),
    path('qc-variance/', views.qc_variance_view, name='qc_variance'),
]
