"""
billing プレゼンテーション層 - URLルーティング
"""
from django.urls import path
from . import views

app_name = 'billing'

urlpatterns = [
    # ダッシュボード
    path('', views.DashboardView.as_view(), name='dashboard'),

    # 請求先
    path('customers/', views.CustomerListView.as_view(), name='customer_list'),
    path('customers/new/', views.CustomerCreateView.as_view(), name='customer_create'),
    path('customers/<int:pk>/edit/', views.CustomerUpdateView.as_view(), name='customer_update'),
    path('customers/<int:pk>/delete/', views.CustomerDeleteView.as_view(), name='customer_delete'),

    # 商品
    path('products/', views.ProductListView.as_view(), name='product_list'),
    path('products/new/', views.ProductCreateView.as_view(), name='product_create'),
    path('products/<int:pk>/edit/', views.ProductUpdateView.as_view(), name='product_update'),
    path('products/<int:pk>/delete/', views.ProductDeleteView.as_view(), name='product_delete'),

    # 商品API（JSON）
    path('api/products/<int:pk>/', views.ProductAPIView.as_view(), name='product_api'),

    # 請求書
    path('invoices/', views.InvoiceListView.as_view(), name='invoice_list'),
    path('invoices/new/', views.InvoiceCreateView.as_view(), name='invoice_create'),
    path('invoices/<uuid:pk>/', views.InvoiceDetailView.as_view(), name='invoice_detail'),
    path('invoices/<uuid:pk>/edit/', views.InvoiceUpdateView.as_view(), name='invoice_update'),
    path('invoices/<uuid:pk>/delete/', views.InvoiceDeleteView.as_view(), name='invoice_delete'),

    # PDF
    path('invoices/<uuid:pk>/pdf/', views.InvoicePDFView.as_view(), name='invoice_pdf'),
    path('invoices/<uuid:pk>/pdf/download/', views.InvoicePDFDownloadView.as_view(), name='invoice_pdf_download'),

    # Googleドライブ
    path('invoices/<uuid:pk>/drive/', views.InvoiceDriveUploadView.as_view(), name='invoice_drive_upload'),

    # メール
    path('invoices/<uuid:pk>/mail/', views.InvoiceMailView.as_view(), name='invoice_mail'),

    # 受注管理
    path('received-orders/', views.ReceivedOrderListView.as_view(), name='received_order_list'),
    path('received-orders/monthly/', views.ReceivedOrderMonthlyListView.as_view(), name='received_order_monthly_list'),
    path('received-orders/new/', views.ReceivedOrderCreateView.as_view(), name='received_order_create'),
    path('received-orders/<int:pk>/', views.ReceivedOrderDetailView.as_view(), name='received_order_detail'),
    path('received-orders/<int:pk>/edit/', views.ReceivedOrderEditView.as_view(), name='received_order_edit'),
    path('received-orders/<int:pk>/generate-invoice/', views.GenerateInvoiceFromOrderView.as_view(), name='generate_invoice_from_order'),
    path('received-orders/<int:pk>/rollforward/', views.RollforwardOrderView.as_view(), name='rollforward_order'),
    path('received-orders/rollforward-all/', views.RollforwardAllView.as_view(), name='rollforward_all'),

    # 勤怠報告
    path('timesheets/', views.TimesheetListView.as_view(), name='timesheet_list'),
    path('timesheets/new/', views.TimesheetCreateView.as_view(), name='timesheet_create'),
    path('timesheets/excel-upload/', views.TimesheetExcelUploadView.as_view(), name='timesheet_excel_upload'),
    path('timesheets/excel-confirm/', views.TimesheetExcelConfirmView.as_view(), name='timesheet_excel_confirm'),
    path('timesheets/<int:pk>/action/', views.TimesheetApproveView.as_view(), name='timesheet_approve'),
    path('timesheets/<int:pk>/send/', views.TimesheetSendView.as_view(), name='timesheet_send'),
    # === API（PayrollSystem連携）===
    path('api/timesheets/', views.TimesheetAPIView.as_view(), name='api_timesheets'),
    path('api/sync-employees/', views.EmployeeSyncView.as_view(), name='api_sync_employees'),
]
