from django.urls import path
from . import views, webhooks, basic_info_views

app_name = 'orders'

urlpatterns = [
    path('staff/create/', views.OrderCreateView.as_view(), name='order_create'),
    path('admin/pdf/<str:order_id>/', views.AdminOrderPDFView.as_view(), name='admin_order_pdf'),
    path('admin/acceptance/pdf/<str:order_id>/', views.AdminAcceptancePDFView.as_view(), name='admin_acceptance_pdf'),
    path('my/pdf/<str:order_id>/', views.CustomerOrderPDFView.as_view(), name='customer_order_pdf'),
    path('my/acceptance/pdf/<str:order_id>/', views.CustomerAcceptancePDFView.as_view(), name='customer_acceptance_pdf'),
    path('my/orders/', views.OrderListView.as_view(), name='order_list'),
    path('my/orders/<str:order_id>/', views.OrderDetailView.as_view(), name='order_detail'),
    path('my/orders/<str:order_id>/approve/', views.OrderApproveView.as_view(), name='order_approve'),
    path('admin/publish/<str:order_id>/', views.OrderPublishView.as_view(), name='order_publish'),
    path('admin/republish/<str:order_id>/', views.OrderRepublishView.as_view(), name='order_republish'),
    path('admin/edit/<str:order_id>/', views.OrderEditView.as_view(), name='order_edit'),
    path('admin/delete/<str:order_id>/', views.OrderDeleteView.as_view(), name='order_delete'),
    path('webhook/signature/', webhooks.signature_webhook, name='signature_webhook'),
    # 発注基本情報
    path('basic-info/', basic_info_views.BasicInfoListView.as_view(), name='basic_info_list'),
    path('basic-info/create/', basic_info_views.BasicInfoCreateView.as_view(), name='basic_info_create'),
    path('basic-info/<int:pk>/edit/', basic_info_views.BasicInfoUpdateView.as_view(), name='basic_info_edit'),
    path('basic-info/<int:pk>/create-order/', basic_info_views.CreateOrderFromBasicInfoView.as_view(), name='create_order_from_basic_info'),
    # データ連携（XML / JSON）
    path('xml/<str:order_id>/', views.OrderXMLDownloadView.as_view(), name='order_xml'),
    path('json/<str:order_id>/', views.OrderJSONDownloadView.as_view(), name='order_json'),
    # ダッシュボード
    path('staff/dashboard/monthly-progress/', views.PartnerMonthlyProgressView.as_view(), name='partner_monthly_progress'),
]

