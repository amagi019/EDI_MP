import datetime
from django.db import models
from django.utils.translation import gettext_lazy as _


class MonthlyTask(models.Model):
    """
    月次ルーチンタスク（注文書・作業報告・請求書の期限管理）

    Order / Invoice モデルに依存しない独立モデル。
    Partner / Project への直接参照のみ。
    """
    TASK_TYPES = [
        ('ORDER_CREATE', _('注文書作成')),
        ('ORDER_APPROVE', _('注文書承認')),
        ('REPORT_UPLOAD', _('作業報告書アップロード')),
        ('INVOICE_CREATE', _('請求書作成')),
        ('INVOICE_APPROVE', _('請求書承認')),
    ]
    STATUS_CHOICES = [
        ('PENDING', _('未着手')),
        ('DONE', _('完了')),
        ('OVERDUE', _('期限超過')),
    ]
    RESPONSIBLE_CHOICES = [
        ('STAFF', _('自社')),
        ('PARTNER', _('パートナー')),
    ]

    # ── 対象の特定（Order/Invoiceに依存しない） ──
    partner = models.ForeignKey(
        'core.Partner', on_delete=models.CASCADE,
        verbose_name=_("パートナー"), related_name='monthly_tasks'
    )
    project = models.ForeignKey(
        'orders.Project', on_delete=models.CASCADE,
        verbose_name=_("プロジェクト"), related_name='monthly_tasks'
    )
    work_month = models.DateField(
        _("作業対象月"), help_text="YYYY-MM-01形式"
    )

    # ── タスク情報 ──
    task_type = models.CharField(
        _("タスク種別"), max_length=20, choices=TASK_TYPES
    )
    responsible = models.CharField(
        _("担当区分"), max_length=10, choices=RESPONSIBLE_CHOICES, default='STAFF'
    )
    deadline = models.DateField(_("期限日"))
    status = models.CharField(
        _("ステータス"), max_length=10, choices=STATUS_CHOICES, default='PENDING'
    )
    completed_at = models.DateTimeField(_("完了日時"), null=True, blank=True)

    # ── メモ・参照（汎用、FKなし） ──
    note = models.TextField(_("メモ"), blank=True, help_text="完了時の備考や関連情報")

    # ── 通知管理 ──
    reminder_sent = models.BooleanField(_("リマインド送信済み"), default=False)
    alert_sent = models.BooleanField(_("アラート送信済み"), default=False)
    deadline_notified = models.BooleanField(_("期限到来通知済み"), default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("月次タスク")
        verbose_name_plural = _("月次タスク")
        unique_together = ('partner', 'project', 'work_month', 'task_type')
        ordering = ['deadline', 'task_type']

    def __str__(self):
        return f"{self.partner.name} {self.work_month.strftime('%Y/%m')} {self.get_task_type_display()}"

    @property
    def is_overdue(self):
        """期限超過かどうか"""
        return self.status == 'PENDING' and self.deadline < datetime.date.today()

    @property
    def days_until_deadline(self):
        """期限までの日数（負の値は超過）"""
        return (self.deadline - datetime.date.today()).days
