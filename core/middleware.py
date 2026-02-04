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
