"""Django admin permission checks that follow FactoryOps roles.

Model permissions on their own must not let a printing-station operator
record stock, a stores operator open a production run, or QC rewrite output.
"""

from apps.accounts.access import (
    enforce_admin_factory,
    machines_limited_to_assignment,
    scope_factory_admin,
)


def limit_admin_foreign_keys(db_field, request, kwargs):
    """Offer only records in the user's factory, and only assigned machines."""
    user = request.user
    factory_id = getattr(user, 'factory_id', None)
    if not factory_id:
        return kwargs
    name = db_field.name
    model = db_field.related_model
    if name == 'factory':
        kwargs['queryset'] = model.objects.filter(pk=factory_id)
    elif name in {'material', 'finished_good', 'product', 'packaging', 'category', 'warehouse', 'customer'}:
        if any(field.name == 'factory' for field in model._meta.fields):
            kwargs['queryset'] = model.objects.filter(factory_id=factory_id)
    elif name == 'production_line':
        kwargs['queryset'] = model.objects.filter(factory_id=factory_id)
    elif name == 'machine':
        if machines_limited_to_assignment(user):
            kwargs['queryset'] = user.assigned_machines.all()
        else:
            kwargs['queryset'] = model.objects.filter(production_line__factory_id=factory_id)
    elif name == 'production_run':
        queryset = model.objects.filter(factory_id=factory_id)
        if machines_limited_to_assignment(user):
            queryset = queryset.filter(machine__in=user.assigned_machines.all())
        kwargs['queryset'] = queryset
    elif name == 'batch':
        kwargs['queryset'] = model.objects.filter(material__factory_id=factory_id)
    elif name == 'variant':
        kwargs['queryset'] = model.objects.filter(product__factory_id=factory_id)
    return kwargs


class RoleBoundAdminMixin:
    """Replace Django model permissions with one FactoryOps access check.

    ``writes_allowed`` False keeps the changelist readable and rejects POST.
    ``factory_lookup`` hides other plants. Empty means the model is global.
    """

    access_check = staticmethod(lambda user: False)
    factory_lookup = None
    writes_allowed = True

    def _allowed(self, request):
        return self.access_check(request.user)

    def has_module_permission(self, request):
        return self._allowed(request)

    def has_view_permission(self, request, obj=None):
        return self._allowed(request)

    def has_add_permission(self, request):
        return self.writes_allowed and self._allowed(request)

    def has_change_permission(self, request, obj=None):
        return self.writes_allowed and self._allowed(request)

    def has_delete_permission(self, request, obj=None):
        return self.writes_allowed and self._allowed(request)

    def get_queryset(self, request):
        return scope_factory_admin(
            super().get_queryset(request),
            request.user,
            self.factory_lookup,
        )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        limit_admin_foreign_keys(db_field, request, kwargs)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        enforce_admin_factory(request.user, obj)
        super().save_model(request, obj, form, change)
