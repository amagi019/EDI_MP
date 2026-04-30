"""
勤怠報告サービス層

MonthlyTimesheetのビジネスロジック：
 - 受注ベースの勤怠報告作成
 - daily_dataからの残業・深夜・休日時間の自動算出
"""
import datetime
import logging
from decimal import Decimal
from billing.domain.models import (
    MonthlyTimesheet, ReceivedOrder, ReceivedOrderItem,
)

logger = logging.getLogger(__name__)

# =====================================================================
# 残業・深夜・休日時間の自動算出ルール
# =====================================================================
STANDARD_DAILY_HOURS = 8.0    # 所定労働時間（1日あたり）
NIGHT_START_HOUR = 22         # 深夜開始（22:00）
NIGHT_END_HOUR = 5            # 深夜終了（05:00）


def _calculate_overtime_breakdown(daily_data):
    """
    daily_dataから残業・深夜・休日の時間内訳を自動算出する。

    ルール:
        残業時間: 1日の稼働が8時間を超えた分
        深夜時間: 22:00〜翌5:00 の稼働時間
        休日時間: 土曜・日曜・祝日の稼働時間

    Args:
        daily_data: 日別データのリスト
            [{"date": "2026-03-01", "hours": 8.0,
              "start": "9:00", "end": "18:00"}, ...]

    Returns:
        dict: {
            'overtime_hours': Decimal,
            'night_hours': Decimal,
            'holiday_hours': Decimal,
        }
    """
    if not daily_data:
        return {
            'overtime_hours': Decimal('0'),
            'night_hours': Decimal('0'),
            'holiday_hours': Decimal('0'),
        }

    total_overtime = 0.0
    total_night = 0.0
    total_holiday = 0.0

    for entry in daily_data:
        hours = float(entry.get('hours', 0))
        if hours <= 0:
            continue

        date_str = entry.get('date', '')
        start_str = entry.get('start', '')
        end_str = entry.get('end', '')

        # 日付の解析
        try:
            work_date = datetime.date.fromisoformat(date_str)
        except (ValueError, TypeError):
            continue

        # 休日判定（土日）
        is_holiday = work_date.weekday() >= 5  # 5=土, 6=日
        if not is_holiday:
            is_holiday = _is_national_holiday(work_date)

        if is_holiday:
            total_holiday += hours

        # 残業時間（1日8時間超の分。休日出勤は別カウントのため除外）
        if not is_holiday and hours > STANDARD_DAILY_HOURS:
            total_overtime += hours - STANDARD_DAILY_HOURS

        # 深夜時間（22:00〜翌5:00の稼働分を算出）
        if start_str and end_str:
            night = _calc_night_hours(start_str, end_str)
            total_night += night

    return {
        'overtime_hours': Decimal(str(round(total_overtime, 2))),
        'night_hours': Decimal(str(round(total_night, 2))),
        'holiday_hours': Decimal(str(round(total_holiday, 2))),
    }


def _calc_night_hours(start_str, end_str):
    """
    開始・終了時刻から深夜時間帯（22:00〜翌5:00）の稼働時間を算出。

    Args:
        start_str: 開始時刻（"9:00" 形式）
        end_str: 終了時刻（"18:00" 形式）

    Returns:
        float: 深夜時間帯の稼働時間
    """
    try:
        parts = start_str.split(':')
        start_h, start_m = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
        parts = end_str.split(':')
        end_h, end_m = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        return 0.0

    start_minutes = start_h * 60 + start_m
    end_minutes = end_h * 60 + end_m

    # 日をまたぐ場合（例: 22:00〜翌2:00）
    if end_minutes <= start_minutes:
        end_minutes += 24 * 60

    night_minutes = 0.0

    # 深夜帯1: 0:00〜5:00（0〜300分）
    night1_start = 0
    night1_end = NIGHT_END_HOUR * 60
    overlap1 = _overlap(start_minutes, end_minutes, night1_start, night1_end)
    night_minutes += overlap1

    # 深夜帯2: 22:00〜24:00（1320〜1440分）
    night2_start = NIGHT_START_HOUR * 60
    night2_end = 24 * 60
    overlap2 = _overlap(start_minutes, end_minutes, night2_start, night2_end)
    night_minutes += overlap2

    # 日跨ぎの深夜帯: 翌0:00〜翌5:00（1440〜1740分）
    if end_minutes > 24 * 60:
        night3_start = 24 * 60
        night3_end = 24 * 60 + NIGHT_END_HOUR * 60
        overlap3 = _overlap(start_minutes, end_minutes, night3_start, night3_end)
        night_minutes += overlap3

    return night_minutes / 60.0


