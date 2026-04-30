"""
billing プレゼンテーション層 - 受注管理・勤怠報告・ロールフォワード
"""
import datetime as dt
import json
from decimal import Decimal
from itertools import groupby

from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.contrib import messages
from django.views import View
from django.views.generic import ListView, DetailView
from django.views.decorators.csrf import csrf_exempt

from billing.domain.models import (
    BillingCustomer, ReceivedOrder, ReceivedOrderItem, MonthlyTimesheet,
)
from core.api_auth import require_api_key
from core.permissions import StaffRequiredMixin
from django.contrib.auth.mixins import LoginRequiredMixin


# ============================================================
# 受注管理（ReceivedOrder）
# ============================================================

class ReceivedOrderListView(StaffRequiredMixin, View):
    """受注管理 — プロジェクト（取引先×業務名）単位でグルーピング"""

    def get(self, request):
        orders = ReceivedOrder.objects.select_related('customer').prefetch_related('items').order_by(
            'customer__name', 'project_name', '-target_month'
        )
        projects = []
        for key, group in groupby(orders, key=lambda o: (o.customer_id, o.project_name)):
            group_list = list(group)
            latest = group_list[0]
            projects.append({
                'customer': latest.customer,
                'project_name': latest.project_name,
                'latest': latest,
                'order_count': len(group_list),
                'is_recurring': latest.is_recurring,
                'items': latest.items.all(),
            })

        return render(request, 'billing/received_order_list.html', {
            'projects': projects,
        })


class ReceivedOrderMonthlyListView(StaffRequiredMixin, ListView):
    """注文書一覧 — 月次の注文書を一覧表示"""
    model = ReceivedOrder
    template_name = 'billing/received_order_monthly_list.html'
    context_object_name = 'orders'
    ordering = ['-target_month', 'customer__name']

    def get_queryset(self):
        return super().get_queryset().select_related('customer').prefetch_related('items')


class ReceivedOrderDetailView(StaffRequiredMixin, DetailView):
    """受注詳細"""
    model = ReceivedOrder
    template_name = 'billing/received_order_detail.html'
    context_object_name = 'order'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['items'] = self.object.items.all()
        return context


class ReceivedOrderCreateView(StaffRequiredMixin, View):
    """受注登録（PDF自動パース / 手動入力）"""

    def get(self, request):
        return render(request, 'billing/received_order_create.html', {
            'customers': BillingCustomer.objects.all(),
        })

    def post(self, request):
        action = request.POST.get('action')
        if action == 'pdf_upload':
            return self._handle_pdf_upload(request)
        else:
            return self._handle_manual(request)

    def _handle_pdf_upload(self, request):
        from billing.services.received_order_service import create_received_order_from_pdf

        customer_id = request.POST.get('customer_id')
        pdf_files = request.FILES.getlist('order_pdf')

        if not customer_id or not pdf_files:
            messages.error(request, '取引先とPDFファイルを選択してください。')
            return redirect('billing:received_order_create')

        customer = get_object_or_404(BillingCustomer, pk=customer_id)

        created_orders = []
        skipped = []
        for pdf_file in pdf_files:
            try:
                order, parsed, errors = create_received_order_from_pdf(
                    pdf_file, customer, user=request.user
                )
                # 重複チェック: 同じ注文番号が既に存在する場合
                if order.order_number:
                    dup = ReceivedOrder.objects.filter(
                        customer=customer,
                        order_number=order.order_number,
                    ).exclude(pk=order.pk).first()
                    if dup:
                        messages.warning(
                            request,
                            f'⚠ 注文番号 {order.order_number} は既に登録済みです（重複の可能性）'
                        )
                if errors:
                    for e in errors:
                        messages.warning(request, f'⚠ {e}')
                created_orders.append(order)
            except Exception as e:
                skipped.append(f'{pdf_file.name}: {e}')

        if created_orders:
            if len(created_orders) == 1:
                o = created_orders[0]
                messages.success(
                    request,
                    f'受注を登録しました（注文番号: {o.order_number or "なし"}）'
                )
                return redirect('billing:received_order_detail', pk=o.pk)
            else:
                messages.success(
                    request,
                    f'{len(created_orders)}件の受注を一括登録しました'
                )
        if skipped:
            for s in skipped:
                messages.error(request, f'パース失敗: {s}')

        return redirect('billing:received_order_list')

    def _handle_manual(self, request):
        from billing.services.received_order_service import create_received_order_manual

        customer_id = request.POST.get('manual_customer_id')
        if not customer_id:
            messages.error(request, '取引先を選択してください。')
            return redirect('billing:received_order_create')

        customer = get_object_or_404(BillingCustomer, pk=customer_id)

        try:
            target_month_str = request.POST.get('target_month', '')
            target_month = dt.date.fromisoformat(f"{target_month_str}-01")
            work_start = dt.date.fromisoformat(request.POST.get('work_start', ''))
            work_end = dt.date.fromisoformat(request.POST.get('work_end', ''))
        except ValueError:
            messages.error(request, '日付の形式が正しくありません。')
            return redirect('billing:received_order_create')

        order = create_received_order_manual(
            customer=customer,
            target_month=target_month,
            work_start=work_start,
            work_end=work_end,
            order_number=request.POST.get('order_number', ''),
            project_name=request.POST.get('project_name', ''),
        )
        messages.success(request, f'受注を登録しました（注文番号: {order.order_number or "手動登録"}）')
        return redirect('billing:received_order_detail', pk=order.pk)


