"""
billing プレゼンテーション層 - 受注管理・勤怠報告・ロールフォワード
"""
import datetime as dt
import json
from decimal import Decimal
from itertools import groupby

from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.contrib import messages
from django.views import View
from django.views.generic import ListView, DetailView
from django.views.decorators.csrf import csrf_exempt

from billing.domain.models import (
    BillingCustomer, ReceivedOrder, ReceivedOrderItem, StaffTimesheet,
)
from core.api_auth import require_api_key
from core.permissions import StaffRequiredMixin


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
        pdf_file = request.FILES.get('order_pdf')

        if not customer_id or not pdf_file:
            messages.error(request, '取引先とPDFファイルを選択してください。')
            return redirect('billing:received_order_create')

        customer = get_object_or_404(BillingCustomer, pk=customer_id)

        try:
            order, parsed, errors = create_received_order_from_pdf(
                pdf_file, customer, user=request.user
            )
            if errors:
                for e in errors:
                    messages.warning(request, f'⚠ {e}')
            messages.success(
                request,
                f'受注を登録しました（{parsed["format"]}形式・注文番号: {order.order_number or "なし"}）'
            )
            return redirect('billing:received_order_detail', pk=order.pk)
        except Exception as e:
            messages.error(request, f'PDFパースに失敗しました: {e}')
            return redirect('billing:received_order_create')

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
# 勤怠報告（StaffTimesheet）
# ============================================================

class TimesheetListView(StaffRequiredMixin, ListView):
    """勤怠報告一覧"""
    model = StaffTimesheet
    template_name = 'billing/timesheet_list.html'
    context_object_name = 'timesheets'


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
        order = get_object_or_404(ReceivedOrder, pk=order_id)

        target_month_str = request.POST.get('target_month', '')
        try:
            target_month = dt.date.fromisoformat(f"{target_month_str}-01")
        except ValueError:
            messages.error(request, '対象月の形式が正しくありません。')
            return redirect('billing:timesheet_create')

        order_item = order.items.first()
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

        ts = get_object_or_404(StaffTimesheet, pk=pk)
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

        ts = get_object_or_404(StaffTimesheet, pk=pk)
        default_subject = f'{ts.worker_name}の稼働報告'
        default_body = _build_default_body(ts, ts.order, ts.order.customer)
        return render(request, 'billing/timesheet_send.html', {
            'timesheet': ts,
            'default_subject': default_subject,
            'default_body': default_body,
        })

    def post(self, request, pk):
        from billing.services.timesheet_service import send_work_report_email

        ts = get_object_or_404(StaffTimesheet, pk=pk)
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

class TimesheetExcelUploadView(StaffRequiredMixin, View):
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


class TimesheetExcelConfirmView(StaffRequiredMixin, View):
    """解析結果の確認・編集 → StaffTimesheet一括登録"""

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
            if not order_id:
                continue

            try:
                order = ReceivedOrder.objects.get(pk=order_id)
            except ReceivedOrder.DoesNotExist:
                continue

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

        qs = StaffTimesheet.objects.filter(
            target_month=target_month
        ).select_related('order', 'order__customer')

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
                'status': ts.status,
                'order_id': ts.order_id,
                'order_number': ts.order.order_number if ts.order else '',
                'customer_name': (
                    ts.order.customer.name if ts.order and ts.order.customer
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
