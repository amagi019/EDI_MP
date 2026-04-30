"""
payroll ドメインモデル

給与計算自動化のためのマスタデータと計算結果モデル。
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
import datetime
import math


class Employee(models.Model):
    """社員マスタ"""
    employee_id = models.CharField(_("社員番号"), max_length=20, unique=True)
    name = models.CharField(_("氏名"), max_length=64)
    name_kana = models.CharField(_("フリガナ"), max_length=128, blank=True)
    birth_date = models.DateField(_("生年月日"), null=True, blank=True)
    hire_date = models.DateField(_("入社日"), null=True, blank=True)
    email = models.EmailField(_("メールアドレス"), blank=True)
    phone = models.CharField(_("電話番号"), max_length=20, blank=True)

    # 住所
    postal_code = models.CharField(
        _("郵便番号"), max_length=10, blank=True)
    address_1 = models.CharField(
        _("住所1"), max_length=200, blank=True,
        help_text=_("都道府県・市区町村・番地"))
    address_2 = models.CharField(
        _("住所2"), max_length=200, blank=True,
        help_text=_("建物名・部屋番号"))
    # 給与
    base_salary = models.IntegerField(_("基本給"), default=0)
    position_allowance = models.IntegerField(_("役職手当"), default=0)
    housing_allowance = models.IntegerField(_("住宅手当"), default=0)
    commuting_allowance = models.IntegerField(
        _("通勤手当"), default=0,
        help_text=_("非課税"))
    standard_monthly_hours = models.DecimalField(
        _("所定労働時間"), max_digits=5, decimal_places=1, default=180.0)

    # 社会保険
    insurance_start_date = models.DateField(
        _("社会保険加入日"), null=True, blank=True)
    # 税・保険
    dependents_count = models.IntegerField(_("扶養家族人数"), default=0)
    is_tax_exempt = models.BooleanField(_("非課税所得者"), default=False)
    pension_enrolled = models.BooleanField(_("厚生年金加入"), default=True)
    health_enrolled = models.BooleanField(_("健康保険加入"), default=True)
    nursing_enrolled = models.BooleanField(
        _("介護保険加入"), default=False,
        help_text=_("40〜64歳が対象"))
    employment_enrolled = models.BooleanField(_("雇用保険加入"), default=True)

    # 標準報酬月額（算定基礎届で年1回決定、9月〜翌8月適用）
    standard_remuneration = models.IntegerField(
        _("標準報酬月額"), default=0,
        help_text=_("算定基礎届で決定された金額"))

    is_active = models.BooleanField(_("在籍"), default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("社員")
        verbose_name_plural = _("社員")
        ordering = ['employee_id']

    def __str__(self):
        return f"{self.employee_id} {self.name}"

    @property
    def fixed_salary(self):
        """固定給合計（基本給+役職手当+住宅手当）"""
        return self.base_salary + self.position_allowance + self.housing_allowance


class EmployeeBankAccount(models.Model):
    """振込先マスタ"""
    ACCOUNT_TYPE_CHOICES = [
        ('ordinary', _('普通')),
        ('current', _('当座')),
        ('savings', _('貯蓄')),
    ]
    employee = models.OneToOneField(
        Employee, on_delete=models.CASCADE,
        verbose_name=_("社員"), related_name='bank_account')
    bank_name = models.CharField(_("銀行名"), max_length=64)
    branch_name = models.CharField(_("支店名"), max_length=64)
    branch_code = models.CharField(_("店番"), max_length=10, blank=True)
    account_type = models.CharField(
        _("口座種別"), max_length=10,
        choices=ACCOUNT_TYPE_CHOICES, default='ordinary')
    account_number = models.CharField(_("口座番号"), max_length=20)
    account_holder_kana = models.CharField(
        _("口座名義（カナ）"), max_length=128)

    class Meta:
        verbose_name = _("振込先")
        verbose_name_plural = _("振込先")

    def __str__(self):
        return f"{self.employee.name} - {self.bank_name} {self.branch_name}"


class InsuranceRate(models.Model):
    """保険料率マスタ（年度ごと）"""
    fiscal_year = models.IntegerField(_("適用年度"), unique=True)
    pension_rate = models.DecimalField(
        _("厚生年金保険料率(%)"), max_digits=5, decimal_places=2,
        default=18.30,
        help_text=_("労使合計。従業員負担は半額"))
    health_rate = models.DecimalField(
        _("健康保険料率(%)"), max_digits=5, decimal_places=2,
        default=9.98,
        help_text=_("協会けんぽ。都道府県で異なる"))
    nursing_rate = models.DecimalField(
        _("介護保険料率(%)"), max_digits=5, decimal_places=2,
        default=1.60)
    employment_rate_employee = models.DecimalField(
        _("雇用保険料率・従業員(%)"), max_digits=5,
        decimal_places=3, default=0.600,
        help_text=_("折半しない。この率が従業員負担"))
    employment_rate_employer = models.DecimalField(
        _("雇用保険料率・事業主(%)"), max_digits=5,
        decimal_places=3, default=0.950)
    prefecture = models.CharField(
        _("都道府県"), max_length=10, default="東京都")

    class Meta:
        verbose_name = _("保険料率")
        verbose_name_plural = _("保険料率")
        ordering = ['-fiscal_year']

    def __str__(self):
        return f"{self.fiscal_year}年度 保険料率"


class WithholdingTaxRow(models.Model):
    """源泉徴収税額表（月額表・甲欄）の1行"""
    fiscal_year = models.IntegerField(_("適用年度"))
    salary_from = models.IntegerField(_("給与範囲（以上）"))
    salary_to = models.IntegerField(
        _("給与範囲（未満）"),
        help_text=_("最大行は999999999"))
    tax_dep_0 = models.IntegerField(_("扶養0人"), default=0)
    tax_dep_1 = models.IntegerField(_("扶養1人"), default=0)
    tax_dep_2 = models.IntegerField(_("扶養2人"), default=0)
    tax_dep_3 = models.IntegerField(_("扶養3人"), default=0)
    tax_dep_4 = models.IntegerField(_("扶養4人"), default=0)
    tax_dep_5 = models.IntegerField(_("扶養5人"), default=0)
    tax_dep_6 = models.IntegerField(_("扶養6人"), default=0)
    tax_dep_7 = models.IntegerField(_("扶養7人"), default=0)

    class Meta:
        verbose_name = _("源泉徴収税額")
        verbose_name_plural = _("源泉徴収税額表")
        ordering = ['fiscal_year', 'salary_from']
        indexes = [
            models.Index(fields=['fiscal_year', 'salary_from']),
        ]

    def __str__(self):
        return f"{self.fiscal_year}年 {self.salary_from:,}〜{self.salary_to:,}円"


class ResidentTaxSchedule(models.Model):
    """住民税特別徴収スケジュール（6月〜翌5月）"""
    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE,
        verbose_name=_("社員"),
        related_name='resident_tax_schedules')
    fiscal_year = models.IntegerField(
        _("年度"),
        help_text=_("住民税の年度（6月〜翌5月）"))
    municipality = models.CharField(
        _("市区町村"), max_length=64, blank=True)
    month_06 = models.IntegerField(_("6月"), default=0)
    month_07 = models.IntegerField(_("7月"), default=0)
    month_08 = models.IntegerField(_("8月"), default=0)
    month_09 = models.IntegerField(_("9月"), default=0)
    month_10 = models.IntegerField(_("10月"), default=0)
    month_11 = models.IntegerField(_("11月"), default=0)
    month_12 = models.IntegerField(_("12月"), default=0)
    month_01 = models.IntegerField(_("1月"), default=0)
    month_02 = models.IntegerField(_("2月"), default=0)
    month_03 = models.IntegerField(_("3月"), default=0)
    month_04 = models.IntegerField(_("4月"), default=0)
    month_05 = models.IntegerField(_("5月"), default=0)

    class Meta:
        verbose_name = _("住民税スケジュール")
        verbose_name_plural = _("住民税スケジュール")
        unique_together = ['employee', 'fiscal_year']

    def __str__(self):
        return f"{self.employee.name} {self.fiscal_year}年度 住民税"

    def get_amount_for_month(self, month):
        """指定月（1-12）の住民税額を返す"""
        field_map = {
            1: self.month_01, 2: self.month_02,
            3: self.month_03, 4: self.month_04,
            5: self.month_05, 6: self.month_06,
            7: self.month_07, 8: self.month_08,
            9: self.month_09, 10: self.month_10,
            11: self.month_11, 12: self.month_12,
        }
        return field_map.get(month, 0)


class Payroll(models.Model):
    """給与計算結果"""
    STATUS_CHOICES = [
        ('DRAFT', _('下書き')),
        ('CONFIRMED', _('確認済')),
        ('PAID', _('振込済')),
    ]
    TRANSFER_STATUS_CHOICES = [
        ('PENDING', _('未振込')),
        ('PROCESSING', _('処理中')),
        ('COMPLETED', _('完了')),
        ('FAILED', _('失敗')),
    ]

    employee = models.ForeignKey(
        Employee, on_delete=models.PROTECT,
        verbose_name=_("社員"), related_name='payrolls')
    year_month = models.DateField(
        _("対象年月"),
        help_text=_("YYYY-MM-01形式"))
    timesheet = models.ForeignKey(
        'billing.MonthlyTimesheet', on_delete=models.SET_NULL,
        verbose_name=_("勤怠報告"), null=True, blank=True)
    status = models.CharField(
        _("ステータス"), max_length=10,
        choices=STATUS_CHOICES, default='DRAFT')

    # === 勤怠実績 ===
    work_days = models.IntegerField(_("出勤日数"), default=0)
    total_hours = models.DecimalField(
        _("総労働時間"), max_digits=6, decimal_places=2, default=0)
    overtime_hours = models.DecimalField(
        _("残業時間"), max_digits=6, decimal_places=2, default=0)
    overtime_60_hours = models.DecimalField(
        _("60h超残業"), max_digits=6, decimal_places=2, default=0)
    night_hours = models.DecimalField(
        _("深夜時間"), max_digits=6, decimal_places=2, default=0)
    holiday_hours = models.DecimalField(
        _("休日出勤時間"), max_digits=6, decimal_places=2, default=0)
    absence_days = models.IntegerField(_("欠勤日数"), default=0)
    paid_leave_days = models.IntegerField(_("有給日数"), default=0)
    payment_date = models.DateField(
        _("支給日"), null=True, blank=True,
        help_text=_("給与支給日"))

    # === 支給 ===
    base_salary = models.IntegerField(_("基本給"), default=0)
    position_allowance = models.IntegerField(_("役職手当"), default=0)
    housing_allowance = models.IntegerField(_("住宅手当"), default=0)
    commuting_allowance = models.IntegerField(_("通勤手当"), default=0)
    overtime_pay = models.IntegerField(_("残業手当"), default=0)
    overtime_60_pay = models.IntegerField(_("60h超手当"), default=0)
    night_pay = models.IntegerField(_("深夜手当"), default=0)
    holiday_pay = models.IntegerField(_("休日出勤手当"), default=0)
    absence_deduction = models.IntegerField(
        _("不就労控除"), default=0,
        help_text=_("マイナス値で保存"))
    taxable_total = models.IntegerField(_("課税支給合計"), default=0)
    non_taxable_total = models.IntegerField(
        _("非課税支給合計"), default=0)
    gross_pay = models.IntegerField(_("支給合計"), default=0)

    # === 控除 ===
    pension_premium = models.IntegerField(_("厚生年金"), default=0)
    health_premium = models.IntegerField(_("健康保険"), default=0)
    nursing_premium = models.IntegerField(_("介護保険"), default=0)
    employment_premium = models.IntegerField(_("雇用保険"), default=0)
    social_insurance_total = models.IntegerField(
        _("社会保険料合計"), default=0)
    income_tax = models.IntegerField(_("所得税"), default=0)
    resident_tax = models.IntegerField(_("住民税"), default=0)
    deduction_total = models.IntegerField(_("控除合計"), default=0)

    # === 最終 ===
    net_pay = models.IntegerField(_("差引支給額"), default=0)

    # === 振込 ===
    transfer_status = models.CharField(
        _("振込ステータス"), max_length=15,
        choices=TRANSFER_STATUS_CHOICES, default='PENDING')
    transfer_date = models.DateTimeField(
        _("振込実行日時"), null=True, blank=True)
    transfer_reference = models.CharField(
        _("振込参照番号"), max_length=100, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("給与")
        verbose_name_plural = _("給与")
        ordering = ['-year_month', 'employee__employee_id']
        unique_together = ['employee', 'year_month']

    def __str__(self):
        ym = self.year_month.strftime('%Y/%m')
        return f"{self.employee.name} {ym}"

    @property
    def status_badge_style(self):
        styles = {
            'PAID': 'background: rgba(16,185,129,0.15); color: #10B981;',
            'CONFIRMED': 'background: rgba(79,70,229,0.15); color: #818CF8;',
            'DRAFT': 'background: rgba(148,163,184,0.15); color: #94A3B8;',
        }
        return styles.get(self.status, styles['DRAFT'])
