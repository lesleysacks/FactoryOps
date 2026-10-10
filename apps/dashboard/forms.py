"""
FactoryOps — Operator capture forms.

Bind to existing StockRecord, MaterialBatch, and MaterialAddition models.
Factory is taken from the authenticated user, never from posted IDs.
"""

from decimal import Decimal

from django import forms
from django.utils import timezone

from apps.machines.models import Machine
from apps.materials.models import Material, MaterialAddition, MaterialBatch, StockRecord
from apps.materials.workflow import record_material_consumption
from apps.production.workflow import (
    record_material_state,
    record_production_output,
    start_production_run,
)

from .querysets import (
    active_machines_on_line_for,
    active_materials_for,
    batches_for_material,
    user_factory,
)

CONTROL_ATTRS = {
    'class': 'input-control',
}
QUANTITY_ATTRS = {
    'class': 'input-control',
    'step': '0.001',
    'inputmode': 'decimal',
    'min': '0',
}


class OperatorCaptureForm(forms.Form):
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.factory = user_factory(user)
        materials = active_materials_for(user)
        if 'material' in self.fields:
            self.fields['material'].queryset = materials
            self.fields['material'].empty_label = 'Select a material'

    def clean(self):
        cleaned = super().clean()
        if self.factory is None:
            raise forms.ValidationError(
                'Your account is not assigned to a factory. Ask a supervisor to assign you.'
            )
        material = cleaned.get('material')
        if material is not None and material.factory_id != self.factory.id:
            raise forms.ValidationError({
                'material': 'This material does not belong to your factory.',
            })
        return cleaned


class StockCountForm(OperatorCaptureForm):
    material = forms.ModelChoiceField(
        queryset=Material.objects.none(),
        label='Material',
        widget=forms.Select(attrs=CONTROL_ATTRS),
    )
    opening_quantity = forms.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=Decimal('0'),
        label='Opening quantity',
        widget=forms.NumberInput(attrs=QUANTITY_ATTRS),
    )
    closing_quantity = forms.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=Decimal('0'),
        required=False,
        label='Closing quantity',
        help_text='Leave blank if the closing count has not been taken yet.',
        widget=forms.NumberInput(attrs=QUANTITY_ATTRS),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['material'].queryset = active_materials_for(self.user)

    def clean(self):
        cleaned = super().clean()
        material = cleaned.get('material')
        if self.factory and material:
            recording_date = timezone.now().date()
            if StockRecord.objects.filter(
                factory=self.factory,
                material=material,
                recording_date=recording_date,
            ).exists():
                raise forms.ValidationError({
                    'material': 'A stock count for this material is already recorded today.',
                })
        return cleaned

    def save(self):
        closing = self.cleaned_data.get('closing_quantity')
        return StockRecord.objects.create(
            factory=self.factory,
            material=self.cleaned_data['material'],
            recording_date=timezone.now().date(),
            opening_quantity=self.cleaned_data['opening_quantity'],
            closing_quantity=closing,
        )


