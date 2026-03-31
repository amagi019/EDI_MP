
# ドメイン層（エンティティ定義）
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _


class Customer(models.Model):
    """取引先（我が社に注文を出す会社）"""
    name = models.CharField(_("会社名"), max_length=128)
    postal_code = models.CharField(_("郵便番号"), max_length=10, blank=True)
    address = models.CharField(_("住所"), max_length=255, blank=True)
    tel = models.CharField(_("電話番号"), max_length=20, blank=True)
    email = models.EmailField(_("メールアドレス"), blank=True)
    representative_title = models.CharField(_("代表者役職"), max_length=64, default="代表取締役", blank=True)
    representative_name = models.CharField(_("代表者名"), max_length=64, blank=True)
    registration_no = models.CharField(_("登録番号"), max_length=20, blank=True, help_text=_("T13桁の番号"))
    url = models.URLField(_("URL"), max_length=200, blank=True)
    has_edi = models.BooleanField(
        _("EDI保有"), default=False,
        help_text=_("EDIを保有している取引先は請求書の送付が不要")
    )

    class Meta:
        db_table = 'core_client'
        verbose_name = _("取引先")
        verbose_name_plural = _("取引先")

    def __str__(self):
        return self.name

    @property
    def needs_invoice(self):
        """請求書の作成・送付が必要かどうか"""
        return not self.has_edi


class Partner(models.Model):
    """パートナー（我が社が注文を出す会社）"""
    partner_id = models.CharField(max_length=32, primary_key=True)
    name = models.CharField(_("会社名"), max_length=128)
    name_kana = models.CharField(_("会社名（フリガナ）"), max_length=255, blank=True)
    postal_code = models.CharField(_("郵便番号"), max_length=10, blank=True)
    address = models.CharField(_("住所"), max_length=255, blank=True)
    tel = models.CharField(_("電話番号"), max_length=20, blank=True)
    fax = models.CharField(_("FAX番号"), max_length=20, blank=True)
    email = models.EmailField(_("メールアドレス"))
    report_email = models.EmailField(
        _("報告用メールアドレス"), blank=True,
        help_text=_("稼働報告メールの送信元アドレス（メインアドレスと異なる場合に設定）")
    )
    cc = models.TextField(_("Cc"), blank=True, help_text=_("複数指定する場合はカンマ区切りで入力してください"))
    bcc = models.TextField(_("Bcc"), blank=True, help_text=_("複数指定する場合はカンマ区切りで入力してください"))
    
    class Meta:
        db_table = 'core_customer'
        verbose_name = _("パートナー")
        verbose_name_plural = _("パートナー")

    # 代表者・主担当情報
    representative_name = models.CharField(_("代表者名"), max_length=64, blank=True)
    representative_name_kana = models.CharField(_("代表者名（フリガナ）"), max_length=128, blank=True)
    representative_position = models.CharField(_("代表者役職"), max_length=64, blank=True)
    responsible_person = models.CharField(_("委託業務責任者"), max_length=64, blank=True)
    contact_person = models.CharField(_("連絡窓口担当者"), max_length=64, blank=True)

    # インボイス制度対応
    registration_no = models.CharField(_("登録番号"), max_length=20, blank=True, help_text=_("T13桁の番号"))

    # 自社担当者（契約承認時の通知先）
    staff_contact = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name=_("自社担当者"),
        related_name='managed_partners',
        help_text=_("契約承認時の通知メール送信先となるスタッフ"),
        limit_choices_to={'is_staff': True},
    )

    # 添付書類
    attachment_file = models.FileField(_("添付書類（決算報告書等）"), upload_to='customers/attachments/', blank=True, null=True)

    # 銀行口座情報
    bank_name = models.CharField(_("銀行名"), max_length=64, blank=True)
    bank_branch = models.CharField(_("支店名"), max_length=64, blank=True)
    account_type = models.CharField(_("口座種別"), max_length=20, default="普通", choices=[('普通', '普通'), ('当座', '当座')])
    account_number = models.CharField(_("口座番号"), max_length=20, blank=True)
    account_name = models.CharField(_("口座名義"), max_length=128, blank=True)

    def save(self, *args, **kwargs):
        if not self.partner_id:
            last_partner = Partner.objects.filter(partner_id__regex=r'^\d+$').order_by('-partner_id').first()
            if last_partner:
                next_id = int(last_partner.partner_id) + 1
            else:
                next_id = 1
            self.partner_id = str(next_id).zfill(10)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"[{self.partner_id}] {self.name}"

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('core:contract_approve', kwargs={'partner_id': self.partner_id})

class Profile(models.Model):
    """ユーザープロフィール（初回ログインフラグ管理）"""
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    partner = models.ForeignKey(Partner, on_delete=models.CASCADE, null=True, blank=True, verbose_name="パートナー")
    is_first_login = models.BooleanField(default=True)  # 初回ログインフラグ

    class Meta:
        verbose_name = _("ユーザープロフィール")
        verbose_name_plural = _("ユーザープロフィール")

    def __str__(self):
        return self.user.username

@receiver(post_delete, sender=Profile)
def delete_user_on_profile_delete(sender, instance, **kwargs):
    """Profileが削除されたとき、紐付くUserも削除する"""
    if instance.user:
        try:
            instance.user.delete()
        except User.DoesNotExist:
            pass


