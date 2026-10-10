"""Append-only audit events and controlled corrections."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.accounts.models import User
from apps.audit.models import AuditAction, AuditEvent
from apps.audit.services import apply_controlled_correction, record_event
from apps.production.models import QCVerification


@pytest.fixture
def supervisor(db, factory):
    return User.objects.create_user(
        username='audit_supervisor',
        password='Password123!',
        role=User.Role.SUPERVISOR,
        factory=factory,
    )


@pytest.fixture
def operator(db, factory):
    return User.objects.create_user(
        username='audit_operator',
        password='Password123!',
        role=User.Role.OPERATOR,
        factory=factory,
    )


@pytest.fixture
def run(db, factory):
    from apps.production.models import ProductionRun

    return ProductionRun.objects.create(factory=factory, reference='PR-AUDIT-1')


def test_stage_event_records_who_and_when(factory, supervisor, run):
    event = record_event(
        factory=factory,
        actor=supervisor,
        action=AuditAction.STAGE_CHANGE,
        target=run,
        field_name='stage',
        old_value='DRAFT',
        new_value='INPUTS_COMPLETE',
    )
    assert event.actor == supervisor
    assert event.old_value == 'DRAFT'
    assert event.new_value == 'INPUTS_COMPLETE'
    assert event.created_at is not None


def test_audit_event_cannot_be_changed_or_deleted(factory, supervisor, run):
    event = record_event(
        factory=factory,
        actor=supervisor,
        action=AuditAction.STAGE_CHANGE,
        target=run,
        field_name='stage',
        old_value='DRAFT',
        new_value='CANCELLED',
    )
    event.reason = 'changed'
    with pytest.raises(ValidationError):
        event.save()
    with pytest.raises(ValidationError):
        event.delete()
    with pytest.raises(ValidationError):
        AuditEvent.objects.all().delete()


def test_correction_requires_reason_and_preserves_original_output(factory, supervisor, operator, run):
    from apps.production.models import ProductionOutput

    output = ProductionOutput.objects.create(
        production_run=run,
        output_name='Pads',
        quantity=Decimal('3400'),
    )
    verification = QCVerification.objects.create(
        production_run=run,
        recorded_quantity=Decimal('3400'),
        qc_verified_quantity=Decimal('3000'),
    )
    with pytest.raises(ValidationError):
        apply_controlled_correction(
            verification,
            'recorded_quantity',
            Decimal('3000'),
            actor=operator,
            reason='Operator cannot correct',
        )
    with pytest.raises(ValidationError):
        apply_controlled_correction(
            verification,
            'recorded_quantity',
            Decimal('3000'),
            actor=supervisor,
            reason='   ',
        )
    apply_controlled_correction(
        verification,
        'recorded_quantity',
        Decimal('3000'),
        actor=supervisor,
        reason='Packaging count mismatch confirmed during QC',
    )
    output.refresh_from_db()
    verification.refresh_from_db()
    assert output.quantity == Decimal('3400.000')
    assert verification.recorded_quantity == Decimal('3000.000')
    event = AuditEvent.objects.get(action=AuditAction.CORRECTION)
    assert Decimal(event.old_value) == Decimal('3400')
    assert Decimal(event.new_value) == Decimal('3000')
    assert 'Packaging count mismatch' in event.reason
    assert event.actor == supervisor
