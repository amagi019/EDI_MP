from django.shortcuts import render, get_object_or_404, redirect
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.contrib import messages
from django.urls import reverse
from django.core.mail import send_mail
from django.conf import settings
from django.views import View
from django.views.generic import ListView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from core.permissions import (
    Role, get_user_role, get_user_partner, is_owner_of_partner,
    StaffRequiredMixin,
)
from .models import Invoice
from .services.pdf_generator import generate_invoice_pdf, generate_payment_notice_pdf

class AdminInvoicePDFView(StaffRequiredMixin, View):
    """管理者用 請求書PDFダウンロード"""

    def get(self, request, invoice_id):
        invoice = get_object_or_404(Invoice, pk=invoice_id)
        buffer = generate_invoice_pdf(invoice)
        
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="invoice_{invoice.invoice_no}.pdf"'
        return response

class AdminPaymentNoticePDFView(StaffRequiredMixin, View):
    """管理者用 支払い通知書PDFダウンロード"""

    def get(self, request, invoice_id):
        invoice = get_object_or_404(Invoice, pk=invoice_id)
        buffer = generate_payment_notice_pdf(invoice)
        
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="payment_notice_{invoice.invoice_no}.pdf"'
        return response

class PartnerInvoicePDFView(LoginRequiredMixin, View):
    """パートナー用 請求書PDFダウンロード"""

    def get(self, request, invoice_id):
        invoice = get_object_or_404(Invoice, pk=invoice_id)

        # スタッフは全閲覧可、パートナーは自分のリソースのみ
        role = get_user_role(request.user)
        if role != Role.STAFF:
            if not is_owner_of_partner(request.user, invoice.order.partner):
                raise PermissionDenied("権限がありません。")

        buffer = generate_invoice_pdf(invoice)
        
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="invoice_{invoice.invoice_no}.pdf"'
        return response

class PartnerInvoiceListView(LoginRequiredMixin, ListView):
    """パートナー用 請求書一覧"""
    model = Invoice
    template_name = 'invoices/invoice_list.html'
    context_object_name = 'invoices'
    ordering = ['-issue_date']

    def get_queryset(self):
        user = self.request.user
        role = get_user_role(user)
        if role == Role.STAFF:
            return Invoice.objects.filter(
                status__in=['ISSUED', 'SENT', 'CONFIRMED']
            ).order_by('-issue_date')

        partner = get_user_partner(user)
        if not partner:
            return Invoice.objects.none()

        return Invoice.objects.filter(
            order__partner=partner,
            status__in=['ISSUED', 'SENT', 'CONFIRMED']
        ).order_by('-issue_date')

class PartnerInvoiceDetailView(LoginRequiredMixin, DetailView):
    """パートナー用 請求書詳細"""
    model = Invoice
    template_name = 'invoices/invoice_detail.html'
    context_object_name = 'invoice'
    pk_url_kwarg = 'invoice_id'

    def get_queryset(self):
        user = self.request.user
        role = get_user_role(user)
        if role == Role.STAFF:
            return Invoice.objects.all()
        partner = get_user_partner(user)
        if not partner:
            return Invoice.objects.none()
        return Invoice.objects.filter(order__partner=partner)

class PartnerInvoiceConfirmView(LoginRequiredMixin, View):
    """パートナー用 請求書承認"""

    def post(self, request, invoice_id):
        invoice = get_object_or_404(Invoice, pk=invoice_id)

        # パートナー本人のみ承認可能
        if not is_owner_of_partner(request.user, invoice.order.partner):
            raise PermissionDenied("権限がありません。")
        
        if invoice.status not in ('ISSUED', 'SENT'):
            messages.error(request, "この請求書は承認できません。")
            return redirect('invoices:invoice_detail', invoice_id=invoice.pk)
        
        invoice.status = 'CONFIRMED'
        invoice.save()
        
        # 自社担当者へ承認通知メール送信
        partner = get_user_partner(request.user)
        partner_name = partner.name if partner else '不明'
        subject = f"【請求書承認通知】請求番号：{invoice.invoice_no}"
        invoice_url = request.build_absolute_uri(
            reverse('invoices:invoice_detail', kwargs={'invoice_id': invoice.pk})
        )
        message = f"""{partner_name} 様より、以下の請求書（支払通知書）が承認されました。

■請求番号：{invoice.invoice_no}
■対象年月：{invoice.target_month.strftime('%Y年%m月') if invoice.target_month else '未設定'}
■税込合計：¥{invoice.total_amount:,}-

■ 請求書確認URL:
{invoice_url}
"""
        # 自社担当者のメールアドレス（未設定の場合はDEFAULT_FROM_EMAIL）
        if partner and partner.staff_contact and partner.staff_contact.email:
            notify_email = partner.staff_contact.email
        else:
            notify_email = settings.DEFAULT_FROM_EMAIL
        try:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [notify_email],
                fail_silently=False,
            )
            messages.success(request, f"請求書 {invoice.invoice_no} を承認しました。管理者へ通知されました。")
        except Exception as e:
            messages.warning(request, f"請求書 {invoice.invoice_no} を承認しましたが、メール通知に失敗しました。")

        return redirect('invoices:invoice_list')