class StockCloseForm(forms.Form):
    closing_quantity = forms.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=Decimal('0'),
        label='Closing quantity',
        widget=forms.NumberInput(attrs=QUANTITY_ATTRS),
    )

    def __init__(self, *args, stock_record=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.stock_record = stock_record

    def save(self):
        self.stock_record.closing_quantity = self.cleaned_data['closing_quantity']
        self.stock_record.save()
        return self.stock_record


class MaterialReceiptForm(OperatorCaptureForm):
    material = forms.ModelChoiceField(
        queryset=Material.objects.none(),
        label='Material',
        widget=forms.Select(attrs=CONTROL_ATTRS),
    )
    lot_number = forms.CharField(
        max_length=100,
        label='Lot number',
        widget=forms.TextInput(attrs={
            **CONTROL_ATTRS,
            'placeholder': 'Enter the lot or batch number',
            'autocomplete': 'off',
        }),
    )
    quantity = forms.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=Decimal('0.001'),
        label='Quantity received',
        widget=forms.NumberInput(attrs={**QUANTITY_ATTRS, 'min': '0.001'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['material'].queryset = active_materials_for(self.user)

    def clean_lot_number(self):
        return self.cleaned_data['lot_number'].strip()

    def save(self):
        material = self.cleaned_data['material']
        lot_number = self.cleaned_data['lot_number']
        batch, _created = MaterialBatch.objects.get_or_create(
            material=material,
            lot_number=lot_number,
        )
        return MaterialAddition.objects.create(
            factory=self.factory,
            material=material,
            batch=batch,
            quantity=self.cleaned_data['quantity'],
        )


class StartRunForm(OperatorCaptureForm):
    machine = forms.ModelChoiceField(
        queryset=Machine.objects.none(),
        label='Machine',
        widget=forms.Select(attrs=CONTROL_ATTRS),
    )

    def __init__(self, *args, line=None, **kwargs):
        self.line = line
        super().__init__(*args, **kwargs)
        if line is not None:
            self.fields['machine'].queryset = active_machines_on_line_for(self.user, line)
            self.fields['machine'].empty_label = 'Select a machine'

    def save(self):
        return start_production_run(
            self.user,
            self.cleaned_data['machine'],
            line=self.line,
        )


class ProductionOutputForm(forms.Form):
    output_name = forms.CharField(
        max_length=150,
        label='Output',
        widget=forms.TextInput(attrs={
            **CONTROL_ATTRS,
            'placeholder': 'What was produced',
            'autocomplete': 'off',
        }),
    )
    quantity = forms.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=Decimal('0.001'),
        label='Quantity',
        widget=forms.NumberInput(attrs={**QUANTITY_ATTRS, 'min': '0.001'}),
    )

    def clean_output_name(self):
        return self.cleaned_data['output_name'].strip()

    def save(self, user, run_id):
        return record_production_output(
            user,
            run_id,
            self.cleaned_data['quantity'],
            self.cleaned_data['output_name'],
        )


class MaterialConsumptionForm(OperatorCaptureForm):
    material = forms.ModelChoiceField(
        queryset=Material.objects.none(),
        label='Material',
        widget=forms.Select(attrs={
            **CONTROL_ATTRS,
            'onchange': (
                'if(this.value){window.location.search="material="+this.value}'
                'else{window.location.search=""}'
            ),
        }),
    )
    batch = forms.ModelChoiceField(
        queryset=MaterialBatch.objects.none(),
        label='Batch',
        widget=forms.Select(attrs=CONTROL_ATTRS),
    )
    quantity = forms.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=Decimal('0.001'),
        label='Quantity',
        widget=forms.NumberInput(attrs={**QUANTITY_ATTRS, 'min': '0.001'}),
    )

    def __init__(self, *args, run=None, **kwargs):
        self.run = run
        super().__init__(*args, **kwargs)
        material = None
        if self.is_bound:
            material = self.fields['material'].queryset.filter(
                pk=self.data.get('material'),
            ).first()
        elif self.initial.get('material'):
            material = self.fields['material'].queryset.filter(
                pk=self.initial.get('material'),
            ).first()
            self.fields['material'].initial = material
        self.fields['batch'].queryset = batches_for_material(self.user, material)
        self.fields['batch'].empty_label = 'Select a batch'

    def clean(self):
        cleaned = super().clean()
        material = cleaned.get('material')
        batch = cleaned.get('batch')
        if (
            material is not None
            and batch is not None
            and batch.material_id != material.id
        ):
            raise forms.ValidationError({
                'batch': 'This batch does not belong to the selected material.',
            })
        if self.run is not None and self.factory is not None:
            if self.run.factory_id != self.factory.id:
                raise forms.ValidationError(
                    'This production run does not belong to your factory.'
                )
        return cleaned

    def save(self):
        return record_material_consumption(
            self.user,
            self.run.pk,
            self.cleaned_data['material'],
            self.cleaned_data['batch'],
            self.cleaned_data['quantity'],
        )


class MaterialStateForm(OperatorCaptureForm):
    material = forms.ModelChoiceField(
        queryset=Material.objects.none(),
        label='Material',
        widget=forms.Select(attrs=CONTROL_ATTRS),
    )
    roll_quantity = forms.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=Decimal('0'),
        label='Roll quantity',
        help_text='Currently loaded on the machine.',
        widget=forms.NumberInput(attrs=QUANTITY_ATTRS),
    )
    spare_roll_quantity = forms.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=Decimal('0'),
        label='Spare roll quantity',
        help_text='Available beside the machine.',
        widget=forms.NumberInput(attrs=QUANTITY_ATTRS),
    )

    def __init__(self, *args, run=None, **kwargs):
        self.run = run
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        if self.run is not None and self.factory is not None:
            if self.run.factory_id != self.factory.id:
                raise forms.ValidationError(
                    'This production run does not belong to your factory.'
                )
        return cleaned

    def save(self):
        return record_material_state(
            self.user,
            self.run.pk,
            self.cleaned_data['material'],
            self.cleaned_data['roll_quantity'],
            self.cleaned_data['spare_roll_quantity'],
        )
