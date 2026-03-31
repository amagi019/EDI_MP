from django.shortcuts import render, get_object_or_404, redirect
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, JsonResponse
import json
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
from core.utils import normalize_name, get_notify_email
from .models import Invoice, InvoiceItem
from orders.models import Order
from .services.pdf_generator import generate_invoice_pdf, generate_payment_notice_pdf
from .services.xml_generator import generate_invoice_xml
from .services.json_exporter import generate_invoice_json

import logging

logger = logging.getLogger(__name__)

def _create_invoice_items_from_order(invoice, order):
    """OrderItemからInvoiceItemを一括生成する（共通ヘルパー）。"""
    from orders.models import OrderItem
    for oi in OrderItem.objects.filter(order=order):
        InvoiceItem.objects.create(
            invoice=invoice,
            person_name=oi.person_name,
            work_time=0,
            base_fee=oi.base_fee,
            time_lower_limit=oi.time_lower_limit,
            time_upper_limit=oi.time_upper_limit,
            shortage_rate=oi.shortage_rate,
            excess_rate=oi.excess_rate,
        )

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
        response['Content-Disposition'] = f'inline; filename="invoice_{invoice.invoice_no}.pdf"'
        return response

class PartnerPaymentNoticePDFView(LoginRequiredMixin, View):
    """パートナー用 支払い通知書PDF表示"""

    def get(self, request, invoice_id):
        invoice = get_object_or_404(Invoice, pk=invoice_id)

        # スタッフは全閲覧可、パートナーは自分のリソースのみ
        role = get_user_role(request.user)
        if role != Role.STAFF:
            if not is_owner_of_partner(request.user, invoice.order.partner):
                raise PermissionDenied("権限がありません。")

        buffer = generate_payment_notice_pdf(invoice)
        
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="payment_notice_{invoice.invoice_no}.pdf"'
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
        from .services.invoice_service import confirm_invoice

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


class InvoiceCreateFromBasicInfoView(StaffRequiredMixin, View):
    """基本情報一覧からワンクリック請求書作成"""

    def post(self, request, pk):
        from orders.models import OrderBasicInfo, OrderItem
        from .services.billing_calculator import BillingCalculator
        import datetime
        from calendar import monthrange

        basic_info = get_object_or_404(OrderBasicInfo, pk=pk)

        # 翌月分の注文書を検索
        today = datetime.date.today()
        if today.month == 12:
            target_year, target_month = today.year + 1, 1
        else:
            target_year, target_month = today.year, today.month + 1
        target_ym = datetime.date(target_year, target_month, 1)

        order = Order.objects.filter(
            partner=basic_info.partner,
            project=basic_info.project,
            order_end_ym=target_ym,
        ).first()

        if not order:
            messages.warning(request,
                f'{target_year}年{target_month}月分の注文書が見つかりません。先に注文書を作成してください。')
            return redirect('orders:basic_info_list')

        # 重複チェック
        existing = Invoice.objects.filter(order=order, target_month=target_ym).first()
        if existing:
            messages.info(request, f'この月の請求書は作成済みです（{existing.invoice_no}）')
            return redirect('invoices:invoice_edit', invoice_id=existing.pk)

        # Invoice作成
        invoice = Invoice(
            order=order,
            target_month=target_ym,
            status='DRAFT',
        )
        invoice.save()

        # OrderItemからInvoiceItemを生成
        _create_invoice_items_from_order(invoice, order)

        BillingCalculator.calculate_invoice(invoice)
        messages.success(request, f'請求書 {invoice.invoice_no} を作成しました。稼働時間を入力してください。')
        return redirect('invoices:invoice_edit', invoice_id=invoice.pk)


