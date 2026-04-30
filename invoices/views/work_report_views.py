"""
invoices - 稼働報告書関連ビュー（アップロード / 確認 / 承認 / クライアント送付）
"""
import logging

from django.shortcuts import render, get_object_or_404, redirect
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.urls import reverse
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin

from core.permissions import (
    Role, get_user_role, get_user_partner,
    StaffRequiredMixin,
)
from core.utils import normalize_name

logger = logging.getLogger(__name__)


class WorkReportUploadView(LoginRequiredMixin, View):
    """パートナー向け 稼働報告書アップロード（複数ファイル対応）"""

    def get(self, request):
        from orders.models import Order, OrderItem
        from billing.domain.models import MonthlyTimesheet

        partner = get_user_partner(request.user)
        role = get_user_role(request.user)

        # クエリパラメータで特定注文にフィルタ
        filter_order_id = request.GET.get('order_id')
        filter_order = None

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

        if filter_order_id:
            filter_order = Order.objects.filter(order_id=filter_order_id).select_related('partner', 'project').first()

        if role == Role.STAFF:
            report_qs = MonthlyTimesheet.objects.all().select_related('order__partner', 'order__project')
            if filter_order:
                report_qs = report_qs.filter(order=filter_order)
            existing_reports = report_qs.order_by('-uploaded_at')[:20]
        elif partner:
            existing_reports = MonthlyTimesheet.objects.filter(order__partner=partner).order_by('-uploaded_at')[:20]
        else:
            existing_reports = MonthlyTimesheet.objects.none()

        # 管理者向け: 注文ごとの作業者別提出状況
        report_status_by_order = []
        if role == Role.STAFF:
            target_orders = [filter_order] if filter_order else orders
            for order in target_orders:
                if not order:
                    continue
                items = OrderItem.objects.filter(order=order)
                reports = MonthlyTimesheet.objects.filter(order=order)
                report_names = {normalize_name(r.worker_name): r for r in reports if r.worker_name}

                workers = []
                for item in items:
                    if not item.person_name:
                        continue
                    norm = normalize_name(item.person_name)
                    report = report_names.get(norm)
                    workers.append({
                        'name': item.person_name,
                        'submitted': report is not None,
                        'report': report,
                        'hours': report.total_hours if report else None,
                        'status': report.get_status_display() if report else '未提出',
                    })

                if workers:
                    submitted = sum(1 for w in workers if w['submitted'])
                    report_status_by_order.append({
                        'order': order,
                        'workers': workers,
                        'submitted_count': submitted,
                        'total_count': len(workers),
                        'all_done': submitted == len(workers),
                    })

        return render(request, 'invoices/work_report_upload.html', {
            'orders': orders,
            'existing_reports': existing_reports,
            'report_status_by_order': report_status_by_order,
        })

    def post(self, request):
        from orders.models import Order, OrderItem
        from billing.domain.models import MonthlyTimesheet
        from invoices.services.excel_parser import auto_detect_and_parse
        from decimal import Decimal

        order_id = request.POST.get('order_id')
        order = get_object_or_404(Order, order_id=order_id)

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
            report = MonthlyTimesheet(
                report_type='PARTNER',
                worker_type='PARTNER',
                order=order,
                uploaded_by=request.user,
                excel_file=f,
                original_filename=f.name,
            )
            report.save()

            try:
                report.excel_file.seek(0)
                result = auto_detect_and_parse(report.excel_file, original_filename=f.name)

                if result['error']:
                    report.status = 'ERROR'
                    report.error_message = result['error']
                else:
                    worker_name = result['worker_name']
                    order_mismatch_warning = ''
                    if worker_name:
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
                        existing = MonthlyTimesheet.objects.filter(
                            order=order,
                            worker_name=worker_name,
                            target_month=result['target_month'],
                        ).exclude(pk=report.pk).first()

                    if existing:
                        if existing.excel_file:
                            existing.excel_file.delete(save=False)
                        existing.excel_file = report.excel_file
                        existing.original_filename = f.name
                        existing.uploaded_by = request.user
                        existing.worker_name = worker_name
                        existing.target_month = result['target_month']
                        existing.total_hours = result['total_hours']
                        existing.work_days = result['work_days']
                        existing.daily_data = result['daily_data']
                        existing.alerts_json = result['alerts'] if result['alerts'] else None
                        warnings = [w for w in [result.get('name_mismatch_warning', ''), order_mismatch_warning] if w]
                        existing.error_message = ' / '.join(warnings)
                        existing.status = 'ALERT' if (result['alerts'] or order_mismatch_warning) else 'APPROVED'
                        existing.save()
                        # PDF自動生成
                        if existing.status == 'APPROVED':
                            try:
                                from billing.services.timesheet_pdf_service import generate_workreport_pdf
                                generate_workreport_pdf(existing)
                            except Exception as pdf_e:
                                import logging
                                logging.getLogger(__name__).warning(f'MonthlyTimesheet PDF生成エラー ({worker_name}): {pdf_e}')
                        report.delete()
                        report_ids.append(existing.pk)
                        messages.info(request, f"「{worker_name}」の報告書を更新しました（上書き）。")
                        continue

                    report.worker_name = worker_name
                    report.target_month = result['target_month']
                    report.total_hours = result['total_hours']
                    report.work_days = result['work_days']
                    report.daily_data = result['daily_data']
                    report.alerts_json = result['alerts'] if result['alerts'] else None

                    warnings = [w for w in [result.get('name_mismatch_warning', ''), order_mismatch_warning] if w]
                    if warnings:
                        report.error_message = ' / '.join(warnings)

                    report.status = 'ALERT' if (result['alerts'] or order_mismatch_warning) else 'APPROVED'

                report.save()
                # PDF自動生成
                if report.status == 'APPROVED':
                    try:
                        from billing.services.timesheet_pdf_service import generate_workreport_pdf
                        generate_workreport_pdf(report)
                    except Exception as pdf_e:
                        import logging
                        logging.getLogger(__name__).warning(f'MonthlyTimesheet PDF生成エラー ({report.worker_name}): {pdf_e}')
                report_ids.append(report.pk)

            except Exception as e:
                report.status = 'ERROR'
                report.error_message = f'処理中にエラーが発生しました: {e}'
                report.save()
                report_ids.append(report.pk)

        ids_param = ','.join(str(pk) for pk in report_ids)
        return redirect(f"{reverse('invoices:work_report_results')}?ids={ids_param}")


