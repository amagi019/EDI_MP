"""
billing プレゼンテーション層 - ビュー定義
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.contrib import messages
from django.views import View
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView,
)
from django.urls import reverse_lazy, reverse
from django.db.models import Sum, Q

from billing.domain.models import (
    BillingCustomer, BillingProduct, BillingInvoice, BillingItem,
)
from billing.application.forms import (
    BillingCustomerForm, BillingProductForm, BillingInvoiceForm,
    BillingItemFormSet, InvoiceMailForm,
)
from billing.application.services.pdf_generator import generate_billing_pdf
from billing.application.services.drive_service import upload_to_drive, get_drive_file_url
from billing.application.services.mail_service import (
    send_invoice_email, parse_email_list,
)
from core.domain.models import CompanyInfo
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


# ============================================================
# 請求書（BillingInvoice）
# ============================================================

class InvoiceListView(StaffRequiredMixin, ListView):
    model = BillingInvoice
    template_name = 'billing/invoice_list.html'
    context_object_name = 'invoices'

    def get_queryset(self):
        qs = super().get_queryset()
        status = self.request.GET.get('status')
        q = self.request.GET.get('q')
        if status:
            qs = qs.filter(status=status)
        if q:
            qs = qs.filter(
                Q(customer__name__icontains=q) | Q(subject__icontains=q)
            )
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        current = self.request.GET.get('status', '')
        context['current_status'] = current
        context['search_query'] = self.request.GET.get('q', '')
        context['status_options'] = [
            {'value': 'DRAFT', 'label': '下書き', 'selected': current == 'DRAFT'},
            {'value': 'ISSUED', 'label': '発行済', 'selected': current == 'ISSUED'},
            {'value': 'SENT', 'label': '送付済', 'selected': current == 'SENT'},
            {'value': 'PAID', 'label': '入金済', 'selected': current == 'PAID'},
        ]
        return context


class InvoiceCreateView(StaffRequiredMixin, CreateView):
    model = BillingInvoice
    form_class = BillingInvoiceForm
    template_name = 'billing/invoice_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['formset'] = BillingItemFormSet(self.request.POST)
        else:
            context['formset'] = BillingItemFormSet()
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        formset = context['formset']
        if formset.is_valid():
            self.object = form.save()
            formset.instance = self.object
            items = formset.save(commit=False)
            for item in items:
                if item.product:
                    item.product_name = item.product.name
                    item.unit_price = item.product.unit_price
                    item.tax_category = item.product.tax_category
                item.save()
            for obj in formset.deleted_objects:
                obj.delete()
            messages.success(self.request, '請求書を作成しました。')
            return redirect('billing:invoice_list')
        else:
            return self.render_to_response(context)


class InvoiceUpdateView(StaffRequiredMixin, UpdateView):
    model = BillingInvoice
    form_class = BillingInvoiceForm
    template_name = 'billing/invoice_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['formset'] = BillingItemFormSet(
                self.request.POST, instance=self.object
            )
        else:
            context['formset'] = BillingItemFormSet(instance=self.object)
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        formset = context['formset']
        if formset.is_valid():
            self.object = form.save()
            formset.instance = self.object
            items = formset.save(commit=False)
            for item in items:
                if item.product:
                    item.product_name = item.product.name
                    item.unit_price = item.product.unit_price
                    item.tax_category = item.product.tax_category
                item.save()
            for obj in formset.deleted_objects:
                obj.delete()
            messages.success(self.request, '請求書を更新しました。')
            return redirect('billing:invoice_list')
        else:
            return self.render_to_response(context)


class InvoiceDetailView(StaffRequiredMixin, DetailView):
    model = BillingInvoice
    template_name = 'billing/invoice_detail.html'
    context_object_name = 'invoice'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['items'] = self.object.items.all()
        tax_summary = self.object.tax_summary
        for rate, amounts in tax_summary.items():
            amounts['tax_fmt'] = f"{amounts['tax']:,}"
        context['tax_summary'] = tax_summary
        inv = self.object
        context['status_display'] = inv.get_status_display()
        context['status_style'] = inv.status_badge_style
        return context


class InvoiceDeleteView(StaffRequiredMixin, DeleteView):
    model = BillingInvoice
    template_name = 'billing/invoice_confirm_delete.html'
    success_url = reverse_lazy('billing:invoice_list')

    def form_valid(self, form):
        messages.success(self.request, '請求書を削除しました。')
        return super().form_valid(form)


# ============================================================
# PDF
# ============================================================

@method_decorator(xframe_options_sameorigin, name='dispatch')
class InvoicePDFView(StaffRequiredMixin, View):
    """PDF生成・プレビュー"""
    def get(self, request, pk):
        invoice = get_object_or_404(BillingInvoice, pk=pk)
        pdf_buffer = generate_billing_pdf(invoice)
        response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="invoice_{invoice.invoice_number}.pdf"'
        return response


class InvoicePDFDownloadView(StaffRequiredMixin, View):
    """PDFダウンロード"""
    def get(self, request, pk):
        invoice = get_object_or_404(BillingInvoice, pk=pk)
        pdf_buffer = generate_billing_pdf(invoice)
        response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="invoice_{invoice.invoice_number}.pdf"'
        return response


# ============================================================
# Googleドライブ保存
# ============================================================

class InvoiceDriveUploadView(StaffRequiredMixin, View):
    """Googleドライブに保存"""
    def post(self, request, pk):
        invoice = get_object_or_404(BillingInvoice, pk=pk)

        try:
            # フォルダID取得
            import re
            folder_url = request.POST.get('folder_url', '').strip()
            use_mydrive = request.POST.get('use_mydrive')
            folder_id = None

            if use_mydrive:
                folder_id = ''  # マイドライブ直下
            elif folder_url:
                # URLからフォルダIDを抽出
                m = re.search(r'/folders/([a-zA-Z0-9_-]+)', folder_url)
                if m:
                    folder_id = m.group(1)
                else:
                    folder_id = folder_url  # 直接IDとして使用

            pdf_buffer = generate_billing_pdf(invoice)
            filename = f"請求書_{invoice.customer.name}_{invoice.issue_date}.pdf"
            file_id = upload_to_drive(pdf_buffer, filename, folder_id=folder_id)

            invoice.drive_file_id = file_id
            invoice.save(update_fields=['drive_file_id'])

            messages.success(request, 'Googleドライブに保存しました。')
        except Exception as e:
            import traceback
            traceback.print_exc()
            detail = str(e)
            if hasattr(e, 'reason'):
                detail = e.reason
            if hasattr(e, 'content'):
                detail = e.content.decode('utf-8', errors='replace')[:500]
            messages.error(request, f'ドライブ保存に失敗しました: {detail}')

        return redirect('billing:invoice_detail', pk=pk)


# ============================================================
# メール送信
# ============================================================

class InvoiceMailView(StaffRequiredMixin, View):
    """メール送信"""
    def get(self, request, pk):
        invoice = get_object_or_404(BillingInvoice, pk=pk)
        customer = invoice.customer

        # デフォルト値を設定
        contact = customer.contact_person or ''
        greeting = f'{customer.name}　御中'
        if contact:
            greeting += f'\n{contact}様'

        body_text = (
            f'{greeting}\n\n'
            f'いつもお世話になっております。\n'
            f'有限会社マックプランニング　吉川です。\n\n'
            f'下記の件、ご請求書を送りします。\n'
            f'ご査収のほどお願い致します。\n\n'
            f'請求日：{invoice.issue_date}\n'
            f'支払期日：{invoice.due_date or "-"}\n'
            f'件名：{invoice.subject or "ご請求書"}\n\n'
            f'Best regards.'
        )

        initial = {
            'to_email': customer.email,
            'cc_email': customer.cc_email,
            'subject': f'請求書をお送りします。',
            'body': body_text,
        }
        form = InvoiceMailForm(initial=initial)
        return render(request, 'billing/invoice_mail.html', {
            'invoice': invoice, 'form': form,
        })

    def post(self, request, pk):
        invoice = get_object_or_404(BillingInvoice, pk=pk)
        form = InvoiceMailForm(request.POST)

        if form.is_valid():
            to_list = parse_email_list(form.cleaned_data['to_email'])
            cc_list = parse_email_list(form.cleaned_data['cc_email'])
            subject = form.cleaned_data['subject']
            body = form.cleaned_data['body']

            # PDF生成して添付
            pdf_buffer = generate_billing_pdf(invoice)

            success = send_invoice_email(
                invoice, to_list, cc_list, subject, body, pdf_buffer
            )

            if success:
                if invoice.status in ('DRAFT', 'ISSUED'):
                    invoice.status = 'SENT'
                    invoice.save(update_fields=['status'])
                messages.success(request, 'メールを送信しました。')
                return redirect('billing:invoice_detail', pk=pk)
            else:
                messages.error(request, 'メール送信に失敗しました。')

        return render(request, 'billing/invoice_mail.html', {
            'invoice': invoice, 'form': form,
        })
