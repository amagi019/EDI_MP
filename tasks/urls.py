from django.urls import path
from tasks import views

app_name = 'tasks'

urlpatterns = [
    path('calendar/', views.reminder_calendar, name='calendar'),
    path('calendar/events/', views.calendar_events_api, name='calendar_events'),
    path('<int:task_id>/complete/', views.task_force_complete, name='task_force_complete'),
    path('<int:task_id>/delete/', views.task_delete, name='task_delete'),
    path('bulk-complete/', views.bulk_force_complete, name='bulk_force_complete'),
    path('mark-payment-done/', views.mark_payment_done, name='mark_payment_done'),
]
