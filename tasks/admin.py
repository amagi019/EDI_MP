from django.contrib import admin
from .models import MonthlyTask


@admin.register(MonthlyTask)
class MonthlyTaskAdmin(admin.ModelAdmin):
    list_display = ('partner', 'project', 'work_month', 'task_type', 'responsible', 'deadline', 'status')
    list_filter = ('status', 'task_type', 'responsible', 'partner')
    list_editable = ('status',)
    search_fields = ('partner__name', 'project__name')
    ordering = ('deadline',)
