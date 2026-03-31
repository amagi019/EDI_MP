"""
社員同期キャッシュモデル

PayrollSystem（社員マスタの正）からAPI経由で同期した社員データのキャッシュ。
EDI側で勤怠登録時にドロップダウン選択などに使用する。
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone


class SyncedEmployee(models.Model):
    """PayrollSystemから同期された社員データ（キャッシュ）"""
    employee_id = models.CharField(
        _("社員番号"), max_length=20, unique=True,
        help_text=_("PayrollSystemの社員番号と一致"))
    name = models.CharField(_("氏名"), max_length=64)
    name_kana = models.CharField(_("フリガナ"), max_length=128, blank=True)
    is_active = models.BooleanField(_("在籍"), default=True)
    synced_at = models.DateTimeField(
        _("最終同期日時"), default=timezone.now)

    class Meta:
        verbose_name = _("同期社員")
        verbose_name_plural = _("同期社員")
        ordering = ['employee_id']

    def __str__(self):
        return f"{self.employee_id} {self.name}"
