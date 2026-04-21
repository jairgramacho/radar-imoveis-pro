"""
Blueprint de Faturamento e Assinatura Stripe.

Gerencia:
- Página de planos (visualização)
- Criação de sessões de checkout Stripe
- Webhook de eventos do Stripe
"""

import importlib
import logging
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, current_app
from models import db, Usuario, Imovel, StripeEventoWebhook
from radar_app.auth import UsuarioRepository
from radar_app.imoveis import ImovelRepository

billing_bp = Blueprint('billing', __name__)
logger = logging.getLogger(__name__)

# ============================================
# Constantes e Configuração
# ============================================

LIMITES_ANUNCIOS_POR_PLANO = {
    'free': 3,
    'pro': 15,
    'empresa': 50,
}

# ============================================
# Helpers de Stripe
# ============================================

_stripe_module_cache = None


def _stripe_client():
    """Retorna o cliente Stripe ou None se não disponível."""
    global _stripe_module_cache
    if _stripe_module_cache is not None:
        return _stripe_module_cache

    try:
        _stripe_module_cache = importlib.import_module('stripe')
    except Exception:
        _stripe_module_cache = False

    return _stripe_module_cache if _stripe_module_cache else None


def _stripe_price_ids_por_plano():
    """Retorna mapeamento de planos para Stripe price IDs."""
    return {
        'pro': (current_app.config.get('STRIPE_PRICE_PRO') or '').strip(),
        'empresa': (current_app.config.get('STRIPE_PRICE_EMPRESA') or '').strip(),
    }


def _stripe_checkout_habilitado():
    """Verifica se checkout do Stripe está disponível e configurado."""
    secret_key = (current_app.config.get('STRIPE_SECRET_KEY') or '').strip()
    price_ids = _stripe_price_ids_por_plano()
    return bool(secret_key and price_ids.get('pro') and price_ids.get('empresa'))


def _stripe_price_id_por_plano(plano):
    """Retorna o Stripe price ID para um plano específico."""
    return _stripe_price_ids_por_plano().get(_normalizar_plano(plano), '')


def _plano_por_stripe_price_id(price_id):
    """Retorna o nome do plano dado um Stripe price ID."""
    price_id = (price_id or '').strip()
    if not price_id:
        return None

    for plano, stripe_price in _stripe_price_ids_por_plano().items():
        if stripe_price and stripe_price == price_id:
            return plano
    return None


# ============================================
# Helpers de Negócio
# ============================================

def _normalizar_plano(plano):
    """Normaliza nome de plano para um dos valores reconhecidos."""
    plano_normalizado = (plano or 'free').strip().lower()
    return plano_normalizado if plano_normalizado in LIMITES_ANUNCIOS_POR_PLANO else 'free'


def _timestamp_para_datetime(timestamp):
    """Converte timestamp Unix para datetime."""
    try:
        return datetime.utcfromtimestamp(int(timestamp)) if timestamp else None
    except Exception:
        return None


def _buscar_usuario_por_stripe(customer_id=None, subscription_id=None, usuario_id=None):
    """Localiza usuário via Stripe customer_id, subscription_id ou usuario_id."""
    if usuario_id:
        return _usuario_repo().buscar_por_id(usuario_id)

    if subscription_id:
        usuario = _usuario_repo().buscar_por_stripe_subscription_id(subscription_id)
        if usuario:
            return usuario

    if customer_id:
        usuario = _usuario_repo().buscar_por_stripe_customer_id(customer_id)
        if usuario:
            return usuario

    return None


def _atualizar_assinatura_usuario(usuario, plano=None, status=None, renova_em=None, customer_id=None, subscription_id=None):
    """Atualiza dados de assinatura do usuário."""
    if plano:
        plano_normalizado = _normalizar_plano(plano)
        usuario.plano = plano_normalizado
        usuario.limite_anuncios = LIMITES_ANUNCIOS_POR_PLANO[plano_normalizado]

    if status:
        status_norm = (status or '').strip().lower()
        if status_norm in {'ativa', 'vencida', 'cancelada', 'inadimplente', 'incompleta'}:
            usuario.status_assinatura = status_norm

    if renova_em is not None:
        usuario.assinatura_renova_em = renova_em

    if customer_id:
        usuario.stripe_customer_id = customer_id

    if subscription_id:
        usuario.stripe_subscription_id = subscription_id


def _registrar_evento_webhook_stripe(event_id, event_type):
    """Registra evento Stripe para evitar processamento duplicado."""
    if not event_id:
        return False

    existente = StripeEventoWebhook.query.filter_by(stripe_event_id=event_id).first()
    if existente:
        return False

    db.session.add(StripeEventoWebhook(stripe_event_id=event_id, tipo=event_type))
    return True


# ============================================
# Importações de Negócio (evitar circular import)
# ============================================

def _usuario_logado_atual():
    """Retorna usuário logado na sessão atual."""
    usuario_id = session.get('usuario_id')
    if usuario_id:
        return _usuario_repo().buscar_por_id(usuario_id)
    return None


