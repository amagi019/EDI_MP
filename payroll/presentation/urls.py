"""
payroll URLルーティング
"""
from django.urls import path
from payroll.presentation import views
from payroll.presentation import api_views

app_name = 'payroll'

urlpatterns = [
    # 給与一覧（管理者用）
    path('', views.PayrollListView.as_view(), name='payroll_list'),
    # 一括計算
    path('calculate/', views.PayrollCalculateView.as_view(),
         name='payroll_calculate'),
    # 確認・承認
    path('confirm/<int:year>/<int:month>/',
         views.PayrollConfirmView.as_view(), name='payroll_confirm'),
    # 給与明細PDF
    path('payslip/<int:pk>/pdf/',
         views.PayslipPDFView.as_view(), name='payslip_pdf'),
    # マイ給与明細（社員用）
    path('my-payslips/',
         views.MyPayslipListView.as_view(), name='my_payslip_list'),
    # 社員管理
    path('employees/', views.EmployeeListView.as_view(),
         name='employee_list'),
    path('employees/new/', views.EmployeeCreateView.as_view(),
         name='employee_create'),
    path('employees/<int:pk>/edit/',
         views.EmployeeUpdateView.as_view(), name='employee_update'),
    # 保険料率
    path('insurance-rates/', views.InsuranceRateListView.as_view(),
         name='insurance_rate_list'),
    # 権限管理
    path('permissions/', views.PermissionListView.as_view(),
         name='permission_list'),
    path('permissions/<int:pk>/edit/',
         views.PermissionEditView.as_view(), name='permission_edit'),
    # 給与設定
    path('settings/', views.PayrollSettingsView.as_view(),
         name='payroll_settings'),
    # === API（外部システム連携）===
    path('api/employees/',
         api_views.EmployeeListAPIView.as_view(), name='api_employees'),
]