class ReceivedOrderEditView(StaffRequiredMixin, View):
    """受注編集（パース結果の修正含む）"""

    def get(self, request, pk):
        order = get_object_or_404(ReceivedOrder, pk=pk)
        items = order.items.all()
        return render(request, 'billing/received_order_edit.html', {
            'order': order, 'items': items,
        })

    def post(self, request, pk):
        order = get_object_or_404(ReceivedOrder, pk=pk)

        # ヘッダー更新
        order.order_number = request.POST.get('order_number', '')
        order.project_name = request.POST.get('project_name', '')
        order.status = request.POST.get('status', order.status)
        order.is_recurring = 'is_recurring' in request.POST
        order.remarks = request.POST.get('remarks', '')
        order.report_to_email = request.POST.get('report_to_email', '')
        order.report_cc_emails = request.POST.get('report_cc_emails', '')
        order.invoice_to_email = request.POST.get('invoice_to_email', '')
        order.invoice_cc_emails = request.POST.get('invoice_cc_emails', '')

        try:
            tm = request.POST.get('target_month', '')
            order.target_month = dt.date.fromisoformat(f"{tm}-01")
            order.work_start = dt.date.fromisoformat(request.POST.get('work_start', ''))
            order.work_end = dt.date.fromisoformat(request.POST.get('work_end', ''))
            order.order_date = dt.date.fromisoformat(request.POST.get('order_date', ''))
        except ValueError:
            pass

        order.save()

        # 明細更新（既存更新/新規作成/削除）
        item_count = int(request.POST.get('item_count', 0))
        processed_ids = set()
        for i in range(item_count):
            item_id = request.POST.get(f'item_id_{i}')
            if not item_id:
                continue
            person_name = request.POST.get(f'item_person_{i}', '')
            unit_price = int(request.POST.get(f'item_price_{i}', 0))
            man_month = Decimal(request.POST.get(f'item_manmonth_{i}', '1'))
            settlement_type = request.POST.get(f'item_settlement_{i}', 'RANGE')
            settlement_middle_hours = Decimal(request.POST.get(f'item_middle_{i}', '170'))
            lower = Decimal(request.POST.get(f'item_lower_{i}', '140'))
            upper = Decimal(request.POST.get(f'item_upper_{i}', '180'))
            excess = int(request.POST.get(f'item_excess_{i}', 0))
            shortage = int(request.POST.get(f'item_shortage_{i}', 0))

            if item_id == '-1':
                if person_name.strip():
                    new_item = ReceivedOrderItem.objects.create(
                        order=order,
                        person_name=person_name,
                        unit_price=unit_price,
                        man_month=man_month,
                        settlement_type=settlement_type,
                        settlement_middle_hours=settlement_middle_hours,
                        time_lower_limit=lower,
                        time_upper_limit=upper,
                        excess_rate=excess,
                        shortage_rate=shortage,
                    )
                    processed_ids.add(new_item.pk)
            else:
                try:
                    item = ReceivedOrderItem.objects.get(pk=item_id)
                    item.person_name = person_name
                    item.unit_price = unit_price
                    item.man_month = man_month
                    item.settlement_type = settlement_type
                    item.settlement_middle_hours = settlement_middle_hours
                    item.time_lower_limit = lower
                    item.time_upper_limit = upper
                    item.excess_rate = excess
                    item.shortage_rate = shortage
                    item.save()
                    processed_ids.add(item.pk)
                except (ReceivedOrderItem.DoesNotExist, ValueError):
                    pass

        ReceivedOrderItem.objects.filter(
            order=order
        ).exclude(pk__in=processed_ids).delete()

        messages.success(request, '受注を更新しました。')
        return redirect('billing:received_order_detail', pk=pk)


# ============================================================
# 請求連携（受注 → 請求書生成）
# ============================================================

class GenerateInvoiceFromOrderView(StaffRequiredMixin, View):
    """受注から請求書を自動生成"""

    def post(self, request, pk):
        from billing.services.billing_service import create_invoice_from_received_order

        order = get_object_or_404(ReceivedOrder, pk=pk)

        try:
            invoice, item_count, warnings = create_invoice_from_received_order(order)
            for w in warnings:
                messages.warning(request, f'⚠ {w}')
            messages.success(
                request,
                f'請求書を生成しました（{item_count}件の明細）'
            )
            return redirect('billing:invoice_detail', pk=invoice.pk)
        except Exception as e:
            messages.error(request, f'請求書の生成に失敗しました: {e}')
            return redirect('billing:received_order_detail', pk=pk)


# ============================================================
# ロールフォワード
# ============================================================

