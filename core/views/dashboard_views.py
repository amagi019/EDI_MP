import datetime
import json

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Q

from core.permissions import Role, get_user_role, get_user_partner
from core.domain.models import MasterContractProgress
from orders.models import Order
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
    }
    return render(request, 'core/dashboard.html', context)

