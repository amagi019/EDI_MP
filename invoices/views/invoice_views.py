"""
invoices - 請求書関連ビュー（CRUD / PDF / XML / JSON / メール送信）
"""
import json
import logging

from django.shortcuts import render, get_object_or_404, redirect
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
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
from invoices.models import Invoice, InvoiceItem
from orders.models import Order
from invoices.services.pdf_generator import generate_invoice_pdf, generate_payment_notice_pdf
from invoices.services.xml_generator import generate_invoice_xml
from invoices.services.json_exporter import generate_invoice_json

logger = logging.getLogger(__name__)


def _create_invoice_items_from_order(invoice, order):
    """OrderItemからInvoiceItemを一括生成する（共通ヘルパー）。"""
    from orders.models import OrderItem
    from billing.domain.models import MonthlyTimesheet
    from core.utils import normalize_name

    # MonthlyTimesheetから稼働時間マップを作成
    hours_map = {}
    if invoice.target_month:
        tm = invoice.target_month
        for ts in MonthlyTimesheet.objects.filter(
            target_month__year=tm.year,
            target_month__month=tm.month,
            status__in=('SUBMITTED', 'APPROVED', 'SENT'),
        ):
            if ts.worker_name and ts.total_hours:
                hours_map[normalize_name(ts.worker_name)] = ts.total_hours

    for oi in OrderItem.objects.filter(order=order):
        # 名前から稼働時間を自動設定
        work_time = 0
        if oi.person_name:
            work_time = hours_map.get(normalize_name(oi.person_name), 0)
        InvoiceItem.objects.create(
            invoice=invoice,
            person_name=oi.person_name,
            work_time=work_time,
            base_fee=oi.base_fee,
            time_lower_limit=oi.time_lower_limit,
            time_upper_limit=oi.time_upper_limit,
            shortage_rate=oi.shortage_rate,
            excess_rate=oi.excess_rate,
        )


# ============================================================
# PDF ビュー
# ============================================================

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
        role = get_user_role(request.user)
        if role != Role.STAFF:
            if not is_owner_of_partner(request.user, invoice.order.partner):
                raise PermissionDenied("権限がありません。")
        buffer = generate_invoice_pdf(invoice)
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="invoice_{invoice.invoice_no}.pdf"'
        return response


class PartnerPaymentNoticePDFView(LoginRequiredMixin, View):
    """パートナー用 支払い通知書PDF表示"""
    def get(self, request, invoice_id):
        invoice = get_object_or_404(Invoice, pk=invoice_id)
        role = get_user_role(request.user)
        if role != Role.STAFF:
            if not is_owner_of_partner(request.user, invoice.order.partner):
                raise PermissionDenied("権限がありません。")
        buffer = generate_payment_notice_pdf(invoice)
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="payment_notice_{invoice.invoice_no}.pdf"'
        return response


# ============================================================
# 請求書一覧・詳細・承諾
# ============================================================

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
            return Invoice.objects.all().order_by('-issue_date')
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
    """パートナー用 請求書承諾"""
    def post(self, request, invoice_id):
        from invoices.services.invoice_service import confirm_invoice

        invoice = get_object_or_404(Invoice, pk=invoice_id)
        if not is_owner_of_partner(request.user, invoice.order.partner):
            raise PermissionDenied("権限がありません。")
        if invoice.status not in ('ISSUED', 'SENT'):
            messages.error(request, "この請求書は承諾できません。")
            return redirect('invoices:invoice_detail', invoice_id=invoice.pk)

        partner = get_user_partner(request.user)
        email_sent = confirm_invoice(invoice, partner, request)

        if email_sent:
            messages.success(request, f"請求書 {invoice.invoice_no} を承諾しました。管理者へ通知されました。")
        else:
            messages.warning(request, f"請求書 {invoice.invoice_no} を承諾しましたが、メール通知に失敗しました。")
        return redirect('invoices:invoice_list')


# ============================================================
# 請求書作成・編集・削除
# ============================================================

class InvoiceCreateFromBasicInfoView(StaffRequiredMixin, View):
    """基本情報一覧からワンクリック請求書作成"""
    def post(self, request, pk):
        from orders.models import OrderBasicInfo
        from invoices.services.billing_calculator import BillingCalculator
        import datetime

        basic_info = get_object_or_404(OrderBasicInfo, pk=pk)
        today = datetime.date.today()
        target_ym = datetime.date(today.year, today.month, 1)

        order = Order.objects.filter(
            partner=basic_info.partner,
            project=basic_info.project,
            order_end_ym=target_ym,
        ).first()

        if not order:
            messages.warning(request,
                f'{today.year}年{today.month}月分の注文書が見つかりません。先に注文書を作成してください。')
            return redirect('orders:basic_info_list')

        existing = Invoice.objects.filter(order=order, target_month=target_ym).first()
        if existing:
            messages.info(request, f'この月の請求書は作成済みです（{existing.invoice_no}）')
            return redirect('invoices:invoice_edit', invoice_id=existing.pk)

        invoice = Invoice(order=order, target_month=target_ym, status='DRAFT')
        invoice.save()
        _create_invoice_items_from_order(invoice, order)
        BillingCalculator.calculate_invoice(invoice)
        messages.success(request, f'請求書 {invoice.invoice_no} を作成しました。稼働時間を入力してください。')
        return redirect('invoices:invoice_edit', invoice_id=invoice.pk)


