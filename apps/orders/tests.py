"""
Tests for Orders App — M11 Customer Orders & Dispatch Allocation Foundations
"""

from datetime import date, datetime, timezone as dt_timezone
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.factories.models import Factory
from apps.orders.models import (
    Customer,
    CustomerOrder,
    CustomerOrderLine,
    CustomerOrderStatus,
    DispatchAllocation,
)
from apps.production.models import (
    FinishedGood,
    FinishedGoodDispatch,
    Warehouse,
)


@pytest.fixture
def customer(db, factory):
    return Customer.objects.create(
        factory=factory,
        code='CUST-001',
        name='Harbour Packers',
        contact_name='Amina Ndlovu',
        email='amina@harbourpackers.example',
        phone='+27 21 000 0000',
    )


@pytest.fixture
def finished_good(db, factory):
    return FinishedGood.objects.create(
        factory=factory,
        code='CRATE-001',
        name='Plastic Crates',
    )


@pytest.fixture
def warehouse(db, factory):
    return Warehouse.objects.create(
        factory=factory,
        code='FG-MAIN',
        name='Finished Goods Main Store',
    )


@pytest.fixture
def customer_order(db, factory, customer):
    return CustomerOrder.objects.create(
        factory=factory,
        customer=customer,
        reference='SO-20261001-001',
        order_date=date(2026, 10, 1),
        notes='Weekly crate order',
    )


@pytest.fixture
def order_line(db, customer_order, finished_good):
    return CustomerOrderLine.objects.create(
        customer_order=customer_order,
        finished_good=finished_good,
        quantity=Decimal('150.000'),
    )


@pytest.fixture
def dispatch(db, warehouse, finished_good):
    return FinishedGoodDispatch.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('100.000'),
        dispatched_at=datetime(2026, 10, 1, 8, 0, tzinfo=dt_timezone.utc),
        reference='FG-OUT-001',
    )


@pytest.mark.django_db
def test_customer_creation(customer, factory):
    assert customer.factory == factory
    assert customer.code == 'CUST-001'
    assert customer.name == 'Harbour Packers'
    assert customer.contact_name == 'Amina Ndlovu'
    assert customer.email == 'amina@harbourpackers.example'
    assert customer.phone == '+27 21 000 0000'
    assert customer.is_active is True
    assert customer.created_at is not None
    assert customer.updated_at is not None
    assert factory.customers.count() == 1


@pytest.mark.django_db
def test_customer_code_uniqueness(factory, customer):
    duplicate = Customer(
        factory=factory,
        code='CUST-001',
        name='Duplicate Packers',
    )
    with pytest.raises(ValidationError):
        duplicate.save()


@pytest.mark.django_db
def test_same_customer_code_allowed_across_factories(factory, customer):
    other_factory = Factory.objects.create(name='South Plant', location='Building 2')
    other = Customer.objects.create(
        factory=other_factory,
        code='CUST-001',
        name='South Packers',
    )
    assert other.code == customer.code
    assert other.factory != customer.factory
    assert Customer.objects.filter(code='CUST-001').count() == 2


@pytest.mark.django_db
def test_inactive_factory_customer_rejected(factory):
    factory.is_active = False
    factory.save()
    customer = Customer(
        factory=factory,
        code='CUST-099',
        name='Harbour Packers',
    )
    with pytest.raises(ValidationError) as extra_info:
        customer.save()
    assert 'factory' in extra_info.value.message_dict


@pytest.mark.django_db
def test_inactive_customer_order_rejected(factory, customer):
    customer.is_active = False
    customer.save()
    order = CustomerOrder(
        factory=factory,
        customer=customer,
        reference='SO-20261001-099',
        order_date=date(2026, 10, 1),
    )
    with pytest.raises(ValidationError) as extra_info:
        order.save()
    assert 'customer' in extra_info.value.message_dict


@pytest.mark.django_db
def test_order_creation(customer_order, factory, customer):
    assert customer_order.factory == factory
    assert customer_order.customer == customer
    assert customer_order.reference == 'SO-20261001-001'
    assert customer_order.order_date == date(2026, 10, 1)
    assert customer_order.status == CustomerOrderStatus.OPEN
    assert customer_order.notes == 'Weekly crate order'
    assert customer_order.created_at is not None
    assert factory.customer_orders.count() == 1
    assert customer.orders.count() == 1


