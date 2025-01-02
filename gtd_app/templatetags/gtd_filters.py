from django import template

register = template.Library()

@register.filter
def isinstance(value, class_name):
    """Check if an object is an instance of a class by its name."""
    return value.__class__.__name__ == class_name 