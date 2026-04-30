"""
作業報告書 一括送付サービス

受注（ReceivedOrder）に紐づく全作業者の稼働報告書（Excel + PDF）を
クライアント担当者にメール送信する。
"""
import logging
from django.core.mail import EmailMessage
from django.conf import settings
from django.core.files.storage import default_storage

logger = logging.getLogger(__name__)


def send_report_email(received_order):
    """
    受注に紐づく全MonthlyTimesheetのExcel+PDFをクライアントへメール送信する。

    Args:
        received_order: ReceivedOrder インスタンス

    Returns:
        dict: {'success': bool, 'message': str, 'sent_count': int}
    """
    from billing.domain.models import MonthlyTimesheet
    from billing.application.services.mail_service import parse_email_list
    from core.utils import normalize_name

    ro = received_order

    # 送信先: 受注 → クライアント.report_email → クライアント.email
    to_email = ro.report_to_email
    if not to_email:
        to_email = ro.customer.report_email or ro.customer.email or ''
    if not to_email:
        return {
            'success': False,
            'message': f'{ro.customer.name}: 送信先メールが未設定です。請求先マスタで設定してください。',
            'sent_count': 0,
        }

    # 対象のMonthlyTimesheetを取得（受注に直接紐づくもの + 名前マッチ）
    worker_names = list(
        ro.items.exclude(person_name='').values_list('person_name', flat=True)
    )

    send_targets = []
    for wname in worker_names:
        wname_norm = normalize_name(wname)
        # まずreceived_orderで直接検索
        ts = MonthlyTimesheet.objects.filter(
            received_order=ro, worker_name=wname
        ).first()
        # なければ名前 + 年月で検索
        if not ts:
            for candidate in MonthlyTimesheet.objects.filter(
                target_month__year=ro.target_month.year,
                target_month__month=ro.target_month.month,
                status__in=('SUBMITTED', 'APPROVED'),
            ):
                if normalize_name(candidate.worker_name) == wname_norm:
                    ts = candidate
                    break
        if ts and ts.status in ('SUBMITTED', 'APPROVED'):
            send_targets.append(ts)

    if not send_targets:
        return {
            'success': False,
            'message': '送付可能な稼働報告がありません。',
            'sent_count': 0,
        }

    # メール構築
    target_month_str = ro.target_month.strftime('%Y年%m月')
    subject = f'【マックプランニング】{target_month_str}度 作業報告書のご送付'

    # 作業者サマリー
    worker_lines = []
    for ts in send_targets:
        hours = ts.total_hours or '—'
        days = ts.work_days or '—'
        worker_lines.append(f'  ・{ts.worker_name}（{hours}h / {days}日）')
    workers_summary = '\n'.join(worker_lines)

    body = f"""お世話になっております。
マックプランニングです。

{target_month_str}度の作業報告書をお送りいたします。

■ 対象案件: {ro.project_name or ro.order_number}
■ 作業者:
{workers_summary}

添付ファイルをご確認いただけますようお願いいたします。

何かご不明な点がございましたら、お気軽にご連絡ください。

よろしくお願いいたします。

---
株式会社マックプランニング
"""

    to_list = parse_email_list(to_email) if ',' in to_email else [to_email]
    cc_emails = ro.report_cc_emails or ro.customer.cc_email or ''
    cc_list = parse_email_list(cc_emails)

    from core.utils import get_email_config
    from django.core.mail import get_connection
    config = get_email_config()
    from_email = config['DEFAULT_FROM_EMAIL']

    connection = get_connection(
        host=config['EMAIL_HOST'],
        port=config['EMAIL_PORT'],
        username=config['EMAIL_HOST_USER'],
        password=config['EMAIL_HOST_PASSWORD'],
        use_tls=config['EMAIL_USE_TLS'],
    )

    email = EmailMessage(
        subject=subject,
        body=body,
        from_email=from_email,
        to=to_list,
        cc=cc_list,
        connection=connection,
    )

    # 添付ファイル
    attached_count = 0
    month_label = ro.target_month.strftime('%Y年%m月')
    project = ro.project_name or ro.order_number

    def _std_excel_name(worker_name):
        """統一ファイル名: 2026年04月AJS_（吉川裕）作業報告書.xlsm"""
        clean = worker_name.replace('\u3000', '').replace(' ', '')
        return f'{month_label}{project}_（{clean}）作業報告書.xlsm'

    def _std_pdf_name(worker_name):
        clean = worker_name.replace('\u3000', '').replace(' ', '')
        return f'{month_label}{project}_（{clean}）作業報告書.pdf'

    for ts in send_targets:
        # Excel添付
        if ts.excel_file and ts.excel_file.name:
            try:
                ts.excel_file.open('rb')
                fname = _std_excel_name(ts.worker_name)
                email.attach(fname, ts.excel_file.read(),
                             'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                ts.excel_file.close()
                attached_count += 1
            except Exception as e:
                logger.warning(f'Excel添付エラー ({ts.worker_name}): {e}')
        # PDF添付
        if ts.pdf_file and ts.pdf_file.name:
            try:
                ts.pdf_file.open('rb')
                email.attach(_std_pdf_name(ts.worker_name), ts.pdf_file.read(), 'application/pdf')
                ts.pdf_file.close()
                attached_count += 1
            except Exception as e:
                logger.warning(f'PDF添付エラー ({ts.worker_name}): {e}')

    if attached_count == 0:
        return {
            'success': False,
            'message': '添付可能なファイルがありません。ExcelまたはPDFを確認してください。',
            'sent_count': 0,
        }

    # 送信
    try:
        email.send()
        logger.info(f'報告書メール送信成功: {ro.order_number} → {to_email}')

        # ステータスをSENTに更新
        from django.utils import timezone
        now = timezone.now()
        for ts in send_targets:
            ts.status = 'SENT'
            ts.sent_to_client_at = now
            ts.save(update_fields=['status', 'sent_to_client_at', 'updated_at'])

        # 送信ログ
        try:
            from core.domain.models import SentEmailLog
            SentEmailLog.objects.create(
                partner=None,
                subject=subject,
                body=body,
            )
        except Exception:
            pass

        return {
            'success': True,
            'message': f'{len(send_targets)}名分の報告書を{to_email}へ送信しました。',
            'sent_count': len(send_targets),
        }
    except Exception as e:
        logger.error(f'報告書メール送信失敗: {ro.order_number} → {e}')
        return {
            'success': False,
            'message': f'メール送信に失敗しました: {e}',
            'sent_count': 0,
        }
