"""
メール受信・自動取込サービス

IMAP経由でGmailに接続し、パートナーからの稼働報告メール（Excel添付）を
自動的に取り込みMonthlyTimesheetとして登録する。

処理フロー:
  1. IMAP接続 → 未読メール検索
  2. 件名フィルタ（稼働報告/作業報告/請求書）
  3. 送信元 → Partner.email / Partner.report_email で照合
  4. Excel添付ファイル抽出 → excel_parser で解析
  5. MonthlyTimesheet 自動登録
  6. 処理済みメールにGmailラベル付与
  7. 管理者通知メール送信
"""
import imaplib
import email
from email.header import decode_header
import io
import re
import logging
import datetime

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.mail import send_mail
from django.utils import timezone
from django.db.models import Q

logger = logging.getLogger(__name__)

# 件名に含まれるキーワード（いずれかがマッチすれば対象）
SUBJECT_KEYWORDS = ['稼働報告', '作業報告', '請求書', '勤怠', '報告書']

# 対象添付ファイルの拡張子
EXCEL_EXTENSIONS = ('.xlsx', '.xlsm')

# 処理済みラベル
GMAIL_LABEL = 'EDI/取込済'


def fetch_and_process_emails():
    """
    メインエントリポイント: メール受信 → 解析 → MonthlyTimesheet登録

    Returns:
        dict: {'processed': int, 'imported': int, 'errors': list}
    """
    result = {'processed': 0, 'imported': 0, 'errors': [], 'details': []}

    import os
    imap_host = getattr(settings, 'IMAP_HOST', os.environ.get('IMAP_HOST', 'imap.gmail.com'))
    imap_port = int(getattr(settings, 'IMAP_PORT', os.environ.get('IMAP_PORT', 993)))
    imap_user = getattr(settings, 'IMAP_USER', os.environ.get('IMAP_USER', ''))
    imap_password = getattr(settings, 'IMAP_PASSWORD', os.environ.get('IMAP_PASSWORD', ''))

    if not imap_user or not imap_password:
        # SMTP設定をフォールバックとして使用
        imap_user = imap_user or getattr(settings, 'EMAIL_HOST_USER', os.environ.get('EMAIL_HOST_USER', ''))
        imap_password = imap_password or getattr(settings, 'EMAIL_HOST_PASSWORD', os.environ.get('EMAIL_HOST_PASSWORD', ''))

    if not imap_user or not imap_password:
        result['errors'].append('IMAP認証情報が設定されていません。')
        return result

    try:
        mail = imaplib.IMAP4_SSL(imap_host, imap_port)
        mail.login(imap_user, imap_password)
        mail.select('INBOX')

        # 未読メールを検索
        status, messages = mail.search(None, 'UNSEEN')
        if status != 'OK':
            result['errors'].append('メール検索に失敗しました。')
            mail.logout()
            return result

        email_ids = messages[0].split()
        logger.info(f'[メール受信] 未読メール: {len(email_ids)}件')

        for eid in email_ids:
            try:
                detail = _process_single_email(mail, eid)
                result['processed'] += 1
                if detail.get('imported'):
                    result['imported'] += 1
                result['details'].append(detail)
            except Exception as e:
                logger.exception(f'[メール受信] メール処理エラー (ID={eid}): {e}')
                result['errors'].append(f'メールID {eid}: {e}')

        mail.logout()

    except imaplib.IMAP4.error as e:
        result['errors'].append(f'IMAP接続エラー: {e}')
        logger.error(f'[メール受信] IMAP接続エラー: {e}')
    except Exception as e:
        result['errors'].append(f'予期しないエラー: {e}')
        logger.exception(f'[メール受信] 予期しないエラー: {e}')

    # 取込があった場合は管理者に通知
    if result['imported'] > 0:
        _send_admin_notification(result)

    return result


