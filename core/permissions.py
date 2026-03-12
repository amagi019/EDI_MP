"""
core/permissions.py — ロールと権限の一元管理モジュール

全てのビューはこのモジュールのヘルパー関数・Mixin・デコレータを通じて
権限チェックを行う。直接 is_staff / hasattr(user, 'profile') を
ビュー内で書かないこと。
"""

from functools import wraps

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect


# ============================================================
# ロール定義
# ============================================================

class Role:
    """システム内で使用するロール定数"""
    STAFF = 'STAFF'
    PARTNER = 'PARTNER'
    ANONYMOUS = 'ANONYMOUS'


# ============================================================
# ヘルパー関数
# ============================================================

def get_user_role(user):
    """
    ユーザーのロールを判定して返す。
    - 未認証 → ANONYMOUS
    - is_staff=True → STAFF
    - それ以外 → PARTNER
    """
    if not user.is_authenticated:
        return Role.ANONYMOUS
    if user.is_staff:
        return Role.STAFF
    return Role.PARTNER


def get_user_partner(user):
    """
    ユーザーに紐付く Partner オブジェクトを安全に取得する。
    紐付けがない場合は None を返す。
    """
    try:
        if hasattr(user, 'profile') and user.profile.partner:
            return user.profile.partner
    except Exception:
        pass
    return None


def is_staff(user):
    """スタッフかどうかを判定（FBV用ショートカット）"""
    return get_user_role(user) == Role.STAFF


def is_partner(user):
    """パートナーかどうかを判定（FBV用ショートカット）"""
    return get_user_role(user) == Role.PARTNER


def is_owner_of_partner(user, partner):
    """ユーザーが指定パートナーの所有者かどうかを判定"""
    user_partner = get_user_partner(user)
    if user_partner is None or partner is None:
        return False
    return user_partner == partner


# ============================================================
# CBV Mixin — クラスベースビュー用
# ============================================================

class StaffRequiredMixin(LoginRequiredMixin):
    """
    スタッフ専用ビュー。
    非スタッフがアクセスすると PermissionDenied (403) を送出。
    """
    def dispatch(self, request, *args, **kwargs):
        if get_user_role(request.user) != Role.STAFF:
            raise PermissionDenied("この操作にはスタッフ権限が必要です。")
        return super().dispatch(request, *args, **kwargs)


class PartnerRequiredMixin(LoginRequiredMixin):
    """
    パートナー専用ビュー。
    スタッフや未登録ユーザーがアクセスすると PermissionDenied (403)。
    """
    def dispatch(self, request, *args, **kwargs):
        if get_user_role(request.user) != Role.PARTNER:
            raise PermissionDenied("この操作にはパートナー権限が必要です。")
        if get_user_partner(request.user) is None:
            raise PermissionDenied("パートナー情報が登録されていません。")
        return super().dispatch(request, *args, **kwargs)


class PartnerOwnerMixin:
    """
    パートナー本人のリソースのみアクセス可能にするMixin。
    get_partner_for_permission() をオーバーライドして対象パートナーを返す。
    """
    def get_partner_for_permission(self):
        """サブクラスで対象パートナーオブジェクトを返すようオーバーライド"""
        raise NotImplementedError(
            "get_partner_for_permission() を実装してください。"
        )

    def check_partner_ownership(self, request):
        """パートナー本人かどうかをチェック"""
        target_partner = self.get_partner_for_permission()
        if not is_owner_of_partner(request.user, target_partner):
            raise PermissionDenied("権限がありません。")
        return target_partner


class StaffOrOwnerMixin(LoginRequiredMixin):
    """
    スタッフまたはリソース所有パートナーがアクセス可能。
    - スタッフ → 無条件でアクセス許可
    - パートナー → 自分のリソースのみアクセス許可
    - それ以外 → PermissionDenied

    使い方: サブクラスで partner_field を指定するか、
    get_object_partner() をオーバーライドする。
    """
    partner_field = 'partner'  # モデル上の Partner FK フィールド名

    def get_object_partner(self, obj):
        """オブジェクトからパートナーを取得。ネストがある場合はオーバーライド"""
        return getattr(obj, self.partner_field, None)

    def check_object_permission(self, request, obj):
        """オブジェクトに対するアクセス権限をチェック"""
        role = get_user_role(request.user)
        if role == Role.STAFF:
            return  # スタッフは全アクセス可
        if role == Role.ANONYMOUS:
            raise PermissionDenied("ログインが必要です。")

        user_partner = get_user_partner(request.user)
        obj_partner = self.get_object_partner(obj)
        if user_partner is None:
            raise PermissionDenied("パートナー情報が登録されていません。")
        if obj_partner != user_partner:
            raise PermissionDenied("権限がありません。")


# ============================================================
# FBV デコレータ — 関数ベースビュー用
# ============================================================

def staff_required(view_func):
    """スタッフ専用ビューデコレータ（FBV用）"""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if get_user_role(request.user) != Role.STAFF:
            raise PermissionDenied("この操作にはスタッフ権限が必要です。")
        return view_func(request, *args, **kwargs)
    return _wrapped


def partner_required(view_func):
    """パートナー専用ビューデコレータ（FBV用）"""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if get_user_role(request.user) != Role.PARTNER:
            raise PermissionDenied("この操作にはパートナー権限が必要です。")
        if get_user_partner(request.user) is None:
            raise PermissionDenied("パートナー情報が登録されていません。")
        return view_func(request, *args, **kwargs)
    return _wrapped


def require_role(*roles):
    """指定されたロールのいずれかを持つユーザーのみ許可（FBV用）"""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            user_role = get_user_role(request.user)
            if user_role not in roles:
                raise PermissionDenied("この操作を実行する権限がありません。")
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator
