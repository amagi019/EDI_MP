import datetime
import json

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.urls import reverse

from core.permissions import Role, get_user_role, get_user_partner
from core.domain.models import MasterContractProgress
from orders.models import Order, OrderCycle
from tasks.models import MonthlyTask
from invoices.models import Invoice
from billing.domain.models import (
    BillingInvoice, ReceivedOrder, StaffTimesheet,
)


@login_required
def dashboard(request):
    """進捗管理ダッシュボード"""
    user = request.user
    role = get_user_role(user)
    partner = get_user_partner(user)

    # フィルター条件の構築
    order_filter = Q()
    invoice_filter = Q()

    if role != Role.STAFF:
        if partner:
            order_filter &= Q(partner=partner)
            invoice_filter &= Q(order__partner=partner)
        else:
            order_filter = Q(pk__in=[])
            invoice_filter = Q(pk__in=[])

    # 統計情報の取得
    unconfirmed_orders = Order.objects.filter(order_filter, status='UNCONFIRMED').select_related('partner', 'project')
    received_orders = Order.objects.filter(order_filter, status__in=['RECEIVED', 'APPROVED']).select_related('partner', 'project')
    confirming_invoices = Invoice.objects.filter(invoice_filter, status__in=['ISSUED', 'SENT']).select_related('order__partner', 'order__project')

    # スタッフ用：契約進捗リスト
    contract_progress_list = []
    if role == Role.STAFF:
        contract_progress_list = MasterContractProgress.objects.select_related('partner').all().order_by('-updated_at')

    # 月次タスク管理（スタッフ用）
    monthly_tasks = []
    overdue_tasks = []
    upcoming_tasks = []
    overdue_count = 0
    this_week_count = 0

    if role == Role.STAFF:
        today = datetime.date.today()
        week_later = today + datetime.timedelta(days=7)

        all_pending = MonthlyTask.objects.filter(
            status='PENDING'
        ).select_related('partner', 'project').order_by('deadline')

        overdue_tasks = [t for t in all_pending if t.deadline < today]
        upcoming_tasks = [t for t in all_pending if today <= t.deadline <= week_later]
        overdue_count = len(overdue_tasks)
        this_week_count = len(upcoming_tasks)

        # ダッシュボードには超過 + 今週期限を表示（最大8件）
        monthly_tasks = (overdue_tasks + upcoming_tasks)[:8]

        # 各タスクに最適な遷移先URLを付与
        for task in monthly_tasks:
            task.action_url = _resolve_task_action_url(task)

    # リマインドカレンダー（スタッフ用）
    calendar_events_json = '[]'
    cal_year = 0
    cal_month = 0
    cal_today = ''
    if role == Role.STAFF:
        today = datetime.date.today()
        cal_year = today.year
        cal_month = today.month
        cal_today = today.isoformat()
        try:
            from tasks.scheduler import get_all_calendar_events
            events = get_all_calendar_events(cal_year, cal_month)
            calendar_events_json = json.dumps(events, ensure_ascii=False)
        except Exception:
            calendar_events_json = '[]'

    # クライアント管理データ
    client_received_orders = []
    client_pending_timesheets = []
    client_invoices_summary = {}
    if role == Role.STAFF:
        client_received_orders = ReceivedOrder.objects.filter(
            status__in=['REGISTERED', 'ACTIVE']
        ).select_related('customer')[:5]
        client_pending_timesheets = StaffTimesheet.objects.filter(
            status__in=['DRAFT', 'SUBMITTED']
        ).select_related('order__customer')[:5]
        client_invoices_summary = {
            'draft': BillingInvoice.objects.filter(status='DRAFT').count(),
            'issued': BillingInvoice.objects.filter(status='ISSUED').count(),
            'sent': BillingInvoice.objects.filter(status='SENT').count(),
            'paid': BillingInvoice.objects.filter(status='PAID').count(),
        }

    # 発注進捗パイプライン（スタッフ用）
    pipeline_data = []
    partner_list = []
    client_pipeline_data = []
    client_list = []
    if role == Role.STAFF:
        pipeline_data, partner_list = _build_pipeline_data()
        client_pipeline_data, client_list = _build_client_pipeline_data()

    context = {
        'unconfirmed_orders_count': unconfirmed_orders.count(),
        'received_orders_count': received_orders.count(),
        'confirming_invoices_count': confirming_invoices.count(),
        'unconfirmed_orders': unconfirmed_orders,
        'received_orders': received_orders,
        'confirming_invoices': confirming_invoices,
        'is_authorized': role == Role.STAFF or (partner is not None),
        'contract_progress_list': contract_progress_list,
        # 月次タスク
        'monthly_tasks': monthly_tasks,
        'overdue_count': overdue_count,
        'this_week_count': this_week_count,
        # カレンダー
        'calendar_events_json': calendar_events_json,
        'cal_year': cal_year,
        'cal_month': cal_month,
        'cal_today': cal_today,
        # クライアント管理
        'client_received_orders': client_received_orders,
        'client_pending_timesheets': client_pending_timesheets,
        'client_invoices': client_invoices_summary,
        # パイプライン
        'pipeline_data': json.dumps(pipeline_data, ensure_ascii=False, default=str),
        'partner_list': partner_list,
        'client_pipeline_data': json.dumps(client_pipeline_data, ensure_ascii=False, default=str),
        'client_list': client_list,
    }
    return render(request, 'core/dashboard.html', context)


