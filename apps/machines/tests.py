"""
Tests for Machines App
"""

import pytest
from apps.machines.models import Machine


@pytest.mark.django_db
def test_machine_creation(production_line):
    machine = Machine.objects.create(
        production_line=production_line,
        name="CNC Router X1",
        code="CNC-01",
        status="operational"
    )
    assert machine.production_line == production_line
    assert machine.code == "CNC-01"
    assert machine.status == "operational"
    assert str(machine) == "CNC-01 (CNC Router X1)"