def _process_single_email(mail, email_id):
    """
    1件のメールを処理する。

    Returns:
        dict: {'subject': str, 'from': str, 'imported': bool, 'reason': str}
    """
    from invoices.models import ReceivedEmail

    status, msg_data = mail.fetch(email_id, '(RFC822)')
    if status != 'OK':
        return {'imported': False, 'reason': 'メール取得失敗'}

    raw_email = msg_data[0][1]
    msg = email.message_from_bytes(raw_email)

    # ヘッダー解析
    message_id = msg.get('Message-ID', '')
    from_header = msg.get('From', '')
    from_name, from_email_addr = _parse_from_header(from_header)
    subject = _decode_subject(msg.get('Subject', ''))
    date_str = msg.get('Date', '')
    received_at = _parse_date(date_str)

    detail = {
        'subject': subject,
        'from': from_email_addr,
        'from_name': from_name,
        'imported': False,
        'reason': '',
    }

    # 重複チェック
    if message_id and ReceivedEmail.objects.filter(message_id=message_id).exists():
        detail['reason'] = '処理済み（重複）'
        return detail

    # 件名フィルタ
    if not _matches_subject_filter(subject, from_email_addr):
        detail['reason'] = '件名が対象外'
        # 未読に戻す（他のメールとして残す）
        mail.store(email_id, '-FLAGS', '\\Seen')
        return detail

    # パートナー照合
    partner = _match_partner(from_email_addr)
    if not partner:
        detail['reason'] = 'パートナー照合失敗'
        # ReceivedEmailには記録する（手動照合用）
        _save_received_email(
            message_id, from_email_addr, from_name, subject,
            received_at, _get_body_text(msg), None, 'NEW',
            error_message='パートナーが照合できませんでした'
        )
        mail.store(email_id, '-FLAGS', '\\Seen')
        return detail

    # Excel添付ファイル抽出
    excel_files = _extract_excel_attachments(msg)
    if not excel_files:
        detail['reason'] = 'Excel添付なし'
        _save_received_email(
            message_id, from_email_addr, from_name, subject,
            received_at, _get_body_text(msg), partner, 'IGNORED',
            error_message='Excel添付ファイルがありませんでした'
        )
        return detail

    # 各添付ファイルを処理
    for filename, file_bytes in excel_files:
        try:
            work_report = _import_excel_as_work_report(
                partner, filename, file_bytes
            )

            received = _save_received_email(
                message_id, from_email_addr, from_name, subject,
                received_at, _get_body_text(msg), partner, 'IMPORTED',
                monthly_timesheet=work_report,
                attachment_filename=filename,
                attachment_bytes=file_bytes,
            )
            detail['imported'] = True
            detail['reason'] = f'取込完了: {filename}'
            detail['worker_name'] = work_report.worker_name if work_report else ''

        except Exception as e:
            logger.exception(f'[メール受信] Excel取込エラー: {filename}: {e}')
            _save_received_email(
                message_id, from_email_addr, from_name, subject,
                received_at, _get_body_text(msg), partner, 'ERROR',
                error_message=f'{filename}: {e}',
                attachment_filename=filename,
                attachment_bytes=file_bytes,
            )
            detail['reason'] = f'エラー: {e}'

    # Gmailラベル付与
    _apply_gmail_label(mail, email_id, GMAIL_LABEL)

    return detail


# ============================================================
# ヘッダー解析ユーティリティ
# ============================================================

def _parse_from_header(from_header):
    """Fromヘッダーから名前とメールアドレスを抽出"""
    # "名前 <email@example.com>" パターン
    m = re.match(r'(.+?)\s*<(.+?)>', from_header)
    if m:
        name = _decode_mime_string(m.group(1).strip().strip('"'))
        addr = m.group(2).strip()
        return name, addr
    # メールアドレスのみ
    addr = from_header.strip().strip('<>').strip()
    return '', addr


def _decode_subject(subject_raw):
    """MIMEエンコードされた件名をデコード"""
    if not subject_raw:
        return ''
    return _decode_mime_string(subject_raw)