class InvoiceCreateFromOrderView(StaffRequiredMixin, View):
    """注文書から請求書を手動作成"""

    def _create(self, request, order_id):
        from invoices.services.billing_calculator import BillingCalculator

        order = get_object_or_404(Order, order_id=order_id)
        target_month = order.order_end_ym

        existing = Invoice.objects.filter(order=order, target_month=target_month).first()
        if existing:
            messages.info(request, f'この注文書の請求書は作成済みです（{existing.invoice_no}）')
            return redirect('invoices:invoice_edit', invoice_id=existing.pk)

        invoice = Invoice(order=order, target_month=target_month, status='DRAFT')
        invoice.save()
        _create_invoice_items_from_order(invoice, order)
        BillingCalculator.calculate_invoice(invoice)
        messages.success(request, f'請求書 {invoice.invoice_no} を作成しました。稼働時間を入力してください。')
        return redirect('invoices:invoice_edit', invoice_id=invoice.pk)

    def get(self, request, order_id):
        return self._create(request, order_id)

    def post(self, request, order_id):
        return self._create(request, order_id)


class InvoiceDeleteView(StaffRequiredMixin, View):
    """下書き請求書の削除"""
    def post(self, request, invoice_id):
        invoice = get_object_or_404(Invoice, pk=invoice_id)
        if invoice.status != 'DRAFT':
            messages.error(request, '下書き状態の請求書のみ削除できます。')
            return redirect('invoices:invoice_list')
        invoice_no = invoice.invoice_no
        invoice.delete()
        messages.success(request, f'請求書 {invoice_no} を削除しました。')
        return redirect('invoices:invoice_list')


class InvoiceEditView(StaffRequiredMixin, View):
    """DRAFT請求書の編集（稼働時間入力・金額再計算）"""

    def get(self, request, invoice_id):
        from billing.domain.models import MonthlyTimesheet

        invoice = get_object_or_404(Invoice, pk=invoice_id)
        items = invoice.items.all()

        work_reports = []
        all_approved = False
        if invoice.order and invoice.target_month:
            work_reports = list(MonthlyTimesheet.objects.filter(
                order=invoice.order,
                target_month__year=invoice.target_month.year,
                target_month__month=invoice.target_month.month,
            ).order_by('worker_name'))
            all_approved = len(work_reports) > 0 and all(
                r.status == 'APPROVED' for r in work_reports
            )

        return render(request, 'invoices/invoice_edit.html', {
            'invoice': invoice,
            'items': items,
            'work_reports': work_reports,
            'all_reports_approved': all_approved,
        })

    def post(self, request, invoice_id):
        from invoices.services.billing_calculator import BillingCalculator
        from decimal import Decimal

        invoice = get_object_or_404(Invoice, pk=invoice_id)
        action = request.POST.get('action', 'save')

        for item in invoice.items.all():
            work_time_key = f'work_time_{item.pk}'
            if work_time_key in request.POST:
                try:
                    item.work_time = Decimal(request.POST[work_time_key])
                    item.save()
                except (ValueError, Exception):
                    pass

        BillingCalculator.calculate_invoice(invoice)
        invoice.refresh_from_db()

        if action == 'submit_review':
            invoice.status = 'PENDING_REVIEW'
            invoice.save()
            messages.success(request, f'請求書 {invoice.invoice_no} を確認依頼しました。')
            return redirect('invoices:staff_invoice_review', invoice_id=invoice.pk)

        if action == 'preview_send':
            return redirect('invoices:invoice_send_preview', invoice_id=invoice.pk)

        messages.success(request, f'請求書 {invoice.invoice_no} を保存しました。')
        return redirect('invoices:invoice_edit', invoice_id=invoice.pk)


