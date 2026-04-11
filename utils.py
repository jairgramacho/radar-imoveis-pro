from flask import session
from models import Usuario

LIMITES_ANUNCIOS_POR_PLANO = {
    'free': 3,
    'pro': 20,
    'empresa': 100,
}


def get_usuario_logado():
    """Retorna o usuário logado ou None"""
    usuario_id = session.get('usuario_id')
    if usuario_id:
        return Usuario.query.get(usuario_id)
    return None


def _normalizar_plano(plano):
    plano_normalizado = (plano or 'free').strip().lower()
    return plano_normalizado if plano_normalizado in LIMITES_ANUNCIOS_POR_PLANO else 'free'