class InvoiceCreateFromOrderView(StaffRequiredMixin, View):
    """注文書から請求書を手動作成"""

    def post(self, request, order_id):
        from orders.models import OrderItem
        from .services.billing_calculator import BillingCalculator
        import datetime

        order = get_object_or_404(Order, order_id=order_id)

        # 対象月は注文書のorder_end_ym
        target_month = order.order_end_ym

        # 重複チェック
        existing = Invoice.objects.filter(order=order, target_month=target_month).first()
        if existing:
            messages.info(request, f'この注文書の請求書は作成済みです（{existing.invoice_no}）')
            return redirect('invoices:invoice_edit', invoice_id=existing.pk)

        # Invoice作成
        invoice = Invoice(
            order=order,
            target_month=target_month,
            status='DRAFT',
        )
        invoice.save()

        # OrderItemからInvoiceItemを生成
        _create_invoice_items_from_order(invoice, order)

        # 金額計算
        BillingCalculator.calculate_invoice(invoice)

        messages.success(request, f'請求書 {invoice.invoice_no} を作成しました。稼働時間を入力してください。')
        return redirect('invoices:invoice_edit', invoice_id=invoice.pk)


class InvoiceEditView(StaffRequiredMixin, View):
    """DRAFT請求書の編集（稼働時間入力・金額再計算）"""

    def get(self, request, invoice_id):
        invoice = get_object_or_404(Invoice, pk=invoice_id)
        items = invoice.items.all()
        return render(request, 'invoices/invoice_edit.html', {
            'invoice': invoice,
            'items': items,
        })

    def post(self, request, invoice_id):
        from .services.billing_calculator import BillingCalculator
        from decimal import Decimal

        invoice = get_object_or_404(Invoice, pk=invoice_id)

        action = request.POST.get('action', 'save')

        # 明細の稼働時間を更新
        for item in invoice.items.all():
            work_time_key = f'work_time_{item.pk}'
            if work_time_key in request.POST:
                try:
                    item.work_time = Decimal(request.POST[work_time_key])
                    item.save()
                except (ValueError, Exception):
                    pass

        # 金額再計算
        BillingCalculator.calculate_invoice(invoice)
        invoice.refresh_from_db()

        if action == 'submit_review':
            # 確認依頼（DRAFT → PENDING_REVIEW）
            invoice.status = 'PENDING_REVIEW'
            invoice.save()
            messages.success(request, f'請求書 {invoice.invoice_no} を確認依頼しました。')
            return redirect('invoices:staff_invoice_review', invoice_id=invoice.pk)

        messages.success(request, f'請求書 {invoice.invoice_no} を保存しました。')
        return redirect('invoices:invoice_edit', invoice_id=invoice.pk)


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
                invoice_url = request.build_absolute_uri(
                    reverse('invoices:invoice_detail', kwargs={'invoice_id': invoice.pk})
                )

                from core.utils import compose_invoice_send_email
                subject, message = compose_invoice_send_email(invoice, partner, login_url, invoice_url)

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


# ──────────────────────────────────────────
# 稼働報告書アップロード・確認・承認
# ──────────────────────────────────────────

