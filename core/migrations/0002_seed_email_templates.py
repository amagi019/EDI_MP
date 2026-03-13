from django.db import migrations


def seed_email_templates(apps, schema_editor):
    EmailTemplate = apps.get_model('core', 'EmailTemplate')

    templates = [
        {
            'code': 'partner_invitation',
            'description': '① アカウント発行メール（自社→パートナー）',
            'subject': '【{{ company_name }}】EDIシステム アカウント発行のご案内',
            'body': """{{ company_name }}
{{ partner_name }} 様

EDIシステムをご案内いたします。

この度、弊社との取引に関連して、EDIシステムのアカウントを発行いたしました。
本システムでは、注文書の確認、および会社情報の登録を行っていただけます。

以下の情報を使用してログインし、まず初めに「基本情報登録」をお願いいたします。

■ ログイン情報
ログインURL: {{ login_url }}
ログインID: {{ email }}
仮パスワード: {{ password }}

■ 初回ログイン後の流れ
1. 仮パスワードでログインしてください。
2. 自動的にパスワード変更画面が表示されますので、新しいパスワードを設定してください。
3. ダッシュボードの「会社情報を登録・更新する」より、貴社の基本情報および振込先情報の入力をお願いいたします。

本メールに心当たりがない場合は、お手数ですが破棄していただくか、弊社窓口までご連絡ください。

--------------------------------------------------
{{ company_name }}
{{ company_address }}
TEL: {{ company_tel }}
--------------------------------------------------
""",
        },
        {
            'code': 'partner_info_registered',
            'description': '② 基本情報登録通知メール（パートナー→自社）',
            'subject': '【基本情報登録完了】{{ partner_name }}',
            'body': """{{ partner_name }} 様がパートナー基本情報の登録を完了しました。

以下の内容をご確認いただき、基本契約書の作成・送付をお願いいたします。

《登録情報》
■ 会社名：{{ partner_name }}
■ 住所：{{ address }}
■ 代表者：{{ representative_name }}
■ 登録番号：{{ registration_no }}

《次のステップ》
1. 下記URLより登録内容を確認してください。
2. 問題なければ基本契約書を作成し、パートナーへ送付してください。

■ 基本契約進捗の確認:
{{ progress_url }}
""",
        },
        {
            'code': 'contract_send',
            'description': '③ 契約書承認依頼メール（自社→パートナー）',
            'subject': '【{{ company_name }}】基本契約書のご確認（{{ partner_name }}様）',
            'body': """{{ partner_name }}　御中

いつもお世話になっております。
{{ company_name }}でございます。

この度、基本契約書を作成いたしましたので、
下記ＵＲＬよりご確認をお願いいたします。

《URL》
{{ contract_url }}

《送付物》
「基本契約書」
  1通

《お願い》
契約書内容をご確認いただき、内容にご同意いただける場合は
「承認」ボタンを押してください。
承認いただけない場合はメールにてご返信ください。

※「承認」をいただいた場合は、従来のように契約書のご返送は不要となります。

御手数ではございますが、ご協力の程お願い申し上げます。

《ご参考》
承認済みの契約書は、ログイン後サイドバーの「基本契約書」からいつでもご確認いただけます。

操作手順について不明な点がございましたら
サイドバーの「操作マニュアル」をご参照ください。

以上、よろしくお願いいたします。

--------------------------------------------------
{{ company_name }}
TEL: {{ company_tel }}
--------------------------------------------------
""",
        },
        {
            'code': 'contract_approve',
            'description': '④ 契約書承認メール（パートナー→自社）',
            'subject': '【基本契約承認通知】{{ partner_name }}',
            'body': """{{ partner_name }} 様が基本契約書を承認しました。
契約が締結されましたのでお知らせいたします。

■ パートナー名：{{ partner_name }}
■ 承認日時：{{ signed_at }}
■ 承認者：{{ signed_by }}

■ 契約書確認URL:
{{ contract_url }}

※承認済みの契約書PDFは上記URLよりご確認いただけます。
""",
        },
        {
            'code': 'order_publish',
            'description': '⑤ 注文書送付メール（自社→パートナー）',
            'subject': '【{{ company_name }}】注文書送付のご連絡（注文番号：{{ order_id }}）',
            'body': """いつもお世話になっております。
{{ company_name }}でございます。

EDIシステムに注文書を登録いたしましたので、
下記URLよりログインし、注文書の内容をご確認ください。

《URL》
{{ order_url }}

《送付物》

「注文書」
「注文請書」
  各1通

《お願い》

注文書内容をご確認いただき、内容にご同意いただける場合は
「承認」ボタンを押してください。
承認いただけない場合はメールにてご返信ください。

※「承認」をいただいた場合は、注文請書のご返送は不要となります。

■注文番号：{{ order_id }}
■プロジェクト：{{ project_name }}
■注文日：{{ order_date }}
■作業期間：{{ work_start }} 〜 {{ work_end }}

▼ログインURL
{{ login_url }}

操作手順について不明な点がございましたら、
ダッシュボードの「操作マニュアル」をご参照ください。

以上、よろしくお願いいたします。

--------------------------------------------------
{{ company_name }}
TEL: {{ company_tel }}
--------------------------------------------------
""",
        },
        {
            'code': 'order_approve',
            'description': '⑥ 注文書承認メール（パートナー→自社）',
            'subject': '【承認通知】{{ partner_name }}様 注文番号：{{ order_id }}',
            'body': """{{ partner_name }} 様より、以下の注文書が承認されました。

■注文番号：{{ order_id }}
■プロジェクト：{{ project_name }}
■注文日：{{ order_date }}

■ 注文書確認URL:
{{ order_url }}
""",
        },
        {
            'code': 'invoice_send',
            'description': '⑦ 支払通知・請求書送付メール（自社→パートナー）',
            'subject': '【{{ company_name }}】支払通知書送付（請求番号：{{ invoice_no }}）',
            'body': """{{ partner_name }}　御中

いつもお世話になっております。
{{ company_name }}でございます。

EDIシステムに支払通知書を登録しましたので、
下記ＵＲＬからログインし、内容をご確認ください。

《URL》
{{ invoice_url }}

《送付物》
「支払通知書」
「請求書」
  各1通

《お願い》
請求書内容をご確認いただき、内容にご同意いただける場合は「承認する」ボタンを押してください。
承認いただけない場合はメールにてご返信ください。

   対象月：{{ target_month }}
   税込合計：¥{{ total_amount }}-

※尚、「承認」をいただいた場合は、従来のように請求書のご返送は不要となります。

御手数ではございますが、ご協力の程お願い申し上げます。

▼ログインURL
{{ login_url }}

操作手順について不明な点がございましたら
サイドバーの「操作マニュアル」をご参照ください。

以上、よろしくお願いいたします。

--------------------------------------------------
{{ company_name }}
TEL: {{ company_tel }}
--------------------------------------------------
""",
        },
        {
            'code': 'invoice_approve',
            'description': '⑧ 請求書承認メール（パートナー→自社）',
            'subject': '【請求書承認通知】請求番号：{{ invoice_no }}',
            'body': """{{ partner_name }} 様より、以下の請求書（支払通知書）が承認されました。

■請求番号：{{ invoice_no }}
■対象年月：{{ target_month }}
■税込合計：¥{{ total_amount }}-

■ 請求書確認URL:
{{ invoice_url }}
""",
        },
    ]

    for tmpl in templates:
        EmailTemplate.objects.get_or_create(
            code=tmpl['code'],
            defaults={
                'description': tmpl['description'],
                'subject': tmpl['subject'],
                'body': tmpl['body'],
            }
        )


def reverse_seed(apps, schema_editor):
    EmailTemplate = apps.get_model('core', 'EmailTemplate')
    EmailTemplate.objects.filter(
        code__in=[
            'partner_invitation', 'partner_info_registered',
            'contract_send', 'contract_approve',
            'order_publish', 'order_approve',
            'invoice_send', 'invoice_approve',
        ]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_email_templates, reverse_seed),
    ]
