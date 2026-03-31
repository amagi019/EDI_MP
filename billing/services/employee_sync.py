"""
社員データ同期サービス

PayrollSystemの社員マスタAPIからデータを取得し、
EDI側の SyncedEmployee テーブルに同期する。
"""
import json
import logging
import urllib.request
import urllib.error
from django.conf import settings
from django.utils import timezone

from billing.domain.synced_employee import SyncedEmployee

logger = logging.getLogger(__name__)


def sync_employees():
    """
    PayrollSystemの社員マスタAPIから全社員を取得し、
    SyncedEmployee テーブルを更新する。

    Returns:
        dict: 同期結果
            - created: 新規作成数
            - updated: 更新数
            - deactivated: 非活性化数
            - errors: エラーリスト
    """
    payroll_url = getattr(settings, 'PAYROLL_API_URL', '')
    api_key = getattr(settings, 'EDI_API_KEY', '')

    result = {
        'created': 0,
        'updated': 0,
        'deactivated': 0,
        'errors': [],
    }

    if not payroll_url:
        result['errors'].append('PAYROLL_API_URL が設定されていません')
        return result

    if not api_key:
        result['errors'].append('EDI_API_KEY が設定されていません')
        return result

    # APIを呼び出し
    url = f"{payroll_url.rstrip('/')}/payroll/api/employees/?active_only=false"
    req = urllib.request.Request(url)
    req.add_header('X-API-Key', api_key)
    req.add_header('Accept', 'application/json')

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        msg = f'PayrollSystem API エラー: HTTP {e.code}'
        logger.error(msg)
        result['errors'].append(msg)
        return result
    except urllib.error.URLError as e:
        msg = f'PayrollSystem 接続エラー: {e.reason}'
        logger.error(msg)
        result['errors'].append(msg)
        return result
    except Exception as e:
        msg = f'PayrollSystem API 通信エラー: {e}'
        logger.error(msg)
        result['errors'].append(msg)
        return result

    employees = data.get('employees', [])
    now = timezone.now()

    # 受信した社員IDを追跡
    received_ids = set()

    for emp_data in employees:
        employee_id = emp_data.get('employee_id', '')
        if not employee_id:
            continue

        received_ids.add(employee_id)

        obj, created = SyncedEmployee.objects.update_or_create(
            employee_id=employee_id,
            defaults={
                'name': emp_data.get('name', ''),
                'name_kana': emp_data.get('name_kana', ''),
                'is_active': emp_data.get('is_active', True),
                'synced_at': now,
            }
        )

        if created:
            result['created'] += 1
            logger.info(f'[EmployeeSync] 新規: {employee_id} {obj.name}')
        else:
            result['updated'] += 1

    # PayrollSystemで削除/非活性化された社員を非活性化
    deactivated = SyncedEmployee.objects.filter(
        is_active=True
    ).exclude(
        employee_id__in=received_ids
    ).update(is_active=False, synced_at=now)

    result['deactivated'] = deactivated

    total = result['created'] + result['updated']
    logger.info(
        f'[EmployeeSync] 同期完了: '
        f'新規{result["created"]} 更新{result["updated"]} '
        f'非活性化{result["deactivated"]} (合計{total}件)'
    )

    return result