class RollforwardOrderView(StaffRequiredMixin, View):
    """受注の翌月ロールフォワード"""

    def post(self, request, pk):
        from billing.services.received_order_service import rollforward_order

        order = get_object_or_404(ReceivedOrder, pk=pk)
        try:
            new_order = rollforward_order(order)
            messages.success(
                request,
                f'翌月分を生成しました: {new_order.target_month.strftime("%Y/%m")}'
            )
            return redirect('billing:received_order_detail', pk=new_order.pk)
        except ValueError as e:
            messages.error(request, str(e))
            return redirect('billing:received_order_detail', pk=pk)


class RollforwardAllView(StaffRequiredMixin, View):
    """継続注文の一括ロールフォワード"""

    def post(self, request):
        from billing.services.received_order_service import rollforward_all_recurring

        results = rollforward_all_recurring()
        if results:
            for src, new in results:
                messages.success(
                    request,
                    f'{src.customer.name}: {new.target_month.strftime("%Y/%m")}分を生成'
                )
        else:
            messages.info(request, '生成対象の継続注文はありません。')
        return redirect('billing:received_order_list')


# ============================================================
# 勤怠報告（MonthlyTimesheet）
# ============================================================

class TimesheetListView(LoginRequiredMixin, ListView):
    """勤怠報告一覧"""
    model = MonthlyTimesheet
    template_name = 'billing/timesheet_list.html'
    context_object_name = 'timesheets'

    def get_queryset(self):
        qs = super().get_queryset()
        if not self.request.user.is_staff:
            # 非スタッフは自分の名前のデータのみ
            full_name = f'{self.request.user.last_name} {self.request.user.first_name}'.strip()
            if full_name:
                qs = qs.filter(worker_name=full_name)
            else:
                qs = qs.none()
        return qs


class TimesheetDetailView(LoginRequiredMixin, DetailView):
    """稼働報告詳細（日別稼働データ表示）"""
    model = MonthlyTimesheet
    template_name = 'billing/timesheet_detail.html'
    context_object_name = 'ts'


class TimesheetCreateView(StaffRequiredMixin, View):
    """勤怠登録"""

    def get(self, request):
        orders = ReceivedOrder.objects.filter(
            status__in=['REGISTERED', 'ACTIVE']
        )
        return render(request, 'billing/timesheet_create.html', {
            'orders': orders,
        })

    def post(self, request):
        from billing.services.timesheet_service import create_timesheet

        order_id = request.POST.get('order_id')
        order = None
        order_item = None
        if order_id:
            order = get_object_or_404(ReceivedOrder, pk=order_id)
            order_item = order.items.first()

        target_month_str = request.POST.get('target_month', '')
        try:
            target_month = dt.date.fromisoformat(f"{target_month_str}-01")
        except ValueError:
            messages.error(request, '対象月の形式が正しくありません。')
            return redirect('billing:timesheet_create')

        total_hours = request.POST.get('total_hours', 0)
        work_days = request.POST.get('work_days', 0)

        ts = create_timesheet(
            order=order,
            order_item=order_item,
            worker_name=request.POST.get('worker_name', ''),
            worker_type=request.POST.get('worker_type', 'INTERNAL'),
            target_month=target_month,
            total_hours=float(total_hours),
            work_days=int(work_days),
        )
        messages.success(request, f'稼働報告を登録しました: {ts.worker_name}')
        return redirect('billing:timesheet_list')


class TimesheetApproveView(StaffRequiredMixin, View):
    """勤怠報告の承認・ステータス変更"""

    def post(self, request, pk):
        from billing.services.timesheet_service import approve_timesheet, submit_timesheet, mark_as_sent

        ts = get_object_or_404(MonthlyTimesheet, pk=pk)
        action = request.POST.get('action', 'approve')

        if action == 'submit':
            submit_timesheet(ts)
            messages.success(request, f'{ts.worker_name}の勤怠を提出しました。')
        elif action == 'sent':
            mark_as_sent(ts)
            messages.success(request, f'{ts.worker_name}の作業報告書を送付済みにしました。')
        elif action == 'approve':
            approve_timesheet(ts)
            messages.success(request, f'{ts.worker_name}の勤怠を承認しました。')

        return redirect('billing:timesheet_list')


class TimesheetSendView(StaffRequiredMixin, View):
    """作業報告書のメール送信"""

    def get(self, request, pk):
        from billing.services.timesheet_service import _build_default_body

        ts = get_object_or_404(MonthlyTimesheet, pk=pk)
        if not ts.order:
            messages.error(request, '受注が紐付いていないため、作業報告書を送信できません。')
            return redirect('billing:timesheet_list')
        default_subject = f'{ts.worker_name}の稼働報告'
        default_body = _build_default_body(ts, ts.order, ts.order.customer)
        return render(request, 'billing/timesheet_send.html', {
            'timesheet': ts,
            'default_subject': default_subject,
            'default_body': default_body,
        })

    def post(self, request, pk):
        from billing.services.timesheet_service import send_work_report_email

        ts = get_object_or_404(MonthlyTimesheet, pk=pk)
        subject = request.POST.get('email_subject', '')
        body = request.POST.get('email_body', '')

        result = send_work_report_email(
            ts,
            subject=subject or None,
            body=body or None,
        )

        if result['sent']:
            messages.success(request, f'{ts.worker_name}の作業報告書を送信しました。')
        else:
            for err in result['errors']:
                messages.error(request, err)

        return redirect('billing:timesheet_list')


