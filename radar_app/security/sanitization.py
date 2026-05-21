"""XSS Protection: Sanitização de entrada de usuários (OWASP)."""

import bleach
from html import unescape


# Tags HTML permitidas em descrições
ALLOWED_TAGS_DESCRICAO = ['p', 'br', 'strong', 'em', 'u', 'a', 'ul', 'ol', 'li']
ALLOWED_ATTRIBUTES = {'a': ['href', 'title']}
ALLOWED_PROTOCOLS = ['http', 'https', 'mailto']


def sanitizar_descricao(texto):
    """
    Sanitiza descrição de imóvel/perfil.
    Remove scripts, JS, eventos inline.
    Permite formatting básico (bold, italic, links).
    """
    if not texto:
        return ''
    
    texto = str(texto).strip()
    
    # Remove null bytes e caracteres de controle
    texto = ''.join(char for char in texto if ord(char) >= 32 or char in '\n\r\t')
    
    # Sanitiza com bleach
    sanitizado = bleach.clean(
        texto,
        tags=ALLOWED_TAGS_DESCRICAO,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True
    )
    
    # Decode HTML entities (ex: &amp; → &)
    sanitizado = unescape(sanitizado)
    
    return sanitizado[:1000]  # Máximo 1000 caracteres


def sanitizar_mensagem_chat(texto):
    """
    Sanitiza mensagens de chat.
    Remove TODA a formatação HTML (apenas texto limpo).
    """
    if not texto:
        return ''
    
    texto = str(texto).strip()
    
    # Remove null bytes
    texto = ''.join(char for char in texto if ord(char) >= 32 or char in '\n\r\t')
    
    # Remove HTML completamente
    sanitizado = bleach.clean(texto, tags=[], strip=True)
    
    # Decode entities
    sanitizado = unescape(sanitizado)
    
    return sanitizado[:5000]  # Máximo 5000 caracteres


def sanitizar_nome(texto):
    """Sanitiza nome de usuário (apenas alfanumérico + espaço)."""
    if not texto:
        return ''
    
    texto = str(texto).strip()
    
    # Remove caracteres especiais, mantém apenas letras, números e espaço
    sanitizado = ''.join(char for char in texto if char.isalnum() or char in ' -.')
    
    return sanitizado[:120]


def sanitizar_email(texto):
    """Sanitiza email (remove scripts, mantém formato)."""
    if not texto:
        return ''
    
    texto = str(texto).strip().lower()
    
    # Remove caracteres HTML/script
    sanitizado = bleach.clean(texto, tags=[], strip=True)
    
    return sanitizado[:120]
