"""
FactoryOps Dashboard — URL Configuration
"""

from django.urls import path

from . import control_views, operator_views, production_views, views

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
    path(
        'operator/production/configure/',
        control_views.configure_run,
        name='configure_run',
    ),
    path(
        'operator/production/runs/<int:pk>/start-controlled/',
        control_views.start_controlled_run,
        name='start_controlled_run',
    ),
    path(
        'operator/production/runs/<int:pk>/output-recorded/',
        control_views.mark_output_recorded,
        name='mark_output_recorded',
    ),
    path(
        'operator/production/runs/<int:pk>/submit-qc/',
        control_views.submit_for_qc,
        name='submit_for_qc',
    ),
    path(
        'operator/production/runs/<int:pk>/cancel-controlled/',
        control_views.cancel_controlled_run,
        name='cancel_controlled_run',
    ),
    path('qc/', control_views.qc_queue, name='qc_queue'),
    path('qc/runs/<int:pk>/', control_views.qc_verification, name='qc_verification'),
    path('exceptions/', control_views.exception_queue, name='exception_queue'),
    path('exceptions/runs/<int:pk>/', control_views.exception_detail, name='exception_detail'),
    path('supervisor/', views.supervisor, name='supervisor'),
    path('manager/', views.manager, name='manager'),
    path('executive/', views.executive, name='executive'),
    path('inventory/', views.inventory, name='inventory'),
]
