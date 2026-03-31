from django.urls import path
from tasks import views

app_name = 'tasks'

urlpatterns = [
    path('calendar/', views.reminder_calendar, name='calendar'),
    path('calendar/events/', views.calendar_events_api, name='calendar_events'),
]
