"""
payroll 権限モデル

給与情報のアクセス制御。
- 社員は自分の給与のみ閲覧可能
- 社長（管理者）は全社員の給与を閲覧可能
- 権限は管理画面から編集可能
"""
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _


class PayrollPermission(models.Model):
    """給与閲覧権限"""
    PERMISSION_CHOICES = [
        ('SELF_ONLY', _('自分のみ')),
        ('ALL', _('全社員')),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name=_("ユーザー"),
        related_name='payroll_permission')
    permission_level = models.CharField(
        _("権限レベル"), max_length=10,
        choices=PERMISSION_CHOICES, default='SELF_ONLY')
    employee = models.ForeignKey(
        'payroll.Employee',
        on_delete=models.SET_NULL,
        verbose_name=_("紐付き社員"),
        null=True, blank=True,
        help_text=_("このユーザーに紐付く社員レコード"))
    can_calculate = models.BooleanField(
        _("計算実行権限"), default=False,
        help_text=_("給与計算を実行できるか"))
    can_approve = models.BooleanField(
        _("承認権限"), default=False,
        help_text=_("給与を確認済みにできるか"))
    can_transfer = models.BooleanField(
        _("振込実行権限"), default=False,
        help_text=_("振込を実行できるか"))

    class Meta:
        verbose_name = _("給与権限")
        verbose_name_plural = _("給与権限")

    def __str__(self):
        return f"{self.user.username} - {self.get_permission_level_display()}"
