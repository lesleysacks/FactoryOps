"""
FactoryOps Accounts — Custom User Model
"""

from django.contrib.auth.models import AbstractUser, UserManager as BaseUserManager
from django.db import models


class Role(models.TextChoices):
    ADMIN      = 'ADMIN',      'Admin'
    SUPERVISOR = 'SUPERVISOR', 'Supervisor'
    OPERATOR   = 'OPERATOR',   'Operator'
    QC         = 'QC',         'QC Inspector'


class UserManager(BaseUserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('role', Role.ADMIN)
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    Role = Role

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.OPERATOR,
        help_text="Determines what this user can access and do in the system.",
    )
    employee_id = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        unique=True,
        help_text="Factory employee number or badge ID. Must be unique if provided.",
    )
    factory = models.ForeignKey(
        'factories.Factory',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users',
        help_text="The factory this user is assigned to. Null for platform administrators.",
    )

    objects = UserManager()

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"

    @property
    def is_admin(self) -> bool:
        return self.role == Role.ADMIN

    @property
    def is_supervisor(self) -> bool:
        return self.role == Role.SUPERVISOR

    @property
    def is_operator(self) -> bool:
        return self.role == Role.OPERATOR

    @property
    def is_qc(self) -> bool:
        return self.role == Role.QC
