"""
Tests for Orders App — M12 Reservations, Availability & Fulfilment
"""

from datetime import date, datetime, timezone as dt_timezone
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.factories.models import Factory
from apps.orders.models import (
    Customer,
    CustomerOrder,
    CustomerOrderFulfilmentStatus,
    CustomerOrderLine,
    CustomerOrderStatus,
    DispatchAllocation,
    OrderReservation,
)
from apps.orders.services import calculate_available_stock
from apps.production.models import (
    FinishedGood,
    FinishedGoodDispatch,
    FinishedGoodStockRecord,
    Warehouse,
)


@pytest.fixture
def customer(db, factory):
    return Customer.objects.create(
        factory=factory,
        code='CUST-001',
        name='Harbour Packers',
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
    )


@pytest.fixture
def order_line(db, customer_order, finished_good):
    return CustomerOrderLine.objects.create(
        customer_order=customer_order,
        finished_good=finished_good,
        quantity=Decimal('100.000'),
    )


@pytest.fixture
def stock_record(db, warehouse, finished_good):
    return FinishedGoodStockRecord.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        recording_date=date(2026, 10, 1),
        opening_quantity=Decimal('80.000'),
        closing_quantity=Decimal('150.000'),
    )


@pytest.mark.django_db
def test_reservation_creation(warehouse, order_line):
    reservation = OrderReservation.objects.create(
        warehouse=warehouse,
        order_line=order_line,
        quantity=Decimal('50.000'),
    )
    assert reservation.warehouse == warehouse
    assert reservation.order_line == order_line
    assert reservation.quantity == Decimal('50.000')
    assert reservation.created_at is not None
    assert warehouse.reservations.count() == 1
    assert order_line.reservations.count() == 1


@pytest.mark.django_db
def test_reservation_quantity_validation(warehouse, order_line):
    zero = OrderReservation(
        warehouse=warehouse,
        order_line=order_line,
        quantity=Decimal('0.000'),
    )
    with pytest.raises(ValidationError) as extra_info:
        zero.save()
    assert 'quantity' in extra_info.value.message_dict

    negative = OrderReservation(
        warehouse=warehouse,
        order_line=order_line,
        quantity=Decimal('-10.000'),
    )
    with pytest.raises(ValidationError) as extra_info:
        negative.save()
    assert 'quantity' in extra_info.value.message_dict


@pytest.mark.django_db
def test_cross_factory_reservation_rejection(order_line):
    other_factory = Factory.objects.create(name='South Plant', location='Building 2')
    other_warehouse = Warehouse.objects.create(
        factory=other_factory,
        code='FG-MAIN',
        name='South Finished Goods Store',
    )
    reservation = OrderReservation(
        warehouse=other_warehouse,
        order_line=order_line,
        quantity=Decimal('10.000'),
    )
    with pytest.raises(ValidationError) as extra_info:
        reservation.save()
    assert 'warehouse' in extra_info.value.message_dict


@pytest.mark.django_db
def test_availability_calculation(warehouse, finished_good, order_line, stock_record):
    OrderReservation.objects.create(
        warehouse=warehouse,
        order_line=order_line,
        quantity=Decimal('40.000'),
    )
    result = calculate_available_stock(warehouse, finished_good)
    assert result['on_hand_quantity'] == Decimal('150.000')
    assert result['reserved_quantity'] == Decimal('40.000')
    assert result['available_quantity'] == Decimal('110.000')
    assert result['recording_date'] == date(2026, 10, 1)


@pytest.mark.django_db
def test_multiple_reservation_calculation(
    warehouse, finished_good, order_line, stock_record
):
    OrderReservation.objects.create(
        warehouse=warehouse,
        order_line=order_line,
        quantity=Decimal('50.000'),
    )
    OrderReservation.objects.create(
        warehouse=warehouse,
        order_line=order_line,
        quantity=Decimal('25.000'),
    )
    OrderReservation.objects.create(
        warehouse=warehouse,
        order_line=order_line,
        quantity=Decimal('10.000'),
    )
    result = calculate_available_stock(warehouse, finished_good)
    assert result['reserved_quantity'] == Decimal('85.000')
    assert result['available_quantity'] == Decimal('65.000')


@pytest.mark.django_db
def test_zero_available_stock(warehouse, finished_good, order_line, stock_record):
    OrderReservation.objects.create(
        warehouse=warehouse,
        order_line=order_line,
        quantity=Decimal('150.000'),
    )
    result = calculate_available_stock(warehouse, finished_good)
    assert result['available_quantity'] == Decimal('0.000')


@pytest.mark.django_db
def test_availability_uses_latest_counted_closing(
    warehouse, finished_good, order_line, stock_record
):
    FinishedGoodStockRecord.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        recording_date=date(2026, 10, 2),
        opening_quantity=Decimal('150.000'),
        closing_quantity=Decimal('90.000'),
    )
    OrderReservation.objects.create(
        warehouse=warehouse,
        order_line=order_line,
        quantity=Decimal('10.000'),
    )
    result = calculate_available_stock(warehouse, finished_good)
    assert result['recording_date'] == date(2026, 10, 2)
    assert result['on_hand_quantity'] == Decimal('90.000')
    assert result['available_quantity'] == Decimal('80.000')


