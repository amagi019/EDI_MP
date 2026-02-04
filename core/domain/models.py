
# ドメイン層（エンティティ定義）
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _

class Customer(models.Model):
    """取引先（顧客）"""
    customer_id = models.CharField(max_length=32, primary_key=True)
    name = models.CharField(_("会社名"), max_length=128)
    name_kana = models.CharField(_("会社名（フリガナ）"), max_length=255, blank=True)
    postal_code = models.CharField(_("郵便番号"), max_length=10, blank=True)
    address = models.CharField(_("住所"), max_length=255, blank=True)
    tel = models.CharField(_("電話番号"), max_length=20, blank=True)
    fax = models.CharField(_("FAX番号"), max_length=20, blank=True)
    email = models.EmailField(_("メールアドレス"))
    cc = models.TextField(_("Cc"), blank=True, help_text=_("複数指定する場合はカンマ区切りで入力してください"))
    bcc = models.TextField(_("Bcc"), blank=True, help_text=_("複数指定する場合はカンマ区切りで入力してください"))
    
    # 代表者・主担当情報
    representative_name = models.CharField(_("代表者名"), max_length=64, blank=True)
    representative_name_kana = models.CharField(_("代表者名（フリガナ）"), max_length=128, blank=True)
    representative_position = models.CharField(_("代表者役職"), max_length=64, blank=True)
    responsible_person = models.CharField(_("委託業務責任者"), max_length=64, blank=True)
    contact_person = models.CharField(_("連絡窓口担当者"), max_length=64, blank=True)

    # インボイス制度対応
    registration_no = models.CharField(_("登録番号"), max_length=20, blank=True, help_text=_("T13桁の番号"))

    # 添付書類
    attachment_file = models.FileField(_("添付書類（決算報告書等）"), upload_to='customers/attachments/', blank=True, null=True)

    # 銀行口座情報
    bank_name = models.CharField(_("銀行名"), max_length=64, blank=True)
    bank_branch = models.CharField(_("支店名"), max_length=64, blank=True)
    account_type = models.CharField(_("口座種別"), max_length=20, default="普通", choices=[('普通', '普通'), ('当座', '当座')])
    account_number = models.CharField(_("口座番号"), max_length=20, blank=True)
    account_name = models.CharField(_("口座名義"), max_length=128, blank=True)

    def save(self, *args, **kwargs):
        if not self.customer_id:
            last_customer = Customer.objects.filter(customer_id__regex=r'^\d+$').order_by('-customer_id').first()
            if last_customer:
                next_id = int(last_customer.customer_id) + 1
            else:
                next_id = 1
            self.customer_id = str(next_id).zfill(10)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"[{self.customer_id}] {self.name}"

class Profile(models.Model):
    """ユーザープロフィール（初回ログインフラグ管理）"""
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, null=True, blank=True, verbose_name="取引先") # 内部ユーザーはNull可
    is_first_login = models.BooleanField(default=True)  # 初回ログインフラグ

    def __str__(self):
        return self.user.username

@receiver(post_delete, sender=Profile)
def delete_user_on_profile_delete(sender, instance, **kwargs):
    """Profileが削除されたとき（Customer削除等に連動）、紐付くUserも削除する"""
    if instance.user:
        try:
            instance.user.delete()
        except User.DoesNotExist:
            pass


class CompanyInfo(models.Model):
    """自社登録情報（PDF等で使用）"""
    name = models.CharField(_("社名"), max_length=128, default="有限会社 マックプランニング")
    postal_code = models.CharField(_("郵便番号"), max_length=10, default="116-0012")
    address = models.CharField(_("住所"), max_length=255, default="東京都荒川区東尾久8-9-14")
    tel = models.CharField(_("電話番号"), max_length=20, default="090-3043-0477")
    fax = models.CharField(_("FAX番号"), max_length=20, blank=True)
    representative_title = models.CharField(_("代表者役職"), max_length=64, default="代表取締役")
    representative_name = models.CharField(_("代表者名"), max_length=64, default="吉川 裕")
    registration_no = models.CharField(_("登録番号"), max_length=20, default="TXXXXXXXXXXXXX")
    
    responsible_person = models.CharField(_("委託業務責任者"), max_length=64, default="吉川 裕")
    contact_person = models.CharField(_("連絡窓口担当者"), max_length=64, default="吉川 裕")
    
    # 銀行口座情報
    bank_name = models.CharField(_("銀行名"), max_length=64, blank=True)
    bank_branch = models.CharField(_("支店名"), max_length=64, blank=True)
    account_type = models.CharField(_("口座種別"), max_length=20, default="普通", choices=[('普通', '普通'), ('当座', '当座')])
    account_number = models.CharField(_("口座番号"), max_length=20, blank=True)
    account_name = models.CharField(_("口座名義"), max_length=128, blank=True)

    stamp_image = models.ImageField(_("印影画像"), upload_to='stamps/', blank=True, null=True)
    logo_image = models.ImageField(_("ロゴ画像"), upload_to='logos/', blank=True, null=True)

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
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, verbose_name=_("取引先"), related_name="email_logs")
    subject = models.CharField(_("件名"), max_length=255)
    body = models.TextField(_("本文"))
    sent_at = models.DateTimeField(_("送信日時"), auto_now_add=True)

    class Meta:
        verbose_name = _("メール送信ログ")
        verbose_name_plural = _("メール送信ログ")
        ordering = ['-sent_at']

    def __str__(self):
        return f"{self.customer.name} - {self.subject} ({self.sent_at})"


class MasterContractProgress(models.Model):
    """基本契約進捗状況"""
    STATUS_CHOICES = [
        ('INVITED', '招待済み'),
        ('INFO_DONE', '基本情報登録済み'),
        ('CONTRACT_SENT', '基本契約送信済み'),
        ('COMPLETED', '締結完了'),
    ]

    customer = models.OneToOneField(Customer, on_delete=models.CASCADE, verbose_name=_("取引先"), related_name="contract_progress", unique=True)
    status = models.CharField(_("ステータス"), max_length=20, choices=STATUS_CHOICES, default='INVITED')
    updated_at = models.DateTimeField(_("更新日時"), auto_now=True)

    class Meta:
        verbose_name = _("基本契約進捗")
        verbose_name_plural = _("基本契約進捗")

    def __str__(self):
        return f"{self.customer.name}: {self.get_status_display()}"