def _overlap(work_start, work_end, range_start, range_end):
    """2つの時間範囲の重複部分（分）を算出"""
    overlap_start = max(work_start, range_start)
    overlap_end = min(work_end, range_end)
    return max(0, overlap_end - overlap_start)


def _is_national_holiday(date):
    """
    日本の祝日かどうかを判定する。

    jpholiday パッケージが利用可能な場合はそれを使用し、
    なければ False を返す（土日判定のみにフォールバック）。
    """
    try:
        import jpholiday
        return jpholiday.is_holiday(date)
    except ImportError:
        return False


def create_timesheet(received_order=None, received_order_item=None,
                     order=None, worker_name='', worker_type='INTERNAL',
                     report_type='INTERNAL',
                     target_month=None, total_hours=0, work_days=0,
                     daily_data=None,
                     excel_file_path=None, original_filename=''):
    """勤怠報告を作成（Excelファイル原本の保存含む）

    daily_data がある場合、残業・深夜・休日時間を自動算出する。
    """
    # daily_data から残業内訳を自動算出
    breakdown = _calculate_overtime_breakdown(daily_data)

    ts = MonthlyTimesheet(
        report_type=report_type,
        order=order,
        received_order=received_order,
        received_order_item=received_order_item,
        worker_name=worker_name,
        worker_type=worker_type,
        target_month=target_month,
        total_hours=Decimal(str(total_hours)),
        work_days=work_days,
        overtime_hours=breakdown['overtime_hours'],
        night_hours=breakdown['night_hours'],
        holiday_hours=breakdown['holiday_hours'],
        daily_data=daily_data,
        status='SUBMITTED',
        original_filename=original_filename,
    )

    if daily_data and any(v > 0 for v in breakdown.values()):
        logger.info(
            f'[Timesheet] {worker_name}: 残業内訳を自動算出 '
            f'残業{breakdown["overtime_hours"]}h, '
            f'深夜{breakdown["night_hours"]}h, '
            f'休日{breakdown["holiday_hours"]}h'
        )

    # 一時保存されたExcelファイルをTimesheetに紐付け
    if excel_file_path:
        try:
            from django.core.files.storage import default_storage
            from django.core.files.base import File
            import os

            if default_storage.exists(excel_file_path):
                # 一時ファイルを読み込んで正式パスに保存
                ext = os.path.splitext(excel_file_path)[1] or '.xlsx'
                final_name = f'timesheets/excel/{worker_name}_{target_month.strftime("%Y%m")}{ext}'
                with default_storage.open(excel_file_path, 'rb') as temp_file:
                    ts.excel_file.save(final_name, File(temp_file), save=False)
                # 一時ファイルを削除
                try:
                    default_storage.delete(excel_file_path)
                except Exception:
                    pass
        except Exception:
            pass

    ts.save()
    return ts


def submit_timesheet(timesheet):
    """勤怠報告を提出"""
    timesheet.status = 'SUBMITTED'
    timesheet.save()
    return timesheet


def mark_as_sent(timesheet):
    """勤怠報告を送付済みにする（手動送付時用）"""
    timesheet.status = 'SENT'
    timesheet.save()
    return timesheet


def approve_timesheet(timesheet):
    """勤怠報告を承認"""
    timesheet.status = 'APPROVED'
    timesheet.save()
    return timesheet


def calculate_ses_billing(order_item, total_hours):
    """
    SES精算計算（パートナー側と同じロジック）
    Returns: (base_fee, excess_amount, shortage_amount, subtotal)
    """
    base_fee = int(order_item.unit_price * order_item.man_month)
    lower = float(order_item.time_lower_limit)
    upper = float(order_item.time_upper_limit)
    hours = float(total_hours)

    excess_amount = 0
    shortage_amount = 0

    if hours > upper and order_item.excess_rate > 0:
        excess_amount = int((hours - upper) * order_item.excess_rate)
    elif hours < lower and order_item.shortage_rate > 0:
        shortage_amount = int((lower - hours) * order_item.shortage_rate)

    subtotal = base_fee + excess_amount - shortage_amount
    return base_fee, excess_amount, shortage_amount, subtotal


