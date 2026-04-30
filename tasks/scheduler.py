"""
タスクスケジューラ — リマインドメール自動送信

OrderBasicInfoの設定値からリマインド日を算出し、
APSchedulerのdateトリガーでピンポイントにジョブを登録する。
"""
import datetime
import calendar
import logging

import jpholiday
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger

logger = logging.getLogger(__name__)

# グローバルスケジューラインスタンス
_scheduler = None


def get_scheduler():
    """スケジューラのシングルトンインスタンスを取得"""
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(timezone='Asia/Tokyo')
    return _scheduler


# ============================================================
# 営業日計算
# ============================================================

def is_business_day(d):
    """平日かつ祝日でなければ営業日"""
    return d.weekday() < 5 and not jpholiday.is_holiday(d)


def subtract_business_days(from_date, n_days):
    """
    指定日からn営業日前の日付を返す。
    営業日 = 土日・祝日を除いた平日。
    """
    current = from_date
    count = 0
    while count < n_days:
        current -= datetime.timedelta(days=1)
        if is_business_day(current):
            count += 1
    return current


def calc_month_end_minus(year, month, days_before):
    """月末からX日前の日付を返す（暦日ベース）"""
    last_day = calendar.monthrange(year, month)[1]
    return datetime.date(year, month, last_day) - datetime.timedelta(days=days_before)


# ============================================================
# リマインド日算出
# ============================================================

def calc_reminder_dates_for_basic_info(basic_info):
    """
    OrderBasicInfoから、全月のリマインドスケジュールを算出する。

    Returns:
        list of dict: [{
            'task': MonthlyTask,
            'deadline': date,       # 提出期限
            'reminder_date': date,  # リマインドメール送信日
        }, ...]
    """
    from tasks.models import MonthlyTask

    # 対象タスクを取得
    tasks = MonthlyTask.objects.filter(
        partner=basic_info.partner,
        project=basic_info.project,
        task_type='REPORT_UPLOAD',
        status='PENDING',
    ).order_by('deadline')

    results = []
    for task in tasks:
        reminder_date = subtract_business_days(
            task.deadline,
            basic_info.reminder_days_before
        )
        results.append({
            'task': task,
            'deadline': task.deadline,
            'reminder_date': reminder_date,
        })
    return results


def get_all_calendar_events(year, month):
    """
    指定月のカレンダーイベントを全パートナー分取得する。

    Returns:
        list of dict: [{
            'date': date,
            'type': 'reminder' | 'deadline',
            'partner_name': str,
            'project_name': str,
            'work_month': str,
            'task_id': int,
            'sent': bool,
        }, ...]
    """
    from tasks.models import MonthlyTask
    from orders.models import OrderBasicInfo

    first_day = datetime.date(year, month, 1)
    last_day = datetime.date(year, month, calendar.monthrange(year, month)[1])

    # 当月に期限があるREPORT_UPLOADタスク + 前後の月もリマインド日が当月に入る可能性
    # → PENDINGタスク全体から算出して当月に該当するものを抽出
    events = []

    basic_infos = OrderBasicInfo.objects.select_related('partner', 'project').all()

    for bi in basic_infos:
        tasks = MonthlyTask.objects.filter(
            partner=bi.partner,
            project=bi.project,
            task_type='REPORT_UPLOAD',
        ).order_by('deadline')

        for task in tasks:
            # 期限日イベント
            if first_day <= task.deadline <= last_day:
                events.append({
                    'date': task.deadline.isoformat(),
                    'type': 'deadline',
                    'title': f'📋 期限: {bi.partner.name}',
                    'partner_name': bi.partner.name,
                    'project_name': bi.project.name,
                    'work_month': task.work_month.strftime('%Y/%m'),
                    'task_id': task.pk,
                    'status': task.status,
                    'sent': task.reminder_sent,
                })

            # リマインド日イベント
            if task.status == 'PENDING':
                reminder_date = subtract_business_days(
                    task.deadline,
                    bi.reminder_days_before
                )
                if first_day <= reminder_date <= last_day:
                    events.append({
                        'date': reminder_date.isoformat(),
                        'type': 'reminder',
                        'title': f'📮 リマインド: {bi.partner.name}',
                        'partner_name': bi.partner.name,
                        'project_name': bi.project.name,
                        'work_month': task.work_month.strftime('%Y/%m'),
                        'task_id': task.pk,
                        'status': task.status,
                        'sent': task.reminder_sent,
                    })

    # 日付順にソート
    events.sort(key=lambda e: e['date'])
    return events


# ============================================================
# メール送信
# ============================================================