class StaffInvoiceReviewView(StaffRequiredMixin, View):
    """自社担当者用 請求書確認・承認画面"""

    def get(self, request, invoice_id):
        invoice = get_object_or_404(Invoice, pk=invoice_id)
        return render(request, 'invoices/invoice_review.html', {
            'invoice': invoice,
            'items': invoice.items.all(),
        })

    def post(self, request, invoice_id):
        invoice = get_object_or_404(Invoice, pk=invoice_id)

        if invoice.status != 'PENDING_REVIEW':
            messages.error(request, "この請求書は確認待ち状態ではありません。")
            return redirect('invoices:staff_invoice_review', invoice_id=invoice.pk)

        action = request.POST.get('action')

        if action == 'approve':
            invoice.status = 'ISSUED'
            invoice.save()
            messages.success(request, f"請求書 {invoice.invoice_no} を承認しました。送付内容を確認してください。")
            return redirect('invoices:invoice_send_preview', invoice_id=invoice.pk)

        elif action == 'reject':
            reject_reason = request.POST.get('reject_reason', '')
            invoice.status = 'DRAFT'
            invoice.save()

            subject = f"【請求書差戻し】請求番号：{invoice.invoice_no}"
            message = f"""以下の請求書が差し戻されました。内容を修正してください。

■請求番号：{invoice.invoice_no}
■パートナー：{invoice.order.partner.name if invoice.order and invoice.order.partner else '不明'}
■差戻し理由：{reject_reason or '記載なし'}
"""
            try:
                from core.utils import send_system_mail, get_email_config
                config = get_email_config()
                send_system_mail(subject, message, [config['DEFAULT_FROM_EMAIL']])
            except Exception:
                pass

            messages.warning(request, f"請求書 {invoice.invoice_no} を差し戻しました。")
            return redirect('invoices:staff_invoice_review', invoice_id=invoice.pk)

        messages.error(request, "不正な操作です。")
        return redirect('invoices:staff_invoice_review', invoice_id=invoice.pk)


class InvoiceSendPreviewView(StaffRequiredMixin, View):
    """支払通知・請求書の送付プレビュー画面"""

    def _build_email_content(self, invoice, request):
        partner = invoice.order.partner if invoice.order else None
        if not partner:
            return '', ''
        login_url = request.build_absolute_uri(reverse('login'))
        invoice_url = request.build_absolute_uri(
            reverse('invoices:invoice_detail', kwargs={'invoice_id': invoice.pk})
        )
        from core.utils import compose_invoice_send_email
        subject, body = compose_invoice_send_email(invoice, partner, login_url, invoice_url)
        return subject, body

    def get(self, request, invoice_id):
        invoice = get_object_or_404(Invoice, pk=invoice_id)
        partner = invoice.order.partner if invoice.order else None
        partner_email = partner.email if partner else ''
        subject, body = self._build_email_content(invoice, request)

        return render(request, 'invoices/invoice_send_preview.html', {
            'invoice': invoice,
            'partner': partner,
            'partner_email': partner_email,
            'email_subject': subject,
            'email_body': body,
        })

    def post(self, request, invoice_id):
        from core.domain.models import SentEmailLog
        from tasks.services import complete_invoice_create

        invoice = get_object_or_404(Invoice, pk=invoice_id)
        partner = invoice.order.partner if invoice.order else None

        if not partner or not partner.email:
            messages.error(request, "パートナーのメールアドレスが設定されていません。")
            return redirect('invoices:invoice_send_preview', invoice_id=invoice.pk)

        subject = request.POST.get('email_subject', '')
        body = request.POST.get('email_body', '')

        if not subject or not body:
            messages.error(request, "件名・本文が空です。")
            return redirect('invoices:invoice_send_preview', invoice_id=invoice.pk)

        original_status = invoice.status
        if invoice.status in ('DRAFT', 'PENDING_REVIEW', 'ISSUED'):
            invoice.status = 'SENT'
            invoice.save()

        try:
            from core.utils import send_system_mail, get_email_config

            config = get_email_config()
            cc_list = [addr.strip() for addr in (partner.cc or '').split(',') if addr.strip()]
            bcc_list = [addr.strip() for addr in (partner.bcc or '').split(',') if addr.strip()]
            from_email = config['DEFAULT_FROM_EMAIL']
            if from_email not in bcc_list:
                bcc_list.append(from_email)

            send_system_mail(
                subject, body, [partner.email],
                from_email=from_email,
                bcc=bcc_list if bcc_list else None,
            )

            SentEmailLog.objects.create(
                partner=partner,
                subject=subject,
                body=body,
                recipient=partner.email,
            )

            try:
                complete_invoice_create(invoice)
            except Exception as e:
                logger.warning(f"タスク完了処理失敗: {e}")

            messages.success(request, f"請求書 {invoice.invoice_no} をパートナー ({partner.email}) へ送付しました。")
            return redirect('invoices:staff_invoice_review', invoice_id=invoice.pk)

        except Exception as e:
            if original_status == 'DRAFT':
                invoice.status = 'DRAFT'
                invoice.save()
            logger.error(f"パートナーメール送信失敗: {e}")
            messages.error(request, f"メール送信に失敗しました。ステータスは元に戻されました。エラー: {e}")
            return redirect('invoices:invoice_send_preview', invoice_id=invoice.pk)