# ============================================================
# 勤怠報告 Excel取込
# ============================================================

class TimesheetExcelUploadView(LoginRequiredMixin, View):
    """Excelファイルアップロード → 解析 → セッション保存"""

    def get(self, request):
        orders = ReceivedOrder.objects.filter(
            status__in=['REGISTERED', 'ACTIVE']
        ).select_related('customer').order_by('-target_month')
        return render(request, 'billing/timesheet_excel_upload.html', {
            'orders': orders,
        })

    def post(self, request):
        from invoices.services.excel_parser import auto_detect_and_parse
        from django.core.files.storage import default_storage
        from django.core.files.base import ContentFile
        import uuid as _uuid

        files = request.FILES.getlist('files')
        if not files:
            messages.error(request, 'ファイルを選択してください。')
            return redirect('billing:timesheet_excel_upload')

        parsed_results = []
        for f in files:
            saved_path = ''
            try:
                f.seek(0)
                temp_name = f'timesheets/temp/{_uuid.uuid4().hex}_{f.name}'
                saved_path = default_storage.save(temp_name, ContentFile(f.read()))
                f.seek(0)
            except Exception:
                pass

            try:
                result = auto_detect_and_parse(f, original_filename=f.name)
                parsed_results.append({
                    'filename': f.name,
                    'worker_name': result['worker_name'],
                    'target_month': result['target_month'].isoformat() if result['target_month'] else '',
                    'total_hours': str(result['total_hours']),
                    'work_days': result['work_days'],
                    'daily_data': result['daily_data'],
                    'alerts': result['alerts'],
                    'error': result['error'],
                    'name_mismatch_warning': result.get('name_mismatch_warning', ''),
                    'saved_file_path': saved_path,
                })
            except Exception as e:
                parsed_results.append({
                    'filename': f.name,
                    'worker_name': '',
                    'target_month': '',
                    'total_hours': '0',
                    'work_days': 0,
                    'daily_data': [],
                    'alerts': [],
                    'error': f'ファイルの解析中にエラーが発生しました: {e}',
                    'name_mismatch_warning': '',
                    'saved_file_path': saved_path,
                })

        request.session['timesheet_excel_results'] = json.dumps(
            parsed_results, ensure_ascii=False, default=str
        )

        return redirect('billing:timesheet_excel_confirm')


class TimesheetExcelConfirmView(LoginRequiredMixin, View):
    """解析結果の確認・編集 → MonthlyTimesheet一括登録"""

    def get(self, request):
        raw = request.session.get('timesheet_excel_results')
        if not raw:
            messages.error(request, '解析結果がありません。再度アップロードしてください。')
            return redirect('billing:timesheet_excel_upload')

        parsed_results = json.loads(raw)
        orders = ReceivedOrder.objects.filter(
            status__in=['REGISTERED', 'ACTIVE']
        ).select_related('customer').prefetch_related('items').order_by('-target_month')

        order_items_map = {}
        for order in orders:
            order_items_map[str(order.pk)] = [
                {'id': item.pk, 'name': item.person_name or f'明細{item.pk}'}
                for item in order.items.all()
            ]

        # 自動マッチング: 対象月と作業者名で受注を推定
        from core.utils import normalize_name
        from datetime import date as _date

        for r in parsed_results:
            r['matched_order_id'] = ''
            r['matched_item_id'] = ''
            if r.get('error'):
                continue

            target_month_str = r.get('target_month', '')
            worker_name = r.get('worker_name', '')

            if target_month_str:
                try:
                    tm = _date.fromisoformat(target_month_str)
                except ValueError:
                    tm = None

                if tm:
                    for order in orders:
                        if order.target_month == tm:
                            r['matched_order_id'] = str(order.pk)
                            r['matched_order_display'] = f'{order.customer.name} - {order.project_name or order.order_number} ({order.target_month.strftime("%Y/%m")})'
                            if worker_name:
                                worker_norm = normalize_name(worker_name)
                                for item in order.items.all():
                                    if normalize_name(item.person_name) == worker_norm:
                                        r['matched_item_id'] = str(item.pk)
                                        break
                            break

                    if not r['matched_order_id'] and worker_name:
                        worker_norm = normalize_name(worker_name)
                        for order in orders:
                            for item in order.items.all():
                                if normalize_name(item.person_name) == worker_norm:
                                    r['matched_order_id'] = str(order.pk)
                                    r['matched_item_id'] = str(item.pk)
                                    r['matched_order_display'] = f'{order.customer.name} - {order.project_name or order.order_number} ({order.target_month.strftime("%Y/%m")})'
                                    break
                            if r['matched_order_id']:
                                break

        return render(request, 'billing/timesheet_excel_confirm.html', {
            'results': parsed_results,
            'orders': orders,
            'order_items_json': json.dumps(order_items_map, ensure_ascii=False),
        })

    def post(self, request):
        from billing.services.timesheet_service import create_timesheet

        count = int(request.POST.get('result_count', 0))
        created = 0
        worker_names = []

        for i in range(count):
            if request.POST.get(f'skip_{i}') == '1':
                continue

            order_id = request.POST.get(f'order_id_{i}')
            order = None
            if order_id:
                try:
                    order = ReceivedOrder.objects.get(pk=order_id)
                except ReceivedOrder.DoesNotExist:
                    pass

            order_item_id = request.POST.get(f'order_item_id_{i}')
            order_item = None
            if order_item_id:
                try:
                    order_item = ReceivedOrderItem.objects.get(pk=order_item_id)
                except ReceivedOrderItem.DoesNotExist:
                    pass

            worker_name = request.POST.get(f'worker_name_{i}', '')
            worker_type = request.POST.get(f'worker_type_{i}', 'INTERNAL')
            target_month_str = request.POST.get(f'target_month_{i}', '')
            total_hours = request.POST.get(f'total_hours_{i}', '0')
            work_days = request.POST.get(f'work_days_{i}', '0')
            daily_data_raw = request.POST.get(f'daily_data_{i}', '[]')

            try:
                target_month = dt.date.fromisoformat(f"{target_month_str}-01")
            except ValueError:
                try:
                    target_month = dt.date.fromisoformat(target_month_str)
                except ValueError:
                    messages.warning(request, f'{worker_name}: 対象月が不正なためスキップしました。')
                    continue

            try:
                daily_data = json.loads(daily_data_raw)
            except json.JSONDecodeError:
                daily_data = None

            saved_file_path = request.POST.get(f'saved_file_path_{i}', '')
            excel_file = None
            original_filename = request.POST.get(f'original_filename_{i}', '')
            if saved_file_path:
                try:
                    from django.core.files.storage import default_storage
                    if default_storage.exists(saved_file_path):
                        excel_file = saved_file_path
                except Exception:
                    pass

            ts = create_timesheet(
                order=order,
                order_item=order_item,
                worker_name=worker_name,
                worker_type=worker_type,
                target_month=target_month,
                total_hours=float(total_hours),
                work_days=int(work_days),
                daily_data=daily_data,
                excel_file_path=excel_file,
                original_filename=original_filename,
            )
            # PDF自動生成
            try:
                from billing.services.timesheet_pdf_service import generate_timesheet_pdf
                generate_timesheet_pdf(ts)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f'PDF生成エラー ({worker_name}): {e}')

            worker_names.append(worker_name)
            created += 1

        request.session.pop('timesheet_excel_results', None)

        if created > 0:
            names_str = '、'.join(worker_names)
            messages.success(request, f'{created}件（{len(worker_names)}名: {names_str}）の稼働報告を登録しました。')
        else:
            messages.warning(request, '登録対象がありませんでした。')

        return redirect('billing:timesheet_list')


