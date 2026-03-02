from django import template

register = template.Library()

@register.filter
def filesizeformat_eng(bytes_value):
    """
    Format the value like a 'human-readable' file size (i.e. 13 KB, 4.1 MB, 102 bytes).
    Always returns English units: bytes, KB, MB, GB, TB, PB.
    """
    try:
        bytes_value = float(bytes_value)
    except (TypeError, ValueError, UnicodeDecodeError):
        return "0 bytes"

    if bytes_value < 1024:
        return f"{int(bytes_value)} bytes"
    
    kb = 1024
    mb = kb * 1024
    gb = mb * 1024
    tb = gb * 1024
    pb = tb * 1024

    if bytes_value < mb:
        return f"{bytes_value/kb:.1f} KB"
    if bytes_value < gb:
        return f"{bytes_value/mb:.1f} MB"
    if bytes_value < tb:
        return f"{bytes_value/gb:.1f} GB"
    if bytes_value < pb:
        return f"{bytes_value/tb:.1f} TB"
    
    return f"{bytes_value/pb:.1f} PB"