class WorkReportResultView(LoginRequiredMixin, View):
    """稼働報告書のチェック結果表示"""

    def get(self, request, pk=None):
        from billing.domain.models import MonthlyTimesheet

        if pk:
            reports = [get_object_or_404(MonthlyTimesheet, pk=pk)]
        else:
            ids_str = request.GET.get('ids', '')
            if ids_str:
                ids = [int(i) for i in ids_str.split(',') if i.isdigit()]
                reports = list(MonthlyTimesheet.objects.filter(pk__in=ids).order_by('pk'))
            else:
                reports = []

        if not reports:
            messages.error(request, "報告書が見つかりませんでした。")
            return redirect('invoices:work_report_upload')

        role = get_user_role(request.user)
        if role != Role.STAFF:
            partner = get_user_partner(request.user)
            for r in reports:
                if not partner or r.order.partner != partner:
                    raise PermissionDenied("権限がありません。")

        can_approve = any(r.status in ('PARSED', 'ALERT') for r in reports)

        return render(request, 'invoices/work_report_result.html', {
            'reports': reports,
            'can_approve': can_approve,
        })

    def post(self, request, pk=None):
        from billing.domain.models import MonthlyTimesheet
        from decimal import Decimal
        import datetime as dt

        report_ids = request.POST.getlist('report_ids')
        action = request.POST.get('action', 'save')

        reports = MonthlyTimesheet.objects.filter(
            pk__in=report_ids,
            status__in=['PARSED', 'ALERT']
        ).select_related('order__partner')

        if not reports:
            messages.error(request, "編集対象の報告書がありません。")
            return redirect('invoices:work_report_upload')

        role = get_user_role(request.user)
        partner = get_user_partner(request.user)
        if role != Role.STAFF:
            for r in reports:
                if not partner or r.order.partner != partner:
                    raise PermissionDenied("権限がありません。")

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
            from invoices.services.invoice_service import approve_work_reports
            linked_count, email_sent = approve_work_reports(list(reports), request.user, request)

            if email_sent:
                messages.success(request, "稼働報告書を確定しました。自社担当者に通知しました。")
            else:
                messages.warning(request, "稼働報告書を確定しましたが、メール通知に失敗しました。")
            return redirect('invoices:work_report_upload')
        else:
            messages.success(request, "編集内容を保存しました。")
            ids_param = ','.join(str(r.pk) for r in reports)
            return redirect(f"{reverse('invoices:work_report_results')}?ids={ids_param}")


