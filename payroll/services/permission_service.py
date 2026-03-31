"""
給与権限サービス

ビューから呼び出される権限チェックロジック。
"""
from payroll.domain.permissions import PayrollPermission


def get_payroll_permission(user):
    """ユーザーの給与権限を取得。未設定なら新規作成。"""
    perm, _ = PayrollPermission.objects.get_or_create(
        user=user,
        defaults={
            'permission_level': 'ALL' if user.is_superuser else 'SELF_ONLY',
            'can_calculate': user.is_superuser,
            'can_approve': user.is_superuser,
            'can_transfer': user.is_superuser,
        }
    )
    return perm


def can_view_all_payrolls(user):
    """全社員の給与を閲覧できるか"""
    if user.is_superuser:
        return True
    perm = get_payroll_permission(user)
    return perm.permission_level == 'ALL'


def can_calculate_payroll(user):
    """給与計算を実行できるか"""
    if user.is_superuser:
        return True
    perm = get_payroll_permission(user)
    return perm.can_calculate


def can_approve_payroll(user):
    """給与を承認できるか"""
    if user.is_superuser:
        return True
    perm = get_payroll_permission(user)
    return perm.can_approve


def can_transfer_payroll(user):
    """振込を実行できるか"""
    if user.is_superuser:
        return True
    perm = get_payroll_permission(user)
    return perm.can_transfer


def get_linked_employee(user):
    """ユーザーに紐付く社員を取得"""
    perm = get_payroll_permission(user)
    return perm.employee


def get_viewable_employees(user):
    """閲覧可能な社員リストを返す"""
    from payroll.domain.models import Employee
    if can_view_all_payrolls(user):
        return Employee.objects.filter(is_active=True)

    perm = get_payroll_permission(user)
    if perm.employee:
        return Employee.objects.filter(pk=perm.employee.pk)
    return Employee.objects.none()
