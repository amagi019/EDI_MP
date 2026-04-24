import os

from django.shortcuts import redirect
from django.urls import reverse, resolve

class FirstLoginMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            # 管理者（スタッフまたはスーパーユーザー）は強制リダイレクトの対象外とする
            if request.user.is_staff or request.user.is_superuser:
                return self.get_response(request)

            # プロフィールが存在し、かつ初回ログインフラグがTrueの場合
            if hasattr(request.user, 'profile') and request.user.profile.is_first_login:
                allowed_url_names = [
                    'password_change',
                    'password_change_done',
                    'logout',
                    # admin関連は request.path で判定済みだが、念のため
                    'admin:index',
                    'admin:logout',
                ]
                
                # 現在のURL名を取得
                current_url_name = request.resolver_match.view_name if request.resolver_match else None
                if not current_url_name:
                    try:
                        current_url_name = resolve(request.path).view_name
                    except:
                        current_url_name = None
                
                # 許可リストにない、かつ管理者画面等でない場合はリダイレクト
                # リダイレクトループ防止のため、password_change 自身へのアクセスは許可
                if current_url_name not in allowed_url_names and not request.path.startswith('/admin/'):
                    return redirect('password_change')
        
        return self.get_response(request)


class MaintenanceMiddleware:
    """
    メンテナンスモード用ミドルウェア。
    MAINTENANCE_MODE_FILE が存在する場合、管理者以外に503を返す。
    """
    MAINTENANCE_FLAG = os.environ.get(
        'MAINTENANCE_MODE_FILE', '/tmp/maintenance.flag'
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        import os
        if os.path.exists(self.MAINTENANCE_FLAG):
            # static / media は通す
            if request.path.startswith(('/static/', '/media/')):
                return self.get_response(request)
            # 管理者（staff）はメンテナンス中もアクセス可能
            if hasattr(request, 'user') and request.user.is_authenticated and request.user.is_staff:
                return self.get_response(request)
            # メンテナンス画面を返す
            from django.http import HttpResponse
            html = self._maintenance_html()
            return HttpResponse(html, status=503, content_type='text/html; charset=utf-8')
        return self.get_response(request)

    @staticmethod
    def _maintenance_html():
        return """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>メンテナンス中 | EDIシステム</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Outfit:wght@700&display=swap" rel="stylesheet">
<style>
body{font-family:'Inter',sans-serif;background:#0F172A;color:#F8FAFC;margin:0;display:flex;align-items:center;justify-content:center;min-height:100vh;}
.box{text-align:center;max-width:480px;padding:3rem 2rem;}
.icon{font-size:4rem;margin-bottom:1rem;}
h1{font-family:'Outfit',sans-serif;font-size:1.8rem;margin:0 0 1rem;background:linear-gradient(135deg,#818CF8,#C084FC);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;}
p{color:#94A3B8;line-height:1.8;margin:0;}
.dots{margin-top:2rem;}
.dots span{display:inline-block;width:8px;height:8px;border-radius:50%;background:#818CF8;margin:0 4px;animation:bounce 1.4s infinite both;}
.dots span:nth-child(2){animation-delay:0.2s;}
.dots span:nth-child(3){animation-delay:0.4s;}
@keyframes bounce{0%,80%,100%{transform:scale(0);opacity:0.3;}40%{transform:scale(1);opacity:1;}}
</style>
</head>
<body>
<div class="box">
<div class="icon">🔧</div>
<h1>メンテナンス中</h1>
<p>ただいまシステムの更新作業を行っております。<br>しばらくお待ちください。</p>
<div class="dots"><span></span><span></span><span></span></div>
</div>
</body>
</html>"""
