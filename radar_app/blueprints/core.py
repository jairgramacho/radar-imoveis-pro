"""Blueprint com rotas centrais da aplicação."""

import io
from datetime import datetime

from flask import Blueprint, Response, current_app, flash, jsonify, redirect, render_template, request, url_for
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import text

from models import Imovel, Mensagem, db
from radar_app.blueprints.billing import _stripe_checkout_habilitado
from radar_app.imoveis import ImovelRepository


core_bp = Blueprint('core', __name__)


def _legacy():
    from radar_app import legacy_app

    return legacy_app


def _imovel_repo():
    return ImovelRepository(db, Imovel)


@core_bp.route('/healthz')
def healthcheck():
    """Healthcheck simples para monitoramento do serviço."""
    legacy = _legacy()

    try:
        db.session.execute(text('SELECT 1'))
        db_status = 'ok'
    except Exception:
        db_status = 'error'

    payload = {
        'status': 'ok' if db_status == 'ok' else 'degraded',
        'service': 'radar-imoveis-pro',
        'database': db_status,
        'email_configurado': legacy._smtp_configurado(),
        'smtp_configurado': legacy._smtp_configurado(),
    }
    return jsonify(payload), (200 if db_status == 'ok' else 503)


@core_bp.route('/healthz/ready', methods=['GET'])
def readiness_check():
    """Verifica se o app está pronto para receber requisições."""
    legacy = _legacy()

    try:
        db.session.execute(text('SELECT 1'))

        payload = {
            'status': 'ready',
            'service': 'radar-imoveis-pro',
            'database': 'ok',
            'email': 'ok' if legacy._smtp_configurado() else 'unconfigured',
            'stripe': 'ok' if _stripe_checkout_habilitado() else 'unconfigured',
        }
        return jsonify(payload), 200
    except Exception as e:
        current_app.logger.error('Readiness check falhou: %s', str(e), exc_info=True)
        return jsonify({'status': 'not_ready', 'erro': str(e)}), 503


@core_bp.route('/robots.txt')
def robots_txt():
    """Serve robots.txt para orientar rastreadores."""
    return current_app.send_static_file('robots.txt')


@core_bp.route('/sitemap.xml')
def sitemap_xml():
    """Gera sitemap dinâmico com páginas principais e imóveis ativos."""
    hoje = datetime.utcnow().strftime('%Y-%m-%d')
    urls = [
        {
            'loc': url_for('index', _external=True),
            'lastmod': hoje,
            'changefreq': 'hourly',
            'priority': '1.0',
        },
        {
            'loc': url_for('index', aba='oportunidades', _external=True),
            'lastmod': hoje,
            'changefreq': 'daily',
            'priority': '0.9',
        },
        {
            'loc': url_for('billing.planos', _external=True),
            'lastmod': hoje,
            'changefreq': 'weekly',
            'priority': '0.8',
        },
        {
            'loc': url_for('public.faq_ajuda', _external=True),
            'lastmod': hoje,
            'changefreq': 'monthly',
            'priority': '0.6',
        },
        {
            'loc': url_for('public.termos_uso', _external=True),
            'lastmod': hoje,
            'changefreq': 'yearly',
            'priority': '0.4',
        },
        {
            'loc': url_for('public.politica_privacidade', _external=True),
            'lastmod': hoje,
            'changefreq': 'yearly',
            'priority': '0.4',
        },
        {
            'loc': url_for('public.denunciar_abuso', _external=True),
            'lastmod': hoje,
            'changefreq': 'yearly',
            'priority': '0.3',
        },
    ]

    imoveis_ativos = _imovel_repo().listar_ativos()
    for imovel in imoveis_ativos:
        referencia_data = imovel.atualizado_em or imovel.criado_em or datetime.utcnow()
        urls.append({
            'loc': url_for('detalhe_imovel', id=imovel.id, _external=True),
            'lastmod': referencia_data.strftime('%Y-%m-%d'),
            'changefreq': 'daily',
            'priority': '0.9',
        })

    xml = render_template('sitemap.xml', urls=urls)
    return Response(xml, mimetype='application/xml')