# ============================================================
# 外部API（PayrollSystem連携）
# ============================================================

@method_decorator([csrf_exempt, require_api_key], name='dispatch')
class TimesheetAPIView(View):
    """
    勤怠データAPI — PayrollSystemが呼び出す

    GET /billing/api/timesheets/?year=2026&month=3
    """

    def get(self, request):
        year = request.GET.get('year')
        month = request.GET.get('month')

        if not year or not month:
            return JsonResponse(
                {'error': 'year and month parameters are required'},
                status=400
            )

        try:
            target_month = dt.date(int(year), int(month), 1)
        except (ValueError, TypeError):
            return JsonResponse(
                {'error': 'Invalid year or month'},
                status=400
            )

        qs = MonthlyTimesheet.objects.filter(
            target_month=target_month
        ).select_related('order', 'order__partner')

        status_filter = request.GET.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        timesheets = []
        for ts in qs:
            timesheets.append({
                'id': ts.pk,
                'employee_id': ts.employee_id or '',
                'worker_name': ts.worker_name,
                'worker_type': ts.worker_type,
                'target_month': ts.target_month.isoformat(),
                'total_hours': float(ts.total_hours),
                'work_days': ts.work_days,
                'overtime_hours': float(ts.overtime_hours),
                'night_hours': float(ts.night_hours),
                'holiday_hours': float(ts.holiday_hours),
                'status': ts.status,
                'order_id': ts.order_id,
                'order_number': ts.order.order_id if ts.order else '',
                'partner_name': (
                    ts.order.partner.name if ts.order and ts.order.partner
                    else ''
                ),
            })

        return JsonResponse({
            'year_month': target_month.isoformat(),
            'count': len(timesheets),
            'timesheets': timesheets,
        })


@method_decorator([csrf_exempt, require_api_key], name='dispatch')
class EmployeeSyncView(View):
    """社員データ同期トリガー"""

    def post(self, request):
        from billing.services.employee_sync import sync_employees

        result = sync_employees()

        if result['errors']:
            return JsonResponse({
                'status': 'error',
                'errors': result['errors'],
            }, status=500)

        return JsonResponse({
            'status': 'ok',
            'created': result['created'],
            'updated': result['updated'],
            'deactivated': result['deactivated'],
        })

    def get(self, request):
        """GETでも同期結果の確認ができる（最終同期日時を返す）"""
        from billing.domain.synced_employee import SyncedEmployee

        count = SyncedEmployee.objects.filter(is_active=True).count()
        latest = SyncedEmployee.objects.order_by('-synced_at').first()

        return JsonResponse({
            'status': 'ok',
            'active_count': count,
            'last_synced_at': (
                latest.synced_at.isoformat() if latest else None
            ),
        })


