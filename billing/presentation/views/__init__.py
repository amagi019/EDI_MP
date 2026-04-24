"""
billing プレゼンテーション層 - ビュー定義

モジュール分割: dashboard_views, invoice_views, received_order_views
urls.py からは `from . import views` → `views.XxxView` で参照可能。
"""
# Dashboard / Customer / Product
from .dashboard_views import (  # noqa: F401
    DashboardView,
    CustomerListView, CustomerCreateView, CustomerUpdateView, CustomerDeleteView,
    ProductListView, ProductCreateView, ProductUpdateView, ProductDeleteView,
    ProductAPIView,
)

# Invoice (CRUD / PDF / Drive / Mail)
from .invoice_views import (  # noqa: F401
    InvoiceListView, InvoiceCreateView, InvoiceUpdateView,
    InvoiceDetailView, InvoiceDeleteView,
    InvoicePDFView, InvoicePDFDownloadView,
    InvoiceDriveUploadView, InvoiceMailView,
)

# ReceivedOrder / Timesheet / API
from .received_order_views import (  # noqa: F401
    ReceivedOrderListView, ReceivedOrderMonthlyListView,
    ReceivedOrderDetailView, ReceivedOrderCreateView, ReceivedOrderEditView,
    GenerateInvoiceFromOrderView,
    RollforwardOrderView, RollforwardAllView,
    TimesheetListView, TimesheetCreateView,
    TimesheetApproveView, TimesheetSendView,
    TimesheetExcelUploadView, TimesheetExcelConfirmView,
    TimesheetAPIView, EmployeeSyncView,
)