class CompanyInfo(models.Model):
    """自社登録情報（PDF等で使用）"""
    name = models.CharField(_("社名"), max_length=128, default="")
    postal_code = models.CharField(_("郵便番号"), max_length=10, default="")
    address = models.CharField(_("住所"), max_length=255, default="")
    tel = models.CharField(_("電話番号"), max_length=20, default="")
    fax = models.CharField(_("FAX番号"), max_length=20, blank=True)
    representative_title = models.CharField(_("代表者役職"), max_length=64, default="代表取締役")
    representative_name = models.CharField(_("代表者名"), max_length=64, default="")
    registration_no = models.CharField(_("登録番号"), max_length=20, default="")
    
    responsible_person = models.CharField(_("委託業務責任者"), max_length=64, default="")
    contact_person = models.CharField(_("連絡窓口担当者"), max_length=64, default="")
    
    # 銀行口座情報
    bank_name = models.CharField(_("銀行名"), max_length=64, blank=True)
    bank_branch = models.CharField(_("支店名"), max_length=64, blank=True)
    account_type = models.CharField(_("口座種別"), max_length=20, default="普通", choices=[('普通', '普通'), ('当座', '当座')])
    account_number = models.CharField(_("口座番号"), max_length=20, blank=True)
    account_name = models.CharField(_("口座名義"), max_length=128, blank=True)

    stamp_image = models.ImageField(_("印影画像"), upload_to='stamps/', blank=True, null=True)
    logo_image = models.ImageField(_("ロゴ画像"), upload_to='logos/', blank=True, null=True)

    # 消費税率（%表記、例: 10.00 = 10%）
    tax_rate = models.DecimalField(
        _("消費税率（%）"), max_digits=5, decimal_places=2, default=10.00,
        help_text=_("消費税率をパーセントで入力してください（例: 10.00）")
    )

    class Meta:
        verbose_name = _("自社情報")
        verbose_name_plural = _("自社情報")

    def __str__(self):
        return self.name


class BankMaster(models.Model):
    """銀行マスタ"""
    bank_code = models.CharField(_("銀行コード"), max_length=4)
    bank_name = models.CharField(_("銀行名"), max_length=128)
    branch_code = models.CharField(_("支店コード"), max_length=3)
    branch_name = models.CharField(_("支店名"), max_length=128)

    class Meta:
        verbose_name = _("銀行マスタ")
        verbose_name_plural = _("銀行マスタ")
        unique_together = ('bank_code', 'branch_code')

    def __str__(self):
        return f"{self.bank_name} ({self.branch_name})"


class SentEmailLog(models.Model):
    """送信済みメールログ"""
    partner = models.ForeignKey(Partner, on_delete=models.CASCADE, verbose_name=_("パートナー"), related_name="email_logs")
    subject = models.CharField(_("件名"), max_length=255)
    body = models.TextField(_("本文"))
    recipient = models.EmailField(_("送信先"), blank=True, help_text=_("送信先メールアドレス"))
    sent_at = models.DateTimeField(_("送信日時"), auto_now_add=True)

    class Meta:
        verbose_name = _("メール送信ログ")
        verbose_name_plural = _("メール送信ログ")
        ordering = ['-sent_at']

    def __str__(self):
        return f"{self.partner.name} - {self.subject} ({self.sent_at})"


class MasterContractProgress(models.Model):
    """基本契約進捗状況"""
    STATUS_CHOICES = [
        ('INVITED', '招待済み'),
        ('INFO_DONE', '基本情報登録済み'),
        ('CONTRACT_SENT', '基本契約送信済み'),
        ('PENDING_APPROVAL', '承諾待ち'),
        ('COMPLETED', '締結完了'),
    ]

    partner = models.OneToOneField(Partner, on_delete=models.CASCADE, verbose_name=_("パートナー"), related_name="contract_progress", unique=True)
    status = models.CharField(_("ステータス"), max_length=20, choices=STATUS_CHOICES, default='INVITED')
    updated_at = models.DateTimeField(_("更新日時"), auto_now=True)

    # 基本契約書PDF関連
    contract_pdf = models.FileField(_("契約書PDF"), upload_to='contracts/', blank=True, null=True)
    pdf_hash = models.CharField(_("PDFハッシュ"), max_length=64, blank=True, help_text=_("SHA256ハッシュ値（電帳法対応）"))
    sent_at = models.DateTimeField(_("契約書送信日時"), blank=True, null=True)
    signed_at = models.DateTimeField(_("承認日時"), blank=True, null=True)
    signed_by = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True, verbose_name=_("承認者"))

    class Meta:
        verbose_name = _("基本契約進捗")
        verbose_name_plural = _("基本契約進捗")

    def __str__(self):
        return f"{self.partner.name}: {self.get_status_display()}"

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('core:contract_progress_list')


class EmailTemplate(models.Model):
    """メールテンプレート"""
    code = models.CharField(_("テンプレートコード"), max_length=50, unique=True, help_text=_("システム内で識別するためのコード"))
    subject = models.CharField(_("件名"), max_length=255)
    body = models.TextField(_("本文"), help_text=_("Djangoテンプレート構文が使用可能です。例: {{ partner_name }}"))
    description = models.CharField(_("説明"), max_length=255, blank=True)
    updated_at = models.DateTimeField(_("更新日時"), auto_now=True)

    class Meta:
        verbose_name = _("メールテンプレート")
        verbose_name_plural = _("メールテンプレート")

    def __str__(self):
        return f"{self.subject} ({self.code})"