def _usuario_repo():
    return UsuarioRepository(db, Usuario)


def _imovel_repo():
    return ImovelRepository(db, Imovel)


def _status_assinatura_bloqueada(status_assinatura):
    """Verifica se status indica assinatura bloqueada."""
    status = (status_assinatura or '').strip().lower()
    return status in {'vencida', 'cancelada', 'inadimplente', 'incompleta'}


def _pausar_todos_anuncios_usuario(usuario_id):
    """Pausa todos os anúncios ativos do usuário."""
    _imovel_repo().pausar_todos_anuncios_usuario(usuario_id)


def _reativar_todos_anuncios_usuario(usuario_id):
    """Reativa todos os anúncios inativos do usuário."""
    _imovel_repo().reativar_todos_anuncios_usuario(usuario_id)


# ============================================
# ROTAS
# ============================================

@billing_bp.route('/planos')
def planos():
    """Página pública com os planos disponíveis e seus preços"""
    planos_info = [
        {
            'nome': 'Free',
            'descricao': 'Para quem está começando',
            'preco': 'Grátis',
            'limite_anuncios': 3,
            'features': [
                '3 anúncios ativos',
                'Contato via WhatsApp',
                'Chat integrado',
                'Visualizações básicas',
            ],
            'botao': False,
            'classe': 'card-gratuito'
        },
        {
            'nome': 'Pro',
            'descricao': 'Para profissionais',
            'preco': f'R$ {current_app.config["PRECO_PRO_BRL"]:.2f}',
            'preco_raw': current_app.config['PRECO_PRO_BRL'],
            'limite_anuncios': 15,
            'features': [
                '15 anúncios ativos',
                'Contato via WhatsApp',
                'Chat integrado',
                'Visualizações e estatísticas',
                'Destaque em buscas',
                'Suporte prioritário',
            ],
            'botao': True,
            'classe': 'card-pro'
        },
        {
            'nome': 'Empresa',
            'descricao': 'Para grandes operações',
            'preco': f'R$ {current_app.config["PRECO_EMPRESA_BRL"]:.2f}',
            'preco_raw': current_app.config['PRECO_EMPRESA_BRL'],
            'limite_anuncios': 50,
            'features': [
                '50 anúncios ativos',
                'Contato via WhatsApp',
                'Chat integrado',
                'Visualizações e estatísticas avançadas',
                'Destaque premium em buscas',
                'Suporte 24/7',
                'Análises personalizadas',
            ],
            'botao': True,
            'classe': 'card-empresa'
        },
    ]

    usuario = _usuario_logado_atual()

    return render_template('planos.html',
                          planos=planos_info,
                          usuario=usuario,
                          stripe_checkout_habilitado=_stripe_checkout_habilitado())


@billing_bp.route('/assinatura/checkout', methods=['POST'])
def assinatura_checkout():
    """Cria sessão de checkout Stripe para upgrade de plano."""
    usuario = _usuario_logado_atual()
    if not usuario:
        flash('Você precisa estar logado!', 'error')
        return redirect(url_for('login'))

    stripe_client = _stripe_client()
    if stripe_client is None:
        flash('Stripe não está disponível no servidor. Instale as dependências e tente novamente.', 'error')
        return redirect(url_for('dashboard'))

    if not _stripe_checkout_habilitado():
        flash('Assinaturas indisponíveis no momento. Stripe não está configurado.', 'error')
        return redirect(url_for('dashboard'))

    plano = _normalizar_plano(request.form.get('plano'))
    if plano not in {'pro', 'empresa'}:
        flash('Plano inválido para assinatura.', 'error')
        return redirect(url_for('dashboard'))

    price_id = _stripe_price_id_por_plano(plano)
    if not price_id:
        flash('Preço do plano não configurado no Stripe.', 'error')
        return redirect(url_for('dashboard'))

    try:
        stripe_client.api_key = (current_app.config.get('STRIPE_SECRET_KEY') or '').strip()
        success_url = f"{current_app.config['APP_URL']}{url_for('dashboard')}?assinatura=sucesso"
        cancel_url = f"{current_app.config['APP_URL']}{url_for('dashboard')}?assinatura=cancelada"

        checkout_session = stripe_client.checkout.Session.create(
            mode='subscription',
            line_items=[{
                'price': price_id,
                'quantity': 1,
            }],
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=usuario.email,
            client_reference_id=str(usuario.id),
            metadata={
                'usuario_id': str(usuario.id),
                'plano': plano,
            },
        )

        if checkout_session.get('customer'):
            usuario.stripe_customer_id = checkout_session.get('customer')
            _usuario_repo().commit()

        return redirect(checkout_session.url, code=303)
    except Exception as e:
        current_app.logger.warning('Falha ao criar checkout Stripe: %s', str(e), exc_info=True)
        flash('Não foi possível iniciar o pagamento agora. Tente novamente em instantes.', 'error')
        return redirect(url_for('dashboard'))


