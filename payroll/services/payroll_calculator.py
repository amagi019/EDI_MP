"""
給与計算エンジン

Excelスプレッドシートの計算ロジックを正しく実装。
元ファイルの問題点（残業単価の間違い、雇用保険の折半等）を修正済み。
"""
import math
import datetime
import calendar
from decimal import Decimal

from payroll.domain.models import (
    Employee, InsuranceRate, WithholdingTaxRow,
    ResidentTaxSchedule, Payroll,
)


def calculate_payroll(employee, year_month, timesheet=None,
                      overtime_hours=0, overtime_60_hours=0,
                      night_hours=0, holiday_hours=0,
                      absence_days=0, work_days=0, total_hours=0):
    """
    社員の月次給与を計算する。

    Args:
        employee: Employee インスタンス
        year_month: datetime.date（YYYY-MM-01）
        timesheet: StaffTimesheet（任意、紐付け用）
        overtime_hours: 残業時間
        overtime_60_hours: 60時間超残業
        night_hours: 深夜残業時間
        holiday_hours: 休日出勤時間
        absence_days: 欠勤日数
        work_days: 出勤日数
        total_hours: 総労働時間

    Returns:
        Payroll インスタンス（未保存）
    """
    payroll = Payroll(
        employee=employee,
        year_month=year_month,
        timesheet=timesheet,
        status='DRAFT',
    )

    # === 勤怠実績 ===
    payroll.work_days = work_days
    payroll.total_hours = Decimal(str(total_hours))
    payroll.overtime_hours = Decimal(str(overtime_hours))
    payroll.overtime_60_hours = Decimal(str(overtime_60_hours))
    payroll.night_hours = Decimal(str(night_hours))
    payroll.holiday_hours = Decimal(str(holiday_hours))
    payroll.absence_days = absence_days

    # === 支給日（設定から取得） ===
    from payroll.domain.settings import PayrollSettings
    settings = PayrollSettings.load()
    if settings.payment_day == 0:
        last_day = calendar.monthrange(
            year_month.year, year_month.month)[1]
        payroll.payment_date = datetime.date(
            year_month.year, year_month.month, last_day)
    else:
        day = min(settings.payment_day, calendar.monthrange(
            year_month.year, year_month.month)[1])
        payroll.payment_date = datetime.date(
            year_month.year, year_month.month, day)

    # === 支給計算 ===
    _calculate_pay(payroll, employee)

    # === 控除計算 ===
    _calculate_deductions(payroll, employee, year_month)

    # === 最終計算 ===
    payroll.net_pay = payroll.gross_pay - payroll.deduction_total

    return payroll


def _calculate_pay(payroll, employee):
    """支給額を計算する"""
    # 固定給
    payroll.base_salary = employee.base_salary
    payroll.position_allowance = employee.position_allowance
    payroll.housing_allowance = employee.housing_allowance
    payroll.commuting_allowance = employee.commuting_allowance

    std_hours = float(employee.standard_monthly_hours)
    base_for_overtime = employee.base_salary + employee.position_allowance

    # 残業単価（設定の割増率を使用）
    from payroll.domain.settings import PayrollSettings
    settings = PayrollSettings.load()
    if std_hours > 0:
        overtime_rate = math.ceil(
            base_for_overtime / std_hours
            * float(settings.overtime_rate_multiplier))
        overtime_60_rate = math.ceil(
            base_for_overtime / std_hours
            * float(settings.overtime_60_rate_multiplier))
        night_rate = math.ceil(
            base_for_overtime / std_hours
            * float(settings.night_rate_multiplier))
        holiday_rate = math.ceil(
            base_for_overtime / std_hours
            * float(settings.holiday_rate_multiplier))
    else:
        overtime_rate = overtime_60_rate = night_rate = holiday_rate = 0

    # 変動給
    payroll.overtime_pay = int(overtime_rate * float(payroll.overtime_hours))
    payroll.overtime_60_pay = int(overtime_60_rate * float(payroll.overtime_60_hours))
    payroll.night_pay = int(night_rate * float(payroll.night_hours))
    payroll.holiday_pay = int(holiday_rate * float(payroll.holiday_hours))

    # 不就労控除（日割り計算: 基本給 / 所定労働日数 × 欠勤日数）
    if payroll.absence_days > 0 and payroll.work_days > 0:
        # 所定労働日数 ≒ work_days + absence_days（その月に出勤すべきだった日数）
        scheduled_days = payroll.work_days + payroll.absence_days
        daily_rate = employee.base_salary / scheduled_days
        payroll.absence_deduction = -int(daily_rate * payroll.absence_days)
    else:
        payroll.absence_deduction = 0

    # 課税支給合計
    payroll.taxable_total = (
        payroll.base_salary
        + payroll.position_allowance
        + payroll.housing_allowance
        + payroll.overtime_pay
        + payroll.overtime_60_pay
        + payroll.night_pay
        + payroll.holiday_pay
        + payroll.absence_deduction  # マイナス値
    )

    # 非課税支給合計
    payroll.non_taxable_total = payroll.commuting_allowance

    # 支給合計
    payroll.gross_pay = payroll.taxable_total + payroll.non_taxable_total


