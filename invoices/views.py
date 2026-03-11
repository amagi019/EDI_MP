from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, HttpResponseForbidden
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils.decorators import method_decorator
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
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
        # スタッフは全ての請求書を閲覧可能
        if not user.is_staff:
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
    """パートナー用 請求書承認"""

    @method_decorator(login_required)
    def post(self, request, invoice_id):
        invoice = get_object_or_404(Invoice, pk=invoice_id)
        
        user = request.user
        if not hasattr(user, 'profile') or not user.profile.partner:
            return HttpResponseForbidden("パートナー情報がありません。")
        if invoice.order.partner != user.profile.partner:
            return HttpResponseForbidden("権限がありません。")
        
        if invoice.status not in ('ISSUED', 'SENT'):
            messages.error(request, "この請求書は承認できません。")
            return redirect('invoices:invoice_detail', invoice_id=invoice.pk)
        
        invoice.status = 'CONFIRMED'
        invoice.save()
        
        # 管理者へ承認通知メール送信
        partner_name = user.profile.partner.name if user.profile.partner else '不明'
        subject = f"【請求書承認通知】請求番号：{invoice.invoice_no}"
        message = f"""{partner_name} 様より、以下の請求書（支払通知書）が承認されました。

■請求番号：{invoice.invoice_no}
■対象年月：{invoice.target_month.strftime('%Y年%m月') if invoice.target_month else '未設定'}
■税込合計：¥{invoice.total_amount:,}-

システムにログインして詳細を確認してください。
"""
        try:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [settings.DEFAULT_FROM_EMAIL],  # 管理者のメールアドレス
                fail_silently=False,
            )
            messages.success(request, f"請求書 {invoice.invoice_no} を承認しました。管理者へ通知されました。")
        except Exception as e:
            messages.warning(request, f"請求書 {invoice.invoice_no} を承認しましたが、メール通知に失敗しました。")

        return redirect('invoices:invoice_list')
