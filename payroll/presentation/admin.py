"""
payroll 管理画面
"""
from django.contrib import admin
from payroll.domain.models import (
    Employee, EmployeeBankAccount, InsuranceRate,
    WithholdingTaxRow, ResidentTaxSchedule, Payroll,
)
from payroll.domain.permissions import PayrollPermission
from payroll.domain.settings import PayrollSettings


class BankAccountInline(admin.StackedInline):
    model = EmployeeBankAccount
    extra = 0


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = [
        'employee_id', 'name', 'base_salary',
        'position_allowance', 'standard_remuneration',
        'is_active']
    list_filter = ['is_active', 'pension_enrolled', 'nursing_enrolled']
    search_fields = ['name', 'employee_id']
    inlines = [BankAccountInline]
    fieldsets = (
        ('基本情報', {
            'fields': (
                'employee_id', 'name', 'name_kana',
                'birth_date', 'hire_date', 'insurance_start_date',
                'email', 'phone', 'is_active')
        }),
        ('住所', {
            'fields': ('postal_code', 'address_1', 'address_2')
        }),
        ('給与', {
            'fields': (
                'base_salary', 'position_allowance',
                'housing_allowance', 'commuting_allowance',
                'standard_monthly_hours')
        }),
        ('税・保険', {
            'fields': (
                'dependents_count', 'is_tax_exempt',
                'pension_enrolled', 'health_enrolled',
                'nursing_enrolled', 'employment_enrolled',
                'standard_remuneration')
        }),
    )


@admin.register(InsuranceRate)
class InsuranceRateAdmin(admin.ModelAdmin):
    list_display = [
        'fiscal_year', 'pension_rate', 'health_rate',
        'nursing_rate', 'employment_rate_employee',
        'prefecture']


@admin.register(WithholdingTaxRow)
class WithholdingTaxRowAdmin(admin.ModelAdmin):
    list_display = [
        'fiscal_year', 'salary_from', 'salary_to',
        'tax_dep_0', 'tax_dep_1', 'tax_dep_2', 'tax_dep_3']
    list_filter = ['fiscal_year']
    ordering = ['fiscal_year', 'salary_from']


@admin.register(ResidentTaxSchedule)
class ResidentTaxScheduleAdmin(admin.ModelAdmin):
    list_display = [
        'employee', 'fiscal_year', 'municipality',
        'month_06', 'month_07', 'month_08']
    list_filter = ['fiscal_year']


@admin.register(Payroll)
class PayrollAdmin(admin.ModelAdmin):
    list_display = [
        'employee', 'year_month', 'gross_pay',
        'deduction_total', 'net_pay', 'status',
        'transfer_status']
    list_filter = ['status', 'transfer_status', 'year_month']
    search_fields = ['employee__name']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(PayrollPermission)
class PayrollPermissionAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'permission_level', 'employee',
        'can_calculate', 'can_approve', 'can_transfer']
    list_filter = ['permission_level']


@admin.register(PayrollSettings)
class PayrollSettingsAdmin(admin.ModelAdmin):
    list_display = [
        'payment_day', 'closing_day',
        'overtime_rate_multiplier', 'updated_at']

    def has_add_permission(self, request):
        # シングルトン: 既に1件あれば追加不可
        return not PayrollSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