def send_work_report_email(timesheet, subject=None, body=None, sender_email=None):
    """
    勤怠報告（作業報告書）をメールで送信する。
    Excelファイル原本がある場合はそれを添付する。

    Args:
        timesheet: MonthlyTimesheet
        subject: カスタム件名
        body: カスタム本文
        sender_email: 送信元（省略時はDEFAULT_FROM_EMAIL）

    Returns:
        dict: {'sent': True/False, 'errors': list}
    """
    from django.core.mail import EmailMessage
    from django.conf import settings
    import logging

    logger = logging.getLogger(__name__)
    result = {'sent': False, 'errors': []}

    order = timesheet.order
    customer = order.customer

    # 送信先: 受注の報告書送信先 → 取引先のメールにフォールバック
    to_email = order.report_to_email or customer.email
    if not to_email:
        result['errors'].append(f'{customer.name}のメールアドレスが未設定です。')
        return result

    from_email = sender_email or getattr(settings, 'DEFAULT_FROM_EMAIL', '')
    to_list = [to_email]
    cc_list = []
    # CC: 受注のCC → 取引先のCCにフォールバック
    cc_source = order.report_cc_emails or customer.cc_email
    if cc_source:
        cc_list = [e.strip() for e in cc_source.split(',') if e.strip()]

    # メール構築
    email_subject = subject or f'{timesheet.worker_name}の稼働報告'
    email_body = body or _build_default_body(timesheet, order, customer)

    try:
        email = EmailMessage(
            subject=email_subject,
            body=email_body,
            from_email=from_email,
            to=to_list,
            cc=cc_list,
        )

        # Excelファイル原本を添付（あれば）
        if timesheet.excel_file:
            try:
                filename = timesheet.original_filename or f'作業報告書_{timesheet.worker_name}_{timesheet.target_month.strftime("%Y%m")}.xlsx'
                timesheet.excel_file.open('rb')
                email.attach(filename, timesheet.excel_file.read(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                timesheet.excel_file.close()
            except Exception as e:
                logger.warning(f'[Timesheet] Excelファイル添付スキップ: {e}')

        email.send()
        result['sent'] = True

        # 送信成功時にステータスを「送付済み」に更新
        if timesheet.status in ('DRAFT', 'SUBMITTED'):
            timesheet.status = 'SENT'
            timesheet.save(update_fields=['status'])

        logger.info(f'[Timesheet] 作業報告書メール送信: {to_email} ({timesheet.worker_name})')
    except Exception as e:
        result['errors'].append(f'メール送信エラー: {e}')
        logger.error(f'[Timesheet] メール送信エラー: {e}')

    return result


def _build_default_body(timesheet, order, customer):
    """作業報告書のデフォルトメール本文を構築"""
    from core.domain.models import CompanyInfo

    company = CompanyInfo.objects.first()

    contact = customer.contact_person or customer.name
    company_name = company.name if company else ''
    sender_name = company.contact_person if company else ''
    sender_email_addr = company.email if company else ''
    sender_phone = company.phone if company else ''

    work_start = order.work_start.strftime('%Y年%m月%d日') if order.work_start else ''
    work_end = order.work_end.strftime('%Y年%m月%d日') if order.work_end else ''

    body = (
        f'{customer.name}　{contact}様\n\n'
        f'お世話になっております。{company_name}　{sender_name}です。\n\n'
        f'{timesheet.worker_name}の稼働報告 を送付いたします。\n'
        f'ご確認お願いいたします。\n\n'
        f'注文番号：{order.order_number}\n'
        f'業務名：{order.project_name}\n'
        f'作業期間：{work_start} ～ {work_end}\n'
        f'作業責任者：{timesheet.worker_name}\n\n'
        f'--\n'
        f'*******************************************\n'
        f'{company_name}\n'
        f'{sender_name}\n'
        f'Mail：{sender_email_addr}\n'
        f'TEL：{sender_phone}\n'
        f'*******************************************\n'
    )
    return body