class ReportSubmissionStatusView(StaffRequiredMixin, View):
    """クライアントへの作業報告書提出状況（月別）"""

    def get(self, request):
        from billing.domain.models import MonthlyTimesheet
        from core.utils import normalize_name

        today = dt.date.today()
        month_str = request.GET.get('month', today.strftime('%Y-%m'))
        try:
            year, month = map(int, month_str.split('-'))
            target_date = dt.date(year, month, 1)
        except (ValueError, TypeError):
            target_date = today.replace(day=1)
            month_str = target_date.strftime('%Y-%m')

        # 対象月の受注
        orders = ReceivedOrder.objects.filter(
            target_month__year=target_date.year,
            target_month__month=target_date.month,
        ).select_related('customer').order_by('customer__name', 'project_name')

        # パートナー側の確定済みMonthlyTimesheetを一括取得（対象月）
        work_reports = MonthlyTimesheet.objects.filter(
            target_month__year=target_date.year,
            target_month__month=target_date.month,
            status='APPROVED',
        )
        # 正規化名 → MonthlyTimesheet のマップ
        wr_map = {}
        for wr in work_reports:
            if wr.worker_name:
                wr_map[normalize_name(wr.worker_name)] = wr

        status_rows = []
        total_orders = 0
        total_sent = 0
        total_prepared = 0

        # クライアント単位グループ: customer_id → group
        customer_groups_map = {}

        for order in orders:
            total_orders += 1
            timesheets = MonthlyTimesheet.objects.filter(received_order=order)
            all_timesheets_for_month = MonthlyTimesheet.objects.filter(
                target_month__year=order.target_month.year,
                target_month__month=order.target_month.month,
            )
            items = ReceivedOrderItem.objects.filter(order=order)

            # クライアントグループの取得or作成
            cid = order.customer_id
            if cid not in customer_groups_map:
                customer_groups_map[cid] = {
                    'customer': order.customer,
                    'orders': [],
                    'rows': [],
                    'all_ready': True,
                    'all_sent': True,
                    'has_any': False,
                    'report_to_email': order.report_to_email or '',
                    'order_ids': [],
                }
            cg = customer_groups_map[cid]
            cg['orders'].append(order)
            cg['order_ids'].append(order.pk)
            if order.report_to_email and not cg['report_to_email']:
                cg['report_to_email'] = order.report_to_email

            if items.exists():
                for item in items:
                    ts = timesheets.filter(received_order_item=item).first()
                    if not ts and item.person_name:
                        ts = timesheets.filter(worker_name=item.person_name).first()
                    if not ts and item.person_name:
                        item_norm = normalize_name(item.person_name)
                        for candidate in all_timesheets_for_month:
                            if normalize_name(candidate.worker_name) == item_norm:
                                ts = candidate
                                break

                    wr = None
                    if ts and ts.status == 'SENT':
                        total_sent += 1
                        status_icon = 'sent'
                        status_label = ts.get_status_display()
                        cg['has_any'] = True
                    elif ts and ts.status in ('SUBMITTED', 'APPROVED'):
                        total_prepared += 1
                        status_icon = 'prepared'
                        status_label = '準備完了'
                        cg['all_sent'] = False
                        cg['has_any'] = True
                    elif ts:
                        status_icon = 'draft'
                        status_label = ts.get_status_display()
                        cg['all_ready'] = False
                        cg['all_sent'] = False
                    else:
                        wr = wr_map.get(normalize_name(item.person_name)) if item.person_name else None
                        if wr and wr.sent_to_client_at:
                            total_sent += 1
                            status_icon = 'sent'
                            status_label = '送付済'
                            cg['has_any'] = True
                        elif wr:
                            total_prepared += 1
                            status_icon = 'prepared'
                            status_label = '準備完了'
                            cg['all_sent'] = False
                            cg['has_any'] = True
                        else:
                            wr = None
                            status_icon = 'none'
                            status_label = '未作成'
                            cg['all_ready'] = False
                            cg['all_sent'] = False

                    drive_url = ''
                    if ts and ts.drive_file_id:
                        drive_url = f'https://drive.google.com/file/d/{ts.drive_file_id}/view'
                    elif (not ts) and wr and wr.drive_file_id:
                        drive_url = f'https://drive.google.com/file/d/{wr.drive_file_id}/view'

                    row_data = {
                        'project_name': order.project_name or '—',
                        'order_number': order.order_number,
                        'worker_name': item.person_name or '—',
                        'order_pk': order.pk,
                        'status_icon': status_icon,
                        'status_label': status_label,
                        'timesheet': ts,
                        'work_report': wr if (not ts) else None,
                        'drive_url': drive_url,
                    }
                    status_rows.append(row_data)
                    cg['rows'].append(row_data)
            else:
                ts = timesheets.first()
                if ts and ts.status == 'SENT':
                    total_sent += 1
                    status_icon = 'sent'
                    status_label = ts.get_status_display()
                    cg['has_any'] = True
                elif ts and ts.status in ('SUBMITTED', 'APPROVED'):
                    total_prepared += 1
                    status_icon = 'prepared'
                    status_label = '準備完了'
                    cg['all_sent'] = False
                    cg['has_any'] = True
                elif ts:
                    status_icon = 'draft'
                    status_label = ts.get_status_display()
                    cg['all_ready'] = False
                    cg['all_sent'] = False
                else:
                    status_icon = 'none'
                    status_label = '未作成'
                    cg['all_ready'] = False
                    cg['all_sent'] = False

                row_data = {
                    'project_name': order.project_name or '—',
                    'order_number': order.order_number,
                    'worker_name': '—',
                    'order_pk': order.pk,
                    'status_icon': status_icon,
                    'status_label': status_label,
                    'timesheet': ts,
                }
                status_rows.append(row_data)
                cg['rows'].append(row_data)

        # グループをリストに変換
        customer_groups = []
        for cg in customer_groups_map.values():
            cg['all_ready'] = cg['all_ready'] and cg['has_any']
            cg['all_sent'] = cg['all_sent'] and cg['has_any']
            # メール送信先: 受注 → クライアント.report_email → クライアント.email
            if not cg['report_to_email']:
                customer = cg['customer']
                cg['report_to_email'] = customer.report_email or customer.email or ''
            cg['has_email'] = bool(cg['report_to_email'])
            customer_groups.append(cg)
        customer_groups.sort(key=lambda g: g['customer'].name)

        # 前月・翌月
        if target_date.month == 1:
            prev_month = dt.date(target_date.year - 1, 12, 1)
        else:
            prev_month = dt.date(target_date.year, target_date.month - 1, 1)
        if target_date.month == 12:
            next_month = dt.date(target_date.year + 1, 1, 1)
        else:
            next_month = dt.date(target_date.year, target_date.month + 1, 1)

        return render(request, 'billing/report_submission_status.html', {
            'month_str': month_str,
            'target_date': target_date,
            'status_rows': status_rows,
            'customer_groups': customer_groups,
            'total_orders': total_orders,
            'total_sent': total_sent,
            'total_prepared': total_prepared,
            'prev_month': prev_month.strftime('%Y-%m'),
            'next_month': next_month.strftime('%Y-%m'),
        })

    def post(self, request):
        """クライアント単位で作業報告書をメール送信する"""
        from billing.services.report_email_service import send_report_email

        order_ids = request.POST.getlist('order_ids')
        if not order_ids:
            messages.error(request, '受注IDが指定されていません。')
            return redirect('billing:report_submission_status')

        total_sent = 0
        errors = []
        for oid in order_ids:
            try:
                order = ReceivedOrder.objects.get(pk=oid)
            except ReceivedOrder.DoesNotExist:
                continue
            result = send_report_email(order)
            if result['success']:
                total_sent += result['sent_count']
            elif result['message']:
                errors.append(result['message'])

        if total_sent > 0:
            messages.success(request, f'{total_sent}名分の報告書を送信しました。')
        if errors:
            messages.error(request, ' / '.join(errors))

        month_str = request.POST.get('month', '')
        redirect_url = 'billing:report_submission_status'
        if month_str:
            return redirect(f'{reverse(redirect_url)}?month={month_str}')
        return redirect(redirect_url)