def _resolve_task_action_url(task):
    """
    タスク種別に応じた最適な遷移先URLを返す。
    請求書関連タスクは、対応する請求書があればその編集/確認画面に直行する。
    """
    if task.task_type == 'INVOICE_CREATE':
        # 対象の請求書を検索
        invoice = Invoice.objects.filter(
            order__partner=task.partner,
            order__project=task.project,
            target_month=task.work_month,
        ).first()
        if invoice:
            if invoice.status == 'DRAFT':
                return reverse('invoices:invoice_edit', kwargs={'invoice_id': invoice.pk})
            elif invoice.status == 'PENDING_REVIEW':
                return reverse('invoices:staff_invoice_review', kwargs={'invoice_id': invoice.pk})
            elif invoice.status in ('ISSUED', 'SENT'):
                return reverse('invoices:invoice_send_preview', kwargs={'invoice_id': invoice.pk})
            else:
                return reverse('invoices:staff_invoice_review', kwargs={'invoice_id': invoice.pk})
        return reverse('invoices:invoice_list')

    elif task.task_type == 'INVOICE_APPROVE':
        invoice = Invoice.objects.filter(
            order__partner=task.partner,
            order__project=task.project,
            target_month=task.work_month,
        ).first()
        if invoice:
            return reverse('invoices:staff_invoice_review', kwargs={'invoice_id': invoice.pk})
        return reverse('invoices:invoice_list')

    elif task.task_type == 'ORDER_CREATE':
        return reverse('orders:order_create')
    elif task.task_type == 'ORDER_APPROVE':
        return reverse('orders:order_list')
    elif task.task_type == 'REPORT_UPLOAD':
        # パイプラインから遷移時にパートナー＋月でフィルタ
        url = reverse('invoices:work_report_upload')
        if hasattr(task, 'partner_id') and hasattr(task, 'work_month'):
            from orders.models import Order
            order = Order.objects.filter(
                partner_id=task.partner_id,
                project_id=task.project_id,
                work_start__year=task.work_month.year,
                work_start__month=task.work_month.month,
            ).first()
            if order:
                url += f'?order_id={order.order_id}'
        return url
    else:
        return reverse('invoices:invoice_list')


TASK_TYPE_ORDER = [
    'ORDER_CREATE', 'ORDER_APPROVE', 'REPORT_UPLOAD',
    'INVOICE_CREATE', 'INVOICE_APPROVE', 'INVOICE_APPROVE',
]
STEP_LABELS = ['注文書', '承認', '報告', '請求書', '送付', '承諾', '支払']


def _shorten_name(name):
    """会社名を短縮する（株式会社/合同会社などを除去）"""
    import re
    name = re.sub(r'^(株式会社|合同会社|有限会社|一般社団法人)\s*', '', name)
    name = re.sub(r'\s*(株式会社|合同会社|有限会社)$', '', name)
    return name


