"""
billing プレゼンテーション層 - ダッシュボード・請求先・商品ビュー
"""
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.contrib import messages
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, TemplateView
from django.urls import reverse_lazy

from billing.domain.models import BillingCustomer, BillingProduct, BillingInvoice
from billing.application.forms import BillingCustomerForm, BillingProductForm
from core.permissions import StaffRequiredMixin


# ============================================================
# ダッシュボード
# ============================================================

class DashboardView(StaffRequiredMixin, TemplateView):
    """請求書ダッシュボード"""
    template_name = 'billing/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        invoices = BillingInvoice.objects.all()
        context['total_count'] = invoices.count()
        context['draft_count'] = invoices.filter(status='DRAFT').count()
        context['issued_count'] = invoices.filter(status='ISSUED').count()
        context['sent_count'] = invoices.filter(status='SENT').count()
        context['paid_count'] = invoices.filter(status='PAID').count()
        context['recent_invoices'] = invoices[:10]
        context['unpaid_invoices'] = invoices.exclude(status='PAID')[:10]
        return context


# ============================================================
# 請求先（BillingCustomer）
# ============================================================

class CustomerListView(StaffRequiredMixin, ListView):
    model = BillingCustomer
    template_name = 'billing/customer_list.html'
    context_object_name = 'customers'


class CustomerCreateView(StaffRequiredMixin, CreateView):
    model = BillingCustomer
    form_class = BillingCustomerForm
    template_name = 'billing/customer_form.html'
    success_url = reverse_lazy('billing:customer_list')

    def form_valid(self, form):
        messages.success(self.request, '請求先を登録しました。')
        return super().form_valid(form)


class CustomerUpdateView(StaffRequiredMixin, UpdateView):
    model = BillingCustomer
    form_class = BillingCustomerForm
    template_name = 'billing/customer_form.html'
    success_url = reverse_lazy('billing:customer_list')

    def form_valid(self, form):
        messages.success(self.request, '請求先を更新しました。')
        return super().form_valid(form)


class CustomerDeleteView(StaffRequiredMixin, DeleteView):
    model = BillingCustomer
    template_name = 'billing/customer_confirm_delete.html'
    success_url = reverse_lazy('billing:customer_list')

    def form_valid(self, form):
        messages.success(self.request, '請求先を削除しました。')
        return super().form_valid(form)


# ============================================================
# 商品（BillingProduct）
# ============================================================

class ProductListView(StaffRequiredMixin, ListView):
    model = BillingProduct
    template_name = 'billing/product_list.html'
    context_object_name = 'products'


class ProductCreateView(StaffRequiredMixin, CreateView):
    model = BillingProduct
    form_class = BillingProductForm
    template_name = 'billing/product_form.html'
    success_url = reverse_lazy('billing:product_list')

    def form_valid(self, form):
        messages.success(self.request, '商品を登録しました。')
        return super().form_valid(form)


class ProductUpdateView(StaffRequiredMixin, UpdateView):
    model = BillingProduct
    form_class = BillingProductForm
    template_name = 'billing/product_form.html'
    success_url = reverse_lazy('billing:product_list')

    def form_valid(self, form):
        messages.success(self.request, '商品を更新しました。')
        return super().form_valid(form)


class ProductDeleteView(StaffRequiredMixin, DeleteView):
    model = BillingProduct
    template_name = 'billing/product_confirm_delete.html'
    success_url = reverse_lazy('billing:product_list')

    def form_valid(self, form):
        messages.success(self.request, '商品を削除しました。')
        return super().form_valid(form)


class ProductAPIView(StaffRequiredMixin, View):
    """商品情報API（JSON）"""
    def get(self, request, pk):
        product = get_object_or_404(BillingProduct, pk=pk)
        return JsonResponse({
            'id': product.pk,
            'name': product.name,
            'unit_price': product.unit_price,
            'tax_category': product.tax_category,
        })
