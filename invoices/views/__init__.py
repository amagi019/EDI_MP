"""
invoices - ビュー定義

モジュール分割: invoice_views, work_report_views
urls.py からは `from . import views` → `views.XxxView` で参照可能。
"""
# 請求書関連
from .invoice_views import (  # noqa: F401
    AdminInvoicePDFView, AdminPaymentNoticePDFView,
    PartnerInvoicePDFView, PartnerPaymentNoticePDFView,
    PartnerInvoiceListView, PartnerInvoiceDetailView,
    PartnerInvoiceConfirmView,
    InvoiceCreateFromBasicInfoView, InvoiceCreateFromOrderView,
    InvoiceDeleteView, InvoiceEditView,
    StaffInvoiceReviewView, InvoiceSendPreviewView,
    InvoiceXMLDownloadView, InvoiceJSONDownloadView,
    ReceivedEmailListView, ReceivedEmailActionView,
)

# 稼働報告書関連
from .work_report_views import (  # noqa: F401
    WorkReportUploadView, WorkReportResultView,
    WorkReportApproveView, WorkReportSendToClientView,
)
