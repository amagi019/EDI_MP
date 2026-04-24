import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import Order

logger = logging.getLogger(__name__)


def _verify_webhook_signature(request):
    """
    Webhook リクエストの HMAC-SHA256 署名を検証する。

    外部サービスは X-Webhook-Signature ヘッダに
    HMAC-SHA256(secret, body) の hex digest を付与すること。
    """
    secret = getattr(settings, 'WEBHOOK_SECRET', None)
    if not secret:
        logger.error("[Webhook] WEBHOOK_SECRET が設定されていません")
        return False

    signature = request.headers.get('X-Webhook-Signature', '')
    if not signature:
        return False

    expected = hmac.new(
        secret.encode('utf-8'),
        request.body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(signature, expected)


@csrf_exempt
@require_POST
def signature_webhook(request):
    """
    外部電子署名サービス（Google Docs API等）からのWebhookを受領し、
    注文書や契約書のステータスを自動更新するエンドポイント。

    認証: X-Webhook-Signature ヘッダによる HMAC-SHA256 署名検証。
    """
    # 署名検証
    if not _verify_webhook_signature(request):
        logger.warning(f"[Webhook] 署名検証失敗: {request.META.get('REMOTE_ADDR')}")
        return JsonResponse({'status': 'error', 'message': 'Invalid signature'}, status=403)

    try:
        data = json.loads(request.body)
        signature_id = data.get('signature_id')
        event_type = data.get('event_type')  # 例: 'document_signed'

        if not signature_id:
            return JsonResponse({'status': 'error', 'message': 'signature_id is required'}, status=400)

        order = Order.objects.filter(external_signature_id=signature_id).first()
        if not order:
            logger.warning(f"[Webhook] Order with signature_id {signature_id} not found.")
            return JsonResponse({'status': 'error', 'message': 'Order not found'}, status=404)

        if event_type == 'document_signed':
            # ステータスを「受領済（または署名済）」に自動更新
            if order.status != 'APPROVED':
                order.status = 'APPROVED'
                order.save()
            logger.info(f"[Webhook] Order {order.order_id} signed via external service.")

        return JsonResponse({'status': 'success'})
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"[Webhook] Internal error: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
