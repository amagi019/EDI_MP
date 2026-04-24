from django.urls import path
from . import views

app_name = 'invoices'

urlpatterns = [
    path('admin/pdf/invoice/<int:invoice_id>/', views.AdminInvoicePDFView.as_view(), name='admin_invoice_pdf'),
    path('admin/pdf/payment-notice/<int:invoice_id>/', views.AdminPaymentNoticePDFView.as_view(), name='admin_payment_notice_pdf'),
    path('staff/review/<int:invoice_id>/', views.StaffInvoiceReviewView.as_view(), name='staff_invoice_review'),
    path('my/pdf/<int:invoice_id>/', views.PartnerInvoicePDFView.as_view(), name='partner_invoice_pdf'),
    path('my/pdf/payment-notice/<int:invoice_id>/', views.PartnerPaymentNoticePDFView.as_view(), name='partner_payment_notice_pdf'),
    path('my/list/', views.PartnerInvoiceListView.as_view(), name='invoice_list'),
    path('my/<int:invoice_id>/', views.PartnerInvoiceDetailView.as_view(), name='invoice_detail'),
    path('my/<int:invoice_id>/confirm/', views.PartnerInvoiceConfirmView.as_view(), name='invoice_confirm'),
    # 稼働報告書
    path('my/work-report/', views.WorkReportUploadView.as_view(), name='work_report_upload'),
    path('my/work-report/results/', views.WorkReportResultView.as_view(), name='work_report_results'),
    path('my/work-report/<int:pk>/', views.WorkReportResultView.as_view(), name='work_report_result'),
    path('my/work-report/approve/', views.WorkReportApproveView.as_view(), name='work_report_approve'),
    path('staff/work-report/<int:pk>/send-to-client/', views.WorkReportSendToClientView.as_view(), name='work_report_send_to_client'),
    # 請求書作成・編集
    path('staff/create-from-order/<str:order_id>/', views.InvoiceCreateFromOrderView.as_view(), name='invoice_create_from_order'),
    path('staff/create-from-basic-info/<int:pk>/', views.InvoiceCreateFromBasicInfoView.as_view(), name='invoice_create_from_basic_info'),
    path('staff/edit/<int:invoice_id>/', views.InvoiceEditView.as_view(), name='invoice_edit'),
    path('staff/delete/<int:invoice_id>/', views.InvoiceDeleteView.as_view(), name='invoice_delete'),
    path('staff/send-preview/<int:invoice_id>/', views.InvoiceSendPreviewView.as_view(), name='invoice_send_preview'),
    # データ連携（XML / JSON）
    path('xml/<int:invoice_id>/', views.InvoiceXMLDownloadView.as_view(), name='invoice_xml'),
    path('json/<int:invoice_id>/', views.InvoiceJSONDownloadView.as_view(), name='invoice_json'),
    # 受信メール管理
    path('staff/received-emails/', views.ReceivedEmailListView.as_view(), name='received_email_list'),
    path('staff/received-emails/<int:pk>/action/', views.ReceivedEmailActionView.as_view(), name='received_email_action'),
]
