"""
給与計算の会社設定

支給日、締め日、割増率などの全社共通設定を管理する。
"""
from django.db import models
from django.utils.translation import gettext_lazy as _


class PayrollSettings(models.Model):
    """給与計算の全社設定（シングルトン）"""
    PAYMENT_DAY_CHOICES = [
        (0, _('月末')),
        (25, _('25日')),
        (20, _('20日')),
        (15, _('15日')),
        (10, _('10日')),
    ]
    CLOSING_DAY_CHOICES = [
        (0, _('月末')),
        (25, _('25日')),
        (20, _('20日')),
        (15, _('15日')),
    ]

    # 支給・締め
    payment_day = models.IntegerField(
        _("支給日"), choices=PAYMENT_DAY_CHOICES, default=0,
        help_text=_("0=月末、その他=指定日"))
    closing_day = models.IntegerField(
        _("締め日"), choices=CLOSING_DAY_CHOICES, default=0,
        help_text=_("0=月末締め"))

    # 残業割増率
    overtime_rate_multiplier = models.DecimalField(
        _("残業割増率"), max_digits=4, decimal_places=2,
        default=1.25,
        help_text=_("法定: 1.25"))
    overtime_60_rate_multiplier = models.DecimalField(
        _("60h超残業割増率"), max_digits=4, decimal_places=2,
        default=1.50,
        help_text=_("法定: 1.50"))
    night_rate_multiplier = models.DecimalField(
        _("深夜割増率"), max_digits=4, decimal_places=2,
        default=0.25,
        help_text=_("法定: 0.25（基本給に加算）"))
    holiday_rate_multiplier = models.DecimalField(
        _("休日出勤割増率"), max_digits=4, decimal_places=2,
        default=1.35,
        help_text=_("法定: 1.35"))

    # デフォルト値
    default_work_days = models.IntegerField(
        _("デフォルト出勤日数"), default=20,
        help_text=_("勤怠データなし時に使用"))
    default_monthly_hours = models.DecimalField(
        _("デフォルト所定時間"), max_digits=5,
        decimal_places=1, default=160.0,
        help_text=_("社員個別設定がない場合に使用"))

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("給与設定")
        verbose_name_plural = _("給与設定")

    def __str__(self):
        day = "月末" if self.payment_day == 0 else f"{self.payment_day}日"
        return f"給与設定（支給日: {day}）"

    def save(self, *args, **kwargs):
        # シングルトンパターン: 常にpk=1
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        """設定を取得。未作成なら作成。"""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