@billing_bp.route('/webhooks/stripe', methods=['POST'])
def stripe_webhook():
    """Recebe eventos Stripe e atualiza assinatura automaticamente."""
    stripe_client = _stripe_client()
    if stripe_client is None:
        return jsonify({'ok': False, 'erro': 'stripe_indisponivel'}), 500

    webhook_secret = (current_app.config.get('STRIPE_WEBHOOK_SECRET') or '').strip()
    if not webhook_secret:
        return jsonify({'ok': False, 'erro': 'webhook_nao_configurado'}), 500

    payload = request.get_data()
    signature = request.headers.get('Stripe-Signature', '')

    try:
        stripe_client.api_key = (current_app.config.get('STRIPE_SECRET_KEY') or '').strip()
        event = stripe_client.Webhook.construct_event(payload, signature, webhook_secret)
    except ValueError:
        return jsonify({'ok': False, 'erro': 'payload_invalido'}), 400
    except stripe_client.error.SignatureVerificationError:
        return jsonify({'ok': False, 'erro': 'assinatura_invalida'}), 400
    except Exception:
        return jsonify({'ok': False, 'erro': 'falha_validacao'}), 400

    event_id = event.get('id')
    event_type = event.get('type') or ''

    try:
        if not _registrar_evento_webhook_stripe(event_id, event_type):
            db.session.rollback()
            return jsonify({'ok': True, 'duplicado': True})

        data = event.get('data', {}).get('object', {})
        usuario = None

        if event_type == 'checkout.session.completed':
            metadata = data.get('metadata') or {}
            usuario_id = metadata.get('usuario_id') or data.get('client_reference_id')
            try:
                usuario_id = int(usuario_id) if usuario_id else None
            except (TypeError, ValueError):
                usuario_id = None

            usuario = _buscar_usuario_por_stripe(
                customer_id=data.get('customer'),
                subscription_id=data.get('subscription'),
                usuario_id=usuario_id,
            )

            if usuario:
                plano = _normalizar_plano(metadata.get('plano'))
                renova_em = None
                subscription_id = data.get('subscription')
                if subscription_id:
                    try:
                        sub = stripe_client.Subscription.retrieve(subscription_id)
                        renova_em = _timestamp_para_datetime(sub.get('current_period_end'))
                    except Exception:
                        renova_em = None

                _atualizar_assinatura_usuario(
                    usuario,
                    plano=plano,
                    status='ativa',
                    renova_em=renova_em,
                    customer_id=data.get('customer'),
                    subscription_id=subscription_id,
                )
                _reativar_todos_anuncios_usuario(usuario.id)

        elif event_type in {'customer.subscription.created', 'customer.subscription.updated'}:
            items = ((data.get('items') or {}).get('data') or [])
            price_id = ''
            if items:
                price_id = (((items[0] or {}).get('price') or {}).get('id') or '').strip()
            plano_evento = _plano_por_stripe_price_id(price_id)

            status_stripe = (data.get('status') or '').strip().lower()
            status_local = 'ativa'
            if status_stripe in {'past_due', 'unpaid'}:
                status_local = 'inadimplente'
            elif status_stripe in {'canceled'}:
                status_local = 'cancelada'
            elif status_stripe in {'incomplete', 'incomplete_expired'}:
                status_local = 'incompleta'

            usuario = _buscar_usuario_por_stripe(
                customer_id=data.get('customer'),
                subscription_id=data.get('id'),
            )

            if usuario:
                _atualizar_assinatura_usuario(
                    usuario,
                    plano=plano_evento,
                    status=status_local,
                    renova_em=_timestamp_para_datetime(data.get('current_period_end')),
                    customer_id=data.get('customer'),
                    subscription_id=data.get('id'),
                )
                if _status_assinatura_bloqueada(status_local):
                    _pausar_todos_anuncios_usuario(usuario.id)
                else:
                    _reativar_todos_anuncios_usuario(usuario.id)

        elif event_type == 'invoice.payment_failed':
            usuario = _buscar_usuario_por_stripe(
                customer_id=data.get('customer'),
                subscription_id=data.get('subscription'),
            )
            if usuario:
                _atualizar_assinatura_usuario(usuario, status='inadimplente')
                _pausar_todos_anuncios_usuario(usuario.id)

        elif event_type == 'invoice.payment_succeeded':
            usuario = _buscar_usuario_por_stripe(
                customer_id=data.get('customer'),
                subscription_id=data.get('subscription'),
            )
            if usuario:
                _atualizar_assinatura_usuario(usuario, status='ativa')
                _reativar_todos_anuncios_usuario(usuario.id)

        elif event_type == 'customer.subscription.deleted':
            usuario = _buscar_usuario_por_stripe(
                customer_id=data.get('customer'),
                subscription_id=data.get('id'),
            )
            if usuario:
                _atualizar_assinatura_usuario(
                    usuario,
                    plano='free',
                    status='cancelada',
                    renova_em=None,
                )
                _pausar_todos_anuncios_usuario(usuario.id)

        db.session.commit()
        return jsonify({'ok': True})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error('Erro ao processar webhook Stripe: %s', str(e), exc_info=True)
        return jsonify({'ok': False, 'erro': 'falha_processamento'}), 500
