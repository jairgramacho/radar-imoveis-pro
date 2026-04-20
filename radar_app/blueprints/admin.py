"""Blueprint de administracao de planos."""

import os

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from sqlalchemy import func

from models import Imovel, Usuario, db


admin_bp = Blueprint('admin', __name__)

LIMITES_ANUNCIOS_POR_PLANO = {
    'free': 3,
    'pro': 15,
    'empresa': 50,
}


def _usuario_logado_atual():
    usuario_id = session.get('usuario_id')
    if usuario_id:
        return Usuario.query.get(usuario_id)
    return None


def _emails_admin_configurados():
    bruto = os.getenv('ADMIN_EMAILS', '')
    return {
        item.strip().lower()
        for item in bruto.split(',')
        if item.strip()
    }


def _usuario_eh_admin(usuario):
    if not usuario:
        return False

    return (usuario.email or '').strip().lower() in _emails_admin_configurados()


def _normalizar_plano(plano):
    plano_normalizado = (plano or 'free').strip().lower()
    if plano_normalizado in LIMITES_ANUNCIOS_POR_PLANO:
        return plano_normalizado
    return 'free'


@admin_bp.route('/admin/planos', methods=['GET', 'POST'])
def admin_planos():
    """Painel simples de administracao de planos e limites de anuncios."""
    usuario = _usuario_logado_atual()

    if not usuario:
        flash('Voce precisa estar logado!', 'error')
        return redirect(url_for('login'))

    if not _usuario_eh_admin(usuario):
        flash('Acesso restrito a administradores.', 'error')
        return redirect(url_for('index', aba='buscar'))

    if request.method == 'POST':
        alvo_id = request.form.get('usuario_id', type=int)
        alvo = Usuario.query.get_or_404(alvo_id)

        plano = _normalizar_plano(request.form.get('plano'))
        status_assinatura = (request.form.get('status_assinatura') or 'ativa').strip().lower()
        if status_assinatura not in {'ativa', 'vencida', 'cancelada'}:
            status_assinatura = 'ativa'

        limite_custom_raw = (request.form.get('limite_anuncios') or '').strip()
        limite_final = LIMITES_ANUNCIOS_POR_PLANO[plano]
        if limite_custom_raw:
            try:
                limite_custom = int(limite_custom_raw)
                if limite_custom > 0:
                    limite_final = limite_custom
            except ValueError:
                pass

        alvo.plano = plano
        alvo.status_assinatura = status_assinatura
        alvo.limite_anuncios = limite_final

        db.session.commit()
        flash(f'Plano atualizado para {alvo.nome}.', 'success')
        return redirect(url_for('admin.admin_planos'))

    busca = (request.args.get('q') or '').strip()
    query = Usuario.query
    if busca:
        query = query.filter(
            Usuario.nome.ilike(f'%{busca}%') |
            Usuario.email.ilike(f'%{busca}%')
        )

    usuarios = query.order_by(Usuario.criado_em.desc()).limit(200).all()
    contagem_ativos = dict(
        db.session.query(Imovel.usuario_id, func.count(Imovel.id))
        .filter(Imovel.ativo.is_(True))
        .group_by(Imovel.usuario_id)
        .all()
    )

    return render_template(
        'admin_planos.html',
        usuario=usuario,
        usuarios=usuarios,
        busca=busca,
        contagem_ativos=contagem_ativos,
        limites_por_plano=LIMITES_ANUNCIOS_POR_PLANO,
    )
