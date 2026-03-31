"""PWA用ビュー（Service Worker / Manifest配信）"""
import os
from django.http import HttpResponse
from django.conf import settings


def service_worker_view(request):
    """Service Workerをルートパスから配信"""
    sw_path = os.path.join(settings.BASE_DIR, 'core', 'static', 'core', 'service-worker.js')
    with open(sw_path, 'r') as f:
        return HttpResponse(f.read(), content_type='application/javascript')


def manifest_view(request):
    """PWAマニフェストをルートパスから配信"""
    manifest_path = os.path.join(settings.BASE_DIR, 'core', 'static', 'core', 'manifest.json')
    with open(manifest_path, 'r') as f:
        return HttpResponse(f.read(), content_type='application/json')
