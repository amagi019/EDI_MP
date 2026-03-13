from django import template

register = template.Library()

@register.filter
def format_currency(value):
    try:
        return "{:,}".format(int(value))
    except (ValueError, TypeError):
        return value


@register.simple_tag
def get_partner_id(user):
    """ログインユーザーのpartner_idを返す。パートナーでない場合は空文字。"""
    try:
        profile = getattr(user, 'profile', None)
        if profile and profile.partner:
            return profile.partner.partner_id
    except Exception:
        pass
    return ''
