from django import forms
from django.forms import inlineformset_factory
from .models import OrderBasicInfo, OrderBasicInfoItem


PAYMENT_CONDITION_CHOICES = [
    ('毎月末日締め翌月末日払い（税別）', '毎月末日締め翌月末日払い（税別）'),
    ('毎月末日締め翌々月１５日払い（税別）', '毎月末日締め翌々月１５日払い（税別）'),
    ('毎月末日締め翌々月末日払い（税別）', '毎月末日締め翌々月末日払い（税別）'),
]


class OrderBasicInfoForm(forms.ModelForm):
    """発注基本情報フォーム"""

    payment_condition = forms.ChoiceField(
        choices=PAYMENT_CONDITION_CHOICES,
        label="支払条件",
        required=True,
        initial='毎月末日締め翌月末日払い（税別）',
    )

    class Meta:
        model = OrderBasicInfo
        fields = [
            'partner', 'project',
            'project_start_date', 'project_end_date',
            '甲_責任者', '甲_担当者', '乙_責任者', '乙_担当者', '作業責任者',
            'workplace', 'deliverable_text',
            'payment_condition', 'contract_items',
            'order_create_deadline_day',
            'order_approve_deadline_days_before',
            'report_upload_deadline_days_before',
            'invoice_create_deadline_day',
            'invoice_approve_deadline_day',
            'reminder_days_before', 'alert_days_after',
            'remarks',
        ]
        widgets = {
            'project_start_date': forms.DateInput(attrs={'type': 'date'}),
            'project_end_date': forms.DateInput(attrs={'type': 'date'}),
            'contract_items': forms.Textarea(attrs={'rows': 6}),
            'remarks': forms.Textarea(attrs={'rows': 2}),
        }


class OrderBasicInfoItemForm(forms.ModelForm):
    """発注基本情報 明細行テンプレートフォーム"""

    class Meta:
        model = OrderBasicInfoItem
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


BasicInfoItemFormSet = inlineformset_factory(
    OrderBasicInfo,
    OrderBasicInfoItem,
    form=OrderBasicInfoItemForm,
    extra=1,
    can_delete=True,
)
