"""Blueprint de administracao de planos."""

import os

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from models import Imovel, Usuario, db
from radar_app.auth import UsuarioRepository
from radar_app.imoveis import ImovelRepository


admin_bp = Blueprint('admin', __name__)

LIMITES_ANUNCIOS_POR_PLANO = {
    'free': 3,
    'pro': 15,
    'empresa': 50,
}


def _usuario_logado_atual():
    usuario_id = session.get('usuario_id')
    if usuario_id:
        return _usuario_repo().buscar_por_id(usuario_id)
    return None


def _usuario_repo():
    return UsuarioRepository(db, Usuario)


def _imovel_repo():
    return ImovelRepository(db, Imovel)


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
        alvo = _usuario_repo().buscar_por_id_ou_404(alvo_id)

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

        _usuario_repo().commit()
        flash(f'Plano atualizado para {alvo.nome}.', 'success')
        return redirect(url_for('admin.admin_planos'))

    busca = (request.args.get('q') or '').strip()
    usuarios = _usuario_repo().listar_para_admin(busca, limite=200)
    contagem_ativos = _imovel_repo().contar_ativos_por_usuario_lote()

    return render_template(
        'admin_planos.html',
        usuario=usuario,
        usuarios=usuarios,
        busca=busca,
        contagem_ativos=contagem_ativos,
        limites_por_plano=LIMITES_ANUNCIOS_POR_PLANO,
    )
