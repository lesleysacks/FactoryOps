"""
FactoryOps — Operator production floor views.

Starts, records output on, and completes ProductionRun records.
Records MaterialConsumption and ProductionRunMaterialState against an explicit run.
Does not record waste, rejects, QC, or reconciliation.
"""

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from apps.production.models import ProductionRun, ProductionRunStatus
from apps.production.workflow import (
    complete_production_run,
    current_material_states_for,
    start_production_run,
)

from .forms import (
    MaterialConsumptionForm,
    MaterialStateForm,
    ProductionOutputForm,
    StartRunForm,
)
from .helpers import crumbs
from .permissions import (
    OPERATOR_ROLES,
    PRODUCTION_ROLES,
    can_record_production,
    role_required,
)
from .querysets import (
    active_lines_for,
    active_machines_for,
    active_machines_on_line_for,
    active_production_runs_for,
    completed_production_runs_today_for,
    production_runs_for,
    user_factory,
)


def _page(title, subtitle, trail):
    return {
        'page_title': title,
        'page_subtitle': subtitle,
        'breadcrumbs': trail,
    }


def _validation_message(exc):
    if getattr(exc, 'message_dict', None):
        parts = []
        for field_messages in exc.message_dict.values():
            parts.extend(str(item) for item in field_messages)
        return ' '.join(parts)
    if getattr(exc, 'messages', None):
        return ' '.join(str(item) for item in exc.messages)
    return str(exc)


@role_required(*OPERATOR_ROLES)
def operator_production(request):
    factory = user_factory(request.user)
    today = timezone.now().date()
    return render(request, 'dashboard/operator_production.html', {
        **_page(
            'Production',
            'Select a line, start a run, and record output',
            crumbs({'label': 'Production'}),
        ),
        'factory': factory,
        'lines': list(active_lines_for(request.user)),
        'machines': list(active_machines_for(request.user)),
        'active_runs': list(active_production_runs_for(request.user)[:20]),
        'completed_runs': list(completed_production_runs_today_for(request.user, today)[:20]),
        'can_record_production': can_record_production(request.user),
    })


@role_required(*OPERATOR_ROLES)
@require_http_methods(['GET', 'POST'])
def production_line(request, pk):
    line = get_object_or_404(active_lines_for(request.user), pk=pk)
    form = StartRunForm(
        request.POST if request.method == 'POST' else None,
        user=request.user,
        line=line,
    )
    if request.method == 'POST':
        if not can_record_production(request.user):
            raise PermissionDenied('You do not have access to record production.')
        if form.is_valid():
            try:
                run = form.save()
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                messages.success(request, f'Run {run.reference} started.')
                return redirect('dashboard:production_run', pk=run.pk)
    return render(request, 'dashboard/production_line.html', {
        **_page(
            line.name,
            line.code or 'Production line',
            crumbs(
                {'label': 'Production', 'url': reverse('dashboard:operator_production')},
                {'label': line.name},
            ),
        ),
        'factory': user_factory(request.user),
        'line': line,
        'machines': list(active_machines_on_line_for(request.user, line)),
        'active_runs': list(active_production_runs_for(request.user).filter(production_line=line)[:12]),
        'form': form,
        'can_record_production': can_record_production(request.user),
    })


@role_required(*PRODUCTION_ROLES)
@require_POST
def machine_start(request, pk):
    machine = get_object_or_404(active_machines_for(request.user), pk=pk)
    try:
        run = start_production_run(request.user, machine)
    except ValidationError as exc:
        messages.error(request, _validation_message(exc))
        return redirect('dashboard:operator_machine', pk=machine.pk)
    messages.success(request, f'Run {run.reference} started.')
    return redirect('dashboard:production_run', pk=run.pk)


