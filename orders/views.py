import hashlib
from django.shortcuts import render, get_object_or_404, redirect
from django.core.files.base import ContentFile
from django.http import HttpResponse,  HttpResponseForbidden
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import ListView, DetailView
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from .models import Order
from .services.pdf_generator import generate_order_pdf, generate_acceptance_pdf
from .services.signature_service import SignatureService

class AdminOrderPDFView(View):
    """管理者用PDFプレビュー・ダウンロード"""
    
    @method_decorator(user_passes_test(lambda u: u.is_staff))
    def get(self, request, order_id):
        order = get_object_or_404(Order, order_id=order_id)
        
        # 下書きの場合は透かし入りでプレビュー表示
        if order.status == 'DRAFT':
            buffer = generate_order_pdf(order, watermark="下書き")
            response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
            response['Content-Disposition'] = f'inline; filename="order_{order_id}_draft.pdf"'
            return response

        # 正式発行済みの原本があればそれを返す
        if order.order_pdf:
            response = HttpResponse(order.order_pdf.read(), content_type='application/pdf')
            response['Content-Disposition'] = f'inline; filename="order_{order_id}.pdf"'
            return response

        buffer = generate_order_pdf(order)
        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="order_{order_id}.pdf"'
        return response

class CustomerOrderPDFView(View):
    """取引先用PDFダウンロード"""

    @method_decorator(login_required)
    def get(self, request, order_id):
        order = get_object_or_404(Order, order_id=order_id)
        
        # 権限チェック：自分の会社の注文書のみ閲覧可能
        # Profile -> Customer の紐付けを確認
        if not hasattr(request.user, 'profile') or not request.user.profile.customer:
            return HttpResponseForbidden("取引先情報が紐付いていません。")
            
        if order.customer != request.user.profile.customer:
             return HttpResponseForbidden("この注文書を閲覧する権限がありません。")

        # 既に保存されたPDFがあればそれを返す（電帳法対応：原本の保持）
        if order.order_pdf:
            # 閲覧＝承認とする（ユーザー要望）
            if order.status in ['UNCONFIRMED', 'CONFIRMING']:
                order.status = 'APPROVED'
                order.finalized_at = timezone.now()
                # 承認時に請書も生成・保存するロジック（後述のApproveViewと同様）をここでも実行するか検討
                # 一旦ステータス更新のみ。請書生成はApproveViewまたは別途
                order.save()
            
            response = HttpResponse(order.order_pdf.read(), content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="order_{order_id}.pdf"'
            return response

        buffer = generate_order_pdf(order)

        # 閲覧＝承認とする（ユーザー要望）
        if order.status in ['UNCONFIRMED', 'CONFIRMING']:
            order.status = 'APPROVED'
            order.finalized_at = timezone.now()
            order.save()

        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="order_{order_id}.pdf"'
        return response

class AdminAcceptancePDFView(View):
    """管理者用注文請書PDFプレビュー"""
    
    @method_decorator(user_passes_test(lambda u: u.is_staff))
    def get(self, request, order_id):
        order = get_object_or_404(Order, order_id=order_id)
        buffer = generate_acceptance_pdf(order)
        
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="acceptance_{order_id}.pdf"'
        return response

class CustomerAcceptancePDFView(View):
    """取引先用注文請書PDFダウンロード"""

    @method_decorator(login_required)
    def get(self, request, order_id):
        order = get_object_or_404(Order, order_id=order_id)
        
        if not hasattr(request.user, 'profile') or not request.user.profile.customer:
            return HttpResponseForbidden("取引先情報が紐付いていません。")
            
        if order.customer != request.user.profile.customer:
             return HttpResponseForbidden("権限がありません。")

        if order.acceptance_pdf:
            response = HttpResponse(order.acceptance_pdf.read(), content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="acceptance_{order_id}.pdf"'
            return response

        buffer = generate_acceptance_pdf(order)

        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="acceptance_{order_id}.pdf"'
        return response

class OrderListView(ListView):
    """取引先用：自分宛ての注文書一覧"""
    model = Order
    template_name = 'orders/order_list.html'
    context_object_name = 'orders'
    ordering = ['-order_date']

    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Order.objects.all().order_by('-order_date')

        if not hasattr(user, 'profile') or not user.profile.customer:
             # 取引先が紐付いていない場合は空リスト
             return Order.objects.none()
        
        # 自分のCustomerの注文のみ ＆ 下書き（DRAFT）は非表示
        return Order.objects.filter(customer=user.profile.customer).exclude(status='DRAFT').order_by('-order_date')

class OrderDetailView(DetailView):
    """取引先用：注文書詳細"""
    model = Order
    template_name = 'orders/order_detail.html'
    context_object_name = 'order'
    pk_url_kwarg = 'order_id'

    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Order.objects.all()
            
        if not hasattr(user, 'profile') or not user.profile.customer:
            return Order.objects.none()
        # 取引先用にはDRAFTを非表示に
        return Order.objects.filter(customer=user.profile.customer).exclude(status='DRAFT')

class OrderApproveView(View):
    """取引先用：注文承認処理"""
    
    @method_decorator(login_required)
    def post(self, request, order_id):
        order = get_object_or_404(Order, order_id=order_id)
        
        # 権限チェック
        if not hasattr(request.user, 'profile') or order.customer != request.user.profile.customer:
             return HttpResponseForbidden("権限がありません。")
        
        if order.status == 'APPROVED':
             messages.info(request, "この注文書は既に承認されています。")
             return redirect('orders:order_detail', order_id=order_id)

        # ステータス更新
        order.status = 'APPROVED'
        order.finalized_at = timezone.now()
        
        # 注文請書を生成して保存（永続化・改ざん防止）
        buffer = generate_acceptance_pdf(order)
        content = buffer.getvalue()
        order.document_hash = hashlib.sha256(content).hexdigest()
        order.acceptance_pdf.save(f"acceptance_{order.order_id}.pdf", ContentFile(content), save=False)
        
        # 電子署名依頼（フェーズ4: 外部連携）
        try:
            sig_service = SignatureService()
            sig_result = sig_service.request_signature(order)
            order.external_signature_id = sig_result['signature_id']
        except Exception as e:
            # 署名依頼の失敗はログに留め、本体の承認処理は継続（運用の柔軟性のため）
            import logging
            logging.getLogger(__name__).warning(f"Signature request failed for {order.order_id}: {e}")
            
        order.save()

        # 管理者へメール送信
        subject = f"【承認通知】注文番号：{order.order_id}"
        message = f"""{order.customer.name} 様より、以下の注文書が承認されました。

■注文番号：{order.order_id}
■プロジェクト：{order.project.name}
■注文日：{order.order_date}

システムにログインして詳細を確認してください。
"""
        try:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                ['y.yoshikawa@macplanning.com'],
                fail_silently=False,
            )
            messages.success(request, "注文書を承認しました。管理者へ通知されました。")
        except Exception as e:
            messages.warning(request, "承認ステータスを更新しましたが、メール通知に失敗しました。")

        return redirect('orders:order_detail', order_id=order_id)


class OrderPublishView(View):
    """管理者用：注文書の正式発行（DRAFT -> UNCONFIRMED）"""
    
    @method_decorator(user_passes_test(lambda u: u.is_staff))
    def post(self, request, order_id):
        order = get_object_or_404(Order, order_id=order_id)
        if order.status != 'DRAFT':
            messages.warning(request, "下書き状態の注文書のみ発行可能です。")
            return redirect('orders:order_detail', order_id=order_id)
        
        order.status = 'UNCONFIRMED'
        # 正式発行時に注文書を永続保存
        buffer = generate_order_pdf(order)
        content = buffer.getvalue()
        order.order_pdf.save(f"order_{order.order_id}.pdf", ContentFile(content), save=False)
        order.save()
        
        messages.success(request, f"注文書 {order.order_id} を正式に発行しました。")
        return redirect('orders:order_detail', order_id=order_id)