class WorkReportUploadView(LoginRequiredMixin, View):
    """パートナー向け 稼働報告書アップロード（複数ファイル対応）"""

    def get(self, request):
        partner = get_user_partner(request.user)
        role = get_user_role(request.user)

        # パートナーの注文一覧を取得（発行済以降）
        if role == Role.STAFF:
            orders = Order.objects.filter(
                status__in=['UNCONFIRMED', 'CONFIRMING', 'RECEIVED', 'APPROVED']
            ).select_related('partner', 'project').order_by('-order_date')
        elif partner:
            orders = Order.objects.filter(
                partner=partner,
                status__in=['UNCONFIRMED', 'CONFIRMING', 'RECEIVED', 'APPROVED']
            ).select_related('project').order_by('-order_date')
        else:
            orders = Order.objects.none()

        # 既存の報告書一覧
        from .models import WorkReport
        if role == Role.STAFF:
            existing_reports = WorkReport.objects.all()[:20]
        elif partner:
            existing_reports = WorkReport.objects.filter(
                order__partner=partner
            )[:20]
        else:
            existing_reports = WorkReport.objects.none()

        return render(request, 'invoices/work_report_upload.html', {
            'orders': orders,
            'existing_reports': existing_reports,
        })

    def post(self, request):
        from .models import WorkReport
        from .services.excel_parser import auto_detect_and_parse
        from decimal import Decimal

        order_id = request.POST.get('order_id')
        order = get_object_or_404(Order, order_id=order_id)

        # 権限チェック
        role = get_user_role(request.user)
        if role != Role.STAFF:
            partner = get_user_partner(request.user)
            if not partner or order.partner != partner:
                raise PermissionDenied("権限がありません。")

        files = request.FILES.getlist('files')
        if not files:
            messages.error(request, "ファイルを選択してください。")
            return redirect('invoices:work_report_upload')

        report_ids = []

        for f in files:
            # まず仮のWorkReportを作成してパース
            report = WorkReport(
                order=order,
                uploaded_by=request.user,
                file=f,
                original_filename=f.name,
            )
            report.save()

            # パース実行
            try:
                report.file.seek(0)
                result = auto_detect_and_parse(report.file, original_filename=f.name)

                if result['error']:
                    report.status = 'ERROR'
                    report.error_message = result['error']
                else:
                    # 作業者名と注文の整合性チェック
                    worker_name = result['worker_name']
                    order_mismatch_warning = ''
                    if worker_name:
                        from orders.models import OrderItem
                        worker_norm = normalize_name(worker_name)
                        order_items = OrderItem.objects.filter(order=order)
                        matched = any(
                            normalize_name(oi.person_name) == worker_norm
                            for oi in order_items
                        )
                        if not matched:
                            registered_names = [oi.person_name for oi in order_items]
                            names_str = '、'.join(registered_names) if registered_names else 'なし'
                            order_mismatch_warning = (
                                f'⚠ 作業者「{worker_name}」は選択された注文'
                                f'（{order.project.name}）の明細に登録されていません。'
                                f'（登録済み作業者: {names_str}）'
                                f' 注文の選択が正しいか確認してください。'
                            )

                    # 同一注文・同一作業者・同月の既存レポートがあれば上書き
                    existing = None
                    if worker_name and result['target_month']:
                        existing = WorkReport.objects.filter(
                            order=order,
                            worker_name=worker_name,
                            target_month=result['target_month'],
                        ).exclude(pk=report.pk).first()

                    if existing:
                        # 既存レポートを上書き
                        if existing.file:
                            existing.file.delete(save=False)
                        existing.file = report.file
                        existing.original_filename = f.name
                        existing.uploaded_by = request.user
                        existing.worker_name = worker_name
                        existing.target_month = result['target_month']
                        existing.total_hours = result['total_hours']
                        existing.work_days = result['work_days']
                        existing.daily_data_json = result['daily_data']
                        existing.alerts_json = result['alerts'] if result['alerts'] else None
                        # 警告メッセージを結合
                        warnings = [w for w in [result.get('name_mismatch_warning', ''), order_mismatch_warning] if w]
                        existing.error_message = ' / '.join(warnings)
                        existing.status = 'ALERT' if (result['alerts'] or order_mismatch_warning) else 'PARSED'
                        existing.save()
                        # 仮レポートは削除
                        report.delete()
                        report_ids.append(existing.pk)
                        messages.info(request, f"「{worker_name}」の報告書を更新しました（上書き）。")
                        continue

                    report.worker_name = worker_name
                    report.target_month = result['target_month']
                    report.total_hours = result['total_hours']
                    report.work_days = result['work_days']
                    report.daily_data_json = result['daily_data']
                    report.alerts_json = result['alerts'] if result['alerts'] else None

                    # 警告メッセージを結合（氏名不一致 + 注文不整合）
                    warnings = [w for w in [result.get('name_mismatch_warning', ''), order_mismatch_warning] if w]
                    if warnings:
                        report.error_message = ' / '.join(warnings)

                    report.status = 'ALERT' if (result['alerts'] or order_mismatch_warning) else 'PARSED'

                report.save()
                report_ids.append(report.pk)

            except Exception as e:
                report.status = 'ERROR'
                report.error_message = f'処理中にエラーが発生しました: {e}'
                report.save()
                report_ids.append(report.pk)

        # 結果画面にリダイレクト
        ids_param = ','.join(str(pk) for pk in report_ids)
        return redirect(f"{reverse('invoices:work_report_results')}?ids={ids_param}")