def _decode_mime_string(s):
    """MIMEエンコード文字列をデコード"""
    try:
        parts = decode_header(s)
        decoded = []
        for part, charset in parts:
            if isinstance(part, bytes):
                decoded.append(part.decode(charset or 'utf-8', errors='replace'))
            else:
                decoded.append(str(part))
        return ''.join(decoded)
    except Exception:
        return str(s)


def _parse_date(date_str):
    """メールのDateヘッダーをdatetimeに変換"""
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(date_str)
    except Exception:
        return timezone.now()


def _get_body_text(msg):
    """メッセージ本文（テキストパート）を取得"""
    body = ''
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == 'text/plain':
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or 'utf-8'
                body = payload.decode(charset, errors='replace')
                break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or 'utf-8'
            body = payload.decode(charset, errors='replace')
    return body[:5000]  # 最大5000文字


# ============================================================
# フィルタ・照合
# ============================================================

def _matches_subject_filter(subject, from_email_addr):
    """件名がフィルタ条件に合致するかチェック"""
    from core.domain.models import Partner

    subject_lower = subject.lower()

    # キーワードチェック
    if any(kw in subject for kw in SUBJECT_KEYWORDS):
        return True

    # パートナー社名の一部が件名に含まれるかチェック
    partners = Partner.objects.filter(
        Q(email__iexact=from_email_addr) |
        Q(report_email__iexact=from_email_addr)
    )
    for p in partners:
        # "株式会社", "合同会社" 等を除去して社名コアで照合
        core_name = _extract_company_core_name(p.name)
        if core_name and core_name in subject:
            return True

    return False


def _extract_company_core_name(name):
    """会社名から法人格を除去してコア部分を返す"""
    prefixes = ['株式会社', '有限会社', '合同会社', '合資会社',
                '(株)', '（株）', '(有)', '（有）', '(合)', '（合）']
    result = name
    for p in prefixes:
        result = result.replace(p, '')
    return result.strip()


def _match_partner(from_email_addr):
    """送信元メールアドレスからパートナーを照合"""
    from core.domain.models import Partner

    # email または report_email で照合
    partner = Partner.objects.filter(
        Q(email__iexact=from_email_addr) |
        Q(report_email__iexact=from_email_addr)
    ).first()

    return partner


# ============================================================
# Excel抽出・取込
# ============================================================

def _extract_excel_attachments(msg):
    """メールからExcel添付ファイルを抽出"""
    excel_files = []

    for part in msg.walk():
        if part.get_content_maintype() == 'multipart':
            continue

        filename = part.get_filename()
        if not filename:
            continue

        filename = _decode_mime_string(filename)

        # 拡張子チェック
        if not any(filename.lower().endswith(ext) for ext in EXCEL_EXTENSIONS):
            continue

        payload = part.get_payload(decode=True)
        if payload:
            excel_files.append((filename, payload))

    return excel_files


def _import_excel_as_work_report(partner, filename, file_bytes):
    """
    Excelファイルを解析してMonthlyTimesheetとして登録する。
    """
    from invoices.services.excel_parser import auto_detect_and_parse
    from billing.domain.models import MonthlyTimesheet
    from orders.models import Order

    # Excel解析
    file_obj = io.BytesIO(file_bytes)
    result = auto_detect_and_parse(file_obj, original_filename=filename)

    if result['error']:
        raise ValueError(f"Excel解析エラー: {result['error']}")

    # パートナーに紐づく承諾済み注文を検索
    order = Order.objects.filter(
        partner=partner,
        status='APPROVED'
    ).order_by('-order_end_ym').first()

    if not order:
        # フォールバック: 発行済みの注文
        order = Order.objects.filter(
            partner=partner,
            status__in=['UNCONFIRMED', 'RECEIVED', 'APPROVED']
        ).order_by('-order_end_ym').first()

    if not order:
        raise ValueError(f'{partner.name}に紐づく有効な注文書が見つかりません')

    # MonthlyTimesheet 作成
    from django.core.files.base import ContentFile

    work_report = MonthlyTimesheet(
        report_type='PARTNER',
        worker_type='PARTNER',
        order=order,
        target_month=result['target_month'],
        worker_name=result['worker_name'] or filename,
        uploaded_by=None,  # システム自動取込
        original_filename=filename,
        status='APPROVED',
        total_hours=result['total_hours'],
        work_days=result['work_days'],
        daily_data=result['daily_data'],
        alerts_json=result['alerts'] if result['alerts'] else None,
    )
    work_report.excel_file.save(filename, ContentFile(file_bytes), save=False)
    work_report.save()

    logger.info(
        f'[メール受信] MonthlyTimesheet登録: {partner.name} / '
        f'{result["worker_name"]} / {result["target_month"]}'
    )

    return work_report


