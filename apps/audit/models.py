"""
FactoryOps Audit — append-only record of who changed what, when, and why.
"""

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models


class AuditAction(models.TextChoices):
    STAGE_CHANGE = 'STAGE_CHANGE', 'Stage change'
    QC_VERIFIED = 'QC_VERIFIED', 'QC verified'
    CORRECTION = 'CORRECTION', 'Correction'
    EXCEPTION_ACCEPTED = 'EXCEPTION_ACCEPTED', 'Exception accepted'


class AuditEventQuerySet(models.QuerySet):
    def delete(self):
        raise ValidationError('Audit events cannot be deleted.')

    def update(self, **kwargs):
        raise ValidationError('Audit events cannot be changed.')


class AuditEvent(models.Model):
    factory = models.ForeignKey(
        'factories.Factory',
        on_delete=models.PROTECT,
        related_name='audit_events',
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_events',
    )
    action = models.CharField(max_length=50, choices=AuditAction.choices)
    target_content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT)
    target_object_id = models.PositiveBigIntegerField()
    target = GenericForeignKey('target_content_type', 'target_object_id')
    field_name = models.CharField(max_length=100, blank=True)
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = AuditEventQuerySet.as_manager()

    class Meta:
        verbose_name = 'Audit Event'
        verbose_name_plural = 'Audit Events'
        ordering = ('-created_at',)
        indexes = [
            models.Index(fields=['factory', 'created_at']),
            models.Index(fields=['target_content_type', 'target_object_id']),
        ]

    def __str__(self):
        return f'{self.action} — {self.created_at}'

    def clean(self):
        super().clean()
        if self.action in (
            AuditAction.CORRECTION,
            AuditAction.EXCEPTION_ACCEPTED,
        ) and not (self.reason or '').strip():
            raise ValidationError({
                'reason': 'A reason is required for corrections and exception resolution.',
            })

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError('Audit events are append-only and cannot be changed.')
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Audit events cannot be deleted.')
