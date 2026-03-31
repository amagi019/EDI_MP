from django.views.generic import ListView, CreateView, UpdateView
from django.views import View
from django.shortcuts import redirect
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy
from .models import OrderBasicInfo
from .basic_info_forms import OrderBasicInfoForm, BasicInfoItemFormSet


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_staff


class BasicInfoListView(StaffRequiredMixin, ListView):
    model = OrderBasicInfo
    template_name = 'orders/basic_info_list.html'
    context_object_name = 'basic_infos'

    def get_queryset(self):
        return OrderBasicInfo.objects.select_related(
            'partner', 'project', 'workplace'
        ).prefetch_related('template_items').all()


class BasicInfoCreateView(StaffRequiredMixin, CreateView):
    model = OrderBasicInfo
    form_class = OrderBasicInfoForm
    template_name = 'orders/basic_info_form.html'
    success_url = reverse_lazy('orders:basic_info_list')

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data['item_formset'] = BasicInfoItemFormSet(self.request.POST)
        else:
            data['item_formset'] = BasicInfoItemFormSet()
        data['is_edit'] = False
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        item_formset = context['item_formset']
        if item_formset.is_valid():
            self.object = form.save()
            item_formset.instance = self.object
            item_formset.save()
            return super().form_valid(form)
        else:
            return self.render_to_response(self.get_context_data(form=form))


class BasicInfoUpdateView(StaffRequiredMixin, UpdateView):
    model = OrderBasicInfo
    form_class = OrderBasicInfoForm
    template_name = 'orders/basic_info_form.html'
    success_url = reverse_lazy('orders:basic_info_list')

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data['item_formset'] = BasicInfoItemFormSet(
                self.request.POST, instance=self.object
            )
        else:
            data['item_formset'] = BasicInfoItemFormSet(instance=self.object)
        data['is_edit'] = True
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        item_formset = context['item_formset']
        if item_formset.is_valid():
            self.object = form.save()
            item_formset.instance = self.object
            item_formset.save()
            return super().form_valid(form)
        else:
            return self.render_to_response(self.get_context_data(form=form))


class CreateOrderFromBasicInfoView(StaffRequiredMixin, View):
    """ワンクリック発注：基本情報から注文書ドラフトを自動生成"""

    def post(self, request, pk):
        from .models import Order, OrderItem
        import datetime
        from calendar import monthrange

        basic_info = OrderBasicInfo.objects.select_related(
            'partner', 'project', 'workplace'
        ).prefetch_related('template_items').get(pk=pk)

        # 対象月の自動判定: 翌月分
        today = datetime.date.today()
        if today.month == 12:
            target_year, target_month = today.year + 1, 1
        else:
            target_year, target_month = today.year, today.month + 1

        # 日付を自動計算
        last_day = monthrange(target_year, target_month)[1]
        work_start = datetime.date(target_year, target_month, 1)
        work_end = datetime.date(target_year, target_month, last_day)
        order_end_ym = datetime.date(target_year, target_month, 1)

        # 重複チェック：同じパートナー×プロジェクト×対象月の注文が既にあるか
        existing = Order.objects.filter(
            partner=basic_info.partner,
            project=basic_info.project,
            order_end_ym=order_end_ym,
        ).first()
        if existing:
            from django.contrib import messages
            messages.warning(request,
                f'{target_year}年{target_month}月分の注文書は既に作成済みです（{existing.order_id}）')
            return redirect('orders:basic_info_list')

        # Order作成
        order = Order(
            partner=basic_info.partner,
            project=basic_info.project,
            order_date=today,
            order_end_ym=order_end_ym,
            work_start=work_start,
            work_end=work_end,
            workplace=basic_info.workplace,
            deliverable_text=basic_info.deliverable_text,
            payment_condition=basic_info.payment_condition,
            contract_items=basic_info.contract_items,
            甲_責任者=basic_info.甲_責任者,
            甲_担当者=basic_info.甲_担当者,
            乙_責任者=basic_info.乙_責任者,
            乙_担当者=basic_info.乙_担当者,
            作業責任者=basic_info.作業責任者,
            remarks=basic_info.remarks,
            status='DRAFT',
        )
        order.save()

        # OrderItem作成（テンプレートからコピー）
        for tmpl in basic_info.template_items.all():
            OrderItem.objects.create(
                order=order,
                person_name=tmpl.person_name,
                effort=tmpl.effort,
                base_fee=tmpl.base_fee,
                time_lower_limit=tmpl.time_lower_limit,
                time_upper_limit=tmpl.time_upper_limit,
                shortage_rate=tmpl.shortage_rate,
                excess_rate=tmpl.excess_rate,
                price=int(tmpl.effort * tmpl.base_fee),
            )

        from django.contrib import messages
        messages.success(request,
            f'{target_year}年{target_month}月分の注文書ドラフトを作成しました（{order.order_id}）')

        # 月次タスク（ORDER_CREATE）を完了にする
        from tasks.services import complete_order_create
        complete_order_create(order)

        return redirect('orders:order_edit', order_id=order.order_id)

