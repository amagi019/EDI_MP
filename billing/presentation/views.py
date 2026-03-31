"""
billing プレゼンテーション層 - ビュー定義
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.contrib import messages
from django.views import View
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView,
)
from django.urls import reverse_lazy, reverse
from django.db.models import Sum, Q

from billing.domain.models import (
    BillingCustomer, BillingProduct, BillingInvoice, BillingItem,
    ReceivedOrder, ReceivedOrderItem,
)
from billing.application.forms import (
    BillingCustomerForm, BillingProductForm, BillingInvoiceForm,
    BillingItemFormSet, InvoiceMailForm,
)
from billing.application.services.pdf_generator import generate_billing_pdf
from billing.application.services.drive_service import upload_to_drive, get_drive_file_url
from billing.application.services.mail_service import (
    send_invoice_email, parse_email_list,
)
from core.domain.models import CompanyInfo
from core.permissions import StaffRequiredMixin


# ============================================================
# ダッシュボード
# ============================================================

class DashboardView(StaffRequiredMixin, TemplateView):
    """請求書ダッシュボード"""
    template_name = 'billing/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        invoices = BillingInvoice.objects.all()
        context['total_count'] = invoices.count()
        context['draft_count'] = invoices.filter(status='DRAFT').count()
        context['issued_count'] = invoices.filter(status='ISSUED').count()
        context['sent_count'] = invoices.filter(status='SENT').count()
        context['paid_count'] = invoices.filter(status='PAID').count()
        context['recent_invoices'] = invoices[:10]
        context['unpaid_invoices'] = invoices.exclude(status='PAID')[:10]
        return context


# ============================================================
# 請求先（BillingCustomer）
# ============================================================

class CustomerListView(StaffRequiredMixin, ListView):
    model = BillingCustomer
    template_name = 'billing/customer_list.html'
    context_object_name = 'customers'


class CustomerCreateView(StaffRequiredMixin, CreateView):
    model = BillingCustomer
    form_class = BillingCustomerForm
    template_name = 'billing/customer_form.html'
    success_url = reverse_lazy('billing:customer_list')

    def form_valid(self, form):
        messages.success(self.request, '請求先を登録しました。')
        return super().form_valid(form)


class CustomerUpdateView(StaffRequiredMixin, UpdateView):
    model = BillingCustomer
    form_class = BillingCustomerForm
    template_name = 'billing/customer_form.html'
    success_url = reverse_lazy('billing:customer_list')

    def form_valid(self, form):
        messages.success(self.request, '請求先を更新しました。')
        return super().form_valid(form)


class CustomerDeleteView(StaffRequiredMixin, DeleteView):
    model = BillingCustomer
    template_name = 'billing/customer_confirm_delete.html'
    success_url = reverse_lazy('billing:customer_list')

    def form_valid(self, form):
        messages.success(self.request, '請求先を削除しました。')
        return super().form_valid(form)


# ============================================================
# 商品（BillingProduct）
# ============================================================

class ProductListView(StaffRequiredMixin, ListView):
    model = BillingProduct
    template_name = 'billing/product_list.html'
    context_object_name = 'products'


class ProductCreateView(StaffRequiredMixin, CreateView):
    model = BillingProduct
    form_class = BillingProductForm
    template_name = 'billing/product_form.html'
    success_url = reverse_lazy('billing:product_list')

    def form_valid(self, form):
        messages.success(self.request, '商品を登録しました。')
        return super().form_valid(form)


class ProductUpdateView(StaffRequiredMixin, UpdateView):
    model = BillingProduct
    form_class = BillingProductForm
    template_name = 'billing/product_form.html'
    success_url = reverse_lazy('billing:product_list')

    def form_valid(self, form):
        messages.success(self.request, '商品を更新しました。')
        return super().form_valid(form)


class ProductDeleteView(StaffRequiredMixin, DeleteView):
    model = BillingProduct
    template_name = 'billing/product_confirm_delete.html'
    success_url = reverse_lazy('billing:product_list')

    def form_valid(self, form):
        messages.success(self.request, '商品を削除しました。')
        return super().form_valid(form)


class ProductAPIView(StaffRequiredMixin, View):
    """商品情報API（JSON）"""
    def get(self, request, pk):
        product = get_object_or_404(BillingProduct, pk=pk)
        return JsonResponse({
            'id': product.pk,
            'name': product.name,
            'unit_price': product.unit_price,
            'tax_category': product.tax_category,
        })


# ============================================================
# 請求書（BillingInvoice）
# ============================================================

class InvoiceListView(StaffRequiredMixin, ListView):
    model = BillingInvoice
    template_name = 'billing/invoice_list.html'
    context_object_name = 'invoices'

    def get_queryset(self):
        qs = super().get_queryset()
        status = self.request.GET.get('status')
        q = self.request.GET.get('q')
        if status:
            qs = qs.filter(status=status)
        if q:
            qs = qs.filter(
                Q(customer__name__icontains=q) | Q(subject__icontains=q)
            )
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        current = self.request.GET.get('status', '')
        context['current_status'] = current
        context['search_query'] = self.request.GET.get('q', '')
        context['status_options'] = [
            {'value': 'DRAFT', 'label': '下書き', 'selected': current == 'DRAFT'},
            {'value': 'ISSUED', 'label': '発行済', 'selected': current == 'ISSUED'},
            {'value': 'SENT', 'label': '送付済', 'selected': current == 'SENT'},
            {'value': 'PAID', 'label': '入金済', 'selected': current == 'PAID'},
        ]
        return context


class InvoiceCreateView(StaffRequiredMixin, CreateView):
    model = BillingInvoice
    form_class = BillingInvoiceForm
    template_name = 'billing/invoice_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['formset'] = BillingItemFormSet(self.request.POST)
        else:
            context['formset'] = BillingItemFormSet()
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        formset = context['formset']
        if formset.is_valid():
            self.object = form.save()
            formset.instance = self.object
            items = formset.save(commit=False)
            for item in items:
                if item.product:
                    item.product_name = item.product.name
                    item.unit_price = item.product.unit_price
                    item.tax_category = item.product.tax_category
                item.save()
            for obj in formset.deleted_objects:
                obj.delete()
            messages.success(self.request, '請求書を作成しました。')
            return redirect('billing:invoice_list')
        else:
            return self.render_to_response(context)


class InvoiceUpdateView(StaffRequiredMixin, UpdateView):
    model = BillingInvoice
    form_class = BillingInvoiceForm
    template_name = 'billing/invoice_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['formset'] = BillingItemFormSet(
                self.request.POST, instance=self.object
            )
        else:
            context['formset'] = BillingItemFormSet(instance=self.object)
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        formset = context['formset']
        if formset.is_valid():
            self.object = form.save()
            formset.instance = self.object
            items = formset.save(commit=False)
            for item in items:
                if item.product:
                    item.product_name = item.product.name
                    item.unit_price = item.product.unit_price
                    item.tax_category = item.product.tax_category
                item.save()
            for obj in formset.deleted_objects:
                obj.delete()
            messages.success(self.request, '請求書を更新しました。')
            return redirect('billing:invoice_list')
        else:
            return self.render_to_response(context)


class InvoiceDetailView(StaffRequiredMixin, DetailView):
    model = BillingInvoice
    template_name = 'billing/invoice_detail.html'
    context_object_name = 'invoice'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['items'] = self.object.items.all()
        tax_summary = self.object.tax_summary
        for rate, amounts in tax_summary.items():
            amounts['tax_fmt'] = f"{amounts['tax']:,}"
        context['tax_summary'] = tax_summary
        inv = self.object
        context['status_display'] = inv.get_status_display()
        context['status_style'] = inv.status_badge_style
        return context


class InvoiceDeleteView(StaffRequiredMixin, DeleteView):
    model = BillingInvoice
    template_name = 'billing/invoice_confirm_delete.html'
    success_url = reverse_lazy('billing:invoice_list')

    def form_valid(self, form):
        messages.success(self.request, '請求書を削除しました。')
        return super().form_valid(form)


# ============================================================
# PDF
# ============================================================

@method_decorator(xframe_options_sameorigin, name='dispatch')
class InvoicePDFView(StaffRequiredMixin, View):
    """PDF生成・プレビュー"""
    def get(self, request, pk):
        invoice = get_object_or_404(BillingInvoice, pk=pk)
        pdf_buffer = generate_billing_pdf(invoice)
        response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="invoice_{invoice.invoice_number}.pdf"'
        return response


class InvoicePDFDownloadView(StaffRequiredMixin, View):
    """PDFダウンロード"""
    def get(self, request, pk):
        invoice = get_object_or_404(BillingInvoice, pk=pk)
        pdf_buffer = generate_billing_pdf(invoice)
        response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="invoice_{invoice.invoice_number}.pdf"'
        return response


# ============================================================
# Googleドライブ保存
# ============================================================

class InvoiceDriveUploadView(StaffRequiredMixin, View):
    """Googleドライブに保存"""
    def post(self, request, pk):
        invoice = get_object_or_404(BillingInvoice, pk=pk)

        try:
            # フォルダID取得
            import re
            folder_url = request.POST.get('folder_url', '').strip()
            use_mydrive = request.POST.get('use_mydrive')
            folder_id = None

            if use_mydrive:
                folder_id = ''  # マイドライブ直下
            elif folder_url:
                # URLからフォルダIDを抽出
                m = re.search(r'/folders/([a-zA-Z0-9_-]+)', folder_url)
                if m:
                    folder_id = m.group(1)
                else:
                    folder_id = folder_url  # 直接IDとして使用

            pdf_buffer = generate_billing_pdf(invoice)
            filename = f"請求書_{invoice.customer.name}_{invoice.issue_date}.pdf"
            file_id = upload_to_drive(pdf_buffer, filename, folder_id=folder_id)

            invoice.drive_file_id = file_id
            invoice.save(update_fields=['drive_file_id'])

            messages.success(request, 'Googleドライブに保存しました。')
        except Exception as e:
            import traceback
            traceback.print_exc()
            detail = str(e)
            if hasattr(e, 'reason'):
                detail = e.reason
            if hasattr(e, 'content'):
                detail = e.content.decode('utf-8', errors='replace')[:500]
            messages.error(request, f'ドライブ保存に失敗しました: {detail}')

        return redirect('billing:invoice_detail', pk=pk)


# ============================================================
# メール送信
# ============================================================

class InvoiceMailView(StaffRequiredMixin, View):
    """メール送信"""
    def get(self, request, pk):
        invoice = get_object_or_404(BillingInvoice, pk=pk)
        customer = invoice.customer

        # デフォルト値を設定
        contact = customer.contact_person or ''
        greeting = f'{customer.name}　御中'
        if contact:
            greeting += f'\n{contact}様'

        company = CompanyInfo.objects.first()
        sender_name = f'{company.name}　{company.contact_person}' if company else ''

        body_text = (
            f'{greeting}\n\n'
            f'いつもお世話になっております。\n'
            f'{sender_name}です。\n\n'
            f'下記の件、ご請求書を送りします。\n'
            f'ご査収のほどお願い致します。\n\n'
            f'請求日：{invoice.issue_date}\n'
            f'支払期日：{invoice.due_date or "-"}\n'
            f'件名：{invoice.subject or "ご請求書"}\n\n'
            f'Best regards.'
        )

        initial = {
            'to_email': customer.email,
            'cc_email': customer.cc_email,
            'subject': f'請求書をお送りします。',
            'body': body_text,
        }
        form = InvoiceMailForm(initial=initial)
        return render(request, 'billing/invoice_mail.html', {
            'invoice': invoice, 'form': form,
        })

    def post(self, request, pk):
        invoice = get_object_or_404(BillingInvoice, pk=pk)
        form = InvoiceMailForm(request.POST)

        if form.is_valid():
            to_list = parse_email_list(form.cleaned_data['to_email'])
            cc_list = parse_email_list(form.cleaned_data['cc_email'])
            subject = form.cleaned_data['subject']
            body = form.cleaned_data['body']

            # PDF生成して添付
            pdf_buffer = generate_billing_pdf(invoice)

            success = send_invoice_email(
                invoice, to_list, cc_list, subject, body, pdf_buffer
            )

            if success:
                if invoice.status in ('DRAFT', 'ISSUED'):
                    invoice.status = 'SENT'
                    invoice.save(update_fields=['status'])

                # Google Drive保存
                try:
                    from billing.services.billing_service import _save_invoice_to_drive
                    pdf_buffer.seek(0)
                    drive_id = _save_invoice_to_drive(invoice, pdf_buffer.getvalue())
                    if drive_id:
                        messages.success(request, 'メールを送信し、Google Driveに保存しました。')
                    else:
                        messages.success(request, 'メールを送信しました。（Drive保存はスキップ）')
                except Exception as e:
                    messages.success(request, f'メールを送信しました。（Drive保存エラー: {e}）')

                return redirect('billing:invoice_detail', pk=pk)
            else:
                messages.error(request, 'メール送信に失敗しました。')

        return render(request, 'billing/invoice_mail.html', {
            'invoice': invoice, 'form': form,
        })


# ============================================================
# 受注管理（ReceivedOrder）
# ============================================================

class ReceivedOrderListView(StaffRequiredMixin, View):
    """受注管理 — プロジェクト（取引先×業務名）単位でグルーピング"""

    def get(self, request):
        from itertools import groupby
        from operator import attrgetter

        orders = ReceivedOrder.objects.select_related('customer').prefetch_related('items').order_by(
            'customer__name', 'project_name', '-target_month'
        )
        # プロジェクトキーでグルーピング（取引先×業務名）
        projects = []
        for key, group in groupby(orders, key=lambda o: (o.customer_id, o.project_name)):
            group_list = list(group)
            latest = group_list[0]  # 最新月
            projects.append({
                'customer': latest.customer,
                'project_name': latest.project_name,
                'latest': latest,
                'order_count': len(group_list),
                'is_recurring': latest.is_recurring,
                'items': latest.items.all(),
            })

        return render(request, 'billing/received_order_list.html', {
            'projects': projects,
        })


class ReceivedOrderMonthlyListView(StaffRequiredMixin, ListView):
    """注文書一覧 — 月次の注文書を一覧表示"""
    model = ReceivedOrder
    template_name = 'billing/received_order_monthly_list.html'
    context_object_name = 'orders'
    ordering = ['-target_month', 'customer__name']

    def get_queryset(self):
        return super().get_queryset().select_related('customer').prefetch_related('items')


class ReceivedOrderDetailView(StaffRequiredMixin, DetailView):
    """受注詳細"""
    model = ReceivedOrder
    template_name = 'billing/received_order_detail.html'
    context_object_name = 'order'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['items'] = self.object.items.all()
        return context


class ReceivedOrderCreateView(StaffRequiredMixin, View):
    """受注登録（PDF自動パース / 手動入力）"""

    def get(self, request):
        return render(request, 'billing/received_order_create.html', {
            'customers': BillingCustomer.objects.all(),
        })

    def post(self, request):
        action = request.POST.get('action')

        if action == 'pdf_upload':
            return self._handle_pdf_upload(request)
        else:
            return self._handle_manual(request)

    def _handle_pdf_upload(self, request):
        from billing.services.received_order_service import create_received_order_from_pdf

        customer_id = request.POST.get('customer_id')
        pdf_file = request.FILES.get('order_pdf')

        if not customer_id or not pdf_file:
            messages.error(request, '取引先とPDFファイルを選択してください。')
            return redirect('billing:received_order_create')

        customer = get_object_or_404(BillingCustomer, pk=customer_id)

        try:
            order, parsed, errors = create_received_order_from_pdf(
                pdf_file, customer, user=request.user
            )
            if errors:
                for e in errors:
                    messages.warning(request, f'⚠ {e}')
            messages.success(
                request,
                f'受注を登録しました（{parsed["format"]}形式・注文番号: {order.order_number or "なし"}）'
            )
            return redirect('billing:received_order_detail', pk=order.pk)
        except Exception as e:
            messages.error(request, f'PDFパースに失敗しました: {e}')
            return redirect('billing:received_order_create')

    def _handle_manual(self, request):
        import datetime
        from billing.services.received_order_service import create_received_order_manual

        customer_id = request.POST.get('manual_customer_id')
        if not customer_id:
            messages.error(request, '取引先を選択してください。')
            return redirect('billing:received_order_create')

        customer = get_object_or_404(BillingCustomer, pk=customer_id)

        try:
            target_month_str = request.POST.get('target_month', '')
            target_month = datetime.date.fromisoformat(f"{target_month_str}-01")
            work_start = datetime.date.fromisoformat(request.POST.get('work_start', ''))
            work_end = datetime.date.fromisoformat(request.POST.get('work_end', ''))
        except ValueError:
            messages.error(request, '日付の形式が正しくありません。')
            return redirect('billing:received_order_create')

        order = create_received_order_manual(
            customer=customer,
            target_month=target_month,
            work_start=work_start,
            work_end=work_end,
            order_number=request.POST.get('order_number', ''),
            project_name=request.POST.get('project_name', ''),
        )
        messages.success(request, f'受注を登録しました（注文番号: {order.order_number or "手動登録"}）')
        return redirect('billing:received_order_detail', pk=order.pk)


# ============================================================
# 勤怠報告（StaffTimesheet）
# ============================================================

from billing.domain.models import StaffTimesheet


class TimesheetListView(StaffRequiredMixin, ListView):
    """勤怠報告一覧"""
    model = StaffTimesheet
    template_name = 'billing/timesheet_list.html'
    context_object_name = 'timesheets'


class TimesheetCreateView(StaffRequiredMixin, View):
    """勤怠登録"""

    def get(self, request):
        orders = ReceivedOrder.objects.filter(
            status__in=['REGISTERED', 'ACTIVE']
        )
        return render(request, 'billing/timesheet_create.html', {
            'orders': orders,
        })

    def post(self, request):
        import datetime as dt
        from billing.services.timesheet_service import create_timesheet

        order_id = request.POST.get('order_id')
        order = get_object_or_404(ReceivedOrder, pk=order_id)

        target_month_str = request.POST.get('target_month', '')
        try:
            target_month = dt.date.fromisoformat(f"{target_month_str}-01")
        except ValueError:
            messages.error(request, '対象月の形式が正しくありません。')
            return redirect('billing:timesheet_create')

        order_item = order.items.first()
        total_hours = request.POST.get('total_hours', 0)
        work_days = request.POST.get('work_days', 0)

        ts = create_timesheet(
            order=order,
            order_item=order_item,
            worker_name=request.POST.get('worker_name', ''),
            worker_type=request.POST.get('worker_type', 'INTERNAL'),
            target_month=target_month,
            total_hours=float(total_hours),
            work_days=int(work_days),
        )
        messages.success(request, f'稼働報告を登録しました: {ts.worker_name}')
        return redirect('billing:timesheet_list')


class TimesheetApproveView(StaffRequiredMixin, View):
    """勤怠報告の承認・ステータス変更"""

    def post(self, request, pk):
        from billing.services.timesheet_service import approve_timesheet, submit_timesheet, mark_as_sent

        ts = get_object_or_404(StaffTimesheet, pk=pk)
        action = request.POST.get('action', 'approve')

        if action == 'submit':
            submit_timesheet(ts)
            messages.success(request, f'{ts.worker_name}の勤怠を提出しました。')
        elif action == 'sent':
            mark_as_sent(ts)
            messages.success(request, f'{ts.worker_name}の作業報告書を送付済みにしました。')
        elif action == 'approve':
            approve_timesheet(ts)
            messages.success(request, f'{ts.worker_name}の勤怠を承認しました。')

        return redirect('billing:timesheet_list')


class TimesheetSendView(StaffRequiredMixin, View):
    """作業報告書のメール送信"""

    def get(self, request, pk):
        from billing.services.timesheet_service import _build_default_body

        ts = get_object_or_404(StaffTimesheet, pk=pk)
        default_subject = f'{ts.worker_name}の稼働報告'
        default_body = _build_default_body(ts, ts.order, ts.order.customer)
        return render(request, 'billing/timesheet_send.html', {
            'timesheet': ts,
            'default_subject': default_subject,
            'default_body': default_body,
        })

    def post(self, request, pk):
        from billing.services.timesheet_service import send_work_report_email

        ts = get_object_or_404(StaffTimesheet, pk=pk)
        subject = request.POST.get('email_subject', '')
        body = request.POST.get('email_body', '')

        result = send_work_report_email(
            ts,
            subject=subject or None,
            body=body or None,
        )

        if result['sent']:
            messages.success(request, f'{ts.worker_name}の作業報告書を送信しました。')
        else:
            for err in result['errors']:
                messages.error(request, err)

        return redirect('billing:timesheet_list')


# ============================================================
# 請求連携（受注 → 請求書生成）
# ============================================================

class GenerateInvoiceFromOrderView(StaffRequiredMixin, View):
    """受注から請求書を自動生成"""

    def post(self, request, pk):
        from billing.services.billing_service import create_invoice_from_received_order

        order = get_object_or_404(ReceivedOrder, pk=pk)

        try:
            invoice, item_count, warnings = create_invoice_from_received_order(order)
            for w in warnings:
                messages.warning(request, f'⚠ {w}')
            messages.success(
                request,
                f'請求書を生成しました（{item_count}件の明細）'
            )
            return redirect('billing:invoice_detail', pk=invoice.pk)
        except Exception as e:
            messages.error(request, f'請求書の生成に失敗しました: {e}')
            return redirect('billing:received_order_detail', pk=pk)


# ============================================================
# 受注編集
# ============================================================

class ReceivedOrderEditView(StaffRequiredMixin, View):
    """受注編集（パース結果の修正含む）"""

    def get(self, request, pk):
        order = get_object_or_404(ReceivedOrder, pk=pk)
        items = order.items.all()
        return render(request, 'billing/received_order_edit.html', {
            'order': order, 'items': items,
        })

    def post(self, request, pk):
        import datetime as dt
        from decimal import Decimal

        order = get_object_or_404(ReceivedOrder, pk=pk)

        # ヘッダー更新
        order.order_number = request.POST.get('order_number', '')
        order.project_name = request.POST.get('project_name', '')
        order.status = request.POST.get('status', order.status)
        order.is_recurring = 'is_recurring' in request.POST
        order.remarks = request.POST.get('remarks', '')
        order.report_to_email = request.POST.get('report_to_email', '')
        order.report_cc_emails = request.POST.get('report_cc_emails', '')
        order.invoice_to_email = request.POST.get('invoice_to_email', '')
        order.invoice_cc_emails = request.POST.get('invoice_cc_emails', '')

        try:
            tm = request.POST.get('target_month', '')
            order.target_month = dt.date.fromisoformat(f"{tm}-01")
            order.work_start = dt.date.fromisoformat(request.POST.get('work_start', ''))
            order.work_end = dt.date.fromisoformat(request.POST.get('work_end', ''))
            order.order_date = dt.date.fromisoformat(request.POST.get('order_date', ''))
        except ValueError:
            pass

        order.save()

        # 明細更新（既存更新/新規作成/削除）
        item_count = int(request.POST.get('item_count', 0))
        processed_ids = set()
        for i in range(item_count):
            item_id = request.POST.get(f'item_id_{i}')
            if not item_id:
                continue
            person_name = request.POST.get(f'item_person_{i}', '')
            unit_price = int(request.POST.get(f'item_price_{i}', 0))
            man_month = Decimal(request.POST.get(f'item_manmonth_{i}', '1'))
            settlement_type = request.POST.get(f'item_settlement_{i}', 'RANGE')
            settlement_middle_hours = Decimal(request.POST.get(f'item_middle_{i}', '170'))
            lower = Decimal(request.POST.get(f'item_lower_{i}', '140'))
            upper = Decimal(request.POST.get(f'item_upper_{i}', '180'))
            excess = int(request.POST.get(f'item_excess_{i}', 0))
            shortage = int(request.POST.get(f'item_shortage_{i}', 0))

            if item_id == '-1':
                # 新規作成
                if person_name.strip():
                    new_item = ReceivedOrderItem.objects.create(
                        order=order,
                        person_name=person_name,
                        unit_price=unit_price,
                        man_month=man_month,
                        settlement_type=settlement_type,
                        settlement_middle_hours=settlement_middle_hours,
                        time_lower_limit=lower,
                        time_upper_limit=upper,
                        excess_rate=excess,
                        shortage_rate=shortage,
                    )
                    processed_ids.add(new_item.pk)
            else:
                # 既存更新
                try:
                    item = ReceivedOrderItem.objects.get(pk=item_id)
                    item.person_name = person_name
                    item.unit_price = unit_price
                    item.man_month = man_month
                    item.settlement_type = settlement_type
                    item.settlement_middle_hours = settlement_middle_hours
                    item.time_lower_limit = lower
                    item.time_upper_limit = upper
                    item.excess_rate = excess
                    item.shortage_rate = shortage
                    item.save()
                    processed_ids.add(item.pk)
                except (ReceivedOrderItem.DoesNotExist, ValueError):
                    pass

        # テンプレートから削除された明細を実際に削除
        ReceivedOrderItem.objects.filter(
            order=order
        ).exclude(pk__in=processed_ids).delete()

        messages.success(request, '受注を更新しました。')
        return redirect('billing:received_order_detail', pk=pk)


# ============================================================
# ロールフォワード
# ============================================================

class RollforwardOrderView(StaffRequiredMixin, View):
    """受注の翌月ロールフォワード"""

    def post(self, request, pk):
        from billing.services.received_order_service import rollforward_order

        order = get_object_or_404(ReceivedOrder, pk=pk)
        try:
            new_order = rollforward_order(order)
            messages.success(
                request,
                f'翌月分を生成しました: {new_order.target_month.strftime("%Y/%m")}'
            )
            return redirect('billing:received_order_detail', pk=new_order.pk)
        except ValueError as e:
            messages.error(request, str(e))
            return redirect('billing:received_order_detail', pk=pk)


class RollforwardAllView(StaffRequiredMixin, View):
    """継続注文の一括ロールフォワード"""

    def post(self, request):
        from billing.services.received_order_service import rollforward_all_recurring

        results = rollforward_all_recurring()
        if results:
            for src, new in results:
                messages.success(
                    request,
                    f'{src.customer.name}: {new.target_month.strftime("%Y/%m")}分を生成'
                )
        else:
            messages.info(request, '生成対象の継続注文はありません。')
        return redirect('billing:received_order_list')


# ============================================================
# 勤怠報告 Excel取込
# ============================================================

import json as _json


class TimesheetExcelUploadView(StaffRequiredMixin, View):
    """Excelファイルアップロード → 解析 → セッション保存"""

    def get(self, request):
        orders = ReceivedOrder.objects.filter(
            status__in=['REGISTERED', 'ACTIVE']
        ).select_related('customer').order_by('-target_month')
        return render(request, 'billing/timesheet_excel_upload.html', {
            'orders': orders,
        })

    def post(self, request):
        from invoices.services.excel_parser import auto_detect_and_parse
        from decimal import Decimal
        from django.core.files.storage import default_storage
        from django.core.files.base import ContentFile
        import uuid as _uuid

        files = request.FILES.getlist('files')
        if not files:
            messages.error(request, 'ファイルを選択してください。')
            return redirect('billing:timesheet_excel_upload')

        parsed_results = []
        for f in files:
            # Excelファイル原本を一時保存（確認後にTimesheetに紐付ける）
            saved_path = ''
            try:
                f.seek(0)
                temp_name = f'timesheets/temp/{_uuid.uuid4().hex}_{f.name}'
                saved_path = default_storage.save(temp_name, ContentFile(f.read()))
                f.seek(0)  # パーサー用に先頭に戻す
            except Exception:
                pass

            try:
                result = auto_detect_and_parse(f, original_filename=f.name)
                parsed_results.append({
                    'filename': f.name,
                    'worker_name': result['worker_name'],
                    'target_month': result['target_month'].isoformat() if result['target_month'] else '',
                    'total_hours': str(result['total_hours']),
                    'work_days': result['work_days'],
                    'daily_data': result['daily_data'],
                    'alerts': result['alerts'],
                    'error': result['error'],
                    'name_mismatch_warning': result.get('name_mismatch_warning', ''),
                    'saved_file_path': saved_path,
                })
            except Exception as e:
                parsed_results.append({
                    'filename': f.name,
                    'worker_name': '',
                    'target_month': '',
                    'total_hours': '0',
                    'work_days': 0,
                    'daily_data': [],
                    'alerts': [],
                    'error': f'ファイルの解析中にエラーが発生しました: {e}',
                    'name_mismatch_warning': '',
                    'saved_file_path': saved_path,
                })

        # セッションに保存
        request.session['timesheet_excel_results'] = _json.dumps(
            parsed_results, ensure_ascii=False, default=str
        )

        return redirect('billing:timesheet_excel_confirm')


class TimesheetExcelConfirmView(StaffRequiredMixin, View):
    """解析結果の確認・編集 → StaffTimesheet一括登録"""

    def get(self, request):
        raw = request.session.get('timesheet_excel_results')
        if not raw:
            messages.error(request, '解析結果がありません。再度アップロードしてください。')
            return redirect('billing:timesheet_excel_upload')

        parsed_results = _json.loads(raw)
        orders = ReceivedOrder.objects.filter(
            status__in=['REGISTERED', 'ACTIVE']
        ).select_related('customer').prefetch_related('items').order_by('-target_month')

        # order_items をJSON化してテンプレートのJSで使う
        order_items_map = {}
        for order in orders:
            order_items_map[str(order.pk)] = [
                {'id': item.pk, 'name': item.person_name or f'明細{item.pk}'}
                for item in order.items.all()
            ]

        # 自動マッチング: 対象月と作業者名で受注を推定
        from core.utils import normalize_name
        from datetime import date as _date

        for r in parsed_results:
            r['matched_order_id'] = ''
            r['matched_item_id'] = ''
            if r.get('error'):
                continue

            target_month_str = r.get('target_month', '')
            worker_name = r.get('worker_name', '')

            if target_month_str:
                try:
                    tm = _date.fromisoformat(target_month_str)
                except ValueError:
                    tm = None

                if tm:
                    # 対象月が一致する受注を検索
                    for order in orders:
                        if order.target_month == tm:
                            r['matched_order_id'] = str(order.pk)
                            # 作業者名で明細をマッチング
                            if worker_name:
                                worker_norm = normalize_name(worker_name)
                                for item in order.items.all():
                                    if normalize_name(item.person_name) == worker_norm:
                                        r['matched_item_id'] = str(item.pk)
                                        break
                            break

                    # 対象月で見つからなければ、作業者名だけでも探す
                    if not r['matched_order_id'] and worker_name:
                        worker_norm = normalize_name(worker_name)
                        for order in orders:
                            for item in order.items.all():
                                if normalize_name(item.person_name) == worker_norm:
                                    r['matched_order_id'] = str(order.pk)
                                    r['matched_item_id'] = str(item.pk)
                                    break
                            if r['matched_order_id']:
                                break

        return render(request, 'billing/timesheet_excel_confirm.html', {
            'results': parsed_results,
            'orders': orders,
            'order_items_json': _json.dumps(order_items_map, ensure_ascii=False),
        })

    def post(self, request):
        import datetime as dt
        from decimal import Decimal
        from billing.services.timesheet_service import create_timesheet

        count = int(request.POST.get('result_count', 0))
        created = 0
        worker_names = []

        for i in range(count):
            # エラーのあるものはスキップ
            if request.POST.get(f'skip_{i}') == '1':
                continue

            order_id = request.POST.get(f'order_id_{i}')
            if not order_id:
                continue

            try:
                order = ReceivedOrder.objects.get(pk=order_id)
            except ReceivedOrder.DoesNotExist:
                continue

            order_item_id = request.POST.get(f'order_item_id_{i}')
            order_item = None
            if order_item_id:
                try:
                    order_item = ReceivedOrderItem.objects.get(pk=order_item_id)
                except ReceivedOrderItem.DoesNotExist:
                    pass

            worker_name = request.POST.get(f'worker_name_{i}', '')
            worker_type = request.POST.get(f'worker_type_{i}', 'INTERNAL')
            target_month_str = request.POST.get(f'target_month_{i}', '')
            total_hours = request.POST.get(f'total_hours_{i}', '0')
            work_days = request.POST.get(f'work_days_{i}', '0')
            daily_data_raw = request.POST.get(f'daily_data_{i}', '[]')

            try:
                target_month = dt.date.fromisoformat(f"{target_month_str}-01")
            except ValueError:
                try:
                    target_month = dt.date.fromisoformat(target_month_str)
                except ValueError:
                    messages.warning(request, f'{worker_name}: 対象月が不正なためスキップしました。')
                    continue

            try:
                daily_data = _json.loads(daily_data_raw)
            except _json.JSONDecodeError:
                daily_data = None

            # 一時保存されたExcelファイルを取得
            saved_file_path = request.POST.get(f'saved_file_path_{i}', '')
            excel_file = None
            original_filename = request.POST.get(f'original_filename_{i}', '')
            if saved_file_path:
                try:
                    from django.core.files.storage import default_storage
                    if default_storage.exists(saved_file_path):
                        excel_file = saved_file_path
                except Exception:
                    pass

            ts = create_timesheet(
                order=order,
                order_item=order_item,
                worker_name=worker_name,
                worker_type=worker_type,
                target_month=target_month,
                total_hours=float(total_hours),
                work_days=int(work_days),
                daily_data=daily_data,
                excel_file_path=excel_file,
                original_filename=original_filename,
            )
            worker_names.append(worker_name)
            created += 1

        # セッション内の解析結果をクリア
        request.session.pop('timesheet_excel_results', None)

        if created > 0:
            names_str = '、'.join(worker_names)
            messages.success(request, f'{created}件（{len(worker_names)}名: {names_str}）の稼働報告を登録しました。')
        else:
            messages.warning(request, '登録対象がありませんでした。')

        return redirect('billing:timesheet_list')


# ============================================================
# 外部API（PayrollSystem連携）
# ============================================================

from django.views.decorators.csrf import csrf_exempt
from core.api_auth import require_api_key


@method_decorator([csrf_exempt, require_api_key], name='dispatch')
class TimesheetAPIView(View):
    """
    勤怠データAPI — PayrollSystemが呼び出す

    GET /billing/api/timesheets/?year=2026&month=3
    GET /billing/api/timesheets/?year=2026&month=3&status=APPROVED

    Response:
    {
        "year_month": "2026-03-01",
        "count": 3,
        "timesheets": [...]
    }
    """

    def get(self, request):
        import datetime

        year = request.GET.get('year')
        month = request.GET.get('month')

        if not year or not month:
            return JsonResponse(
                {'error': 'year and month parameters are required'},
                status=400
            )

        try:
            target_month = datetime.date(int(year), int(month), 1)
        except (ValueError, TypeError):
            return JsonResponse(
                {'error': 'Invalid year or month'},
                status=400
            )

        qs = StaffTimesheet.objects.filter(
            target_month=target_month
        ).select_related('order', 'order__customer')

        # ステータスフィルタ（任意）
        status_filter = request.GET.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        timesheets = []
        for ts in qs:
            timesheets.append({
                'id': ts.pk,
                'employee_id': ts.employee_id or '',
                'worker_name': ts.worker_name,
                'worker_type': ts.worker_type,
                'target_month': ts.target_month.isoformat(),
                'total_hours': float(ts.total_hours),
                'work_days': ts.work_days,
                'status': ts.status,
                'order_id': ts.order_id,
                'order_number': ts.order.order_number if ts.order else '',
                'customer_name': (
                    ts.order.customer.name if ts.order and ts.order.customer
                    else ''
                ),
            })

        return JsonResponse({
            'year_month': target_month.isoformat(),
            'count': len(timesheets),
            'timesheets': timesheets,
        })


@method_decorator([csrf_exempt, require_api_key], name='dispatch')
class EmployeeSyncView(View):
    """
    社員データ同期トリガー

    POST /billing/api/sync-employees/
    PayrollSystemから社員マスタを取得し、SyncedEmployeeを更新する。
    """

    def post(self, request):
        from billing.services.employee_sync import sync_employees

        result = sync_employees()

        if result['errors']:
            return JsonResponse({
                'status': 'error',
                'errors': result['errors'],
            }, status=500)

        return JsonResponse({
            'status': 'ok',
            'created': result['created'],
            'updated': result['updated'],
            'deactivated': result['deactivated'],
        })

    def get(self, request):
        """GETでも同期結果の確認ができる（最終同期日時を返す）"""
        from billing.domain.synced_employee import SyncedEmployee

        count = SyncedEmployee.objects.filter(is_active=True).count()
        latest = SyncedEmployee.objects.order_by('-synced_at').first()

        return JsonResponse({
            'status': 'ok',
            'active_count': count,
            'last_synced_at': (
                latest.synced_at.isoformat() if latest else None
            ),
        })

