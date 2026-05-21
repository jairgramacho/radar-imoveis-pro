"""Rate Limiting para endpoints críticos (brute force protection)."""

from flask import current_app


def aplicar_rate_limit_login(limiter):
    """Retorna decorador para rate limit em login (5 tentativas/15min)."""
    return limiter.limit("5 per 15 minutes")


def aplicar_rate_limit_cadastro(limiter):
    """Retorna decorador para rate limit em cadastro (3/hora por IP)."""
    return limiter.limit("3 per hour")


def aplicar_rate_limit_chat(limiter):
    """Retorna decorador para rate limit em chat (30 msgs/hora por IP)."""
    return limiter.limit("30 per hour")


def aplicar_rate_limit_upload(limiter):
    """Retorna decorador para rate limit em upload (10 uploads/hora por IP)."""
    return limiter.limit("10 per hour")


def aplicar_rate_limit_email(limiter):
    """Retorna decorador para rate limit em envio de email (3/hora)."""
    return limiter.limit("3 per hour")