class CustomerReportEmailUpdateView(StaffRequiredMixin, View):
    """BillingCustomerの報告書送付先メールをAJAX更新"""

    def post(self, request, pk):
        import json
        from billing.domain.models import BillingCustomer

        try:
            customer = BillingCustomer.objects.get(pk=pk)
        except BillingCustomer.DoesNotExist:
            return JsonResponse({'error': '請求先が見つかりません'}, status=404)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            data = request.POST

        report_email = data.get('report_email', '').strip()
        customer.report_email = report_email
        customer.save(update_fields=['report_email'])

        return JsonResponse({'success': True, 'report_email': report_email})


class ReportSendPreviewView(StaffRequiredMixin, View):
    """送信プレビュー画面: 宛先・件名・添付ファイルを確認してから送信"""

    def get(self, request):
        from billing.domain.models import BillingCustomer
        from billing.application.services.mail_service import parse_email_list
        from core.utils import normalize_name

        customer_id = request.GET.get('customer_id')
        month_str = request.GET.get('month', '')

        if not customer_id:
            messages.error(request, 'クライアントIDが指定されていません。')
            return redirect('billing:report_submission_status')

        try:
            customer = BillingCustomer.objects.get(pk=customer_id)
        except BillingCustomer.DoesNotExist:
            messages.error(request, 'クライアントが見つかりません。')
            return redirect('billing:report_submission_status')

        # 対象月
        try:
            year, month = map(int, month_str.split('-'))
            target_date = dt.date(year, month, 1)
        except (ValueError, TypeError):
            target_date = dt.date.today().replace(day=1)
            month_str = target_date.strftime('%Y-%m')

        # 対象受注
        orders = ReceivedOrder.objects.filter(
            customer=customer,
            target_month__year=target_date.year,
            target_month__month=target_date.month,
        )

        # 送信先
        to_email = ''
        for o in orders:
            if o.report_to_email:
                to_email = o.report_to_email
                break
        if not to_email:
            to_email = customer.report_email or customer.email or ''

        cc_email = ''
        for o in orders:
            if o.report_cc_emails:
                cc_email = o.report_cc_emails
                break
        if not cc_email:
            cc_email = customer.cc_email or ''

        # 添付ファイル一覧
        attachments = []
        order_ids = []
        for order in orders:
            order_ids.append(order.pk)
            month_label = order.target_month.strftime('%Y年%m月')
            project = order.project_name or order.order_number

            def _std_name(wn, ext):
                clean = wn.replace('\u3000', '').replace(' ', '')
                return f'{month_label}{project}_（{clean}）作業報告書.{ext}'

            worker_names = list(
                order.items.exclude(person_name='').values_list('person_name', flat=True)
            )
            for wname in worker_names:
                ts = MonthlyTimesheet.objects.filter(received_order=order, worker_name=wname).first()
                if not ts:
                    wname_norm = normalize_name(wname)
                    for candidate in MonthlyTimesheet.objects.filter(
                        target_month__year=order.target_month.year,
                        target_month__month=order.target_month.month,
                    ):
                        if normalize_name(candidate.worker_name) == wname_norm:
                            ts = candidate
                            break
                if ts and ts.status in ('SUBMITTED', 'APPROVED'):
                    attachments.append({
                        'worker_name': ts.worker_name,
                        'source': 'MonthlyTimesheet',
                        'excel': _std_name(ts.worker_name, 'xlsm') if ts.excel_file and ts.excel_file.name else '—',
                        'has_excel': bool(ts.excel_file and ts.excel_file.name),
                        'pdf': _std_name(ts.worker_name, 'pdf') if ts.pdf_file and ts.pdf_file.name else '—',
                        'has_pdf': bool(ts.pdf_file and ts.pdf_file.name),
                        'hours': ts.total_hours,
                        'days': ts.work_days,
                    })
                else:
                    # パートナー提出分にフォールバック
                    from billing.domain.models import MonthlyTimesheet
                    wname_norm = normalize_name(wname)
                    wr = None
                    for candidate in MonthlyTimesheet.objects.filter(
                        target_month__year=order.target_month.year,
                        target_month__month=order.target_month.month,
                        status='APPROVED',
                    ):
                        if candidate.worker_name and normalize_name(candidate.worker_name) == wname_norm:
                            wr = candidate
                            break
                    if wr:
                        attachments.append({
                            'worker_name': wr.worker_name,
                            'source': 'MonthlyTimesheet（パートナー提出）',
                            'excel': _std_name(wr.worker_name, 'xlsm') if wr.excel_file and wr.excel_file.name else '—',
                            'has_excel': bool(wr.excel_file and wr.excel_file.name),
                            'pdf': _std_name(wr.worker_name, 'pdf') if wr.pdf_file and wr.pdf_file.name else '—',
                            'has_pdf': bool(wr.pdf_file and wr.pdf_file.name),
                            'hours': wr.total_hours or '—',
                            'days': wr.work_days or '—',
                        })

        target_month_str = target_date.strftime('%Y年%m月')
        subject = f'【マックプランニング】{target_month_str}度 作業報告書のご送付'

        # メール本文プレビュー
        worker_lines = []
        for att in attachments:
            worker_lines.append(f'  ・{att["worker_name"]}（{att["hours"]}h / {att["days"]}日）')
        workers_summary = '\n'.join(worker_lines) if worker_lines else '  （なし）'

        # 案件名一覧
        project_names = []
        for order in orders:
            pn = order.project_name or order.order_number
            if pn not in project_names:
                project_names.append(pn)
        project_display = '、'.join(project_names)

        body = f"""お世話になっております。
マックプランニングです。

{target_month_str}度の作業報告書をお送りいたします。

■ 対象案件: {project_display}
■ 作業者:
{workers_summary}

添付ファイルをご確認いただけますようお願いいたします。

何かご不明な点がございましたら、お気軽にご連絡ください。

よろしくお願いいたします。

---
株式会社マックプランニング"""

        return render(request, 'billing/report_send_preview.html', {
            'customer': customer,
            'month_str': month_str,
            'target_month_str': target_month_str,
            'to_email': to_email,
            'cc_email': cc_email,
            'subject': subject,
            'body': body,
            'attachments': attachments,
            'order_ids': order_ids,
        })

    def post(self, request):
        """実際にメール送信"""
        from billing.services.report_email_service import send_report_email

        order_ids = request.POST.getlist('order_ids')
        if not order_ids:
            messages.error(request, '受注IDが指定されていません。')
            return redirect('billing:report_submission_status')

        total_sent = 0
        errors = []
        for oid in order_ids:
            try:
                order = ReceivedOrder.objects.get(pk=oid)
            except ReceivedOrder.DoesNotExist:
                continue
            result = send_report_email(order)
            if result['success']:
                total_sent += result['sent_count']
            elif result['message']:
                errors.append(result['message'])

        if total_sent > 0:
            messages.success(request, f'{total_sent}名分の報告書を送信しました。')
        if errors:
            messages.error(request, ' / '.join(errors))

        month_str = request.POST.get('month', '')
        redirect_url = 'billing:report_submission_status'
        if month_str:
            return redirect(f'{reverse(redirect_url)}?month={month_str}')
        return redirect(redirect_url)
