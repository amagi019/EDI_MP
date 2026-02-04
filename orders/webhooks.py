import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .models import Order

logger = logging.getLogger(__name__)

@csrf_exempt
@require_POST
def signature_webhook(request):
    """
    外部電子署名サービス（Google Docs API等）からのWebhookを受領し、
    注文書や契約書のステータスを自動更新するプロトタイプエンドポイント。
    """
    try:
        data = json.loads(request.body)
        signature_id = data.get('signature_id')
        event_type = data.get('event_type') # 例: 'document_signed'
        
        if not signature_id:
            return JsonResponse({'status': 'error', 'message': 'signature_id is required'}, status=400)

        order = Order.objects.filter(external_signature_id=signature_id).first()
        if not order:
            logger.warning(f"Webhook error: Order with signature_id {signature_id} not found.")
            return JsonResponse({'status': 'error', 'message': 'Order not found'}, status=404)

        if event_type == 'document_signed':
            # ステータスを「受領済（または署名済）」に自動更新
            if order.status != 'APPROVED':
                order.status = 'APPROVED'
                order.save()
            logger.info(f"Order {order.order_id} has been signed via external service (Webhook).")

        return JsonResponse({'status': 'success'})
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Webhook internal error: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