@role_required(*OPERATOR_ROLES)
@require_http_methods(['GET', 'POST'])
def production_run(request, pk):
    run = get_object_or_404(production_runs_for(request.user), pk=pk)
    form = ProductionOutputForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST':
        if not can_record_production(request.user):
            raise PermissionDenied('You do not have access to record production.')
        if form.is_valid():
            try:
                form.save(request.user, run.pk)
            except ProductionRun.DoesNotExist:
                raise Http404
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                messages.success(request, 'Output recorded.')
                return redirect('dashboard:production_run', pk=run.pk)
    outputs = list(run.outputs.all().order_by('-recorded_at'))
    consumptions = list(
        run.material_consumptions.select_related(
            'material', 'batch', 'recorded_by',
        ).order_by('-consumed_at')
    )
    return render(request, 'dashboard/production_run.html', {
        **_page(
            run.reference,
            run.get_status_display(),
            crumbs(
                {'label': 'Production', 'url': reverse('dashboard:operator_production')},
                {'label': run.reference},
            ),
        ),
        'factory': user_factory(request.user),
        'run': run,
        'outputs': outputs,
        'consumptions': consumptions,
        'current_material_states': current_material_states_for(run),
        'form': form,
        'can_record_production': can_record_production(request.user),
        'is_active_run': run.status == ProductionRunStatus.IN_PROGRESS,
    })


@role_required(*PRODUCTION_ROLES)
@require_http_methods(['GET', 'POST'])
def production_consumption(request, pk):
    run = get_object_or_404(active_production_runs_for(request.user), pk=pk)
    selected_material = (
        request.POST.get('material')
        if request.method == 'POST'
        else request.GET.get('material')
    )
    initial = {}
    if request.method != 'POST' and selected_material:
        initial['material'] = selected_material
    form = MaterialConsumptionForm(
        request.POST if request.method == 'POST' else None,
        user=request.user,
        run=run,
        initial=initial or None,
    )
    if request.method == 'POST' and form.is_valid():
        try:
            form.save()
        except ProductionRun.DoesNotExist:
            raise Http404
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, 'Consumption recorded.')
            return redirect('dashboard:production_run', pk=run.pk)
    return render(request, 'dashboard/consumption_form.html', {
        **_page(
            'Record consumption',
            run.reference,
            crumbs(
                {'label': 'Production', 'url': reverse('dashboard:operator_production')},
                {'label': run.reference, 'url': reverse('dashboard:production_run', args=[run.pk])},
                {'label': 'Consumption'},
            ),
        ),
        'factory': user_factory(request.user),
        'run': run,
        'form': form,
        'submit_label': 'Record consumption',
    })


@role_required(*PRODUCTION_ROLES)
@require_http_methods(['GET', 'POST'])
def production_material_state(request, pk):
    run = get_object_or_404(active_production_runs_for(request.user), pk=pk)
    form = MaterialStateForm(
        request.POST if request.method == 'POST' else None,
        user=request.user,
        run=run,
    )
    if request.method == 'POST' and form.is_valid():
        try:
            form.save()
        except ProductionRun.DoesNotExist:
            raise Http404
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, 'Material state recorded.')
            return redirect('dashboard:production_run', pk=run.pk)
    return render(request, 'dashboard/material_state_form.html', {
        **_page(
            'Record material state',
            run.reference,
            crumbs(
                {'label': 'Production', 'url': reverse('dashboard:operator_production')},
                {'label': run.reference, 'url': reverse('dashboard:production_run', args=[run.pk])},
                {'label': 'Material state'},
            ),
        ),
        'factory': user_factory(request.user),
        'run': run,
        'form': form,
        'submit_label': 'Save material state',
    })


@role_required(*PRODUCTION_ROLES)
@require_POST
def production_complete(request, pk):
    try:
        run = complete_production_run(request.user, pk)
    except ProductionRun.DoesNotExist:
        raise Http404
    except ValidationError as exc:
        messages.error(request, _validation_message(exc))
        return redirect('dashboard:production_run', pk=pk)
    messages.success(request, f'Run {run.reference} completed.')
    return redirect('dashboard:production_run', pk=run.pk)
