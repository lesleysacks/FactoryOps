"""
FactoryOps Production — QC verification workflow.

QC writes only QC records. Operator output and consumption stay untouched.
"""

from pathlib import Path

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditAction
from apps.audit.services import record_event
from apps.dashboard.permissions import QC_ROLES
from apps.production.models import (
    QC_PHOTO_CONTENT_TYPES,
    QC_PHOTO_EXTENSIONS,
    MAX_QC_PHOTO_BYTES,
    ProductionStage,
    QCPhoto,
    QCVerification,
    QCVerificationStatus,
)
from apps.production.state_machine import validate_controlled_run


def _require_qc(user):
    if getattr(user, 'role', None) not in QC_ROLES:
        raise ValidationError('You cannot perform QC verification.')
    factory = getattr(user, 'factory', None)
    if factory is None:
        raise ValidationError('Your account is not assigned to a factory.')
    return factory


def _locked_qc_run(user, run):
    factory = _require_qc(user)
    if run.factory_id != factory.id:
        raise ValidationError('This run is not in your factory.')
    if run.stage != ProductionStage.QC_REQUIRED:
        raise ValidationError('QC can only update a run that is waiting for QC.')
    return factory


def save_qc_verification(user, run, *, variant, packaging, qc_verified_quantity):
    factory = _locked_qc_run(user, run)
    if variant is None:
        raise ValidationError({'variant': 'Confirm the variant.'})
    if packaging is None:
        raise ValidationError({'packaging': 'Confirm the packaging.'})
    if variant.product.factory_id != factory.id:
        raise ValidationError({'variant': 'This variant does not belong to your factory.'})
    if packaging.factory_id != factory.id:
        raise ValidationError({'packaging': 'This packaging does not belong to your factory.'})
    if qc_verified_quantity is None or qc_verified_quantity < 0:
        raise ValidationError({
            'qc_verified_quantity': 'Enter the verified finished-goods quantity.',
        })
    with transaction.atomic():
        verification, _created = QCVerification.objects.select_for_update().get_or_create(
            production_run=run,
            defaults={'status': QCVerificationStatus.PENDING},
        )
        if verification.status == QCVerificationStatus.VERIFIED:
            raise ValidationError('This QC record is already verified.')
        verification.variant = variant
        verification.packaging = packaging
        verification.qc_verified_quantity = qc_verified_quantity
        verification.status = QCVerificationStatus.PENDING
        verification.save()
        return verification


def add_qc_photo(user, run, uploaded, caption=''):
    _locked_qc_run(user, run)
    if uploaded is None:
        raise ValidationError({'image': 'Choose a photo.'})
    extension = Path(getattr(uploaded, 'name', '')).suffix.lower()
    if extension not in QC_PHOTO_EXTENSIONS:
        raise ValidationError({'image': 'Photo must be a JPG, PNG, or WebP file.'})
    size = getattr(uploaded, 'size', None)
    if size is not None and size > MAX_QC_PHOTO_BYTES:
        raise ValidationError({'image': 'Photo must be 5 MB or smaller.'})
    content_type = getattr(uploaded, 'content_type', None)
    if content_type and content_type not in QC_PHOTO_CONTENT_TYPES:
        raise ValidationError({'image': 'Photo content type must be JPEG, PNG, or WebP.'})
    with transaction.atomic():
        verification, _created = QCVerification.objects.get_or_create(
            production_run=run,
            defaults={'status': QCVerificationStatus.PENDING},
        )
        return QCPhoto.objects.create(
            qc_verification=verification,
            image=uploaded,
            caption=caption or '',
            uploaded_by=user,
            uploaded_at=timezone.now(),
        )


def complete_qc(user, run):
    factory = _require_qc(user)
    if run.factory_id != factory.id:
        raise ValidationError('This run is not in your factory.')
    with transaction.atomic():
        from apps.production.models import ProductionRun

        locked = ProductionRun.objects.select_for_update().get(pk=run.pk)
        if locked.factory_id != factory.id:
            raise ValidationError('This run is not in your factory.')
        if locked.stage != ProductionStage.QC_REQUIRED:
            raise ValidationError('QC can only complete a run that is waiting for QC.')
        try:
            verification = locked.qc_verification
        except QCVerification.DoesNotExist:
            raise ValidationError('Record the QC verification before completing it.')
        verification.status = QCVerificationStatus.VERIFIED
        verification.verified_by = user
        verification.verified_at = timezone.now()
        verification.save()
        from apps.production.state_machine import transition

        locked = transition(locked, ProductionStage.QC_COMPLETE, actor=user)
        record_event(
            factory=locked.factory,
            actor=user,
            action=AuditAction.QC_VERIFIED,
            target=verification,
            field_name='qc_verified_quantity',
            old_value='',
            new_value=verification.qc_verified_quantity,
            reason='QC completed verification.',
        )
        return validate_controlled_run(locked, actor=user)
