from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET

from core.domain.models import BankMaster


@login_required
@require_GET
def bank_search(request):
    """銀行名で前方一致検索する API。

    GET /api/banks/?q=みず
    → [{"bank_code": "0001", "bank_name": "みずほ銀行"}, ...]
    """
    q = request.GET.get('q', '').strip()
    if len(q) < 1:
        return JsonResponse([], safe=False)

    # 銀行コードでの完全一致 or 銀行名での部分一致
    qs = BankMaster.objects.filter(bank_name__icontains=q)
    # 同じ銀行コード+銀行名で重複除去して返す
    banks = (
        qs.values('bank_code', 'bank_name')
        .distinct()
        .order_by('bank_code')[:20]
    )
    return JsonResponse(list(banks), safe=False)


@login_required
@require_GET
def branch_search(request, bank_code):
    """指定銀行コードの支店を前方一致検索する API。

    GET /api/banks/0001/branches/?q=しぶ
    → [{"branch_code": "210", "branch_name": "渋谷支店"}, ...]
    """
    q = request.GET.get('q', '').strip()
    qs = BankMaster.objects.filter(bank_code=bank_code)
    if q:
        qs = qs.filter(branch_name__icontains=q)
    branches = (
        qs.values('branch_code', 'branch_name')
        .order_by('branch_code')[:20]
    )
    return JsonResponse(list(branches), safe=False)
