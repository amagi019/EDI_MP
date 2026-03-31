"""
受注サービス層

ReceivedOrderのビジネスロジック：
 - PDFアップロードからの受注作成
 - 手動入力からの受注作成
 - 受注明細の管理
"""
import datetime
from decimal import Decimal
from billing.domain.models import (
    ReceivedOrder, ReceivedOrderItem,
    BillingCustomer, ClientContract,
)
from billing.services.order_pdf_parser import parse_order_pdf


def create_received_order_from_pdf(file_obj, customer, contract=None, user=None):
    """
    PDFをパースして受注を作成する。

    Returns:
        tuple: (ReceivedOrder, parsed_data, errors)
    """
    parsed = parse_order_pdf(file_obj)
    errors = []

    # 作業期間の決定
    work_start = None
    work_end = None
    if parsed['work_start']:
        try:
            work_start = datetime.date.fromisoformat(parsed['work_start'])
        except ValueError:
            errors.append(f"作業開始日のパースに失敗: {parsed['work_start']}")
    if parsed['work_end']:
        try:
            work_end = datetime.date.fromisoformat(parsed['work_end'])
        except ValueError:
            errors.append(f"作業終了日のパースに失敗: {parsed['work_end']}")

    # フォールバック: 今月
    today = datetime.date.today()
    if not work_start:
        work_start = today.replace(day=1)
        errors.append("作業開始日を自動設定（当月1日）")
    if not work_end:
        # 月末
        import calendar
        _, last_day = calendar.monthrange(work_start.year, work_start.month)
        work_end = work_start.replace(day=last_day)
        errors.append("作業終了日を自動設定（月末）")

    target_month = work_start.replace(day=1)

    # 注文日
    order_date = today
    if parsed['order_date']:
        try:
            order_date = datetime.date.fromisoformat(parsed['order_date'])
        except ValueError:
            pass

    # 受注作成
    order = ReceivedOrder.objects.create(
        contract=contract,
        customer=customer,
        order_number=parsed['order_number'] or '',
        target_month=target_month,
        work_start=work_start,
        work_end=work_end,
        project_name=parsed['project_name'] or '',
        order_file=file_obj,
        parsed_data=parsed,
        status='REGISTERED',
        order_date=order_date,
    )

    # 明細作成（単価が取れた場合）
    if parsed['unit_price']:
        ReceivedOrderItem.objects.create(
            order=order,
            person_name=parsed.get('person_name') or '',
            unit_price=parsed['unit_price'],
            man_month=Decimal('1.00'),
            time_lower_limit=Decimal(str(parsed.get('time_lower') or 140)),
            time_upper_limit=Decimal(str(parsed.get('time_upper') or 180)),
            shortage_rate=parsed.get('shortage_rate') or 0,
            excess_rate=parsed.get('excess_rate') or 0,
        )

    return order, parsed, errors


def create_received_order_manual(
    customer, target_month, work_start, work_end,
    order_number='', project_name='', contract=None,
    order_date=None, remarks='',
):
    """手動入力で受注を作成する"""
    order = ReceivedOrder.objects.create(
        contract=contract,
        customer=customer,
        order_number=order_number,
        target_month=target_month,
        work_start=work_start,
        work_end=work_end,
        project_name=project_name,
        status='REGISTERED',
        order_date=order_date or datetime.date.today(),
        remarks=remarks,
    )
    return order


def add_order_item(
    order, person_name, unit_price, man_month=Decimal('1.00'),
    time_lower=Decimal('140'), time_upper=Decimal('180'),
    shortage_rate=0, excess_rate=0, product=None,
):
    """受注に明細を追加する"""
    return ReceivedOrderItem.objects.create(
        order=order,
        product=product,
        person_name=person_name,
        unit_price=unit_price,
        man_month=man_month,
        time_lower_limit=time_lower,
        time_upper_limit=time_upper,
        shortage_rate=shortage_rate,
        excess_rate=excess_rate,
    )


def rollforward_order(source_order):
    """
    受注を翌月にロールフォワード（コピー）する。

    Args:
        source_order: コピー元のReceivedOrder

    Returns:
        ReceivedOrder: 新しく作成された翌月の受注
    """
    import calendar

    # 翌月計算
    year = source_order.target_month.year
    month = source_order.target_month.month
    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1

    next_target = datetime.date(next_year, next_month, 1)
    _, last_day = calendar.monthrange(next_year, next_month)
    next_work_end = datetime.date(next_year, next_month, last_day)

    # 重複チェック
    exists = ReceivedOrder.objects.filter(
        customer=source_order.customer,
        target_month=next_target,
        project_name=source_order.project_name,
    ).exists()
    if exists:
        raise ValueError(
            f'{source_order.customer.name} の {next_target.strftime("%Y/%m")} 分は既に存在します'
        )

    # 受注コピー
    new_order = ReceivedOrder.objects.create(
        contract=source_order.contract,
        customer=source_order.customer,
        order_number=source_order.order_number,  # 同じ注文番号を引き継ぎ
        target_month=next_target,
        work_start=next_target,
        work_end=next_work_end,
        project_name=source_order.project_name,
        status='REGISTERED',
        is_recurring=source_order.is_recurring,
        parent_order=source_order.parent_order or source_order,  # 初回注文を参照
        order_date=datetime.date.today(),
        remarks=f'ロールフォワード（元: {source_order.target_month.strftime("%Y/%m")}）',
        report_to_email=source_order.report_to_email,
        report_cc_emails=source_order.report_cc_emails,
        invoice_to_email=source_order.invoice_to_email,
        invoice_cc_emails=source_order.invoice_cc_emails,
    )

    # 明細コピー
    for item in source_order.items.all():
        ReceivedOrderItem.objects.create(
            order=new_order,
            product=item.product,
            person_name=item.person_name,
            unit_price=item.unit_price,
            man_month=item.man_month,
            settlement_type=item.settlement_type,
            settlement_middle_hours=item.settlement_middle_hours,
            time_lower_limit=item.time_lower_limit,
            time_upper_limit=item.time_upper_limit,
            shortage_rate=item.shortage_rate,
            excess_rate=item.excess_rate,
        )

    return new_order


def rollforward_all_recurring():
    """
    is_recurring=Trueの受注のうち、翌月分がまだ存在しないものを一括生成。

    Returns:
        list: (source_order, new_order) のタプルリスト
    """
    import calendar

    today = datetime.date.today()
    current_month = today.replace(day=1)

    # 今月以降の最新のis_recurring=True受注を取得
    recurring_orders = ReceivedOrder.objects.filter(
        is_recurring=True,
        status__in=['REGISTERED', 'ACTIVE'],
    ).order_by('customer', '-target_month')

    # 顧客×プロジェクトごとに最新のものだけ処理
    seen = set()
    results = []
    for order in recurring_orders:
        key = (order.customer_id, order.project_name)
        if key in seen:
            continue
        seen.add(key)

        # 翌月分が存在するか
        year = order.target_month.year
        month = order.target_month.month
        if month == 12:
            next_year, next_month = year + 1, 1
        else:
            next_year, next_month = year, month + 1
        next_target = datetime.date(next_year, next_month, 1)

        exists = ReceivedOrder.objects.filter(
            customer=order.customer,
            target_month=next_target,
            project_name=order.project_name,
        ).exists()

        if not exists:
            try:
                new_order = rollforward_order(order)
                results.append((order, new_order))
            except ValueError:
                pass

    return results

