import hashlib
from django.shortcuts import render, get_object_or_404, redirect
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import ListView, DetailView, CreateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from core.utils import compose_order_publish_email, compose_order_approve_email
from django.utils import timezone
from django.urls import reverse
from core.permissions import (
    Role, get_user_role, get_user_partner, is_owner_of_partner,
    StaffRequiredMixin,
)
from .models import Order
from .forms import OrderCreateForm, OrderItemFormSet
from .services.pdf_generator import generate_order_pdf, generate_acceptance_pdf
from .services.signature_service import SignatureService

class AdminOrderPDFView(StaffRequiredMixin, View):
    """管理者用PDFプレビュー・ダウンロード"""

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

class CustomerOrderPDFView(LoginRequiredMixin, View):
    """パートナー用PDFダウンロード"""

    def get(self, request, order_id):
        order = get_object_or_404(Order, order_id=order_id)

        # 権限チェック：スタッフは全閲覧可、パートナーは自分のリソースのみ
        role = get_user_role(request.user)
        if role != Role.STAFF:
            if not is_owner_of_partner(request.user, order.partner):
                raise PermissionDenied("この注文書を閲覧する権限がありません。")

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

class AdminAcceptancePDFView(StaffRequiredMixin, View):
    """管理者用注文請書PDFプレビュー"""

    def get(self, request, order_id):
        order = get_object_or_404(Order, order_id=order_id)
        buffer = generate_acceptance_pdf(order)
        
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="acceptance_{order_id}.pdf"'
        return response

class CustomerAcceptancePDFView(LoginRequiredMixin, View):
    """パートナー用注文請書PDFダウンロード"""

    def get(self, request, order_id):
        order = get_object_or_404(Order, order_id=order_id)

        role = get_user_role(request.user)
        if role != Role.STAFF:
            if not is_owner_of_partner(request.user, order.partner):
                raise PermissionDenied("権限がありません。")

        if order.acceptance_pdf:
            response = HttpResponse(order.acceptance_pdf.read(), content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="acceptance_{order_id}.pdf"'
            return response

        buffer = generate_acceptance_pdf(order)

        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="acceptance_{order_id}.pdf"'
        return response

class OrderListView(LoginRequiredMixin, ListView):
    """パートナー用：自分宛ての注文書一覧"""
    model = Order
    template_name = 'orders/order_list.html'
    context_object_name = 'orders'
    ordering = ['-order_date']

    def get_queryset(self):
        user = self.request.user
        role = get_user_role(user)
        if role == Role.STAFF:
            return Order.objects.all().order_by('-order_date')

        partner = get_user_partner(user)
        if not partner:
            return Order.objects.none()

        return Order.objects.filter(partner=partner).exclude(status='DRAFT').order_by('-order_date')

class OrderDetailView(LoginRequiredMixin, DetailView):
    """パートナー用：注文書詳細"""
    model = Order
    template_name = 'orders/order_detail.html'
    context_object_name = 'order'
    pk_url_kwarg = 'order_id'

    def get_queryset(self):
        user = self.request.user
        role = get_user_role(user)
        if role == Role.STAFF:
            return Order.objects.all()

        partner = get_user_partner(user)
        if not partner:
            return Order.objects.none()
        return Order.objects.filter(partner=partner).exclude(status='DRAFT')

class OrderApproveView(LoginRequiredMixin, View):
    """パートナー用：注文承認処理"""

    def post(self, request, order_id):
        order = get_object_or_404(Order, order_id=order_id)

        # パートナー本人のみ承認可能
        if not is_owner_of_partner(request.user, order.partner):
            raise PermissionDenied("権限がありません。")
        
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

        # 自社担当者へメール送信
        order_url = request.build_absolute_uri(
            reverse('orders:order_detail', kwargs={'order_id': order.order_id})
        )
        subject, message = compose_order_approve_email(order, order_url)
        # 自社担当者のメールアドレス（未設定の場合はDEFAULT_FROM_EMAIL）
        if order.partner.staff_contact and order.partner.staff_contact.email:
            notify_email = order.partner.staff_contact.email
        else:
            notify_email = settings.DEFAULT_FROM_EMAIL
        try:
            print(f"[注文承認通知] 宛先: {notify_email}, 件名: {subject}")
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [notify_email],
                fail_silently=False,
            )
            print(f"[注文承認通知] 送信成功")
            messages.success(request, "注文書を承認しました。管理者へ通知されました。")
        except Exception as e:
            print(f"[注文承認通知] 送信エラー: {e}")
            messages.warning(request, "承認ステータスを更新しましたが、メール通知に失敗しました。")

        return redirect('orders:order_detail', order_id=order_id)


class OrderPublishView(StaffRequiredMixin, View):
    """管理者用：注文書の正式発行（DRAFT -> UNCONFIRMED）"""

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

        # Google Driveへ自動アップロード
        try:
            from .services.google_drive_service import upload_order_pdf
            result = upload_order_pdf(order)
            order.drive_file_id = result['file_id']
            order.save(update_fields=['drive_file_id'])
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Drive upload failed for {order.order_id}: {e}")

        # パートナーへ注文書送付メール
        email_sent = False
        if order.partner and order.partner.email:
            login_url = request.build_absolute_uri(reverse('login'))
            order_detail_url = request.build_absolute_uri(
                reverse('orders:order_detail', kwargs={'order_id': order.order_id})
            )
            subject, message = compose_order_publish_email(order, order_detail_url, login_url)
            try:
                send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [order.partner.email], fail_silently=False)
                email_sent = True
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Order notification email failed for {order.order_id}: {e}")

        if email_sent:
            messages.success(request, f"注文書 {order.order_id} を正式に発行し、パートナーへメール通知しました。")
        else:
            messages.success(request, f"注文書 {order.order_id} を正式に発行しました。（メール通知は送信されませんでした）")

        return redirect('orders:order_detail', order_id=order_id)


class OrderCreateView(StaffRequiredMixin, CreateView):
    """スタッフ用：発注書新規作成"""
    model = Order
    form_class = OrderCreateForm
    template_name = 'orders/order_create.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['item_formset'] = OrderItemFormSet(self.request.POST, prefix='items')
        else:
            context['item_formset'] = OrderItemFormSet(prefix='items')
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        item_formset = context['item_formset']

        if item_formset.is_valid():
            self.object = form.save(commit=False)
            self.object.status = 'DRAFT'
            self.object.save()

            item_formset.instance = self.object
            item_formset.save()

            messages.success(self.request, f"発注書 {self.object.order_id} を下書きとして作成しました。")
            return redirect('orders:order_detail', order_id=self.object.order_id)
        else:
            return self.render_to_response(self.get_context_data(form=form))

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))
