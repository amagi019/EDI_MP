"""
payroll ビュー

権限制御付き。社員は自分の給与のみ、社長は全社員を閲覧可能。
"""
import datetime
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.utils.translation import gettext_lazy as _
from django.urls import reverse_lazy

from payroll.domain.models import Employee, InsuranceRate, Payroll
from payroll.domain.permissions import PayrollPermission
from payroll.services.payroll_calculator import calculate_all_payrolls
from payroll.services.permission_service import (
    can_view_all_payrolls, can_calculate_payroll,
    can_approve_payroll, get_viewable_employees,
    get_payroll_permission,
)


class StaffRequiredMixin(LoginRequiredMixin):
    login_url = '/login/'


class PayrollListView(StaffRequiredMixin, ListView):
    """給与一覧（月別）- 権限に基づくフィルタリング"""
    model = Payroll
    template_name = 'payroll/payroll_list.html'
    context_object_name = 'payrolls'

    def get_queryset(self):
        qs = Payroll.objects.select_related('employee')

        # 権限フィルタ
        if not can_view_all_payrolls(self.request.user):
            viewable = get_viewable_employees(self.request.user)
            qs = qs.filter(employee__in=viewable)

        year = self.request.GET.get('year')
        month = self.request.GET.get('month')
        if year and month:
            try:
                target = datetime.date(int(year), int(month), 1)
                qs = qs.filter(year_month=target)
            except (ValueError, TypeError):
                pass
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        months = (Payroll.objects
                  .values_list('year_month', flat=True)
                  .distinct()
                  .order_by('-year_month'))
        ctx['available_months'] = months
        ctx['selected_year'] = self.request.GET.get('year', '')
        ctx['selected_month'] = self.request.GET.get('month', '')

        payrolls = ctx['payrolls']
        ctx['total_gross'] = sum(p.gross_pay for p in payrolls)
        ctx['total_deductions'] = sum(p.deduction_total for p in payrolls)
        ctx['total_net'] = sum(p.net_pay for p in payrolls)

        # 権限フラグ
        ctx['can_calculate'] = can_calculate_payroll(self.request.user)
        ctx['can_view_all'] = can_view_all_payrolls(self.request.user)
        return ctx


class PayrollCalculateView(StaffRequiredMixin, View):
    """給与一括計算 - 計算権限が必要"""

    def get(self, request):
        if not can_calculate_payroll(request.user):
            raise PermissionDenied("給与計算の権限がありません")

        today = datetime.date.today()
        if today.month == 1:
            default_year, default_month = today.year - 1, 12
        else:
            default_year, default_month = today.year, today.month - 1

        employees = Employee.objects.filter(is_active=True)
        return render(request, 'payroll/payroll_calculate.html', {
            'employees': employees,
            'default_year': default_year,
            'default_month': default_month,
        })

    def post(self, request):
        if not can_calculate_payroll(request.user):
            raise PermissionDenied("給与計算の権限がありません")

        year = int(request.POST.get('year', datetime.date.today().year))
        month = int(request.POST.get('month', datetime.date.today().month))
        year_month = datetime.date(year, month, 1)

        try:
            results = calculate_all_payrolls(year_month)
            success_count = 0
            for payroll, warnings in results:
                for w in warnings:
                    messages.warning(request, w)
                if payroll.status == 'DRAFT':
                    success_count += 1

            messages.success(
                request,
                f'{year}年{month}月の給与を{success_count}名分計算しました'
            )
            return redirect(reverse_lazy(
                'payroll:payroll_confirm',
                kwargs={'year': year, 'month': month}))
        except Exception as e:
            messages.error(request, f'計算エラー: {e}')
            return redirect('payroll:payroll_calculate')


