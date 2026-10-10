"""
FactoryOps — V1.1 production control screens.

Operator configuration, QC verification, and supervisor exception resolution.
Calculation stays in production services. These views only collect input and
render what those services return.
"""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from apps.audit.models import AuditEvent
from apps.audit.services import apply_controlled_correction
from apps.production.models import ProductionStage
from apps.production.qc import add_qc_photo, complete_qc, save_qc_verification
from apps.production.state_machine import (
    accept_variance,
    create_controlled_run,
    gate_requirements,
    revalidate_after_correction,
    transition,
)
from apps.production.variance import expected_individual_units, variance_for_run

from .forms import (
    AcceptVarianceForm,
    QCPhotoForm,
    QCVerificationForm,
    RunConfigurationForm,
    VarianceCorrectionForm,
)
from .helpers import crumbs
from .permissions import (
    PRODUCTION_ROLES,
    QC_ROLES,
    SUPERVISOR_ROLES,
    can_perform_qc,
    can_record_production,
    role_required,
)
from .production_views import _page, _validation_message
from .querysets import production_runs_for, runs_in_stage_for, user_factory


def _run_for(user, pk):
    return get_object_or_404(production_runs_for(user), pk=pk)


@role_required(*PRODUCTION_ROLES)
@require_http_methods(['GET', 'POST'])
def configure_run(request):
    form = RunConfigurationForm(
        request.POST if request.method == 'POST' else None,
        user=request.user,
    )
    if request.method == 'POST' and form.is_valid():
        try:
            run = create_controlled_run(
                request.user,
                product=form.cleaned_data['product'],
                variant=form.cleaned_data['variant'],
                packaging=form.cleaned_data['packaging'],
                line=form.cleaned_data['production_line'],
                machine=form.cleaned_data['machine'],
                planned_pack_quantity=form.cleaned_data['planned_pack_quantity'],
            )
        except ValidationError as exc:
            form.add_error(None, _validation_message(exc))
        else:
            messages.success(request, f'Run {run.reference} is ready to start.')
            return redirect('dashboard:production_run', pk=run.pk)
    preview_missing = []
    if request.method == 'GET':
        preview_missing = [
            'Product',
            'Variant',
            'Packaging',
            'Production line',
            'Machine',
            'Planned pack quantity',
        ]
    return render(request, 'dashboard/production_config.html', {
        **_page(
            'Configure production',
            'Product, variant, packaging, line, and machine',
            crumbs(
                {'label': 'Production', 'url': reverse('dashboard:operator_production')},
                {'label': 'Configure'},
            ),
        ),
        'factory': user_factory(request.user),
        'form': form,
        'missing': preview_missing,
    })


@role_required(*PRODUCTION_ROLES)
@require_POST
def start_controlled_run(request, pk):
    run = _run_for(request.user, pk)
    return _transition_or_redirect(request, run, ProductionStage.PRODUCTION_ACTIVE)


@role_required(*PRODUCTION_ROLES)
@require_POST
def mark_output_recorded(request, pk):
    run = _run_for(request.user, pk)
    return _transition_or_redirect(request, run, ProductionStage.OUTPUT_RECORDED)


@role_required(*PRODUCTION_ROLES)
@require_POST
def submit_for_qc(request, pk):
    run = _run_for(request.user, pk)
    return _transition_or_redirect(request, run, ProductionStage.QC_REQUIRED)


@role_required(*PRODUCTION_ROLES)
@require_POST
def cancel_controlled_run(request, pk):
    run = _run_for(request.user, pk)
    return _transition_or_redirect(request, run, ProductionStage.CANCELLED)


def _transition_or_redirect(request, run, target):
    try:
        updated = transition(run, target, actor=request.user)
    except ValidationError as exc:
        messages.error(request, _validation_message(exc))
    else:
        messages.success(request, f'{updated.reference} is now {updated.get_stage_display()}.')
    return redirect('dashboard:production_run', pk=run.pk)


@role_required(*QC_ROLES)
def qc_queue(request):
    runs = list(runs_in_stage_for(request.user, ProductionStage.QC_REQUIRED)[:50])
    return render(request, 'dashboard/qc_queue.html', {
        **_page(
            'QC queue',
            'Runs waiting for verification',
            crumbs({'label': 'QC'}),
        ),
        'factory': user_factory(request.user),
        'runs': runs,
        'can_perform_qc': can_perform_qc(request.user),
    })


