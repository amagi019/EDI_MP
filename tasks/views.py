"""
タスクビュー — リマインドカレンダー / タスク完了・削除
"""
import datetime

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST
from django.utils import timezone

from core.permissions import staff_required
from tasks.models import MonthlyTask


@staff_required
def reminder_calendar(request):
    """リマインドカレンダー画面"""
    today = datetime.date.today()
    year = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))

    # 前月/翌月の計算
    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1

    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1

    return render(request, 'tasks/calendar.html', {
        'year': year,
        'month': month,
        'prev_year': prev_year,
        'prev_month': prev_month,
        'next_year': next_year,
        'next_month': next_month,
        'today': today.isoformat(),
    })


@staff_required
def calendar_events_api(request):
    """カレンダーイベントJSON API"""
    from tasks.scheduler import get_all_calendar_events

    today = datetime.date.today()
    year = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))

    events = get_all_calendar_events(year, month)
    return JsonResponse({'events': events})


@staff_required
@require_POST
def task_force_complete(request, task_id):
    """月次タスクを強制完了にする"""
    try:
        task = MonthlyTask.objects.get(pk=task_id)
    except MonthlyTask.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'タスクが見つかりません'}, status=404)

    task.status = 'DONE'
    task.completed_at = timezone.now()
    task.note = (task.note + '\n' if task.note else '') + '手動で強制完了'
    task.save()
    return JsonResponse({'ok': True})


@staff_required
@require_POST
def task_delete(request, task_id):
    """月次タスクを削除する"""
    try:
        task = MonthlyTask.objects.get(pk=task_id)
    except MonthlyTask.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'タスクが見つかりません'}, status=404)

    task.delete()
    return JsonResponse({'ok': True})


@staff_required
@require_POST
def bulk_force_complete(request):
    """複数タスクを一括で強制完了にする"""
    import json
    try:
        body = json.loads(request.body)
        task_ids = body.get('task_ids', [])
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'ok': False, 'error': '不正なリクエスト'}, status=400)

    if not task_ids:
        return JsonResponse({'ok': False, 'error': 'タスクIDが指定されていません'}, status=400)

    count = MonthlyTask.objects.filter(
        pk__in=task_ids
    ).exclude(
        status='DONE'
    ).update(
        status='DONE',
        completed_at=timezone.now(),
        note='一括強制完了',
    )
    return JsonResponse({'ok': True, 'count': count})


@staff_required
@require_POST
def mark_payment_done(request):
    """支払ステップを手動で完了にする（Invoice.status → PAID、またはOrderCycle.payment_completed）"""
    import json
    from invoices.models import Invoice
    from orders.models import OrderCycle
    try:
        body = json.loads(request.body)
        partner_id = body.get('partner_id')
        project_id = body.get('project_id')
        work_month = body.get('work_month')
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'ok': False, 'error': '不正なリクエスト'}, status=400)

    if not all([partner_id, project_id, work_month]):
        return JsonResponse({'ok': False, 'error': 'パラメータ不足'}, status=400)

    # 1. Invoice がある場合は PAID に更新
    invoices = Invoice.objects.filter(
        order__partner_id=partner_id,
        order__project_id=project_id,
        target_month=work_month,
    ).exclude(status='PAID')

    count = invoices.update(
        status='PAID',
        payment_date=datetime.date.today(),
    )

    if count > 0:
        return JsonResponse({'ok': True, 'count': count})

    # 2. Invoice がない場合は OrderCycle のフラグで完了にする
    from django.utils import timezone
    cycle_count = OrderCycle.objects.filter(
        partner_id=partner_id,
        project_id=project_id,
        work_month=work_month,
        payment_completed=False,
    ).update(
        payment_completed=True,
        payment_completed_at=timezone.now(),
    )

    if cycle_count > 0:
        return JsonResponse({
            'ok': True,
            'count': cycle_count,
            'warning': '請求書なしで支払完了にしました',
        })

    return JsonResponse({'ok': False, 'error': '対象が見つかりません（既に完了済みの可能性）'})


