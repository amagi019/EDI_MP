import hashlib
import json
from django.shortcuts import render, get_object_or_404, redirect
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import ListView, DetailView, CreateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from core.utils import compose_order_publish_email, compose_order_approve_email, get_notify_email
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
from .services.xml_generator import generate_order_xml
from .services.json_exporter import generate_order_json


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
                order.save()
                # 月次タスク（ORDER_APPROVE）を完了にする
                from tasks.services import complete_order_approve
                complete_order_approve(order)
            
            response = HttpResponse(order.order_pdf.read(), content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="order_{order_id}.pdf"'
            return response

        buffer = generate_order_pdf(order)

        # 閲覧＝承認とする（ユーザー要望）
        if order.status in ['UNCONFIRMED', 'CONFIRMING']:
            order.status = 'APPROVED'
            order.finalized_at = timezone.now()
            order.save()
            # 月次タスク（ORDER_APPROVE）を完了にする
            from tasks.services import complete_order_approve
            complete_order_approve(order)

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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # 関連する請求書があればcontextに渡す
        from invoices.models import Invoice
        context['invoice'] = Invoice.objects.filter(order=self.object).first()
        return context

class OrderApproveView(LoginRequiredMixin, View):
    """パートナー用：注文承諾処理"""

    def post(self, request, order_id):
        from .services.order_service import approve_order

        order = get_object_or_404(Order, order_id=order_id)

        if not is_owner_of_partner(request.user, order.partner):
            raise PermissionDenied("権限がありません。")

        if order.status == 'APPROVED':
            messages.info(request, "この注文書は既に承諾済みです。")
            return redirect('orders:order_detail', order_id=order_id)

        try:
            approve_order(order, request.user, request)
            messages.success(request, "注文書を承諾しました。管理者へ通知されました。")
        except Exception:
            messages.warning(request, "承諾ステータスを更新しましたが、メール通知に失敗しました。")

        return redirect('orders:order_detail', order_id=order.order_id)


class OrderPublishView(StaffRequiredMixin, View):
    """管理者用：注文書の正式発行（DRAFT -> UNCONFIRMED）"""

    def post(self, request, order_id):
        from .services.order_service import publish_order

        order = get_object_or_404(Order, order_id=order_id)
        if order.status != 'DRAFT':
            messages.warning(request, "下書き状態の注文書のみ発行可能です。")
            return redirect('orders:order_detail', order_id=order_id)

        email_sent = publish_order(order, request)

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


class OrderEditView(StaffRequiredMixin, View):
    """スタッフ用：下書き注文書の編集"""

    def get(self, request, order_id):
        order = get_object_or_404(Order, order_id=order_id)
        if order.status != 'DRAFT':
            messages.warning(request, '下書き状態の注文書のみ編集可能です。')
            return redirect('orders:order_detail', order_id=order_id)

        form = OrderCreateForm(instance=order)
        item_formset = OrderItemFormSet(instance=order, prefix='items')
        return render(request, 'orders/order_create.html', {
            'form': form,
            'item_formset': item_formset,
            'is_edit': True,
            'order': order,
        })

    def post(self, request, order_id):
        order = get_object_or_404(Order, order_id=order_id)
        if order.status != 'DRAFT':
            messages.warning(request, '下書き状態の注文書のみ編集可能です。')
            return redirect('orders:order_detail', order_id=order_id)

        form = OrderCreateForm(request.POST, instance=order)
        item_formset = OrderItemFormSet(request.POST, instance=order, prefix='items')

        if form.is_valid() and item_formset.is_valid():
            form.save()
            item_formset.save()
            messages.success(request, f'注文書 {order.order_id} を更新しました。')
            return redirect('orders:order_detail', order_id=order.order_id)
        else:
            return render(request, 'orders/order_create.html', {
                'form': form,
                'item_formset': item_formset,
                'is_edit': True,
                'order': order,
            })


class OrderDeleteView(StaffRequiredMixin, View):
    """下書き注文書の削除"""

    def post(self, request, order_id):
        order = get_object_or_404(Order, order_id=order_id)
        if order.status != 'DRAFT':
            messages.error(request, '下書き以外の注文書は削除できません。')
            return redirect('orders:order_list')
        order_id_str = order.order_id
        order.delete()
        messages.success(request, f'注文書 {order_id_str} を削除しました。')
        return redirect('orders:order_list')


class OrderXMLDownloadView(LoginRequiredMixin, View):
    """注文書XMLダウンロード（中小企業共通EDI準拠）"""

    def get(self, request, order_id):
        order = get_object_or_404(Order, order_id=order_id)
        # 権限チェック
        role = get_user_role(request.user)
        if role != Role.STAFF:
            if not is_owner_of_partner(request.user, order.partner):
                raise PermissionDenied("この注文書を閲覧する権限がありません。")

        xml_bytes = generate_order_xml(order)
        response = HttpResponse(xml_bytes, content_type='application/xml')
        response['Content-Disposition'] = f'attachment; filename="order_{order_id}.xml"'
        return response


class OrderJSONDownloadView(LoginRequiredMixin, View):
    """注文書JSONダウンロード（実務連携用）"""

    def get(self, request, order_id):
        order = get_object_or_404(Order, order_id=order_id)
        # 権限チェック
        role = get_user_role(request.user)
        if role != Role.STAFF:
            if not is_owner_of_partner(request.user, order.partner):
                raise PermissionDenied("この注文書を閲覧する権限がありません。")

        data = generate_order_json(order)
        response = HttpResponse(
            json.dumps(data, ensure_ascii=False, indent=2),
            content_type='application/json'
        )
        response['Content-Disposition'] = f'attachment; filename="order_{order_id}.json"'
        return response


# ──────────────────────────────────────────
# ダッシュボード
# ──────────────────────────────────────────

class PartnerMonthlyProgressView(StaffRequiredMixin, View):
    """パートナー月次進捗ダッシュボード"""

    def get(self, request):
        from core.domain.models import Partner
        from invoices.models import WorkReport, Invoice
        import datetime

        # 対象月を決定（デフォルトは当月）
        month_str = request.GET.get('month')
        today = datetime.date.today()
        if month_str:
            try:
                target_date = datetime.date.fromisoformat(f"{month_str}-01")
            except ValueError:
                target_date = datetime.date(today.year, today.month, 1)
        else:
            target_date = datetime.date(today.year, today.month, 1)

        target_month_str = target_date.strftime('%Y-%m')

        # 前月・次月リンク用
        import calendar
        prev_month = (target_date.replace(day=1) - datetime.timedelta(days=1)).replace(day=1)
        _, last_day = calendar.monthrange(target_date.year, target_date.month)
        next_month = (target_date.replace(day=last_day) + datetime.timedelta(days=1))

        # 進捗データ集計
        partners = Partner.objects.all().order_by('name')
        
        # 当月の注文書を一括取得
        orders_by_partner = {}
        for order in Order.objects.filter(
            order_end_ym__year=target_date.year, 
            order_end_ym__month=target_date.month
        ).exclude(status='DRAFT'):
            orders_by_partner[order.partner_id] = order

        # 当月の稼働報告を一括取得
        work_reports_by_order = {}
        for wr in WorkReport.objects.filter(
            target_month__year=target_date.year, 
            target_month__month=target_date.month
        ):
            if wr.order_id not in work_reports_by_order:
                work_reports_by_order[wr.order_id] = []
            work_reports_by_order[wr.order_id].append(wr)

        # 当月の請求書を一括取得
        invoices_by_order = {}
        for inv in Invoice.objects.filter(
            target_month__year=target_date.year, 
            target_month__month=target_date.month
        ):
            invoices_by_order[inv.order_id] = inv

        progress_data = []

        for p in partners:
            order = orders_by_partner.get(p.partner_id)
            
            # 各ステップのステータス判定
            step1_order = None    # 注文書送付
            step2_accept = None   # 承諾
            step3_work = None     # 稼働報告
            step4_invoice = None  # 請求書
            step5_payment = None  # 支払

            order_id = None
            invoice_id = None

            if order:
                order_id = order.order_id
                step1_order = 'DONE'

                # 承諾
                if order.status == 'APPROVED':
                    step2_accept = 'DONE'
                else:
                    step2_accept = 'WAITING'

                # 稼働報告
                wrs = work_reports_by_order.get(order.order_id, [])
                if wrs:
                    if any(w.status == 'APPROVED' for w in wrs):
                        step3_work = 'DONE'
                    else:
                        step3_work = 'PROCESSING'
                else:
                    step3_work = 'WAITING'

                # 請求書
                inv = invoices_by_order.get(order.order_id)
                if inv:
                    invoice_id = inv.pk
                    if inv.status in ('ISSUED', 'SENT', 'CONFIRMED', 'PAID'):
                        step4_invoice = 'DONE'
                    else:
                        step4_invoice = 'PROCESSING'

                    # 支払
                    if inv.status == 'PAID':
                        step5_payment = 'DONE'
                    else:
                        step5_payment = 'WAITING'
                else:
                    step4_invoice = 'WAITING'
                    step5_payment = 'WAITING'
            else:
                step1_order = 'NONE'
                step2_accept = 'NONE'
                step3_work = 'NONE'
                step4_invoice = 'NONE'
                step5_payment = 'NONE'

            progress_data.append({
                'partner': p,
                'order_id': order_id,
                'invoice_id': invoice_id,
                'steps': {
                    'order': step1_order,
                    'accept': step2_accept,
                    'work': step3_work,
                    'invoice': step4_invoice,
                    'payment': step5_payment,
                }
            })

        return render(request, 'orders/partner_monthly_progress.html', {
            'target_month_str': target_month_str,
            'target_date': target_date,
            'prev_month': prev_month.strftime('%Y-%m'),
            'next_month': next_month.strftime('%Y-%m'),
            'progress_data': progress_data,
        })

