from django import template

register = template.Library()

@register.filter
def format_currency(value):
    try:
        return "{:,}".format(int(value))
    except (ValueError, TypeError):
        return value