class WorkReportResultView(LoginRequiredMixin, View):
    """稼働報告書のチェック結果表示"""

    def get(self, request, pk=None):
        from .models import WorkReport

        if pk:
            # 単一レポート表示
            reports = [get_object_or_404(WorkReport, pk=pk)]
        else:
            # 複数レポート表示（アップロード直後）
            ids_str = request.GET.get('ids', '')
            if ids_str:
                ids = [int(i) for i in ids_str.split(',') if i.isdigit()]
                reports = list(WorkReport.objects.filter(pk__in=ids).order_by('pk'))
            else:
                reports = []

        if not reports:
            messages.error(request, "報告書が見つかりませんでした。")
            return redirect('invoices:work_report_upload')

        # 権限チェック
        role = get_user_role(request.user)
        if role != Role.STAFF:
            partner = get_user_partner(request.user)
            for r in reports:
                if not partner or r.order.partner != partner:
                    raise PermissionDenied("権限がありません。")

        # 承認可能かどうか
        can_approve = any(r.status in ('PARSED', 'ALERT') for r in reports)

        return render(request, 'invoices/work_report_result.html', {
            'reports': reports,
            'can_approve': can_approve,
        })

    def post(self, request, pk=None):
        from .models import WorkReport
        from decimal import Decimal
        import datetime as dt

        report_ids = request.POST.getlist('report_ids')
        action = request.POST.get('action', 'save')

        reports = WorkReport.objects.filter(
            pk__in=report_ids,
            status__in=['PARSED', 'ALERT']
        ).select_related('order__partner')

        if not reports:
            messages.error(request, "編集対象の報告書がありません。")
            return redirect('invoices:work_report_upload')

        # 権限チェック
        role = get_user_role(request.user)
        partner = get_user_partner(request.user)
        if role != Role.STAFF:
            for r in reports:
                if not partner or r.order.partner != partner:
                    raise PermissionDenied("権限がありません。")

        # 編集内容を保存
        for report in reports:
            worker_name = request.POST.get(f'worker_name_{report.pk}')
            target_month_str = request.POST.get(f'target_month_{report.pk}')
            total_hours = request.POST.get(f'total_hours_{report.pk}')
            work_days = request.POST.get(f'work_days_{report.pk}')

            if worker_name is not None:
                report.worker_name = worker_name
            if target_month_str:
                try:
                    report.target_month = dt.date.fromisoformat(f"{target_month_str}-01")
                except ValueError:
                    pass
            if total_hours is not None:
                try:
                    report.total_hours = Decimal(total_hours)
                except (ValueError, Exception):
                    pass
            if work_days is not None:
                try:
                    report.work_days = int(work_days)
                except (ValueError, Exception):
                    pass
            report.save()

        if action == 'approve':
            # 確定処理
            from .services.invoice_service import approve_work_reports
            linked_count, email_sent = approve_work_reports(list(reports), request.user, request)

            if email_sent:
                messages.success(request, "稼働報告書を確定しました。自社担当者に通知しました。")
            else:
                messages.warning(request, "稼働報告書を確定しましたが、メール通知に失敗しました。")
            return redirect('invoices:work_report_upload')
        else:
            messages.success(request, "編集内容を保存しました。")
            # 結果画面に戻る
            ids_param = ','.join(str(r.pk) for r in reports)
            return redirect(f"{reverse('invoices:work_report_results')}?ids={ids_param}")


