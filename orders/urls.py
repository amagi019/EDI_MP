from django.urls import path
from . import views, webhooks

app_name = 'orders'

urlpatterns = [
    path('admin/pdf/<str:order_id>/', views.AdminOrderPDFView.as_view(), name='admin_order_pdf'),
    path('admin/acceptance/pdf/<str:order_id>/', views.AdminAcceptancePDFView.as_view(), name='admin_acceptance_pdf'),
    path('my/pdf/<str:order_id>/', views.CustomerOrderPDFView.as_view(), name='customer_order_pdf'),
    path('my/acceptance/pdf/<str:order_id>/', views.CustomerAcceptancePDFView.as_view(), name='customer_acceptance_pdf'),
    path('my/orders/', views.OrderListView.as_view(), name='order_list'),
    path('my/orders/<str:order_id>/', views.OrderDetailView.as_view(), name='order_detail'),
    path('my/orders/<str:order_id>/approve/', views.OrderApproveView.as_view(), name='order_approve'),
    path('admin/publish/<str:order_id>/', views.OrderPublishView.as_view(), name='order_publish'),
    path('webhook/signature/', webhooks.signature_webhook, name='signature_webhook'),
]