def _calculate_deductions(payroll, employee, year_month):
    """控除額を計算する"""
    year = year_month.year

    # 保険料率の取得
    rate = _get_insurance_rate(year)

    # === 社会保険料（標準報酬月額ベース） ===
    std_rem = employee.standard_remuneration
    if std_rem <= 0:
        # 標準報酬月額未設定時は支給合計を代用（暫定）
        std_rem = payroll.gross_pay

    # 厚生年金（標準報酬月額 × 料率 / 2、切り上げ）
    if employee.pension_enrolled:
        payroll.pension_premium = math.ceil(
            std_rem * float(rate.pension_rate) / 100 / 2)
    else:
        payroll.pension_premium = 0

    # 健康保険（標準報酬月額 × 料率 / 2、切り上げ）
    if employee.health_enrolled:
        payroll.health_premium = math.ceil(
            std_rem * float(rate.health_rate) / 100 / 2)
    else:
        payroll.health_premium = 0

    # 介護保険（標準報酬月額 × 料率 / 2、切り上げ）
    if employee.nursing_enrolled:
        payroll.nursing_premium = math.ceil(
            std_rem * float(rate.nursing_rate) / 100 / 2)
    else:
        payroll.nursing_premium = 0

    # 雇用保険（支給合計 × 料率。折半しない！）
    if employee.employment_enrolled:
        payroll.employment_premium = math.ceil(
            payroll.gross_pay * float(rate.employment_rate_employee) / 100)
    else:
        payroll.employment_premium = 0

    payroll.social_insurance_total = (
        payroll.pension_premium
        + payroll.health_premium
        + payroll.nursing_premium
        + payroll.employment_premium
    )

    # === 所得税 ===
    taxable_amount = payroll.taxable_total - payroll.social_insurance_total
    if taxable_amount < 0:
        taxable_amount = 0

    payroll.income_tax = lookup_income_tax(
        taxable_amount, employee.dependents_count, year)

    # === 住民税 ===
    payroll.resident_tax = _get_resident_tax(
        employee, year_month.month, year_month.year)

    # === 控除合計 ===
    payroll.deduction_total = (
        payroll.social_insurance_total
        + payroll.income_tax
        + payroll.resident_tax
    )


def _get_insurance_rate(year):
    """年度の保険料率を取得"""
    # 4月〜翌3月の年度で検索
    fiscal_year = year if datetime.date.today().month >= 4 else year - 1
    try:
        return InsuranceRate.objects.get(fiscal_year=fiscal_year)
    except InsuranceRate.DoesNotExist:
        # 最新のものを返す
        rate = InsuranceRate.objects.first()
        if rate:
            return rate
        # デフォルト値で作成
        return InsuranceRate(
            fiscal_year=fiscal_year,
            pension_rate=Decimal('18.30'),
            health_rate=Decimal('9.98'),
            nursing_rate=Decimal('1.60'),
            employment_rate_employee=Decimal('0.600'),
        )


def lookup_income_tax(taxable_amount, dependents_count, fiscal_year):
    """
    源泉徴収税額表から所得税を検索する。

    Args:
        taxable_amount: 課税対象額（社会保険料控除後）
        dependents_count: 扶養家族人数（0〜7）
        fiscal_year: 年度

    Returns:
        int: 所得税額
    """
    if taxable_amount <= 0:
        return 0

    # 扶養人数は0〜7で制限
    dep = min(max(dependents_count, 0), 7)
    field_name = f'tax_dep_{dep}'

    try:
        row = WithholdingTaxRow.objects.filter(
            fiscal_year=fiscal_year,
            salary_from__lte=taxable_amount,
            salary_to__gt=taxable_amount,
        ).first()

        if row:
            return getattr(row, field_name, 0)

        # 見つからない場合、最も近い年度を試す
        row = WithholdingTaxRow.objects.filter(
            salary_from__lte=taxable_amount,
            salary_to__gt=taxable_amount,
        ).order_by('-fiscal_year').first()

        if row:
            return getattr(row, field_name, 0)

    except Exception:
        pass

    return 0