@pytest.mark.django_db
def test_order_status_behaviour(factory, customer):
    order = CustomerOrder.objects.create(
        factory=factory,
        customer=customer,
        reference='SO-20261001-010',
        order_date=date(2026, 10, 1),
    )
    assert order.status == CustomerOrderStatus.OPEN

    order.status = CustomerOrderStatus.PARTIALLY_ALLOCATED
    order.save()
    order.refresh_from_db()
    assert order.status == CustomerOrderStatus.PARTIALLY_ALLOCATED

    order.status = CustomerOrderStatus.ALLOCATED
    order.save()
    order.refresh_from_db()
    assert order.status == CustomerOrderStatus.ALLOCATED

    order.status = CustomerOrderStatus.CANCELLED
    order.save()
    order.refresh_from_db()
    assert order.status == CustomerOrderStatus.CANCELLED


@pytest.mark.django_db
def test_invalid_order_status_rejected(factory, customer):
    order = CustomerOrder(
        factory=factory,
        customer=customer,
        reference='SO-20261001-011',
        order_date=date(2026, 10, 1),
        status='INVOICED',
    )
    with pytest.raises(ValidationError) as extra_info:
        order.save()
    assert 'status' in extra_info.value.message_dict


@pytest.mark.django_db
def test_order_customer_factory_mismatch_rejected(factory, customer):
    other_factory = Factory.objects.create(name='South Plant', location='Building 2')
    order = CustomerOrder(
        factory=other_factory,
        customer=customer,
        reference='SO-SOUTH-001',
        order_date=date(2026, 10, 1),
    )
    with pytest.raises(ValidationError) as extra_info:
        order.save()
    assert 'customer' in extra_info.value.message_dict


@pytest.mark.django_db
def test_order_line_creation(order_line, customer_order, finished_good):
    assert order_line.customer_order == customer_order
    assert order_line.finished_good == finished_good
    assert order_line.quantity == Decimal('150.000')
    assert order_line.created_at is not None
    assert customer_order.lines.count() == 1
    assert finished_good.order_lines.count() == 1


@pytest.mark.django_db
def test_order_line_quantity_validation(customer_order, finished_good):
    zero = CustomerOrderLine(
        customer_order=customer_order,
        finished_good=finished_good,
        quantity=Decimal('0.000'),
    )
    with pytest.raises(ValidationError) as extra_info:
        zero.save()
    assert 'quantity' in extra_info.value.message_dict

    negative = CustomerOrderLine(
        customer_order=customer_order,
        finished_good=finished_good,
        quantity=Decimal('-10.000'),
    )
    with pytest.raises(ValidationError) as extra_info:
        negative.save()
    assert 'quantity' in extra_info.value.message_dict


@pytest.mark.django_db
def test_order_line_finished_good_factory_mismatch_rejected(
    customer_order, finished_good
):
    other_factory = Factory.objects.create(name='South Plant', location='Building 2')
    other_good = FinishedGood.objects.create(
        factory=other_factory,
        code='CRATE-SOUTH',
        name='South Crates',
    )
    line = CustomerOrderLine(
        customer_order=customer_order,
        finished_good=other_good,
        quantity=Decimal('10.000'),
    )
    with pytest.raises(ValidationError) as extra_info:
        line.save()
    assert 'finished_good' in extra_info.value.message_dict


@pytest.mark.django_db
def test_dispatch_allocation_creation(dispatch, order_line):
    allocation = DispatchAllocation.objects.create(
        dispatch=dispatch,
        order_line=order_line,
        quantity=Decimal('100.000'),
    )
    assert allocation.dispatch == dispatch
    assert allocation.order_line == order_line
    assert allocation.quantity == Decimal('100.000')
    assert allocation.created_at is not None
    assert dispatch.allocations.count() == 1
    assert order_line.allocations.count() == 1


@pytest.mark.django_db
def test_dispatch_allocation_quantity_validation(dispatch, order_line):
    zero = DispatchAllocation(
        dispatch=dispatch,
        order_line=order_line,
        quantity=Decimal('0.000'),
    )
    with pytest.raises(ValidationError) as extra_info:
        zero.save()
    assert 'quantity' in extra_info.value.message_dict

    negative = DispatchAllocation(
        dispatch=dispatch,
        order_line=order_line,
        quantity=Decimal('-50.000'),
    )
    with pytest.raises(ValidationError) as extra_info:
        negative.save()
    assert 'quantity' in extra_info.value.message_dict