class PayrollConfirmView(StaffRequiredMixin, View):
    """給与確認・承認 - 承認権限が必要"""

    def get(self, request, year, month):
        if not can_view_all_payrolls(request.user):
            raise PermissionDenied("閲覧権限がありません")

        year_month = datetime.date(year, month, 1)
        payrolls = Payroll.objects.filter(
            year_month=year_month
        ).select_related('employee').order_by('employee__employee_id')

        total_gross = sum(p.gross_pay for p in payrolls)
        total_deductions = sum(p.deduction_total for p in payrolls)
        total_net = sum(p.net_pay for p in payrolls)

        return render(request, 'payroll/payroll_confirm.html', {
            'payrolls': payrolls,
            'year': year,
            'month': month,
            'total_gross': total_gross,
            'total_deductions': total_deductions,
            'total_net': total_net,
            'can_approve': can_approve_payroll(request.user),
        })

    def post(self, request, year, month):
        if not can_approve_payroll(request.user):
            raise PermissionDenied("承認権限がありません")

        action = request.POST.get('action')
        year_month = datetime.date(year, month, 1)

        if action == 'confirm':
            count = Payroll.objects.filter(
                year_month=year_month, status='DRAFT'
            ).update(status='CONFIRMED')
            messages.success(
                request, f'{count}名分の給与を確認済みにしました')
        elif action == 'recalculate':
            Payroll.objects.filter(
                year_month=year_month, status='DRAFT').delete()
            results = calculate_all_payrolls(year_month)
            messages.success(
                request, f'{len(results)}名分を再計算しました')

        return redirect(
            'payroll:payroll_confirm', year=year, month=month)


class EmployeeListView(StaffRequiredMixin, ListView):
    """社員一覧 - 全社員閲覧権限が必要"""
    model = Employee
    template_name = 'payroll/employee_list.html'
    context_object_name = 'employees'

    def get_queryset(self):
        if can_view_all_payrolls(self.request.user):
            return Employee.objects.all()
        # 自分だけ
        return get_viewable_employees(self.request.user)