def send_reminder_for_task(task_id):
    """指定タスクのリマインドメールを送信する"""
    from tasks.models import MonthlyTask
    from core.utils import compose_work_report_reminder_email, send_system_mail

    try:
        task = MonthlyTask.objects.select_related('partner', 'project').get(pk=task_id)
    except MonthlyTask.DoesNotExist:
        logger.warning(f'[リマインド] タスクID={task_id} が見つかりません')
        return False

    if task.status != 'PENDING' or task.reminder_sent:
        logger.info(f'[リマインド] スキップ: {task} (status={task.status}, sent={task.reminder_sent})')
        return False

    partner = task.partner
    if not partner.email:
        logger.warning(f'[リマインド] メールアドレス未設定: {partner.name}')
        return False

    target_month_str = task.work_month.strftime('%Y年%m月')
    deadline_str = task.deadline.strftime('%Y年%m月%d日')

    subject, body = compose_work_report_reminder_email(
        partner=partner,
        project_name=task.project.name,
        target_month_str=target_month_str,
        deadline_str=deadline_str,
    )

    try:
        send_system_mail(
            subject, body,
            [partner.email],
        )
        task.reminder_sent = True
        task.save(update_fields=['reminder_sent'])
        logger.info(f'[リマインド送信] {partner.name} ({partner.email}) / {target_month_str}')
        return True
    except Exception as e:
        logger.error(f'[リマインド送信エラー] {partner.name}: {e}')
        return False


# ============================================================
# スケジューラ登録
# ============================================================

def register_reminder_jobs():
    """全PENDINGのREPORT_UPLOADタスクについてリマインドジョブを登録"""
    from tasks.models import MonthlyTask
    from orders.models import OrderBasicInfo

    scheduler = get_scheduler()
    today = datetime.date.today()
    registered = 0

    basic_infos = OrderBasicInfo.objects.select_related('partner', 'project').all()

    for bi in basic_infos:
        tasks = MonthlyTask.objects.filter(
            partner=bi.partner,
            project=bi.project,
            task_type='REPORT_UPLOAD',
            status='PENDING',
            reminder_sent=False,
        )

        for task in tasks:
            reminder_date = subtract_business_days(
                task.deadline,
                bi.reminder_days_before,
            )

            # 過去の日付はスキップ
            if reminder_date <= today:
                continue

            job_id = f'reminder_{task.pk}'

            # 既に登録済みならスキップ
            if scheduler.get_job(job_id):
                continue

            run_datetime = datetime.datetime.combine(
                reminder_date,
                datetime.time(9, 0),  # 9:00に送信
            )

            scheduler.add_job(
                send_reminder_for_task,
                trigger=DateTrigger(run_date=run_datetime),
                args=[task.pk],
                id=job_id,
                name=f'リマインド: {bi.partner.name} / {task.work_month.strftime("%Y/%m")}',
                replace_existing=True,
            )
            registered += 1
            logger.info(
                f'[スケジューラ] ジョブ登録: {job_id} → {reminder_date} '
                f'({bi.partner.name} / {task.work_month.strftime("%Y/%m")})'
            )

    logger.info(f'[スケジューラ] {registered}件のリマインドジョブを登録しました')
    return registered


def start_scheduler():
    """スケジューラを起動し、全ジョブを登録する"""
    from apscheduler.triggers.cron import CronTrigger

    scheduler = get_scheduler()
    if scheduler.running:
        return

    register_reminder_jobs()

    # メール受信チェックジョブ（毎日 9:00 / 15:00）
    scheduler.add_job(
        _fetch_emails_job,
        trigger=CronTrigger(hour='9,15', minute=0),
        id='email_fetch_regular',
        name='メール受信チェック（定時）',
        replace_existing=True,
    )

    # 月末強化ジョブ（25日以降は 12:00 / 18:00 も追加）
    scheduler.add_job(
        _fetch_emails_job,
        trigger=CronTrigger(day='25-31,1-5', hour='12,18', minute=0),
        id='email_fetch_month_end',
        name='メール受信チェック（月末強化）',
        replace_existing=True,
    )

    scheduler.start()
    logger.info('[スケジューラ] 起動しました')


def _fetch_emails_job():
    """メール受信チェックジョブ（スケジューラから呼ばれる）"""
    try:
        import django
        django.setup()
    except Exception:
        pass

    try:
        from invoices.services.email_receiver import fetch_and_process_emails
        result = fetch_and_process_emails()
        logger.info(
            f'[メール受信ジョブ] 処理: {result["processed"]}件, '
            f'取込: {result["imported"]}件, '
            f'エラー: {len(result["errors"])}件'
        )
    except Exception as e:
        logger.exception(f'[メール受信ジョブ] エラー: {e}')

