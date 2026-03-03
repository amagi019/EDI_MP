from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, HttpResponseForbidden
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils.decorators import method_decorator
from django.contrib import messages
from django.views import View
from django.views.generic import ListView, DetailView
from .models import Invoice
from .services.pdf_generator import generate_invoice_pdf, generate_payment_notice_pdf

class AdminInvoicePDFView(View):
    """管理者用 請求書PDFダウンロード"""
    
    @method_decorator(user_passes_test(lambda u: u.is_staff))
    def get(self, request, invoice_id):
        invoice = get_object_or_404(Invoice, pk=invoice_id)
        buffer = generate_invoice_pdf(invoice)
        
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="invoice_{invoice.invoice_no}.pdf"'
        return response

class AdminPaymentNoticePDFView(View):
    """管理者用 支払い通知書PDFダウンロード"""
    
    @method_decorator(user_passes_test(lambda u: u.is_staff))
    def get(self, request, invoice_id):
        invoice = get_object_or_404(Invoice, pk=invoice_id)
        buffer = generate_payment_notice_pdf(invoice)
        
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="payment_notice_{invoice.invoice_no}.pdf"'
        return response

class PartnerInvoicePDFView(View):
    """パートナー用 請求書PDFダウンロード"""

    @method_decorator(login_required)
    def get(self, request, invoice_id):
        invoice = get_object_or_404(Invoice, pk=invoice_id)
        
        user = request.user
        if not hasattr(user, 'profile') or not user.profile.partner:
             return HttpResponseForbidden("パートナー情報がありません。")
        
        if invoice.order.partner != user.profile.partner:
             return HttpResponseForbidden("権限がありません。")

        buffer = generate_invoice_pdf(invoice)
        
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="invoice_{invoice.invoice_no}.pdf"'
        return response

class PartnerInvoiceListView(ListView):
    """パートナー用 請求書一覧"""
    model = Invoice
    template_name = 'invoices/invoice_list.html'
    context_object_name = 'invoices'
    ordering = ['-issue_date']

    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Invoice.objects.filter(
                status__in=['ISSUED', 'SENT', 'CONFIRMED']
            ).order_by('-issue_date')

        if not hasattr(user, 'profile') or not user.profile.partner:
             return Invoice.objects.none()
        
        return Invoice.objects.filter(
            order__partner=user.profile.partner,
            status__in=['ISSUED', 'SENT', 'CONFIRMED']
        ).order_by('-issue_date')

class PartnerInvoiceDetailView(DetailView):
    """パートナー用 請求書詳細"""
    model = Invoice
    template_name = 'invoices/invoice_detail.html'
    context_object_name = 'invoice'
    pk_url_kwarg = 'invoice_id'

    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Invoice.objects.all()
        if not hasattr(user, 'profile') or not user.profile.partner:
            return Invoice.objects.none()
        return Invoice.objects.filter(order__partner=user.profile.partner)

class PartnerInvoiceConfirmView(View):
    """パートナー用 請求書確定"""

    @method_decorator(login_required)
    def post(self, request, invoice_id):
        invoice = get_object_or_404(Invoice, pk=invoice_id)
        
        user = request.user
        if not hasattr(user, 'profile') or not user.profile.partner:
            return HttpResponseForbidden("パートナー情報がありません。")
        if invoice.order.partner != user.profile.partner:
            return HttpResponseForbidden("権限がありません。")
        
        if invoice.status not in ('ISSUED', 'SENT'):
            messages.error(request, "この請求書は確定できません。")
            return redirect('invoices:invoice_detail', invoice_id=invoice.pk)
        
        invoice.status = 'CONFIRMED'
        invoice.save()
        
        messages.success(request, f"請求書 {invoice.invoice_no} を確定しました。")
        return redirect('invoices:invoice_list')
