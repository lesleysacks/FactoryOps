"""Sync bookkeeping for external reports.

These rows track delivery. They are not a second copy of factory truth.
Source quantities, QC results, and stock movements stay on their own models.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


class SheetSyncStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    SYNCED = 'synced', 'Synced'
    FAILED = 'failed', 'Failed'


class SheetSyncRecord(models.Model):
    """One source row's delivery state for one reporting dataset."""

    dataset = models.CharField(max_length=64)
    source_model = models.CharField(max_length=120)
    source_id = models.PositiveBigIntegerField()
    source_key = models.CharField(max_length=200, unique=True)
    factory = models.ForeignKey(
        'factories.Factory',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sheet_sync_records',
    )
    payload = models.JSONField(default=list)
    payload_hash = models.CharField(max_length=64)
    status = models.CharField(
        max_length=20,
        choices=SheetSyncStatus.choices,
        default=SheetSyncStatus.PENDING,
    )
    attempt_count = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True)
    sheet_row = models.PositiveIntegerField(null=True, blank=True)
    synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Sheet sync record'
        verbose_name_plural = 'Sheet sync records'
        ordering = ('dataset', 'source_model', 'source_id')
        constraints = [
            models.UniqueConstraint(
                fields=('dataset', 'source_model', 'source_id'),
                name='unique_sheet_sync_source_row',
            ),
        ]
        indexes = [
            models.Index(fields=('status', 'next_attempt_at'), name='sheet_sync_due'),
        ]

    def __str__(self):
        return self.source_key


class SheetSyncRun(models.Model):
    """One management-visible attempt to deliver pending rows."""

    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    trigger = models.CharField(max_length=20)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sheet_sync_runs',
    )
    outcome = models.CharField(max_length=20)
    message = models.CharField(max_length=500, blank=True)
    synced_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    pending_count = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'Sheet sync run'
        verbose_name_plural = 'Sheet sync runs'
        ordering = ('-started_at',)

    def __str__(self):
        return f'{self.started_at} — {self.outcome}'


class SheetSyncLock(models.Model):
    """Single-row mutex so two syncs cannot append the same source key."""

    name = models.CharField(max_length=40, primary_key=True)
    locked_until = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name
