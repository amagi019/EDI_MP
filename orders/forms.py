from django import forms
from django.forms import inlineformset_factory
from .models import Order, OrderItem, Project
from core.domain.models import Partner


PAYMENT_CONDITION_CHOICES = [
    ('毎月末日締め翌月末日払い（税別）', '毎月末日締め翌月末日払い（税別）'),
    ('毎月末日締め翌々月１５日払い（税別）', '毎月末日締め翌々月１５日払い（税別）'),
    ('毎月末日締め翌々月末日払い（税別）', '毎月末日締め翌々月末日払い（税別）'),
]


class OrderCreateForm(forms.ModelForm):
    """発注書作成フォーム"""

    payment_condition = forms.ChoiceField(
        choices=PAYMENT_CONDITION_CHOICES,
        label="支払条件",
        required=True,
        initial='毎月末日締め翌月末日払い（税別）',
    )

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
            'base_fee': forms.NumberInput(attrs={'min': '1'}),
            'time_lower_limit': forms.NumberInput(attrs={'step': '0.01', 'min': '1'}),
            'time_upper_limit': forms.NumberInput(attrs={'step': '0.01', 'min': '1'}),
            'shortage_rate': forms.NumberInput(attrs={'min': '1'}),
            'excess_rate': forms.NumberInput(attrs={'min': '1'}),
        }

    def clean_base_fee(self):
        value = self.cleaned_data.get('base_fee')
        if value is None or value <= 0:
            raise forms.ValidationError("月額基本料金は1以上を入力してください。")
        return value

    def clean_time_lower_limit(self):
        value = self.cleaned_data.get('time_lower_limit')
        if value is None or value <= 0:
            raise forms.ValidationError("基準時間（下限）は1以上を入力してください。")
        return value

    def clean_time_upper_limit(self):
        value = self.cleaned_data.get('time_upper_limit')
        if value is None or value <= 0:
            raise forms.ValidationError("基準時間（上限）は1以上を入力してください。")
        return value

    def clean_shortage_rate(self):
        value = self.cleaned_data.get('shortage_rate')
        if value is None or value <= 0:
            raise forms.ValidationError("不足単価（円/h）は1以上を入力してください。")
        return value

    def clean_excess_rate(self):
        value = self.cleaned_data.get('excess_rate')
        if value is None or value <= 0:
            raise forms.ValidationError("超過単価（円/h）は1以上を入力してください。")
        return value

    def clean(self):
        cleaned_data = super().clean()
        lower = cleaned_data.get('time_lower_limit')
        upper = cleaned_data.get('time_upper_limit')
        if lower and upper and lower >= upper:
            raise forms.ValidationError("基準時間の下限は上限より小さくしてください。")
        return cleaned_data


OrderItemFormSet = inlineformset_factory(
    Order,
    OrderItem,
    form=OrderItemForm,
    extra=1,
    can_delete=True,
)
