"""
PayrollSystem API Views

社員マスタデータを外部システム（EDI等）に公開するAPIエンドポイント。
APIキー認証付き。
"""
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from core.api_auth import require_api_key
from payroll.domain.models import Employee


@method_decorator([csrf_exempt, require_api_key], name='dispatch')
class EmployeeListAPIView(View):
    """
    社員一覧API

    GET /payroll/api/employees/
    GET /payroll/api/employees/?active_only=true  (デフォルト: 有効な社員のみ)
    GET /payroll/api/employees/?active_only=false (全社員)

    Response:
    {
        "count": 3,
        "employees": [
            {
                "employee_id": "001",
                "name": "前野謙",
                "name_kana": "マエノケン",
                "is_active": true
            }
        ]
    }
    """

    def get(self, request):
        active_only = request.GET.get('active_only', 'true').lower() != 'false'

        qs = Employee.objects.all()
        if active_only:
            qs = qs.filter(is_active=True)

        employees = []
        for emp in qs.order_by('employee_id'):
            employees.append({
                'employee_id': emp.employee_id,
                'name': emp.name,
                'name_kana': emp.name_kana,
                'is_active': emp.is_active,
            })

        return JsonResponse({
            'count': len(employees),
            'employees': employees,
        })