@core_bp.route('/og-placeholder')
def og_placeholder():
    """Gera imagem de placeholder otimizada para Open Graph."""
    try:
        tipo = request.args.get('tipo', 'Imóvel')
        cidade = request.args.get('cidade', 'Brasil')

        tipo = tipo[:30] if tipo else 'Imóvel'
        cidade = cidade[:30] if cidade else 'Brasil'

        img = Image.new('RGB', (1200, 628), color=(45, 77, 144))

        try:
            draw = ImageDraw.Draw(img)

            try:
                font_grande = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 80)
                font_pequena = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 40)
            except Exception:
                font_grande = ImageFont.load_default()
                font_pequena = ImageFont.load_default()

            texto1 = tipo
            texto2 = f'em {cidade}'

            bbox1 = draw.textbbox((0, 0), texto1, font=font_grande)
            texto1_width = bbox1[2] - bbox1[0]
            texto1_height = bbox1[3] - bbox1[1]

            bbox2 = draw.textbbox((0, 0), texto2, font=font_pequena)
            texto2_width = bbox2[2] - bbox2[0]
            texto2_height = bbox2[3] - bbox2[1]

            x1 = (1200 - texto1_width) // 2
            y1 = (628 - texto1_height - texto2_height) // 2

            x2 = (1200 - texto2_width) // 2
            y2 = y1 + texto1_height + 20

            draw.text((x1, y1), texto1, fill=(255, 255, 255), font=font_grande)
            draw.text((x2, y2), texto2, fill=(200, 200, 200), font=font_pequena)
        except Exception as e:
            current_app.logger.debug('Erro ao desenhar texto no placeholder: %s', str(e))

        img_io = io.BytesIO()
        img.save(img_io, 'PNG')
        img_io.seek(0)

        return Response(
            img_io.getvalue(),
            mimetype='image/png',
            headers={'Cache-Control': 'public, max-age=86400'},
        )
    except Exception as e:
        current_app.logger.error('Erro ao gerar placeholder: %s', str(e))
        img = Image.new('RGB', (1200, 628), color=(45, 77, 144))
        img_io = io.BytesIO()
        img.save(img_io, 'PNG')
        img_io.seek(0)
        return Response(img_io.getvalue(), mimetype='image/png')


@core_bp.route('/dashboard')
def dashboard():
    """Painel de controle do anunciante."""
    legacy = _legacy()
    usuario = legacy.get_usuario_logado()

    if not usuario:
        flash('Você precisa estar logado!', 'error')
        return redirect(url_for('login'))

    imoveis = _imovel_repo().listar_por_usuario(usuario.id)
    legacy._padronizar_negocio_imoveis(imoveis)

    total_imoveis = len(imoveis)
    total_visualizacoes = sum(item.visualizacoes for item in imoveis)
    rating = usuario.get_rating()
    total_avaliacoes = usuario.get_total_avaliacoes()

    mensagens_nao_lidas = Mensagem.query.filter_by(
        destinatario_id=usuario.id,
        lida=False,
    ).count()
    limite_anuncios = legacy._resumo_limite_anuncios(usuario)
    stripe_checkout_habilitado = _stripe_checkout_habilitado()

    ultimos_imoveis = sorted(imoveis, key=lambda item: item.criado_em, reverse=True)[:5]
    imoveis_populares = sorted(imoveis, key=lambda item: item.visualizacoes, reverse=True)[:5]

    return render_template(
        'dashboard.html',
        usuario=usuario,
        total_imoveis=total_imoveis,
        total_visualizacoes=total_visualizacoes,
        rating=rating,
        total_avaliacoes=total_avaliacoes,
        limite_anuncios=limite_anuncios,
        stripe_checkout_habilitado=stripe_checkout_habilitado,
        mensagens_nao_lidas=mensagens_nao_lidas,
        ultimos_imoveis=ultimos_imoveis,
        imoveis_populares=imoveis_populares,
        preco_pro_brl=current_app.config['PRECO_PRO_BRL'],
        preco_empresa_brl=current_app.config['PRECO_EMPRESA_BRL'],
    )