class StaffInvoiceReviewView(StaffRequiredMixin, View):
    """自社担当者用 請求書確認・承認画面"""

    def get(self, request, invoice_id):
        invoice = get_object_or_404(Invoice, pk=invoice_id)
        context = {
            'invoice': invoice,
            'items': invoice.items.all(),
        }
        return render(request, 'invoices/invoice_review.html', context)

    def post(self, request, invoice_id):
        invoice = get_object_or_404(Invoice, pk=invoice_id)

        if invoice.status != 'PENDING_REVIEW':
            messages.error(request, "この請求書は確認待ち状態ではありません。")
            return redirect('invoices:staff_invoice_review', invoice_id=invoice.pk)

        action = request.POST.get('action')

        if action == 'approve':
            # 承認 → ISSUED に変更
            invoice.status = 'ISSUED'
            invoice.save()

            # パートナーへ支払通知書メール送信
            partner = invoice.order.partner if invoice.order else None
            if partner and partner.email:
                login_url = request.build_absolute_uri(reverse('login'))
                subject = f"【支払通知書送付】請求番号：{invoice.invoice_no}"
                message = f"""{partner.name} 様

以下の支払通知書を送付いたします。
システムにログインして内容をご確認の上、承認をお願いいたします。

■請求番号：{invoice.invoice_no}
■対象年月：{invoice.target_month.strftime('%Y年%m月') if invoice.target_month else '未設定'}
■税込合計：¥{invoice.total_amount:,}-

▼ログインURL
{login_url}

ご不明な点がございましたら、担当者までお問い合わせください。
"""
                try:
                    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [partner.email], fail_silently=False)
                    messages.success(request, f"請求書 {invoice.invoice_no} を承認し、パートナー ({partner.email}) へ送付メールを送信しました。")
                except Exception as e:
                    messages.warning(request, f"請求書 {invoice.invoice_no} を承認しましたが、パートナーへのメール送信に失敗しました。")
            else:
                messages.success(request, f"請求書 {invoice.invoice_no} を承認しました。（パートナーのメールアドレスが未設定のため、メール通知は送信されませんでした）")

            return redirect('invoices:staff_invoice_review', invoice_id=invoice.pk)

        elif action == 'reject':
            # 差戻し → DRAFT に変更
            reject_reason = request.POST.get('reject_reason', '')
            invoice.status = 'DRAFT'
            invoice.save()

            # 管理者（DEFAULT_FROM_EMAIL）に差戻し通知
            subject = f"【請求書差戻し】請求番号：{invoice.invoice_no}"
            message = f"""以下の請求書が差し戻されました。内容を修正してください。

■請求番号：{invoice.invoice_no}
■パートナー：{invoice.order.partner.name if invoice.order and invoice.order.partner else '不明'}
■差戻し理由：{reject_reason or '記載なし'}
"""
            try:
                send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [settings.DEFAULT_FROM_EMAIL], fail_silently=False)
            except Exception:
                pass

            messages.warning(request, f"請求書 {invoice.invoice_no} を差し戻しました。")
            return redirect('invoices:staff_invoice_review', invoice_id=invoice.pk)

        messages.error(request, "不正な操作です。")
        return redirect('invoices:staff_invoice_review', invoice_id=invoice.pk)
