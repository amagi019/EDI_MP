"""
API認証ユーティリティ

EDI ↔ PayrollSystem 間のAPI通信で使用する認証デコレータ。
X-API-Key ヘッダーによるAPIキー認証を提供する。
"""
import functools
from django.conf import settings
from django.http import JsonResponse


def require_api_key(view_func):
    """
    APIキー認証デコレータ。

    リクエストヘッダー X-API-Key が settings.EDI_API_KEY と一致することを検証する。
    不一致または未設定の場合は 403 Forbidden を返却。

    Usage:
        @require_api_key
        def my_api_view(request):
            ...

    クラスベースビューで使用する場合:
        @method_decorator(require_api_key, name='dispatch')
        class MyAPIView(View):
            ...
    """
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        api_key = getattr(settings, 'EDI_API_KEY', '')
        if not api_key:
            return JsonResponse(
                {'error': 'API key not configured on server'},
                status=500
            )

        provided_key = request.headers.get('X-API-Key', '')
        if not provided_key or provided_key != api_key:
            return JsonResponse(
                {'error': 'Invalid or missing API key'},
                status=403
            )

        return view_func(request, *args, **kwargs)
    return wrapper
