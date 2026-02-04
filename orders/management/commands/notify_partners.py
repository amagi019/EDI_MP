import datetime
from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
from core.domain.models import CompanyInfo, Customer
from orders.models import Order

class Command(BaseCommand):
    help = 'パートナーへ注文書発行の通知メールを一括送信する'

    def handle(self, *args, **options):
        # 本来は前月末に実行する想定
        # 実行時点から見た「来月」の注文を対象とするか、あるいは未送信のものを対象とするか
        # ここでは、ステータスが UNCONFIRMED の最近の注文を対象とする簡易実装とする
        
        company = CompanyInfo.objects.first()
        company_name = company.name if company else "有限会社 マックプランニング"
        
        # サイトのURL（環境に合わせて設定が必要）
        site_url = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000')

        # 締切日の計算（例：翌月15日）
        next_month = datetime.date.today().replace(day=28) + datetime.timedelta(days=4)
        deadline = next_month.replace(day=15)
        deadline_str = deadline.strftime('%m月%d日')

        # 未通知の注文を取得（通知済みフラグがないので、UNCONFIRMEDのものを対象）
        orders = Order.objects.filter(status='UNCONFIRMED')
        
        sent_count = 0
        for order in orders:
            customer = order.customer
            if not customer.email:
                self.stdout.write(self.style.WARNING(f"Skip: {customer.name} has no email."))
                continue

            url = f"{site_url}{reverse('orders:order_detail', args=[order.order_id])}"

            subject = f"注文書発行のお知らせ（{company_name}）"
            body = f"""{customer.name} 御中

いつもお世話になっております。
{company_name}でございます。

EDIに注文書を登録しましたので、
下記ＵＲＬからユーザＩＤ／パスワードを用いてログインし、
注文書詳細画面から「注文書印刷」ボタンを押下して、
注文書ファイル（ＰＤＦ）のダウンロードを行って下さい。
ダウンロードした注文書は、御社サーバ上に必ず保管して下さい。

《URL》
{url}

《送付物》

「注文書」
「注文請書」
  各1通


《お願い》

注文書内容をご確認いただき、内容にご同意いただける場合は「承認」ボタンを押してください。
承認いただけない場合はメールに記載し御返信ください。

締切：{deadline_str}

※尚、「承認」をいただいた場合は、注文請書のご返送は不要となります。


以上、よろしくお願いします。
"""
            try:
                send_mail(
                    subject,
                    body,
                    settings.DEFAULT_FROM_EMAIL,
                    [customer.email],
                    fail_silently=False,
                )
                sent_count += 1
                self.stdout.write(self.style.SUCCESS(f"Sent to: {customer.email}"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Failed to send to {customer.email}: {e}"))

        self.stdout.write(self.style.SUCCESS(f"Successfully sent {sent_count} emails."))
