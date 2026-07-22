from django import template
from django.template.defaultfilters import stringfilter
from django.utils.html import Urlizer
from django.utils.safestring import mark_safe

register = template.Library()


class ExternalUrlizer(Urlizer):
    url_template = (
        '<a href="{href}"{attrs} target="_blank" rel="noopener noreferrer">{url}</a>'
    )


external_urlizer = ExternalUrlizer()


@register.filter(is_safe=True, needs_autoescape=True)
@stringfilter
def external_urlize(value, autoescape=True):
    return mark_safe(external_urlizer(value, autoescape=autoescape))
