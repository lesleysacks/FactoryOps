"""V1.1 gates, variance, QC permissions, and legacy runs."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.accounts.models import User
from apps.catalog.services import seed_sanitary_catalog
from apps.factories.models import Factory
from apps.machines.models import Machine, MachineStatus
from apps.production.models import (
    MAX_QC_PHOTO_BYTES,
    ProductionOutput,
    ProductionRun,
    ProductionRunStatus,
    ProductionStage,
    QCVerificationStatus,
)
from apps.production.qc import add_qc_photo, complete_qc, save_qc_verification
from apps.audit.services import apply_controlled_correction
from apps.production.state_machine import (
    accept_variance,
    create_controlled_run,
    gate_requirements,
    revalidate_after_correction,
    transition,
)
from apps.production.variance import (
    VARIANCE_EXCEPTION,
    VARIANCE_INSUFFICIENT,
    VARIANCE_OK,
    VARIANCE_WITHIN_TOLERANCE,
    compute_variance,
    expected_individual_units,
    variance_for_run,
    variance_to_json,
)


@pytest.fixture
def operator(db, factory):
    return User.objects.create_user(
        username='ctrl_operator',
        password='Password123!',
        role=User.Role.OPERATOR,
        factory=factory,
    )


@pytest.fixture
def qc_user(db, factory):
    return User.objects.create_user(
        username='ctrl_qc',
        password='Password123!',
        role=User.Role.QC,
        factory=factory,
    )


@pytest.fixture
def supervisor(db, factory):
    return User.objects.create_user(
        username='ctrl_supervisor',
        password='Password123!',
        role=User.Role.SUPERVISOR,
        factory=factory,
    )


@pytest.fixture
def machine(db, production_line):
    return Machine.objects.create(
        production_line=production_line,
        name='Pad Press',
        code='MC-CTRL-001',
        status=MachineStatus.OPERATIONAL,
    )


@pytest.fixture
def catalog(factory):
    seed_sanitary_catalog(factory)
    from apps.catalog.models import Packaging, Product

    product = Product.objects.get(factory=factory, code='SANITARY-PADS')
    return {
        'product': product,
        'variant': product.variants.get(code='MAXIS'),
        'packaging': Packaging.objects.get(factory=factory, code="15's"),
        'base': Packaging.objects.get(factory=factory, code="10's"),
    }


def _controlled(operator, catalog, machine, packs='20'):
    return create_controlled_run(
        operator,
        product=catalog['product'],
        variant=catalog['variant'],
        packaging=catalog['packaging'],
        line=machine.production_line,
        machine=machine,
        planned_pack_quantity=Decimal(packs),
    )


def test_expected_quantity_twenty_by_fifteens(operator, catalog, machine):
    run = _controlled(operator, catalog, machine, '20')
    assert expected_individual_units(run) == Decimal('3000.000')


def test_expected_is_undefined_without_configuration(factory):
    run = ProductionRun.objects.create(factory=factory, reference='LEGACY-1')
    assert run.stage is None
    assert expected_individual_units(run) is None


def test_cross_factory_configuration_rejected(operator, catalog, machine):
    other = Factory.objects.create(name='West Plant')
    other_product_factory = other
    from apps.catalog.models import Product

    foreign = Product.objects.create(
        factory=other_product_factory,
        code='OTHER',
        name='Other',
    )
    with pytest.raises(ValidationError):
        create_controlled_run(
            operator,
            product=foreign,
            variant=catalog['variant'],
            packaging=catalog['packaging'],
            line=machine.production_line,
            machine=machine,
            planned_pack_quantity=Decimal('20'),
        )


def test_gates_block_until_output_exists(operator, catalog, machine):
    run = _controlled(operator, catalog, machine)
    assert run.stage == ProductionStage.INPUTS_COMPLETE
    started = transition(run, ProductionStage.PRODUCTION_ACTIVE, actor=operator)
    assert started.status == ProductionRunStatus.IN_PROGRESS
    assert started.started_at is not None
    blocked = gate_requirements(started, ProductionStage.OUTPUT_RECORDED)
    assert blocked['ok'] is False
    assert 'At least one production output' in blocked['missing']
    with pytest.raises(ValidationError):
        transition(started, ProductionStage.OUTPUT_RECORDED, actor=operator)
    ProductionOutput.objects.create(
        production_run=started,
        output_name='Pads',
        quantity=Decimal('3400'),
    )
    recorded = transition(started, ProductionStage.OUTPUT_RECORDED, actor=operator)
    submitted = transition(recorded, ProductionStage.QC_REQUIRED, actor=operator)
    assert submitted.stage == ProductionStage.QC_REQUIRED


def test_illegal_transition_and_legacy_run_rejected(operator, factory, catalog, machine):
    run = _controlled(operator, catalog, machine)
    with pytest.raises(ValidationError):
        transition(run, ProductionStage.QC_COMPLETE, actor=operator)
    legacy = ProductionRun.objects.create(factory=factory, reference='LEGACY-2')
    with pytest.raises(ValidationError):
        transition(legacy, ProductionStage.INPUTS_COMPLETE, actor=operator)


def test_operator_cannot_complete_qc(operator, qc_user, catalog, machine):
    run = _submit(operator, catalog, machine, Decimal('3400'))
    with pytest.raises(ValidationError):
        save_qc_verification(
            operator,
            run,
            variant=catalog['variant'],
            packaging=catalog['packaging'],
            qc_verified_quantity=Decimal('3000'),
        )
    save_qc_verification(
        qc_user,
        run,
        variant=catalog['variant'],
        packaging=catalog['packaging'],
        qc_verified_quantity=Decimal('3000'),
    )
    photo = SimpleUploadedFile('pad.jpg', b'\xff\xd8\xff\xd9', content_type='image/jpeg')
    with pytest.raises(ValidationError):
        add_qc_photo(operator, run, photo)
    saved = add_qc_photo(
        qc_user,
        run,
        SimpleUploadedFile('pad.jpg', b'\xff\xd8\xff\xd9', content_type='image/jpeg'),
        caption='Carton',
    )
    assert saved.qc_verification.production_run_id == run.id
    assert saved.uploaded_by == qc_user
    assert saved.image.name.startswith('qc/')
    with pytest.raises(ValidationError):
        add_qc_photo(
            qc_user,
            run,
            SimpleUploadedFile('pad.gif', b'GIF89a', content_type='image/gif'),
        )
    with pytest.raises(ValidationError):
        add_qc_photo(
            qc_user,
            run,
            SimpleUploadedFile(
                'pad.jpg',
                b'0' * (MAX_QC_PHOTO_BYTES + 1),
                content_type='image/jpeg',
            ),
        )


def test_qc_cannot_edit_operator_output_via_verification(operator, qc_user, catalog, machine):
    run = _submit(operator, catalog, machine, Decimal('3400'))
    output_id = run.outputs.get().pk
    save_qc_verification(
        qc_user,
        run,
        variant=catalog['variant'],
        packaging=catalog['packaging'],
        qc_verified_quantity=Decimal('3000'),
    )
    output = ProductionOutput.objects.get(pk=output_id)
    assert output.quantity == Decimal('3400.000')
    run.refresh_from_db()
    assert run.variant_id == catalog['variant'].id


def test_variance_recorded_and_qc_examples():
    exception = compute_variance(
        Decimal('3000'),
        Decimal('3400'),
        Decimal('3000'),
        tolerance_pct=Decimal('0'),
    )
    assert exception['recorded_vs_expected'] == Decimal('400.000')
    assert exception['recorded_vs_expected_pct'] == Decimal('13.333')
    assert exception['qc_vs_expected'] == Decimal('0.000')
    assert exception['status'] == VARIANCE_EXCEPTION

    ok = compute_variance(
        Decimal('3000'),
        Decimal('3000'),
        Decimal('3000'),
        tolerance_pct=Decimal('0'),
    )
    assert ok['qc_vs_expected'] == Decimal('0.000')
    assert ok['status'] == VARIANCE_OK

    within = compute_variance(
        Decimal('3000'),
        Decimal('3001'),
        Decimal('3000'),
        tolerance_pct=Decimal('1'),
    )
    assert within['status'] == VARIANCE_WITHIN_TOLERANCE
    assert compute_variance(None, Decimal('1'), Decimal('1'))['status'] == VARIANCE_INSUFFICIENT
    with pytest.raises(ValidationError):
        compute_variance(Decimal('1'), Decimal('-1'), Decimal('1'))
    tiny = compute_variance(
        Decimal('1'),
        Decimal('1.0004'),
        Decimal('1'),
        tolerance_pct=Decimal('0'),
    )
    assert tiny['recorded'] == Decimal('1.000')


def test_variance_json_uses_strings():
    payload = variance_to_json(compute_variance(Decimal('10'), Decimal('10'), Decimal('10')))
    assert payload['expected'] == '10.000'
    assert payload['status'] == VARIANCE_OK


def test_qc_completion_opens_exception_and_supervisor_can_accept(
    operator, qc_user, supervisor, catalog, machine,
):
    run = _ready_for_qc_completion(operator, qc_user, catalog, machine, Decimal('3400'), Decimal('3000'))
    finished = complete_qc(qc_user, run)
    assert finished.stage == ProductionStage.EXCEPTION
    assert finished.qc_verification.recorded_quantity == Decimal('3400.000')
    assert finished.qc_verification.expected_quantity == Decimal('3000.000')
    assert finished.qc_verification.qc_verified_quantity == Decimal('3000.000')
    result = variance_for_run(finished)
    assert result['status'] == VARIANCE_EXCEPTION
    with pytest.raises(ValidationError):
        accept_variance(finished, actor=operator, reason='no')
    accepted = accept_variance(
        finished,
        actor=supervisor,
        reason='Count checked on the floor and accepted',
    )
    assert accepted.stage == ProductionStage.COMPLETED
    assert accepted.status == ProductionRunStatus.COMPLETED
    output = accepted.outputs.get()
    assert output.quantity == Decimal('3400.000')


def test_supervisor_correction_resolves_exception(operator, qc_user, supervisor, catalog, machine):
    run = _ready_for_qc_completion(operator, qc_user, catalog, machine, Decimal('3400'), Decimal('3000'))
    finished = complete_qc(qc_user, run)
    original = finished.outputs.get().quantity
    apply_controlled_correction(
        finished.qc_verification,
        'recorded_quantity',
        Decimal('3000'),
        actor=supervisor,
        reason='Recount matches QC',
    )
    resolved = revalidate_after_correction(
        finished,
        actor=supervisor,
        reason='Recount matches QC',
    )
    assert resolved.stage == ProductionStage.COMPLETED
    assert resolved.outputs.get().quantity == original


def test_matching_qc_completes_without_exception(operator, qc_user, catalog, machine):
    run = _ready_for_qc_completion(operator, qc_user, catalog, machine, Decimal('3000'), Decimal('3000'))
    finished = complete_qc(qc_user, run)
    assert finished.stage == ProductionStage.COMPLETED
    assert finished.qc_verification.status == QCVerificationStatus.VERIFIED


def test_operator_http_cannot_open_qc(client, operator, factory):
    client.force_login(operator)
    response = client.get(reverse('dashboard:qc_queue'))
    assert response.status_code == 403


def test_qc_form_keeps_saved_variant(client, operator, qc_user, catalog, machine):
    run = _submit(operator, catalog, machine, Decimal('3400'))
    client.force_login(qc_user)
    response = client.post(reverse('dashboard:qc_verification', args=[run.pk]), {
        'form': 'details',
        'variant': catalog['variant'].pk,
        'packaging': catalog['packaging'].pk,
        'qc_verified_quantity': '3000',
    })
    assert response.status_code == 302
    page = client.get(reverse('dashboard:qc_verification', args=[run.pk]))
    html = page.content.decode()
    assert f'value="{catalog["variant"].pk}" selected' in html
    assert '3000' in html


def test_qc_http_cannot_configure(client, qc_user):
    client.force_login(qc_user)
    response = client.get(reverse('dashboard:configure_run'))
    assert response.status_code == 403


def test_two_factories_do_not_share_queue(client, operator, qc_user, catalog, machine):
    run = _submit(operator, catalog, machine, Decimal('10'))
    other = Factory.objects.create(name='Isolated Plant')
    other_qc = User.objects.create_user(
        username='other_qc',
        password='Password123!',
        role=User.Role.QC,
        factory=other,
    )
    client.force_login(other_qc)
    response = client.get(reverse('dashboard:qc_verification', args=[run.pk]))
    assert response.status_code == 404
    client.force_login(qc_user)
    visible = client.get(reverse('dashboard:qc_queue'))
    assert visible.status_code == 200
    assert run.reference in visible.content.decode()


def _submit(operator, catalog, machine, quantity):
    run = _controlled(operator, catalog, machine)
    run = transition(run, ProductionStage.PRODUCTION_ACTIVE, actor=operator)
    ProductionOutput.objects.create(
        production_run=run,
        output_name='Pads',
        quantity=quantity,
    )
    run = transition(run, ProductionStage.OUTPUT_RECORDED, actor=operator)
    return transition(run, ProductionStage.QC_REQUIRED, actor=operator)


def _ready_for_qc_completion(operator, qc_user, catalog, machine, recorded, verified):
    run = _submit(operator, catalog, machine, recorded)
    save_qc_verification(
        qc_user,
        run,
        variant=catalog['variant'],
        packaging=catalog['packaging'],
        qc_verified_quantity=verified,
    )
    add_qc_photo(
        qc_user,
        run,
        SimpleUploadedFile('pad.png', b'\x89PNG\r\n', content_type='image/png'),
    )
    return run
