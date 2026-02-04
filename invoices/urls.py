from django.urls import path
from . import views

app_name = 'invoices'

urlpatterns = [
    path('admin/pdf/<int:invoice_id>/', views.AdminInvoicePDFView.as_view(), name='admin_invoice_pdf'),
    path('my/pdf/<int:invoice_id>/', views.PartnerInvoicePDFView.as_view(), name='partner_invoice_pdf'),
    path('my/list/', views.PartnerInvoiceListView.as_view(), name='partner_invoice_list'),
]
