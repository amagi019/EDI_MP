from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
import datetime

# マスタモデル群

class Project(models.Model):
    project_id = models.CharField(_("プロジェクトID"), max_length=50, primary_key=True)
    name = models.CharField(_("プロジェクト名"), max_length=100)

    class Meta:
        verbose_name = _("プロジェクト")
        verbose_name_plural = _("プロジェクト")

    def save(self, *args, **kwargs):
        if not self.project_id:
            # PRJで始まるIDの中から最大値を取得
            last_project = Project.objects.filter(project_id__startswith='PRJ').order_by('-project_id').first()
            if last_project:
                try:
                    # PRJの後の数値を抽出
                    last_id_num = int(last_project.project_id[3:])
                    next_id = last_id_num + 1
                except ValueError:
                    next_id = 1
            else:
                next_id = 1
            self.project_id = f"PRJ{str(next_id).zfill(8)}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"[{self.project_id}] {self.name}"

class Workplace(models.Model):
    workplace_id = models.CharField(_("勤務場所ID"), max_length=50, primary_key=True)
    name = models.CharField(_("勤務場所名"), max_length=100)
    address = models.CharField(_("住所"), max_length=255, blank=True)

    class Meta:
        verbose_name = _("勤務場所")
        verbose_name_plural = _("勤務場所")

    def __str__(self):
        return self.name

class Deliverable(models.Model):
    deliverable_id = models.CharField(_("成果物ID"), max_length=50, primary_key=True)
    description = models.CharField(_("成果物の内容"), max_length=255)

    class Meta:
        verbose_name = _("成果物")
        verbose_name_plural = _("成果物")

    def __str__(self):
        return self.description

class PaymentTerm(models.Model):
    payment_term_id = models.CharField(_("支払条件ID"), max_length=50, primary_key=True)
    description = models.CharField(_("説明"), max_length=255)

    class Meta:
        verbose_name = _("支払条件")
        verbose_name_plural = _("支払条件")

    def __str__(self):
        return self.description

class ContractTerm(models.Model):
    contract_term_id = models.CharField(_("契約条件ID"), max_length=50, primary_key=True)
    description = models.CharField(_("説明"), max_length=255)

    class Meta:
        verbose_name = _("契約条件")
        verbose_name_plural = _("契約条件")

    def __str__(self):
        return self.description

class Product(models.Model):
    product_id = models.CharField(_("商品ID"), max_length=50, primary_key=True)
    name = models.CharField(_("商品名"), max_length=100)
    price = models.IntegerField(_("単価"))

    class Meta:
        verbose_name = _("商品")
        verbose_name_plural = _("商品")

    def __str__(self):
        return self.name

# トランザクションモデル

class OrderBasicInfo(models.Model):
    TIMING_CHOICES = [
        ('FIRST_DAY', _('月初')),
        ('10TH_DAY', _('10日')),
        ('15TH_DAY', _('15日')),
        ('20TH_DAY', _('20日')),
        ('LAST_DAY', _('月末')),
    ]

    customer = models.ForeignKey('core.Customer', on_delete=models.CASCADE, verbose_name=_("取引先"))
    project = models.ForeignKey(Project, on_delete=models.CASCADE, verbose_name=_("プロジェクト"))
    project_start_date = models.DateField(_("プロジェクト開始日"))
    project_end_date = models.DateField(_("プロジェクト終了日"))
    order_issuance_timing = models.CharField(
        _("注文書発行タイミング"), max_length=20, choices=TIMING_CHOICES, default='LAST_DAY'
    )
    invoice_issuance_timing = models.CharField(
        _("請求書発行タイミング"), max_length=20, choices=TIMING_CHOICES, default='LAST_DAY'
    )

    class Meta:
        verbose_name = _("発注基本情報")
        verbose_name_plural = _("発注基本情報")
        unique_together = ('customer', 'project')

    def __str__(self):
        return f"{self.project.name} - {self.customer.name}"

# トランザクションモデル（実績）

