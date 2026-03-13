from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Q

from core.permissions import Role, get_user_role, get_user_partner
from core.domain.models import MasterContractProgress
from orders.models import Order
from invoices.models import Invoice


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

    context = {
        'unconfirmed_orders_count': unconfirmed_orders.count(),
        'received_orders_count': received_orders.count(),
        'confirming_invoices_count': confirming_invoices.count(),
        'unconfirmed_orders': unconfirmed_orders,
        'received_orders': received_orders,
        'confirming_invoices': confirming_invoices,
        'is_authorized': role == Role.STAFF or (partner is not None),
        'contract_progress_list': contract_progress_list,
    }
    return render(request, 'core/dashboard.html', context)