# ============================================================
# XML / JSON ダウンロード
# ============================================================

class InvoiceXMLDownloadView(LoginRequiredMixin, View):
    """請求書XMLダウンロード（JP-PINT準拠）"""
    def get(self, request, invoice_id):
        invoice = get_object_or_404(Invoice, pk=invoice_id)
        role = get_user_role(request.user)
        if role != Role.STAFF:
            partner = get_user_partner(request.user)
            if not partner or invoice.order.partner != partner:
                raise PermissionDenied("この請求書を閲覧する権限がありません。")
        xml_bytes = generate_invoice_xml(invoice)
        response = HttpResponse(xml_bytes, content_type='application/xml')
        response['Content-Disposition'] = f'attachment; filename="invoice_{invoice.invoice_no}.xml"'
        return response


class InvoiceJSONDownloadView(LoginRequiredMixin, View):
    """請求書JSONダウンロード（実務連携用）"""
    def get(self, request, invoice_id):
        invoice = get_object_or_404(Invoice, pk=invoice_id)
        role = get_user_role(request.user)
        if role != Role.STAFF:
            partner = get_user_partner(request.user)
            if not partner or invoice.order.partner != partner:
                raise PermissionDenied("この請求書を閲覧する権限がありません。")
        data = generate_invoice_json(invoice)
        response = HttpResponse(
            json.dumps(data, ensure_ascii=False, indent=2),
            content_type='application/json'
        )
        response['Content-Disposition'] = f'attachment; filename="invoice_{invoice.invoice_no}.json"'
        return response


# ============================================================
# 受信メール管理
# ============================================================

class ReceivedEmailListView(StaffRequiredMixin, View):
    """受信メール一覧（ステータス別フィルタ）"""

    def get(self, request):
        from invoices.models import ReceivedEmail
        from core.domain.models import Partner
        from django.db.models import Count

        status_filter = request.GET.get('status', '')
        qs = ReceivedEmail.objects.select_related('partner', 'work_report')
        if status_filter:
            qs = qs.filter(status=status_filter)

        emails = qs[:100]
        partners = Partner.objects.all().order_by('name')
        status_counts = dict(
            ReceivedEmail.objects.values_list('status')
            .annotate(c=Count('id'))
            .values_list('status', 'c')
        )

        return render(request, 'invoices/received_email_list.html', {
            'emails': emails,
            'partners': partners,
            'status_filter': status_filter,
            'status_counts': status_counts,
            'total_count': ReceivedEmail.objects.count(),
        })


class ReceivedEmailActionView(StaffRequiredMixin, View):
    """受信メールのアクション（手動照合・対象外マーク）"""

    def post(self, request, pk):
        from invoices.models import ReceivedEmail
        from core.domain.models import Partner
        from django.utils import timezone

        email_obj = get_object_or_404(ReceivedEmail, pk=pk)
        action = request.POST.get('action', '')

        if action == 'match_partner':
            partner_id = request.POST.get('partner_id')
            if partner_id:
                partner = get_object_or_404(Partner, pk=partner_id)
                email_obj.partner = partner
                email_obj.status = 'IMPORTED'
                email_obj.processed_at = timezone.now()
                email_obj.error_message = ''
                email_obj.save()
                messages.success(request, f'{partner.name}に照合しました。')

        elif action == 'ignore':
            email_obj.status = 'IGNORED'
            email_obj.processed_at = timezone.now()
            email_obj.save()
            messages.info(request, '対象外にしました。')

        elif action == 'retry':
            if email_obj.attachment_file and email_obj.partner:
                try:
                    from invoices.services.email_receiver import _import_excel_as_work_report
                    email_obj.attachment_file.open('rb')
                    file_bytes = email_obj.attachment_file.read()
                    email_obj.attachment_file.close()
                    work_report = _import_excel_as_work_report(
                        email_obj.partner,
                        email_obj.attachment_filename,
                        file_bytes
                    )
                    email_obj.work_report = work_report
                    email_obj.status = 'IMPORTED'
                    email_obj.processed_at = timezone.now()
                    email_obj.error_message = ''
                    email_obj.save()
                    messages.success(request, '再取込に成功しました。')
                except Exception as e:
                    email_obj.error_message = str(e)
                    email_obj.save()
                    messages.error(request, f'再取込に失敗: {e}')
            else:
                messages.error(request, '添付ファイルまたはパートナーが未設定です。')

        return redirect('invoices:received_email_list')
