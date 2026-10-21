"""
FactoryOps reports — URL configuration.
"""

from django.urls import path

from . import views

app_name = 'reports'

urlpatterns = [
    path('production/', views.production_summary_view, name='production_summary'),
    path('qc-variance/', views.qc_variance_view, name='qc_variance'),
]
