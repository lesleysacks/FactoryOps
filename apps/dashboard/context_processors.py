"""
FactoryOps Dashboard — navigation context for the application shell.
"""

from django.urls import reverse

from apps.accounts.models import Role


def navigation(request):
    user = getattr(request, 'user', None)
    items = []
    if user is not None and user.is_authenticated:
        items.append({
            'id': 'dashboard',
            'label': 'Dashboard',
            'url': reverse('dashboard:home'),
        })
        items.append({
            'id': 'operations',
            'label': 'Operations',
            'url': reverse('dashboard:operator'),
        })
        if user.role in (Role.OPERATOR, Role.QC):
            items.append({
                'id': 'production',
                'label': 'Production',
                'url': reverse('dashboard:operator_production'),
            })
            items.append({
                'id': 'inventory',
                'label': 'Inventory',
                'url': reverse('dashboard:operator_inventory'),
            })
        if user.role in (Role.SUPERVISOR, Role.ADMIN):
            items.append({
                'id': 'inventory',
                'label': 'Inventory',
                'url': reverse('dashboard:inventory'),
            })
            items.append({
                'id': 'production',
                'label': 'Production',
                'url': reverse('dashboard:supervisor'),
            })
        if user.role == Role.ADMIN:
            items.append({
                'id': 'orders',
                'label': 'Orders',
                'url': reverse('dashboard:manager'),
            })
            items.append({
                'id': 'reports',
                'label': 'Reports',
                'url': reverse('dashboard:executive'),
            })
        if user.role in (Role.SUPERVISOR, Role.ADMIN):
            items.append({
                'id': 'admin',
                'label': 'Admin',
                'url': reverse('admin:index'),
            })

    match = getattr(request, 'resolver_match', None)
    url_name = match.url_name if match else ''
    active = {
        'operator': 'operations',
        'supervisor': 'production',
        'inventory': 'inventory',
        'manager': 'orders',
        'executive': 'reports',
        'home': 'dashboard',
        'home_alias': 'dashboard',
        'operator_production': 'production',
        'operator_machine': 'production',
        'production_line': 'production',
        'production_run': 'production',
        'production_consumption': 'production',
        'production_material_state': 'production',
        'production_complete': 'production',
        'machine_start': 'production',
        'operator_inventory': 'inventory',
        'stock_count_create': 'inventory',
        'stock_count_close': 'inventory',
        'material_receipt_create': 'inventory',
    }.get(url_name, '')

    return {
        'nav_items': items,
        'nav_active': active,
        'product_name': 'FactoryOps',
        'product_tagline': 'Production & Inventory Intelligence',
    }
