import os


LIMITES_ANUNCIOS_POR_PLANO = {
    'free': 3,
    'pro': 15,
    'empresa': 50,
}


def status_assinatura_bloqueada(status_assinatura):
    status = (status_assinatura or '').strip().lower()
    return status in {'vencida', 'cancelada', 'inadimplente', 'incompleta'}


def pausar_todos_anuncios_usuario(usuario_id, imovel_model):
    imovel_model.query.filter_by(usuario_id=usuario_id, ativo=True).update(
        {imovel_model.ativo: False},
        synchronize_session=False,
    )


def reativar_todos_anuncios_usuario(usuario_id, imovel_model):
    imovel_model.query.filter_by(usuario_id=usuario_id, ativo=False).update(
        {imovel_model.ativo: True},
        synchronize_session=False,
    )


def emails_admin_configurados(admin_emails_raw=None):
    """Retorna conjunto de emails administradores definidos em ADMIN_EMAILS."""
    bruto = admin_emails_raw if admin_emails_raw is not None else os.getenv('ADMIN_EMAILS', '')
    return {
        item.strip().lower()
        for item in bruto.split(',')
        if item.strip()
    }


def usuario_eh_admin(usuario, admin_emails_raw=None):
    """Verifica se o usuário atual está autorizado como administrador."""
    if not usuario:
        return False
    return (usuario.email or '').strip().lower() in emails_admin_configurados(admin_emails_raw)


def normalizar_plano(plano, limites_por_plano=LIMITES_ANUNCIOS_POR_PLANO):
    plano_normalizado = (plano or 'free').strip().lower()
    return plano_normalizado if plano_normalizado in limites_por_plano else 'free'


def limite_anuncios_usuario(usuario, limites_por_plano=LIMITES_ANUNCIOS_POR_PLANO):
    if not usuario:
        return limites_por_plano['free']

    if getattr(usuario, 'is_admin', False):
        return 999999

    limite_custom = getattr(usuario, 'limite_anuncios', None)
    if isinstance(limite_custom, int) and limite_custom > 0:
        return limite_custom

    plano_usuario = normalizar_plano(getattr(usuario, 'plano', 'free'), limites_por_plano)
    return limites_por_plano[plano_usuario]


def contar_anuncios_ativos(usuario_id, imovel_model):
    return imovel_model.query.filter_by(usuario_id=usuario_id, ativo=True).count()


def resumo_limite_anuncios(usuario, imovel_model, limites_por_plano=LIMITES_ANUNCIOS_POR_PLANO):
    usados = contar_anuncios_ativos(usuario.id, imovel_model)
    limite = limite_anuncios_usuario(usuario, limites_por_plano)
    disponiveis = max(0, limite - usados)
    return {
        'plano': normalizar_plano(getattr(usuario, 'plano', 'free'), limites_por_plano),
        'usados': usados,
        'limite': limite,
        'disponiveis': disponiveis,
        'atingiu_limite': usados >= limite,
    }
