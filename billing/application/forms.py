"""
billing アプリケーション層 - フォーム定義
"""
from django import forms
from django.forms import inlineformset_factory
from billing.domain.models import (
    BillingCustomer, BillingProduct, BillingInvoice, BillingItem
)


class BillingCustomerForm(forms.ModelForm):
    """請求先フォーム"""
    class Meta:
        model = BillingCustomer
        fields = [
            'name', 'title', 'contact_person', 'email', 'cc_email',
            'phone', 'postal_code', 'address',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'contact_person': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'cc_email': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'example1@test.com, example2@test.com',
            }),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'postal_code': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.TextInput(attrs={'class': 'form-control'}),
        }


class BillingProductForm(forms.ModelForm):
    """商品フォーム"""
    class Meta:
        model = BillingProduct
        fields = ['name', 'unit_price', 'unit', 'tax_category']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control'}),
            'unit': forms.TextInput(attrs={'class': 'form-control'}),
            'tax_category': forms.Select(attrs={'class': 'form-select'}),
        }


class BillingInvoiceForm(forms.ModelForm):
    """請求書ヘッダーフォーム"""
    class Meta:
        model = BillingInvoice
        fields = [
            'customer', 'company', 'issue_date', 'due_date',
            'subject', 'notes', 'status',
        ]
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-select'}),
            'company': forms.Select(attrs={'class': 'form-select'}),
            'issue_date': forms.DateInput(attrs={
                'class': 'form-control', 'type': 'date',
            }),
            'due_date': forms.DateInput(attrs={
                'class': 'form-control', 'type': 'date',
            }),
            'subject': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }


class BillingItemForm(forms.ModelForm):
    """請求明細フォーム"""
    product = forms.ModelChoiceField(
        queryset=BillingProduct.objects.all(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select product-select'}),
        label='商品',
    )
    man_month = forms.ChoiceField(
        choices=[
            ('1.00', '1.00'),
            ('0.75', '0.75'),
            ('0.50', '0.50'),
            ('0.25', '0.25'),
        ],
        initial='1.00',
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='人月',
    )

    class Meta:
        model = BillingItem
        fields = [
            'product', 'unit_price',
            'man_month', 'tax_category', 'sort_order',
        ]
        widgets = {
            'unit_price': forms.NumberInput(attrs={
                'class': 'form-control unit-price', 'readonly': 'readonly',
            }),
            'tax_category': forms.Select(attrs={'class': 'form-select'}),
            'sort_order': forms.HiddenInput(),
        }


# 明細のインラインフォームセット
BillingItemFormSet = inlineformset_factory(
    BillingInvoice,
    BillingItem,
    form=BillingItemForm,
    extra=1,
    can_delete=True,
)


class InvoiceMailForm(forms.Form):
    """メール送信フォーム"""
    to_email = forms.CharField(
        label='TO（宛先）',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'example@test.com',
        }),
    )
    cc_email = forms.CharField(
        label='CC',
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'cc1@test.com, cc2@test.com',
        }),
    )
    subject = forms.CharField(
        label='件名',
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    body = forms.CharField(
        label='本文',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 8}),
    )
