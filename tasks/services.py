"""
タスク完了ロジック一元化サービス

MonthlyTaskの完了処理を一箇所に集約。
各ビュー(orders/views.py, basic_info_views.py, invoices/views.py)からはこのサービスを呼ぶだけ。
"""
import logging
from django.utils import timezone
from tasks.models import MonthlyTask

logger = logging.getLogger(__name__)


def _normalize_to_month_start(date_val):
    """日付を月初(1日)に正規化する。work_monthとのマッチ用。"""
    if date_val is None:
        return None
    return date_val.replace(day=1)


def _get_next_month_start(date_val):
    """翌月の月初を返す。order_end_ym→work_monthの変換用。"""
    if date_val is None:
        return None
    dt = date_val.replace(day=1)
    if dt.month == 12:
        return dt.replace(year=dt.year + 1, month=1)
    return dt.replace(month=dt.month + 1)


def _complete_task(partner, project, work_month, task_type, note=''):
    """
    指定されたパートナー×プロジェクト×月のMonthlyTaskを完了にする。
    """
    if not work_month:
        return 0

    count = MonthlyTask.objects.filter(
        partner=partner,
        project=project,
        work_month=work_month,
        task_type=task_type,
        status='PENDING',
    ).update(status='DONE', completed_at=timezone.now(), note=note)

    if count:
        logger.info(f'タスク完了: {task_type} | {partner.name} | {work_month}')
    return count


def complete_order_create(order):
    """注文書作成タスクを完了にする"""
    work_month = _normalize_to_month_start(order.order_end_ym)
    return _complete_task(order.partner, order.project, work_month, 'ORDER_CREATE',
                          note=f'注文書: {order.order_id}')


def complete_order_approve(order):
    """注文書承認タスクを完了にする"""
    work_month = _normalize_to_month_start(order.order_end_ym)
    return _complete_task(order.partner, order.project, work_month, 'ORDER_APPROVE',
                          note=f'注文書: {order.order_id}')


def complete_invoice_create(invoice):
    """請求書作成タスクを完了にする"""
    order = invoice.order
    work_month = _normalize_to_month_start(invoice.target_month)
    return _complete_task(order.partner, order.project, work_month, 'INVOICE_CREATE',
                          note=f'請求書: {invoice.invoice_no}')


def complete_invoice_approve(invoice):
    """請求書承認タスクを完了にする"""
    order = invoice.order
    work_month = _normalize_to_month_start(invoice.target_month)
    return _complete_task(order.partner, order.project, work_month, 'INVOICE_APPROVE',
                          note=f'請求書: {invoice.invoice_no}')


def complete_report_upload(report):
    """稼働報告書アップロードタスクを完了にする"""
    order = report.order
    work_month = _normalize_to_month_start(report.target_month)
    return _complete_task(order.partner, order.project, work_month, 'REPORT_UPLOAD',
                          note=f'報告書: {report.worker_name}')