class WorkReportApproveView(LoginRequiredMixin, View):
    """パートナーによる稼働報告書の承認 → 自社担当者にメール通知"""

    def post(self, request):
        from .models import WorkReport

        report_ids = request.POST.getlist('report_ids')
        reports = WorkReport.objects.filter(
            pk__in=report_ids,
            status__in=['PARSED', 'ALERT']
        ).select_related('order__partner')

        if not reports:
            messages.error(request, "承認対象の報告書がありません。")
            return redirect('invoices:work_report_upload')

        # 権限チェック
        role = get_user_role(request.user)
        partner = get_user_partner(request.user)
        if role != Role.STAFF:
            for r in reports:
                if not partner or r.order.partner != partner:
                    raise PermissionDenied("権限がありません。")

        # サービス層で確定処理
        from .services.invoice_service import approve_work_reports
        linked_count, email_sent = approve_work_reports(list(reports), request.user, request)

        if email_sent:
            messages.success(request, f"稼働報告書を確定しました。自社担当者に通知しました。")
        else:
            messages.warning(request, f"稼働報告書を確定しましたが、メール通知に失敗しました。")

        return redirect('invoices:work_report_upload')


class WorkReportSendToClientView(StaffRequiredMixin, View):
    """
    自社担当者が稼働報告書（Excel）をGoogle Driveへ配置し、クライアントへ通知メールを送付する機能
    GET: プレビュー表示
    POST: 実際の送信
    """
    def _build_email_content(self, work_report, client, client_shared_url="【※ここに共有リンクが自動挿入されます】"):
        from core.domain.models import EmailTemplate
        from django.template import Context, Template
        
        ym_str = work_report.target_month.strftime("%Y年%m月") if work_report.target_month else "該当月"
        partner_name = work_report.worker_name or (work_report.order.partner.name if work_report.order and work_report.order.partner else "未取得")
        client_name = client.name if client else "未設定"
        
        default_subject = "【稼働報告書】{{ partner_name }} 様 ({{ ym_str }}分)"
        default_body = """{{ client_name }} 様\n\nいつもお世話になっております。\n{{ partner_name }} 様の {{ ym_str }}分 稼働報告書を受領いたしました。\n\n以下のURL（Google Drive共有フォルダ）よりご確認をお願いいたします。\n{{ client_shared_url }}\n\n※本メールはシステムより自動送信されています。"""
        
        template_obj, _ = EmailTemplate.objects.get_or_create(
            code='WORK_REPORT_SHARE',
            defaults={
                'subject': default_subject,
                'body': default_body,
                'description': '取引先への稼働報告共有メール',
            }
        )
        ctx = Context({
            'partner_name': partner_name,
            'ym_str': ym_str,
            'client_name': client_name,
            'client_shared_url': client_shared_url,
        }, autoescape=False)
        subject = Template(template_obj.subject).render(ctx)
        body = Template(template_obj.body).render(ctx)
        return subject, body
    def get(self, request, pk):
        from .models import WorkReport
        work_report = get_object_or_404(WorkReport, pk=pk)
        
        client = None
        target_email = None
        if work_report.order and work_report.order.project and hasattr(work_report.order.project, 'customer') and work_report.order.project.customer:
            client = work_report.order.project.customer
            target_email = client.work_report_email

        client_shared_url = work_report.client_shared_url
        try:
            from core.services.google_drive_service import upload_work_report_excel
            drive_result = upload_work_report_excel(work_report)
            client_shared_url = drive_result.get('url', '')
            work_report.client_shared_url = client_shared_url
            work_report.save(update_fields=['client_shared_url'])
        except Exception as e:
            import traceback
            logger.error(f"[Google Drive] プレビューでの稼働報告事前アップロード失敗: {e}\n{traceback.format_exc()}")
            messages.warning(request, f"Google Driveへの事前アップロードに失敗しました。仮のリンクが表示されます。: {e}")
            client_shared_url = "【※Google Driveアップロードエラーによりリンク取得失敗】"

        subject, body = self._build_email_content(work_report, client, client_shared_url)

        return render(request, 'invoices/work_report_send_preview.html', {
            'report': work_report,
            'client': client,
            'target_email': target_email,
            'subject': subject,
            'body': body,
        })

    def post(self, request, pk):
        from .models import WorkReport
        from core.services.google_drive_service import upload_work_report_excel
        from django.utils import timezone
        import traceback

        work_report = get_object_or_404(WorkReport, pk=pk)
        
        # 1. Google Drive アップロード (GET時に取得したURLがあればそれを利用、なければ再実行)
        client_shared_url = work_report.client_shared_url
        if not client_shared_url or "アップロードエラー" in client_shared_url:
            try:
                drive_result = upload_work_report_excel(work_report)
                client_shared_url = drive_result.get('url', '')
                work_report.client_shared_url = client_shared_url
                work_report.save(update_fields=['client_shared_url'])
            except Exception as e:
                logger.error(f"[Google Drive] 稼働報告アップロード失敗: {e}\n{traceback.format_exc()}")
                messages.error(request, f"Google Driveへのアップロードに失敗しました: {e}")
                return redirect('invoices:work_report_result', pk=work_report.pk)

        # 2. クライアント宛に通知メールを送付
        try:
            client = work_report.order.project.customer if hasattr(work_report.order.project, 'customer') else None
            target_email = client.work_report_email if client else None
            
            if not target_email:
                messages.warning(request, "Google Driveには保存されましたが、取引先に「稼働報告送付先メールアドレス」が登録されていないためメール送信をスキップしました。")
            else:
                # メール送信処理
                from django.core.mail import EmailMessage
                from django.conf import settings
                from django.urls import reverse
                
                subject, body = self._build_email_content(work_report, client, client_shared_url)
                
                email = EmailMessage(
                    subject=subject,
                    body=body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[target_email],
                    bcc=[settings.DEFAULT_FROM_EMAIL],
                )
                email.send(fail_silently=False)
                
        except Exception as e:
            logger.error(f"[Mail Send Error] クライアント通知メール失敗: {e}\n{traceback.format_exc()}")
            messages.error(request, "メールの送信に失敗しました（Driveへの保存は完了しています）。")
            return redirect('invoices:work_report_result', pk=work_report.pk)

        # 3. 状態更新
        work_report.sent_to_client_at = timezone.now()
        work_report.save()

        messages.success(request, f"稼働報告書を取引先へ送付（共有）しました。")
        return redirect('invoices:work_report_result', pk=work_report.pk)


class InvoiceXMLDownloadView(LoginRequiredMixin, View):
    """請求書XMLダウンロード（JP-PINT準拠）"""

    def get(self, request, invoice_id):
        invoice = get_object_or_404(Invoice, pk=invoice_id)
        # 権限チェック
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
        # 権限チェック
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


# ──────────────────────────────────────────
# 受信メール管理
# ──────────────────────────────────────────

class ReceivedEmailListView(StaffRequiredMixin, View):
    """受信メール一覧（ステータス別フィルタ）"""

    def get(self, request):
        from .models import ReceivedEmail
        from core.domain.models import Partner

        status_filter = request.GET.get('status', '')
        qs = ReceivedEmail.objects.select_related('partner', 'work_report')

        if status_filter:
            qs = qs.filter(status=status_filter)

        emails = qs[:100]
        partners = Partner.objects.all().order_by('name')

        # ステータス別カウント
        from django.db.models import Count
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
        from .models import ReceivedEmail
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
            # 再取込
            if email_obj.attachment_file and email_obj.partner:
                try:
                    from .services.email_receiver import _import_excel_as_work_report
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

