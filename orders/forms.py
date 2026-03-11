from django import forms
from django.forms import inlineformset_factory
from .models import Order, OrderItem, Project
from core.domain.models import Partner


class OrderCreateForm(forms.ModelForm):
    """発注書作成フォーム"""

    class Meta:
        model = Order
        fields = [
            'partner', 'project', 'order_end_ym', 'order_date',
            'work_start', 'work_end',
            '甲_責任者', '甲_担当者', '乙_責任者', '乙_担当者', '作業責任者',
            'workplace', 'deliverable_text',
            'payment_condition', 'contract_items',
            'remarks',
        ]
        widgets = {
            'partner': forms.Select(attrs={'id': 'id_partner'}),
            'project': forms.Select(attrs={'id': 'id_project'}),
            'order_end_ym': forms.DateInput(attrs={'type': 'date'}),
            'order_date': forms.DateInput(attrs={'type': 'date'}),
            'work_start': forms.DateInput(attrs={'type': 'date'}),
            'work_end': forms.DateInput(attrs={'type': 'date'}),
            'payment_condition': forms.Textarea(attrs={'rows': 3}),
            'contract_items': forms.Textarea(attrs={'rows': 3}),
            'remarks': forms.Textarea(attrs={'rows': 3}),
        }


class OrderItemForm(forms.ModelForm):
    """注文明細フォーム"""

    class Meta:
        model = OrderItem
        fields = [
            'person_name', 'effort', 'base_fee',
            'time_lower_limit', 'time_upper_limit',
            'shortage_rate', 'excess_rate',
        ]
        widgets = {
            'person_name': forms.TextInput(attrs={'placeholder': '作業者氏名'}),
            'effort': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'base_fee': forms.NumberInput(attrs={'min': '0'}),
            'time_lower_limit': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'time_upper_limit': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'shortage_rate': forms.NumberInput(attrs={'min': '0'}),
            'excess_rate': forms.NumberInput(attrs={'min': '0'}),
        }


OrderItemFormSet = inlineformset_factory(
    Order,
    OrderItem,
    form=OrderItemForm,
    extra=1,
    can_delete=True,
)