@pytest.mark.django_db
def test_cross_factory_allocation_rejection(order_line):
    other_factory = Factory.objects.create(name='South Plant', location='Building 2')
    other_warehouse = Warehouse.objects.create(
        factory=other_factory,
        code='FG-MAIN',
        name='South Finished Goods Store',
    )
    other_good = FinishedGood.objects.create(
        factory=other_factory,
        code='CRATE-001',
        name='Plastic Crates',
    )
    other_dispatch = FinishedGoodDispatch.objects.create(
        warehouse=other_warehouse,
        finished_good=other_good,
        quantity=Decimal('100.000'),
        dispatched_at=datetime(2026, 10, 1, 8, 0, tzinfo=dt_timezone.utc),
    )
    allocation = DispatchAllocation(
        dispatch=other_dispatch,
        order_line=order_line,
        quantity=Decimal('50.000'),
    )
    with pytest.raises(ValidationError) as extra_info:
        allocation.save()
    assert 'dispatch' in extra_info.value.message_dict


@pytest.mark.django_db
def test_allocation_finished_good_mismatch_rejected(
    factory, warehouse, customer_order, finished_good, dispatch
):
    other_good = FinishedGood.objects.create(
        factory=factory,
        code='PALLET-001',
        name='Pallets',
    )
    other_line = CustomerOrderLine.objects.create(
        customer_order=customer_order,
        finished_good=other_good,
        quantity=Decimal('20.000'),
    )
    allocation = DispatchAllocation(
        dispatch=dispatch,
        order_line=other_line,
        quantity=Decimal('10.000'),
    )
    with pytest.raises(ValidationError) as extra_info:
        allocation.save()
    assert 'dispatch' in extra_info.value.message_dict


@pytest.mark.django_db
def test_historical_allocations_remain_separate(dispatch, order_line, warehouse, finished_good):
    first = DispatchAllocation.objects.create(
        dispatch=dispatch,
        order_line=order_line,
        quantity=Decimal('100.000'),
    )
    second_dispatch = FinishedGoodDispatch.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('50.000'),
        dispatched_at=datetime(2026, 10, 1, 11, 0, tzinfo=dt_timezone.utc),
        reference='FG-OUT-002',
    )
    second = DispatchAllocation.objects.create(
        dispatch=second_dispatch,
        order_line=order_line,
        quantity=Decimal('50.000'),
    )
    other_order = CustomerOrder.objects.create(
        factory=order_line.customer_order.factory,
        customer=order_line.customer_order.customer,
        reference='SO-20261001-002',
        order_date=date(2026, 10, 1),
    )
    other_line = CustomerOrderLine.objects.create(
        customer_order=other_order,
        finished_good=finished_good,
        quantity=Decimal('200.000'),
    )
    third_dispatch = FinishedGoodDispatch.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('200.000'),
        dispatched_at=datetime(2026, 10, 1, 15, 0, tzinfo=dt_timezone.utc),
        reference='FG-OUT-003',
    )
    third = DispatchAllocation.objects.create(
        dispatch=third_dispatch,
        order_line=other_line,
        quantity=Decimal('200.000'),
    )
    assert first.pk != second.pk != third.pk
    assert order_line.allocations.count() == 2
    assert other_line.allocations.count() == 1
    quantities = list(
        DispatchAllocation.objects.filter(order_line=order_line)
        .order_by('id')
        .values_list('quantity', flat=True)
    )
    assert quantities == [Decimal('100.000'), Decimal('50.000')]


@pytest.mark.django_db
def test_allocation_does_not_alter_dispatch_or_order(
    dispatch, order_line
):
    DispatchAllocation.objects.create(
        dispatch=dispatch,
        order_line=order_line,
        quantity=Decimal('100.000'),
    )
    dispatch.refresh_from_db()
    order_line.refresh_from_db()
    order_line.customer_order.refresh_from_db()
    assert dispatch.quantity == Decimal('100.000')
    assert order_line.quantity == Decimal('150.000')
    assert order_line.customer_order.status == CustomerOrderStatus.OPEN


@pytest.mark.django_db
def test_string_representations(customer, customer_order, order_line, dispatch):
    allocation = DispatchAllocation.objects.create(
        dispatch=dispatch,
        order_line=order_line,
        quantity=Decimal('100.000'),
    )
    assert str(customer) == 'CUST-001 — Harbour Packers'
    assert str(customer_order) == 'Main Factory — SO-20261001-001'
    assert str(order_line) == 'SO-20261001-001 — CRATE-001 — 150.000'
    assert str(allocation) == 'SO-20261001-001 — CRATE-001 — 100.000'


@pytest.mark.django_db
def test_duplicate_order_reference_rejected_per_factory(factory, customer, customer_order):
    duplicate = CustomerOrder(
        factory=factory,
        customer=customer,
        reference='SO-20261001-001',
        order_date=date(2026, 10, 2),
    )
    with pytest.raises(ValidationError):
        duplicate.save()
