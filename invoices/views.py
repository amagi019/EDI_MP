from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, HttpResponseForbidden
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import ListView
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
    """取引先用 請求書PDFダウンロード"""

    @method_decorator(login_required)
    def get(self, request, invoice_id):
        invoice = get_object_or_404(Invoice, pk=invoice_id)
        
        # 権限チェック
        user = request.user
        if not hasattr(user, 'profile') or not user.profile.customer:
             return HttpResponseForbidden("取引先情報がありません。")
        
        if invoice.order.customer != user.profile.customer:
             return HttpResponseForbidden("権限がありません。")

        buffer = generate_invoice_pdf(invoice)
        
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="invoice_{invoice.invoice_no}.pdf"'
        return response

class PartnerInvoiceListView(ListView):
    """取引先用 請求書一覧"""
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
                status__in=['ISSUED', 'SENT']
            ).order_by('-issue_date')

        if not hasattr(user, 'profile') or not user.profile.customer:
             return Invoice.objects.none()
        
        # 自分のCustomerの注文に紐づく請求書のうち、ISSUEDまたはSENTのもの
        return Invoice.objects.filter(
            order__customer=user.profile.customer,
            status__in=['ISSUED', 'SENT']
        ).order_by('-issue_date')
