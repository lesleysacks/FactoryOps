"""
FactoryOps Orders — Reservation availability and fulfilment calculations.

Available stock for a warehouse/finished good:

    latest counted closing quantity − sum of reservations

Stock source of truth:
    FinishedGoodStockRecord.closing_quantity

If several stock dates exist, the record with the latest recording_date that
has a non-null closing_quantity is used. Older counts are ignored. A later
record with a blank closing quantity does not replace an earlier counted
closing. If no counted closing exists, on-hand is treated as zero.

Reservations commit stock. They do not reduce inventory and do not create
dispatches.

Fulfilment is derived from dispatch allocations versus ordered quantities.
It is calculated explicitly via CustomerOrder.calculate_fulfilment() and is
not updated on save().
"""

from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Sum

from apps.orders.models import (
    CustomerOrderFulfilmentStatus,
    DispatchAllocation,
    OrderReservation,
)
from apps.production.models import FinishedGoodStockRecord

ZERO = Decimal('0')
QUANTITY_QUANTUM = Decimal('0.001')


def _as_quantity(value):
    if value is None:
        return ZERO
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(QUANTITY_QUANTUM, rounding=ROUND_HALF_UP)


def _quantity_sum(queryset):
    total = queryset.aggregate(total=Sum('quantity'))['total']
    return _as_quantity(total)


def calculate_available_stock(warehouse, finished_good):
    stock_record = (
        FinishedGoodStockRecord.objects.filter(
            warehouse=warehouse,
            finished_good=finished_good,
            closing_quantity__isnull=False,
        )
        .order_by('-recording_date')
        .first()
    )
    on_hand = (
        _as_quantity(stock_record.closing_quantity)
        if stock_record is not None
        else ZERO
    )
    reserved = _quantity_sum(OrderReservation.objects.filter(
        warehouse=warehouse,
        order_line__finished_good=finished_good,
    ))
    available = _as_quantity(on_hand - reserved)
    return {
        'stock_record': stock_record,
        'recording_date': (
            stock_record.recording_date if stock_record is not None else None
        ),
        'on_hand_quantity': on_hand,
        'reserved_quantity': reserved,
        'available_quantity': available,
    }


def calculate_order_fulfilment(order):
    ordered = _quantity_sum(order.lines.all())
    allocated = _quantity_sum(DispatchAllocation.objects.filter(
        order_line__customer_order=order,
    ))
    if ordered == ZERO or allocated == ZERO:
        status = CustomerOrderFulfilmentStatus.UNFULFILLED
    elif allocated < ordered:
        status = CustomerOrderFulfilmentStatus.PARTIALLY_FULFILLED
    else:
        status = CustomerOrderFulfilmentStatus.FULFILLED
    return {
        'ordered_quantity': ordered,
        'allocated_quantity': allocated,
        'fulfilment_status': status,
    }


def update_order_fulfilment(order):
    result = calculate_order_fulfilment(order)
    order.fulfilment_status = result['fulfilment_status']
    order.save()
    return order