def _build_pipeline_data():
    """
    OrderCycle からパイプラインデータを構築する。
    cycle ごとに7ステップの状態を返す。
    """
    today = datetime.date.today()

    # 直近6ヶ月分のサイクルを取得
    six_months_ago = today.replace(day=1)
    for _ in range(5):
        if six_months_ago.month == 1:
            six_months_ago = six_months_ago.replace(year=six_months_ago.year - 1, month=12)
        else:
            six_months_ago = six_months_ago.replace(month=six_months_ago.month - 1)

    cycles = OrderCycle.objects.filter(
        work_month__gte=six_months_ago
    ).select_related('partner', 'project').prefetch_related('tasks', 'orders__invoice')

    # タスク種別 → ステップインデックスのマッピング
    type_to_step = {
        'ORDER_CREATE': 0,
        'ORDER_APPROVE': 1,
        'REPORT_UPLOAD': 2,
        'INVOICE_CREATE': 3,
    }

    partner_names = set()
    pipeline = []

    for cycle in cycles:
        tasks = list(cycle.tasks.all())
        partner_names.add(_shorten_name(cycle.partner.name))

        # OrderCycle に紐付く Invoice をリレーション経由で取得
        invoice = None
        for order in cycle.orders.all():
            if hasattr(order, 'invoice'):
                invoice = order.invoice
                break

        steps = []
        worst_urgency = 999

        for i, label in enumerate(STEP_LABELS):
            step = {
                'label': label,
                'status': 'pending',
                'deadline': None,
                'days': None,
                'url': None,
                'task_id': None,
            }

            if i <= 3:
                # MonthlyTaskベース（ステップ0〜3）
                task_type = list(type_to_step.keys())[i]
                matching = [t for t in tasks if t.task_type == task_type]
                if matching:
                    t = matching[0]
                    step['task_id'] = t.pk
                    step['responsible'] = t.responsible
                    step['deadline'] = t.deadline.strftime('%m/%d')
                    if t.status == 'DONE':
                        step['status'] = 'done'
                        if t.completed_at:
                            step['days'] = t.completed_at.strftime('%m/%d') + '完了'
                    else:
                        diff = (t.deadline - today).days
                        if diff < 0:
                            step['status'] = 'overdue'
                            step['days'] = f'{abs(diff)}日超過'
                            step['url'] = _resolve_task_action_url(t)
                            worst_urgency = min(worst_urgency, diff)
                        else:
                            step['status'] = 'active'
                            step['days'] = f'あと{diff}日'
                            step['url'] = _resolve_task_action_url(t)
                            worst_urgency = min(worst_urgency, diff)
            else:
                # ステップ4(送付)・5(承諾)・6(支払): Invoiceステータス or payment_completed で判定
                if cycle.payment_completed:
                    # Invoice なしで手動完了された場合 → 全て done
                    step['status'] = 'done'
                    if i == 6 and cycle.payment_completed_at:
                        step['days'] = cycle.payment_completed_at.strftime('%m/%d') + '完了'
                elif i == 4:
                    if invoice and invoice.status in ('SENT', 'CONFIRMED', 'PAID'):
                        step['status'] = 'done'
                    elif invoice:
                        step['status'] = 'active'
                        step['days'] = '送付待ち'
                elif i == 5:
                    approve_tasks = [t for t in tasks if t.task_type == 'INVOICE_APPROVE']
                    if approve_tasks:
                        step['task_id'] = approve_tasks[0].pk
                    if invoice and invoice.status in ('CONFIRMED', 'PAID'):
                        step['status'] = 'done'
                    elif invoice and invoice.status == 'SENT':
                        step['status'] = 'active'
                        step['days'] = '承諾待ち'
                elif i == 6:
                    if invoice and invoice.status == 'PAID':
                        step['status'] = 'done'
                        if invoice.payment_date:
                            step['days'] = invoice.payment_date.strftime('%m/%d') + '完了'
                    elif invoice and invoice.status in ('SENT', 'CONFIRMED'):
                        step['status'] = 'active'
                        if invoice.payment_deadline:
                            diff = (invoice.payment_deadline - today).days
                            step['deadline'] = invoice.payment_deadline.strftime('%m/%d')
                            if diff < 0:
                                step['status'] = 'overdue'
                                step['days'] = f'{abs(diff)}日超過'
                                worst_urgency = min(worst_urgency, diff)
                            else:
                                step['days'] = f'あと{diff}日'
                                worst_urgency = min(worst_urgency, diff)
                        else:
                            step['days'] = '確認待ち'
                    elif invoice and invoice.payment_deadline:
                        diff = (invoice.payment_deadline - today).days
                        step['deadline'] = invoice.payment_deadline.strftime('%m/%d')
                        if diff < 0:
                            step['days'] = f'{abs(diff)}日超過'
                        else:
                            step['days'] = f'あと{diff}日'

            steps.append(step)

        # 全体ステータス判定
        has_overdue = any(s['status'] == 'overdue' for s in steps)
        all_done = all(s['status'] == 'done' for s in steps)
        if has_overdue:
            row_status = 'overdue'
        elif all_done:
            row_status = 'done'
        else:
            row_status = 'active'

        # タスクIDリスト（強制完了用 — DONE以外のみ）
        task_ids = [t.pk for t in tasks if t.status != 'DONE']

        # 最初の注文書ID（詳細遷移用）
        first_order = next((o for o in cycle.orders.all()), None)
        order_id = first_order.order_id if first_order else None

        pipeline.append({
            'partner_name': _shorten_name(cycle.partner.name),
            'project_name': cycle.project.name,
            'work_month': cycle.work_month.strftime('%Y/%m'),
            'steps': steps,
            'row_status': row_status,
            'urgency': worst_urgency,
            'task_ids': task_ids,
            'partner_id': cycle.partner_id,
            'project_id': cycle.project_id,
            'work_month_raw': cycle.work_month.isoformat(),
            'cycle_id': cycle.pk,
            'order_id': order_id,
        })

    # ソート: 会社名 → 対象月昇順
    pipeline.sort(key=lambda r: (r['partner_name'], r['work_month']))

    return pipeline, sorted(partner_names)