class EmployeeCreateView(StaffRequiredMixin, CreateView):
    """社員登録 - 全社員閲覧権限が必要"""
    model = Employee
    template_name = 'payroll/employee_form.html'
    fields = [
        'employee_id', 'name', 'name_kana', 'birth_date',
        'hire_date', 'insurance_start_date',
        'email', 'phone',
        'postal_code', 'address_1', 'address_2',
        'base_salary', 'position_allowance', 'housing_allowance',
        'commuting_allowance', 'standard_monthly_hours',
        'dependents_count', 'is_tax_exempt',
        'pension_enrolled', 'health_enrolled',
        'nursing_enrolled', 'employment_enrolled',
        'standard_remuneration',
    ]
    success_url = reverse_lazy('payroll:employee_list')

    def dispatch(self, request, *args, **kwargs):
        if not can_view_all_payrolls(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(
            self.request, f'{form.instance.name}を登録しました')
        return super().form_valid(form)


class EmployeeUpdateView(StaffRequiredMixin, UpdateView):
    """社員編集"""
    model = Employee
    template_name = 'payroll/employee_form.html'
    fields = EmployeeCreateView.fields
    success_url = reverse_lazy('payroll:employee_list')

    def dispatch(self, request, *args, **kwargs):
        if not can_view_all_payrolls(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(
            self.request, f'{form.instance.name}を更新しました')
        return super().form_valid(form)


class InsuranceRateListView(StaffRequiredMixin, ListView):
    """保険料率一覧"""
    model = InsuranceRate
    template_name = 'payroll/insurance_rate_list.html'
    context_object_name = 'rates'


class PermissionListView(StaffRequiredMixin, ListView):
    """権限管理一覧 - superuserのみ"""
    model = PayrollPermission
    template_name = 'payroll/permission_list.html'
    context_object_name = 'permissions'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return PayrollPermission.objects.select_related(
            'user', 'employee').all()


class PermissionEditView(StaffRequiredMixin, View):
    """権限編集 - superuserのみ"""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, pk):
        perm = get_object_or_404(PayrollPermission, pk=pk)
        employees = Employee.objects.filter(is_active=True)
        return render(request, 'payroll/permission_edit.html', {
            'perm': perm,
            'employees': employees,
            'permission_choices': PayrollPermission.PERMISSION_CHOICES,
        })

    def post(self, request, pk):
        perm = get_object_or_404(PayrollPermission, pk=pk)
        perm.permission_level = request.POST.get(
            'permission_level', 'SELF_ONLY')
        emp_id = request.POST.get('employee')
        if emp_id:
            perm.employee_id = int(emp_id)
        else:
            perm.employee = None
        perm.can_calculate = 'can_calculate' in request.POST
        perm.can_approve = 'can_approve' in request.POST
        perm.can_transfer = 'can_transfer' in request.POST
        perm.save()
        messages.success(
            request,
            f'{perm.user.username}の権限を更新しました')
        return redirect('payroll:permission_list')


class PayrollSettingsView(StaffRequiredMixin, View):
    """給与設定 - superuserのみ"""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        from payroll.domain.settings import PayrollSettings
        settings = PayrollSettings.load()
        return render(request, 'payroll/payroll_settings.html', {
            'settings': settings,
            'payment_day_choices': PayrollSettings.PAYMENT_DAY_CHOICES,
            'closing_day_choices': PayrollSettings.CLOSING_DAY_CHOICES,
        })

    def post(self, request):
        from payroll.domain.settings import PayrollSettings
        settings = PayrollSettings.load()
        settings.payment_day = int(request.POST.get('payment_day', 0))
        settings.closing_day = int(request.POST.get('closing_day', 0))
        settings.overtime_rate_multiplier = request.POST.get(
            'overtime_rate_multiplier', '1.25')
        settings.overtime_60_rate_multiplier = request.POST.get(
            'overtime_60_rate_multiplier', '1.50')
        settings.night_rate_multiplier = request.POST.get(
            'night_rate_multiplier', '0.25')
        settings.holiday_rate_multiplier = request.POST.get(
            'holiday_rate_multiplier', '1.35')
        settings.default_work_days = int(request.POST.get(
            'default_work_days', 20))
        settings.default_monthly_hours = request.POST.get(
            'default_monthly_hours', '160.0')
        settings.save()
        messages.success(request, '給与設定を更新しました')
        return redirect('payroll:payroll_settings')


class PayslipPDFView(StaffRequiredMixin, View):
    """給与明細PDFダウンロード - 権限チェック付き"""

    def get(self, request, pk):
        payroll = get_object_or_404(
            Payroll.objects.select_related('employee'), pk=pk)

        # 自分の給与 or 全社員閲覧権限
        perm = get_payroll_permission(request.user)
        if not can_view_all_payrolls(request.user):
            if not perm.employee or perm.employee != payroll.employee:
                raise PermissionDenied

        from payroll.services.pdf_generator import generate_payslip_pdf
        pdf_buffer = generate_payslip_pdf(payroll)

        ym = payroll.year_month.strftime('%Y%m')
        filename = f"payslip_{payroll.employee.employee_id}_{ym}.pdf"

        response = HttpResponse(
            pdf_buffer.getvalue(),
            content_type='application/pdf')
        response['Content-Disposition'] = (
            f'inline; filename="{filename}"')
        return response


class MyPayslipListView(StaffRequiredMixin, ListView):
    """マイ給与明細 - 社員が自分の給与を閲覧"""
    model = Payroll
    template_name = 'payroll/my_payslip_list.html'
    context_object_name = 'payrolls'

    def get_queryset(self):
        perm = get_payroll_permission(self.request.user)
        if perm.employee:
            return Payroll.objects.filter(
                employee=perm.employee
            ).select_related('employee').order_by('-year_month')
        return Payroll.objects.none()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        perm = get_payroll_permission(self.request.user)
        ctx['employee'] = perm.employee
        return ctx