@pytest.mark.django_db
def test_reservation_does_not_reduce_inventory_or_create_dispatch(
    warehouse, finished_good, order_line, stock_record
):
    OrderReservation.objects.create(
        warehouse=warehouse,
        order_line=order_line,
        quantity=Decimal('50.000'),
    )
    stock_record.refresh_from_db()
    assert stock_record.closing_quantity == Decimal('150.000')
    assert FinishedGoodDispatch.objects.filter(
        warehouse=warehouse,
        finished_good=finished_good,
    ).count() == 0


@pytest.mark.django_db
def test_historical_reservations_remain_separate(warehouse, order_line):
    first = OrderReservation.objects.create(
        warehouse=warehouse,
        order_line=order_line,
        quantity=Decimal('50.000'),
    )
    second = OrderReservation.objects.create(
        warehouse=warehouse,
        order_line=order_line,
        quantity=Decimal('25.000'),
    )
    third = OrderReservation.objects.create(
        warehouse=warehouse,
        order_line=order_line,
        quantity=Decimal('10.000'),
    )
    assert first.pk != second.pk != third.pk
    quantities = list(
        OrderReservation.objects.filter(order_line=order_line)
        .order_by('id')
        .values_list('quantity', flat=True)
    )
    assert quantities == [Decimal('50.000'), Decimal('25.000'), Decimal('10.000')]


@pytest.mark.django_db
def test_reservation_string_representation(warehouse, order_line):
    reservation = OrderReservation.objects.create(
        warehouse=warehouse,
        order_line=order_line,
        quantity=Decimal('50.000'),
    )
    assert str(reservation) == 'SO-20261001-001 — FG-MAIN — 50.000'


@pytest.mark.django_db
def test_order_defaults_to_unfulfilled(customer_order):
    assert customer_order.status == CustomerOrderStatus.OPEN
    assert customer_order.fulfilment_status == CustomerOrderFulfilmentStatus.UNFULFILLED


@pytest.mark.django_db
def test_fulfilment_status_calculation_unfulfilled(customer_order, order_line):
    customer_order.calculate_fulfilment()
    customer_order.refresh_from_db()
    assert customer_order.fulfilment_status == CustomerOrderFulfilmentStatus.UNFULFILLED
    assert customer_order.status == CustomerOrderStatus.OPEN


@pytest.mark.django_db
def test_partial_fulfilment(customer_order, order_line, warehouse, finished_good):
    dispatch = FinishedGoodDispatch.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('40.000'),
        dispatched_at=datetime(2026, 10, 1, 8, 0, tzinfo=dt_timezone.utc),
    )
    DispatchAllocation.objects.create(
        dispatch=dispatch,
        order_line=order_line,
        quantity=Decimal('40.000'),
    )
    customer_order.calculate_fulfilment()
    customer_order.refresh_from_db()
    assert customer_order.fulfilment_status == (
        CustomerOrderFulfilmentStatus.PARTIALLY_FULFILLED
    )
    assert customer_order.status == CustomerOrderStatus.OPEN


@pytest.mark.django_db
def test_full_fulfilment(customer_order, order_line, warehouse, finished_good):
    dispatch = FinishedGoodDispatch.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('100.000'),
        dispatched_at=datetime(2026, 10, 1, 8, 0, tzinfo=dt_timezone.utc),
    )
    DispatchAllocation.objects.create(
        dispatch=dispatch,
        order_line=order_line,
        quantity=Decimal('100.000'),
    )
    customer_order.calculate_fulfilment()
    customer_order.refresh_from_db()
    assert customer_order.fulfilment_status == CustomerOrderFulfilmentStatus.FULFILLED
    assert customer_order.status == CustomerOrderStatus.OPEN


@pytest.mark.django_db
def test_allocation_does_not_auto_update_fulfilment(
    customer_order, order_line, warehouse, finished_good
):
    dispatch = FinishedGoodDispatch.objects.create(
        warehouse=warehouse,
        finished_good=finished_good,
        quantity=Decimal('100.000'),
        dispatched_at=datetime(2026, 10, 1, 8, 0, tzinfo=dt_timezone.utc),
    )
    DispatchAllocation.objects.create(
        dispatch=dispatch,
        order_line=order_line,
        quantity=Decimal('100.000'),
    )
    customer_order.refresh_from_db()
    assert customer_order.fulfilment_status == CustomerOrderFulfilmentStatus.UNFULFILLED


@pytest.mark.django_db
def test_inactive_warehouse_reservation_rejected(warehouse, order_line):
    warehouse.is_active = False
    warehouse.save()
    reservation = OrderReservation(
        warehouse=warehouse,
        order_line=order_line,
        quantity=Decimal('10.000'),
    )
    with pytest.raises(ValidationError) as extra_info:
        reservation.save()
    assert 'warehouse' in extra_info.value.message_dict
