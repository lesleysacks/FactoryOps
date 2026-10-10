from django.db import models
from apps.factories.models import ProductionLine


class MachineStatus(models.TextChoices):
    OPERATIONAL = 'operational', 'Operational'
    MAINTENANCE = 'maintenance', 'In Maintenance'
    OFFLINE     = 'offline',     'Offline'
    DECOMMISSIONED = 'decommissioned', 'Decommissioned'


class Machine(models.Model):
    production_line = models.ForeignKey(ProductionLine, on_delete=models.CASCADE, related_name="machines")
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, unique=True, help_text="Unique asset ID (e.g., MC-012)")
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=MachineStatus.choices,
        default=MachineStatus.OFFLINE
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.code} ({self.name})"
