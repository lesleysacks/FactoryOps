"""
FactoryOps — Operator capture and floor-context views.

Writes StockRecord, MaterialBatch, and MaterialAddition for inventory capture.
Production write paths live in production_views.
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from .forms import MaterialReceiptForm, StockCloseForm, StockCountForm
from .helpers import crumbs
from .permissions import OPERATOR_ROLES, can_record_production, role_required
from .querysets import (
    active_machines_for,
    active_production_runs_for,
    open_stock_counts_for,
    user_factory,
)


def _capture_page(title, subtitle, trail):
    return {
        'page_title': title,
        'page_subtitle': subtitle,
        'breadcrumbs': trail,
    }


@role_required(*OPERATOR_ROLES)
def operator_inventory(request):
    factory = user_factory(request.user)
    return render(request, 'dashboard/operator_inventory.html', {
        **_capture_page(
            'Inventory',
            'Stock counts and receipts',
            crumbs({'label': 'Inventory'}),
        ),
        'factory': factory,
        'open_stock_counts': list(open_stock_counts_for(request.user)[:12]),
    })


@role_required(*OPERATOR_ROLES)
def operator_machine(request, pk):
    machine = get_object_or_404(active_machines_for(request.user), pk=pk)
    return render(request, 'dashboard/operator_machine.html', {
        **_capture_page(
            machine.code,
            machine.name,
            crumbs(
                {'label': 'Production', 'url': reverse('dashboard:operator_production')},
                {
                    'label': machine.production_line.name,
                    'url': reverse('dashboard:production_line', args=[machine.production_line_id]),
                },
                {'label': machine.code},
            ),
        ),
        'factory': user_factory(request.user),
        'machine': machine,
        'active_runs': list(
            active_production_runs_for(request.user).filter(machine=machine)[:8]
        ),
        'can_record_production': can_record_production(request.user),
    })


@role_required(*OPERATOR_ROLES)
@require_http_methods(['GET', 'POST'])
def stock_count_create(request):
    factory = user_factory(request.user)
    form = StockCountForm(
        request.POST if request.method == 'POST' else None,
        user=request.user,
    )
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Entry recorded successfully.')
        return redirect('dashboard:operator')
    return render(request, 'dashboard/capture_form.html', {
        **_capture_page(
            'Record stock count',
            'Opening and closing quantities',
            crumbs(
                {'label': 'Inventory', 'url': reverse('dashboard:operator_inventory')},
                {'label': 'Stock count'},
            ),
        ),
        'factory': factory,
        'form': form,
        'submit_label': 'Save stock count',
        'intro': 'Count the material at your factory. Closing quantity can be added later.',
    })


@role_required(*OPERATOR_ROLES)
@require_http_methods(['GET', 'POST'])
def stock_count_close(request, pk):
    stock_record = get_object_or_404(open_stock_counts_for(request.user), pk=pk)
    form = StockCloseForm(
        request.POST if request.method == 'POST' else None,
        stock_record=stock_record,
    )
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Entry recorded successfully.')
        return redirect('dashboard:operator')
    return render(request, 'dashboard/capture_form.html', {
        **_capture_page(
            'Record closing count',
            stock_record.material.code,
            crumbs(
                {'label': 'Inventory', 'url': reverse('dashboard:operator_inventory')},
                {'label': 'Closing count'},
            ),
        ),
        'factory': user_factory(request.user),
        'form': form,
        'submit_label': 'Save closing count',
        'intro': (
            f'{stock_record.material.code} on {stock_record.recording_date}. '
            f'Opening quantity is {stock_record.opening_quantity}.'
        ),
    })


@role_required(*OPERATOR_ROLES)
@require_http_methods(['GET', 'POST'])
def material_receipt_create(request):
    factory = user_factory(request.user)
    form = MaterialReceiptForm(
        request.POST if request.method == 'POST' else None,
        user=request.user,
    )
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Entry recorded successfully.')
        return redirect('dashboard:operator')
    return render(request, 'dashboard/capture_form.html', {
        **_capture_page(
            'Record receipt',
            'Material arriving at the factory',
            crumbs(
                {'label': 'Inventory', 'url': reverse('dashboard:operator_inventory')},
                {'label': 'Receipt'},
            ),
        ),
        'factory': factory,
        'form': form,
        'submit_label': 'Save receipt',
        'intro': 'Record material that physically arrived. Use the lot number from the bag or pallet.',
    })
