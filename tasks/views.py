"""
タスクビュー — リマインドカレンダー
"""
import datetime

from django.http import JsonResponse
from django.shortcuts import render

from core.permissions import staff_required


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