CLIENT_STEP_LABELS = ['受注', '勤怠', '請求書', '入金']


def _build_client_pipeline_data():
    """
    クライアント側パイプラインを構築する。
    ReceivedOrder(ACTIVE)ごとに4ステップの状態を返す。
    """
    today = datetime.date.today()

    # 直近6ヶ月分のアクティブ受注を取得
    six_months_ago = today.replace(day=1)
    for _ in range(5):
        if six_months_ago.month == 1:
            six_months_ago = six_months_ago.replace(year=six_months_ago.year - 1, month=12)
        else:
            six_months_ago = six_months_ago.replace(month=six_months_ago.month - 1)

    orders = ReceivedOrder.objects.filter(
        target_month__gte=six_months_ago,
        status__in=['REGISTERED', 'ACTIVE', 'COMPLETED'],
    ).select_related('customer').order_by('-target_month')

    client_names = set()
    pipeline = []

    for ro in orders:
        cname = _shorten_name(ro.customer.name)
        client_names.add(cname)
        steps = []
        worst_urgency = 999

        # ステップ1: 受注
        step1 = {'label': '受注', 'status': 'done', 'deadline': None, 'days': None, 'url': None}
        if ro.status == 'REGISTERED':
            step1['status'] = 'active'
            step1['url'] = reverse('billing:received_order_list')
        steps.append(step1)

        # ステップ2: 勤怠報告
        ts = StaffTimesheet.objects.filter(order=ro).first()
        step2 = {'label': '勤怠', 'status': 'pending', 'deadline': None, 'days': None, 'url': None}
        if ts:
            if ts.status in ('SENT', 'APPROVED'):
                step2['status'] = 'done'
            else:
                step2['status'] = 'active'
                step2['url'] = reverse('billing:timesheet_list')
        steps.append(step2)

        # ステップ3: 請求書
        inv = BillingInvoice.objects.filter(received_order=ro).first()
        step3 = {'label': '請求書', 'status': 'pending', 'deadline': None, 'days': None, 'url': None}
        if inv:
            if inv.status in ('SENT', 'PAID'):
                step3['status'] = 'done'
            else:
                step3['status'] = 'active'
                step3['url'] = reverse('billing:invoice_list')
        steps.append(step3)

        # ステップ4: 入金
        step4 = {'label': '入金', 'status': 'pending', 'deadline': None, 'days': None, 'url': None}
        if inv and inv.status == 'PAID':
            step4['status'] = 'done'
        elif inv and inv.status == 'SENT':
            step4['status'] = 'active'
            if inv.due_date:
                diff = (inv.due_date - today).days
                step4['deadline'] = inv.due_date.strftime('%m/%d')
                if diff < 0:
                    step4['status'] = 'overdue'
                    step4['days'] = f'{abs(diff)}日超過'
                    worst_urgency = min(worst_urgency, diff)
                else:
                    step4['days'] = f'あと{diff}日'
                    worst_urgency = min(worst_urgency, diff)
        steps.append(step4)

        # 行ステータス
        has_overdue = any(s['status'] == 'overdue' for s in steps)
        all_done = all(s['status'] == 'done' for s in steps)
        row_status = 'overdue' if has_overdue else ('done' if all_done else 'active')

        pipeline.append({
            'partner_name': cname,
            'project_name': ro.project_name or '---',
            'work_month': ro.target_month.strftime('%Y/%m'),
            'steps': steps,
            'row_status': row_status,
            'urgency': worst_urgency,
            'task_ids': [],
        })

    pipeline.sort(key=lambda r: (r['partner_name'], r['work_month']))
    return pipeline, sorted(client_names)