def _get_resident_tax(employee, month, year):
    """住民税特別徴収スケジュールから当月の天引き額を取得"""
    # 住民税年度: 6月〜翌5月
    if month >= 6:
        fiscal_year = year
    else:
        fiscal_year = year - 1

    try:
        schedule = ResidentTaxSchedule.objects.get(
            employee=employee, fiscal_year=fiscal_year)
        return schedule.get_amount_for_month(month)
    except ResidentTaxSchedule.DoesNotExist:
        return 0


def calculate_all_payrolls(year_month):
    """
    全社員の給与を一括計算する。

    勤怠データの取得方法:
      1. EDI_API_URL設定あり → EDI APIから取得（employee_idでマッチ）
      2. EDI_API_URL未設定 → 直接DB参照（フォールバック）

    Args:
        year_month: datetime.date（YYYY-MM-01）

    Returns:
        list of tuples: [(payroll, warnings), ...]
    """
    results = []
    employees = Employee.objects.filter(is_active=True)

    # EDI APIから勤怠データを取得（可能なら）
    api_timesheets = _fetch_timesheets_from_api(
        year_month.year, year_month.month
    )

    for emp in employees:
        warnings = []

        # 既に計算済みかチェック
        existing = Payroll.objects.filter(
            employee=emp, year_month=year_month).first()
        if existing and existing.status != 'DRAFT':
            warnings.append(f'{emp.name}: 既に確認済み/振込済みのためスキップ')
            results.append((existing, warnings))
            continue

        # 勤怠データの取得
        total_hours, work_days, ts_ref = _get_timesheet_data(
            emp, year_month, api_timesheets, warnings
        )

        payroll = calculate_payroll(
            employee=emp,
            year_month=year_month,
            timesheet=ts_ref,
            work_days=work_days,
            total_hours=total_hours,
        )

        # 既存の下書きがあれば上書き
        if existing:
            existing.delete()

        payroll.save()
        results.append((payroll, warnings))

    return results


def _fetch_timesheets_from_api(year, month):
    """
    EDI APIから勤怠データを取得する。
    API未設定またはエラー時はNoneを返す。

    Returns:
        list[dict] or None
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        from payroll.services.edi_api_client import EDIAPIClient
        client = EDIAPIClient()
        if not client.is_configured:
            return None
        timesheets = client.fetch_timesheets(year, month)
        logger.info(
            f'[Payroll] EDI APIから{len(timesheets)}件の勤怠データを取得'
        )
        return timesheets
    except Exception as e:
        logger.warning(f'[Payroll] EDI API取得失敗、DB直接参照に切替: {e}')
        return None


def _get_timesheet_data(emp, year_month, api_timesheets, warnings):
    """
    社員の勤怠データを取得する。

    Returns:
        tuple: (total_hours, work_days, timesheet_ref)
    """
    # ① API経由のデータがあればemployee_idでマッチ
    if api_timesheets is not None:
        matched = None
        # まずemployee_idで検索
        for ts_data in api_timesheets:
            if ts_data.get('employee_id') == emp.employee_id:
                matched = ts_data
                break
        # employee_id未設定ならworker_nameでフォールバック
        if not matched:
            for ts_data in api_timesheets:
                if ts_data.get('worker_name') == emp.name:
                    matched = ts_data
                    break

        if matched:
            return (
                float(matched.get('total_hours', 0)),
                int(matched.get('work_days', 0)),
                None,  # APIの場合timesheetオブジェクトなし
            )
        else:
            total_hours = float(emp.standard_monthly_hours)
            warnings.append(
                f'{emp.name}: EDI APIに勤怠データなし。所定時間で計算'
            )
            return total_hours, 20, None

    # ② フォールバック: 直接DB参照
    from billing.domain.models import StaffTimesheet

    # employee_idで検索（優先）
    ts = StaffTimesheet.objects.filter(
        employee_id=emp.employee_id,
        target_month=year_month,
        status__in=['SENT', 'APPROVED'],
    ).first()

    # employee_id未設定ならworker_nameでフォールバック
    if not ts:
        ts = StaffTimesheet.objects.filter(
            worker_name=emp.name,
            target_month=year_month,
            status__in=['SENT', 'APPROVED'],
        ).first()

    if ts:
        return float(ts.total_hours), ts.work_days, ts
    else:
        total_hours = float(emp.standard_monthly_hours)
        work_days = 20
        warnings.append(f'{emp.name}: 勤怠データなし。所定時間で計算')
        return total_hours, work_days, None