# ============================================================
# DB保存
# ============================================================

def _save_received_email(message_id, from_email, from_name, subject,
                         received_at, body_text, partner, status,
                         monthly_timesheet=None, error_message='',
                         attachment_filename='', attachment_bytes=None):
    """ReceivedEmail レコードを保存"""
    from invoices.models import ReceivedEmail

    received = ReceivedEmail(
        message_id=message_id or f'auto_{timezone.now().timestamp()}',
        from_email=from_email,
        from_name=from_name,
        subject=subject[:512],
        received_at=received_at,
        body_text=body_text,
        partner=partner,
        status=status,
        monthly_timesheet=work_report,
        error_message=error_message,
        attachment_filename=attachment_filename,
    )

    if attachment_bytes and attachment_filename:
        received.attachment_file.save(
            attachment_filename,
            ContentFile(attachment_bytes),
            save=False
        )

    if status in ('IMPORTED', 'FORWARDED', 'IGNORED', 'ERROR'):
        received.processed_at = timezone.now()

    received.save()
    return received


# ============================================================
# Gmail ラベル付与
# ============================================================

def _apply_gmail_label(mail, email_id, label_name):
    """処理済みメールにGmailラベルを付与する"""
    try:
        # Gmail IMAP拡張: ラベルを作成（既存なら無視）
        mail.create(label_name)
    except Exception:
        pass  # 既に存在する場合はエラーになるが無視

    try:
        # ラベルをコピー（Gmail IMAP ではコピーでラベル付与）
        mail.copy(email_id, label_name)
        logger.info(f'[メール受信] ラベル付与: {label_name}')
    except Exception as e:
        logger.warning(f'[メール受信] ラベル付与失敗: {e}')


# ============================================================
# 管理者通知
# ============================================================

def _send_admin_notification(result):
    """取込結果を管理者にメール通知"""
    try:
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', '')
        admin_email = from_email  # デフォルトでは送信元=受信元

        subject = f'【EDI】稼働報告メール取込完了（{result["imported"]}件）'

        details_text = ''
        for d in result.get('details', []):
            if d.get('imported'):
                details_text += (
                    f'  ✅ {d.get("from", "")} / {d.get("subject", "")} '
                    f'→ {d.get("worker_name", "")}\n'
                )

        errors_text = ''
        for e in result.get('errors', []):
            errors_text += f'  ❌ {e}\n'

        body = (
            f'稼働報告メールの自動取込が完了しました。\n\n'
            f'■ 処理件数: {result["processed"]}件\n'
            f'■ 取込件数: {result["imported"]}件\n'
            f'■ エラー: {len(result["errors"])}件\n\n'
        )
        if details_text:
            body += f'【取込詳細】\n{details_text}\n'
        if errors_text:
            body += f'【エラー詳細】\n{errors_text}\n'

        body += '\n受信メール一覧から詳細を確認できます。'

        send_mail(subject, body, from_email, [admin_email], fail_silently=True)

    except Exception as e:
        logger.error(f'[メール受信] 管理者通知送信エラー: {e}')