class WorkReportApproveView(LoginRequiredMixin, View):
    """パートナーによる稼働報告書の承認"""

    def post(self, request):
        from billing.domain.models import MonthlyTimesheet

        report_ids = request.POST.getlist('report_ids')
        reports = MonthlyTimesheet.objects.filter(
            pk__in=report_ids,
            status__in=['PARSED', 'ALERT']
        ).select_related('order__partner')

        if not reports:
            messages.error(request, "承認対象の報告書がありません。")
            return redirect('invoices:work_report_upload')

        role = get_user_role(request.user)
        partner = get_user_partner(request.user)
        if role != Role.STAFF:
            for r in reports:
                if not partner or r.order.partner != partner:
                    raise PermissionDenied("権限がありません。")

        from invoices.services.invoice_service import approve_work_reports
        linked_count, email_sent = approve_work_reports(list(reports), request.user, request)

        if email_sent:
            messages.success(request, f"稼働報告書を確定しました。自社担当者に通知しました。")
        else:
            messages.warning(request, f"稼働報告書を確定しましたが、メール通知に失敗しました。")

        return redirect('invoices:work_report_upload')


class WorkReportSendToClientView(StaffRequiredMixin, View):
    """自社担当者が稼働報告書（Excel）をGoogle Driveへ配置し、クライアントへ通知メールを送付"""

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
        from billing.domain.models import MonthlyTimesheet

        work_report = get_object_or_404(MonthlyTimesheet, pk=pk)

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
        from billing.domain.models import MonthlyTimesheet
        from core.services.google_drive_service import upload_work_report_excel
        from django.utils import timezone
        from django.conf import settings
        import traceback

        work_report = get_object_or_404(MonthlyTimesheet, pk=pk)

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

        try:
            client = work_report.order.project.customer if hasattr(work_report.order.project, 'customer') else None
            target_email = client.work_report_email if client else None

            if not target_email:
                messages.warning(request, "Google Driveには保存されましたが、取引先に「稼働報告送付先メールアドレス」が登録されていないためメール送信をスキップしました。")
            else:
                from django.core.mail import EmailMessage
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

        work_report.sent_to_client_at = timezone.now()
        work_report.save()

        messages.success(request, f"稼働報告書を取引先へ送付（共有）しました。")
        return redirect('invoices:work_report_result', pk=work_report.pk)


class WorkReportStatusView(StaffRequiredMixin, View):
    """パートナーからの作業報告受領状況（月別）"""

    def get(self, request):
        import datetime as dt
        from orders.models import Order, OrderItem
        from billing.domain.models import MonthlyTimesheet

        today = dt.date.today()
        # 月パラメータ（デフォルト: 当月）
        month_str = request.GET.get('month', today.strftime('%Y-%m'))
        try:
            year, month = map(int, month_str.split('-'))
            target_date = dt.date(year, month, 1)
        except (ValueError, TypeError):
            target_date = today.replace(day=1)
            month_str = target_date.strftime('%Y-%m')

        # 対象月の発注（work_startの年月で絞り込み）
        orders = Order.objects.filter(
            work_start__year=target_date.year,
            work_start__month=target_date.month,
        ).select_related('partner', 'project').order_by('partner__name', 'project__name')

        status_rows = []
        total_expected = 0
        total_received = 0

        for order in orders:
            items = OrderItem.objects.filter(order=order)
            reports = MonthlyTimesheet.objects.filter(order=order)
            report_map = {}
            for r in reports:
                if r.worker_name:
                    from core.utils import normalize_name
                    report_map[normalize_name(r.worker_name)] = r

            for item in items:
                if not item.person_name:
                    continue
                from core.utils import normalize_name
                norm = normalize_name(item.person_name)
                report = report_map.get(norm)
                total_expected += 1
                if report:
                    total_received += 1

                status_rows.append({
                    'partner_name': order.partner.name,
                    'project_name': order.project.name,
                    'worker_name': item.person_name,
                    'order_id': order.order_id,
                    'received': report is not None,
                    'report': report,
                    'hours': report.total_hours if report else None,
                    'status_label': report.get_status_display() if report else '未受領',
                    'uploaded_at': report.uploaded_at if report else None,
                })

        # 前月・翌月
        if target_date.month == 1:
            prev_month = dt.date(target_date.year - 1, 12, 1)
        else:
            prev_month = dt.date(target_date.year, target_date.month - 1, 1)
        if target_date.month == 12:
            next_month = dt.date(target_date.year + 1, 1, 1)
        else:
            next_month = dt.date(target_date.year, target_date.month + 1, 1)

        return render(request, 'invoices/work_report_status.html', {
            'month_str': month_str,
            'target_date': target_date,
            'status_rows': status_rows,
            'total_expected': total_expected,
            'total_received': total_received,
            'total_unreceived': total_expected - total_received,
            'prev_month': prev_month.strftime('%Y-%m'),
            'next_month': next_month.strftime('%Y-%m'),
        })