@role_required(*QC_ROLES)
@require_http_methods(['GET', 'POST'])
def qc_verification(request, pk):
    run = _run_for(request.user, pk)
    if run.stage != ProductionStage.QC_REQUIRED and not hasattr(run, 'qc_verification'):
        messages.error(request, 'This run is not waiting for QC.')
        return redirect('dashboard:qc_queue')
    verification = _verification(run)
    detail_form = QCVerificationForm(
        request.POST if request.POST.get('form') == 'details' else None,
        user=request.user,
    )
    photo_form = QCPhotoForm(
        request.POST if request.POST.get('form') == 'photo' else None,
        request.FILES if request.POST.get('form') == 'photo' else None,
    )
    if request.method == 'POST':
        action = request.POST.get('form')
        try:
            if action == 'details' and detail_form.is_valid():
                save_qc_verification(
                    request.user,
                    run,
                    variant=detail_form.cleaned_data['variant'],
                    packaging=detail_form.cleaned_data['packaging'],
                    qc_verified_quantity=detail_form.cleaned_data['qc_verified_quantity'],
                )
                messages.success(request, 'QC details saved.')
                return redirect('dashboard:qc_verification', pk=run.pk)
            if action == 'photo' and photo_form.is_valid():
                add_qc_photo(
                    request.user,
                    run,
                    photo_form.cleaned_data['image'],
                    caption=photo_form.cleaned_data.get('caption') or '',
                )
                messages.success(request, 'Photo uploaded.')
                return redirect('dashboard:qc_verification', pk=run.pk)
            if action == 'complete':
                complete_qc(request.user, run)
                messages.success(request, f'QC completed for {run.reference}.')
                return redirect('dashboard:production_run', pk=run.pk)
        except ValidationError as exc:
            messages.error(request, _validation_message(exc))
            if action == 'details':
                detail_form.add_error(None, _validation_message(exc))
            elif action == 'photo':
                photo_form.add_error(None, _validation_message(exc))
    photos = list(verification.photos.all()) if verification is not None else []
    return render(request, 'dashboard/qc_verification.html', {
        **_page(
            f'QC {run.reference}',
            'Confirm variant, packaging, photos, and verified quantity',
            crumbs(
                {'label': 'QC', 'url': reverse('dashboard:qc_queue')},
                {'label': run.reference},
            ),
        ),
        'factory': user_factory(request.user),
        'run': run,
        'verification': verification,
        'photos': photos,
        'detail_form': detail_form,
        'photo_form': photo_form,
        'variance': variance_for_run(run),
        'expected': expected_individual_units(run),
        'gate': gate_requirements(run, ProductionStage.QC_COMPLETE),
        'can_edit': run.stage == ProductionStage.QC_REQUIRED,
    })


@role_required(*SUPERVISOR_ROLES)
def exception_queue(request):
    runs = list(runs_in_stage_for(request.user, ProductionStage.EXCEPTION)[:50])
    return render(request, 'dashboard/exception_queue.html', {
        **_page(
            'Exceptions',
            'Runs whose variance needs a supervisor',
            crumbs({'label': 'Exceptions'}),
        ),
        'factory': user_factory(request.user),
        'runs': runs,
    })


@role_required(*SUPERVISOR_ROLES)
@require_http_methods(['GET', 'POST'])
def exception_detail(request, pk):
    run = _run_for(request.user, pk)
    correction_form = VarianceCorrectionForm(
        request.POST if request.POST.get('form') == 'correct' else None,
    )
    accept_form = AcceptVarianceForm(
        request.POST if request.POST.get('form') == 'accept' else None,
    )
    if request.method == 'POST':
        action = request.POST.get('form')
        try:
            if action == 'correct' and correction_form.is_valid():
                verification = _verification(run)
                if verification is None:
                    raise ValidationError('This run has no QC verification to correct.')
                apply_controlled_correction(
                    verification,
                    correction_form.cleaned_data['field'],
                    correction_form.cleaned_data['new_value'],
                    actor=request.user,
                    reason=correction_form.cleaned_data['reason'],
                )
                if run.stage == ProductionStage.EXCEPTION:
                    revalidate_after_correction(
                        run,
                        actor=request.user,
                        reason=correction_form.cleaned_data['reason'],
                    )
                messages.success(request, 'Correction recorded.')
                return redirect('dashboard:exception_detail', pk=run.pk)
            if action == 'accept' and accept_form.is_valid():
                accept_variance(
                    run,
                    actor=request.user,
                    reason=accept_form.cleaned_data['reason'],
                )
                messages.success(request, f'Variance on {run.reference} accepted.')
                return redirect('dashboard:exception_queue')
        except ValidationError as exc:
            messages.error(request, _validation_message(exc))
    verification = _verification(run)
    return render(request, 'dashboard/exception_detail.html', {
        **_page(
            run.reference,
            'Resolve the variance without erasing the original record',
            crumbs(
                {'label': 'Exceptions', 'url': reverse('dashboard:exception_queue')},
                {'label': run.reference},
            ),
        ),
        'factory': user_factory(request.user),
        'run': run,
        'verification': verification,
        'variance': variance_for_run(run),
        'events': _events_for_run(run, verification),
        'correction_form': correction_form,
        'accept_form': accept_form,
        'can_resolve': run.stage == ProductionStage.EXCEPTION,
    })


def _verification(run):
    try:
        return run.qc_verification
    except run.__class__.qc_verification.RelatedObjectDoesNotExist:
        return None


def _events_for_run(run, verification):
    from django.contrib.contenttypes.models import ContentType

    from apps.production.models import ProductionRun, QCVerification

    run_type = ContentType.objects.get_for_model(ProductionRun)
    events = AuditEvent.objects.filter(
        target_content_type=run_type,
        target_object_id=run.pk,
    )
    if verification is not None:
        qc_type = ContentType.objects.get_for_model(QCVerification)
        events = events | AuditEvent.objects.filter(
            target_content_type=qc_type,
            target_object_id=verification.pk,
        )
    return list(events.select_related('actor').order_by('-created_at')[:50])
