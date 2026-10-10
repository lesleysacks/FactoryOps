"""
FactoryOps Dashboard — URL Configuration
"""

from django.urls import path

from . import operator_views, production_views, views

app_name = 'dashboard'

urlpatterns = [
    path('', views.home, name='home'),
    path('dashboard/', views.home, name='home_alias'),
    path('operator/', views.operator, name='operator'),
    path('operator/production/', production_views.operator_production, name='operator_production'),
    path(
        'operator/production/lines/<int:pk>/',
        production_views.production_line,
        name='production_line',
    ),
    path(
        'operator/production/runs/<int:pk>/',
        production_views.production_run,
        name='production_run',
    ),
    path(
        'operator/production/runs/<int:pk>/consumption/',
        production_views.production_consumption,
        name='production_consumption',
    ),
    path(
        'operator/production/runs/<int:pk>/material-state/',
        production_views.production_material_state,
        name='production_material_state',
    ),
    path(
        'operator/production/runs/<int:pk>/complete/',
        production_views.production_complete,
        name='production_complete',
    ),
    path(
        'operator/machines/<int:pk>/',
        operator_views.operator_machine,
        name='operator_machine',
    ),
    path(
        'operator/machines/<int:pk>/start/',
        production_views.machine_start,
        name='machine_start',
    ),
    path('operator/inventory/', operator_views.operator_inventory, name='operator_inventory'),
    path(
        'operator/inventory/stock/',
        operator_views.stock_count_create,
        name='stock_count_create',
    ),
    path(
        'operator/inventory/stock/<int:pk>/closing/',
        operator_views.stock_count_close,
        name='stock_count_close',
    ),
    path(
        'operator/inventory/receipt/',
        operator_views.material_receipt_create,
        name='material_receipt_create',
    ),
    path('supervisor/', views.supervisor, name='supervisor'),
    path('manager/', views.manager, name='manager'),
    path('executive/', views.executive, name='executive'),
    path('inventory/', views.inventory, name='inventory'),
]