class Order(models.Model):
    STATUS_CHOICES = [
        ('DRAFT', _('下書き')),
        ('UNCONFIRMED', _('未確認（発行済）')),
        ('CONFIRMING', _('受領確認中')),
        ('RECEIVED', _('受領済')),
        ('APPROVED', _('承認済')),
    ]

    class Meta:
        verbose_name = _("注文情報")
        verbose_name_plural = _("注文情報")

    order_id = models.CharField(_("注文番号"), max_length=20, primary_key=True, help_text="MP+YYYYMMDD+6桁連番")
    customer = models.ForeignKey('core.Customer', on_delete=models.CASCADE, verbose_name=_("取引先"))
    project = models.ForeignKey(Project, on_delete=models.PROTECT, verbose_name=_("プロジェクト"))
    status = models.CharField(_("ステータス"), max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    
    order_end_ym = models.DateField(_("注文終了年月"), help_text="YYYY-MM-01形式など") # 月末日管理か年月管理かは運用次第だがDate型で保持
    order_date = models.DateField(_("注文日"), default=datetime.date.today)
    work_start = models.DateField(_("作業開始日"))
    work_end = models.DateField(_("作業終了日"))
    
    workplace = models.ForeignKey(Workplace, on_delete=models.PROTECT, verbose_name=_("勤務場所"), blank=True, null=True)
    deliverable = models.ForeignKey(Deliverable, on_delete=models.PROTECT, verbose_name=_("成果物"), blank=True, null=True)
    deliverable_text = models.CharField(_("納入物件（テキスト）"), max_length=255, default="月別作業報告書")
    
    payment_term = models.ForeignKey(PaymentTerm, on_delete=models.PROTECT, verbose_name=_("支払条件"), blank=True, null=True)
    payment_condition = models.TextField(_("詳細支払条件"), blank=True, help_text="PDFの支払条件欄に表示される詳細テキスト")
    contract_term = models.ForeignKey(ContractTerm, on_delete=models.PROTECT, verbose_name=_("契約条件"), blank=True, null=True)
    contract_items = models.TextField(_("契約条項"), blank=True, help_text="PDF下部の契約条項")

    # 担当者・責任者情報
    甲_責任者 = models.CharField(_("委託業務責任者（甲）"), max_length=64, blank=True)
    甲_担当者 = models.CharField(_("連絡窓口担当者（甲）"), max_length=64, blank=True)
    乙_責任者 = models.CharField(_("委託業務責任者（乙）"), max_length=64, blank=True)
    乙_担当者 = models.CharField(_("連絡窓口担当者（乙）"), max_length=64, blank=True)
    作業責任者 = models.CharField(_("作業責任者"), max_length=64, blank=True)
    
    base_fee = models.IntegerField(_("基本料金"), default=0)
    time_lower_limit = models.DecimalField(_("基準時間_下限"), max_digits=5, decimal_places=2, default=0.00, help_text="例: 140.00")
    time_upper_limit = models.DecimalField(_("基準時間_上限"), max_digits=5, decimal_places=2, default=0.00, help_text="例: 180.00")
    shortage_fee = models.IntegerField(_("不足単価"), default=0)
    excess_fee = models.IntegerField(_("超過単価"), default=0)
    
    remarks = models.TextField(_("備考"), blank=True, help_text="口座情報など")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # 電帳法・コンプライアンス対応
    finalized_at = models.DateTimeField(_("確定日時"), null=True, blank=True, help_text="正式発行または承認時のタイムスタンプ")
    document_hash = models.CharField(_("ドキュメントハッシュ"), max_length=64, blank=True, help_text="改ざん防止用のハッシュ値")
    
    # PDFファイルの永続保存
    order_pdf = models.FileField(_("注文書PDF"), upload_to='orders/pdfs/', null=True, blank=True)
    acceptance_pdf = models.FileField(_("注文請書PDF"), upload_to='acceptances/pdfs/', null=True, blank=True)

    # 外部連携
    external_signature_id = models.CharField(_("外部署名ID"), max_length=100, blank=True, null=True)

    def save(self, *args, **kwargs):
        if not self.order_id:
            today_str = datetime.date.today().strftime('%Y%m%d')
            prefix = f"MP{today_str}"
            last_order = Order.objects.filter(order_id__startswith=prefix).order_by('-order_id').first()
            if last_order:
                # MPYYYYMMDDXXXXXX の XXXXXX 部分をインクリメント
                try:
                    last_num = int(last_order.order_id[-6:])
                    next_id_num = last_num + 1
                except ValueError:
                    next_id_num = 1
            else:
                next_id_num = 1
            self.order_id = f"{prefix}{str(next_id_num).zfill(6)}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.order_id} - {self.customer}"

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, verbose_name=_("商品"), null=True, blank=True)
    
    person_name = models.CharField(_("作業者氏名"), max_length=64, blank=True)
    effort = models.DecimalField(_("工数"), max_digits=3, decimal_places=2, default=1.00)
    base_fee = models.IntegerField(_("月額基本料金"), default=0)
    
    actual_hours = models.DecimalField(_("実稼働時間"), max_digits=6, decimal_places=2, default=0.00)
    time_lower_limit = models.DecimalField(_("基準時間_下限"), max_digits=5, decimal_places=2, default=140.00)
    time_upper_limit = models.DecimalField(_("基準時間_上限"), max_digits=5, decimal_places=2, default=180.00)
    shortage_rate = models.IntegerField(_("不足単価"), default=0)
    excess_rate = models.IntegerField(_("超過単価"), default=0)

    quantity = models.IntegerField(_("数量"), default=1)
    price = models.IntegerField(_("金額"), default=0, help_text=_("自動計算: (工数×基本料金) + 調整金"))

    class Meta:
        verbose_name = _("注文明細")
        verbose_name_plural = _("注文明細")

    def save(self, *args, **kwargs):
        # 調整金の計算
        adjustment = 0
        if self.actual_hours > 0:
            if self.actual_hours < self.time_lower_limit:
                shortage_hours = self.time_lower_limit - self.actual_hours
                adjustment = -int(shortage_hours * self.shortage_rate)
            elif self.actual_hours > self.time_upper_limit:
                excess_hours = self.actual_hours - self.time_upper_limit
                adjustment = int(excess_hours * self.excess_rate)
        
        # 合計金額の計算 (工数 * 基本料金 + 調整金)
        self.price = int(self.effort * self.base_fee) + adjustment
        super().save(*args, **kwargs)

    def __str__(self):
        name = self.person_name or (self.product.name if self.product else _("明細"))
        return f"{self.order.order_id} - {name}"

class Person(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='persons')
    role = models.CharField(_("役割"), max_length=50, help_text="委託責任者、指揮命令者など")
    name = models.CharField(_("氏名"), max_length=50)
    contact = models.CharField(_("連絡先"), max_length=100, blank=True)

    class Meta:
        verbose_name = _("担当者")
        verbose_name_plural = _("担当者")

    def __str__(self):
        return f"{self.name} ({self.role})"
