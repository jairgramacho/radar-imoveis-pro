import os
import re
import math
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import urlencode, urlparse
from flask import Flask, request, redirect, url_for, flash, session, jsonify, has_request_context
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect

from dotenv import load_dotenv
# import pillow_heif  # Comentado: trava no Codespace
from models import db, Usuario, Imovel, Mensagem, StripeEventoWebhook, CRMLead, CRMLeadHistorico

load_dotenv()

from email_utils import mail, enviar_email_confirmacao_cadastro, enviar_email_redefinicao_senha
from config import config
from radar_app.blueprints import public_bp, billing_bp, chat_bp, admin_bp, auth_bp, imoveis_bp, core_bp
from radar_app.blueprints import crm_bp
from radar_app.infra.media import (
    allowed_file as media_allowed_file,
    arquivo_upload_existe,
    cloudinary_configurado,
    cloudinary_uploader,
    foto_eh_url,
    foto_url,
    processar_imagem as media_processar_imagem,
    resolver_foto_preview,
    url_cloudinary_og,
)
from radar_app.auth import (
    gerar_token_email,
    serializer_tokens,
    validar_token_email,
)
from radar_app.infra.email import (
    disparar_email_assincrono,
    enviar_email_com_status,
    smtp_configurado,
)
from radar_app.assinatura import (
    LIMITES_ANUNCIOS_POR_PLANO as ASSINATURA_LIMITES_ANUNCIOS_POR_PLANO,
    contar_anuncios_ativos,
    emails_admin_configurados,
    limite_anuncios_usuario,
    normalizar_plano,
    pausar_todos_anuncios_usuario,
    reativar_todos_anuncios_usuario,
    resumo_limite_anuncios,
    status_assinatura_bloqueada,
    usuario_eh_admin,
)
from radar_app.imoveis import (
    aplicar_radar_oportunidades as aplicar_radar_oportunidades_imoveis,
    negocio_canonico as negocio_canonico_imovel,
    normalizar_negocio as normalizar_negocio_imovel,
    normalizar_texto as normalizar_texto_imovel,
    padronizar_negocio_imovel,
    padronizar_negocio_imoveis,
)
from radar_app.infra.bootstrap import (
    configurar_logging_estruturado,
    deve_executar_bootstrap_db,
    garantir_colunas_usuario,
    garantir_tabelas_crm,
    marcar_admin_proprietario,
)

# Registrar conversor HEIC para PIL
# pillow_heif.register_heif_opener()  # Comentado: trava no Codespace

PROJECT_ROOT = Path(__file__).resolve().parent.parent

app = Flask(
    __name__,
    template_folder=str(PROJECT_ROOT / 'templates'),
    static_folder=str(PROJECT_ROOT / 'static'),
    static_url_path='/radar-static',
)
app.register_blueprint(public_bp)
app.register_blueprint(billing_bp)
app.register_blueprint(chat_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(imoveis_bp)
app.register_blueprint(core_bp)
app.register_blueprint(crm_bp)


def _registrar_alias_endpoints(aliases):
    for endpoint_antigo, regra, metodos, endpoint_novo in aliases:
        if endpoint_antigo in app.view_functions:
            continue
        if endpoint_novo not in app.view_functions:
            continue

        app.add_url_rule(
            regra,
            endpoint=endpoint_antigo,
            view_func=app.view_functions[endpoint_novo],
            methods=metodos,
        )


def _registrar_alias_endpoints_auth():
    _registrar_alias_endpoints([
        ('cadastro', '/cadastro', ['GET', 'POST'], 'auth.cadastro'),
        ('login', '/login', ['GET', 'POST'], 'auth.login'),
        ('logout', '/logout', ['GET'], 'auth.logout'),
        ('verificar_2fa', '/verificar-2fa', ['GET', 'POST'], 'auth.verificar_2fa'),
        ('confirmar_email', '/confirmar-email/<token>', ['GET'], 'auth.confirmar_email'),
        ('reenviar_confirmacao', '/reenviar-confirmacao', ['POST'], 'auth.reenviar_confirmacao'),
        ('esqueci_senha', '/esqueci-senha', ['GET', 'POST'], 'auth.esqueci_senha'),
        ('redefinir_senha', '/redefinir-senha/<token>', ['GET', 'POST'], 'auth.redefinir_senha'),
        ('configuracoes_conta', '/configuracoes-conta', ['GET', 'POST'], 'auth.configuracoes_conta'),
        ('excluir_conta', '/excluir-conta', ['POST'], 'auth.excluir_conta'),
    ])


def _registrar_alias_endpoints_imoveis():
    _registrar_alias_endpoints([
        ('index', '/', ['GET'], 'imoveis.index'),
        ('salvar', '/salvar', ['POST'], 'imoveis.salvar'),
        ('meus_anuncios', '/meus-anuncios', ['GET'], 'imoveis.meus_anuncios'),
        ('detalhe_imovel', '/imovel/<int:id>', ['GET'], 'imoveis.detalhe_imovel'),
        ('deletar_imovel', '/deletar-imovel/<int:id>', ['POST'], 'imoveis.deletar_imovel'),
        ('editar_imovel', '/editar-imovel/<int:id>', ['GET', 'POST'], 'imoveis.editar_imovel'),
        ('avaliar_anunciante', '/avaliar-anunciante/<int:usuario_id>', ['GET', 'POST'], 'imoveis.avaliar_anunciante'),
        ('adicionar_fotos', '/imovel/<int:id>/adicionar-fotos', ['GET', 'POST'], 'imoveis.adicionar_fotos'),
    ])


def _registrar_alias_endpoints_core():
    _registrar_alias_endpoints([
        ('healthcheck', '/healthz', ['GET'], 'core.healthcheck'),
        ('readiness_check', '/healthz/ready', ['GET'], 'core.readiness_check'),
        ('robots_txt', '/robots.txt', ['GET'], 'core.robots_txt'),
        ('sitemap_xml', '/sitemap.xml', ['GET'], 'core.sitemap_xml'),
        ('og_placeholder', '/og-placeholder', ['GET'], 'core.og_placeholder'),
        ('dashboard', '/dashboard', ['GET'], 'core.dashboard'),
    ])


def _registrar_alias_endpoints_crm():
    _registrar_alias_endpoints([
        ('crm', '/crm', ['GET'], 'crm.crm_dashboard'),
        ('crm_rastrear_whatsapp', '/crm/whatsapp/<int:imovel_id>', ['GET'], 'crm.rastrear_whatsapp'),
        ('crm_atualizar_lead', '/crm/leads/<int:lead_id>/status', ['POST'], 'crm.atualizar_lead_status'),
    ])


@app.template_filter('moeda_brl')
def moeda_brl(valor):
    """Formata números no padrão brasileiro: 500.000,00."""
    try:
        numero = float(valor or 0)
    except (TypeError, ValueError):
        numero = 0.0

    formatado = f"{numero:,.2f}"
    return formatado.replace(',', '_').replace('.', ',').replace('_', '.')


@app.template_filter('format_descricao')
def format_descricao(texto):
    """Converte texto com \n\n em parágrafos <p> e \n simples em <br>."""
    if not texto:
        return ''
    import re
    # Primeiro escapa HTML básico pra evitar XSS
    texto = str(texto)
    texto = texto.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    # Divide em parágrafos por \n\n (ou \r\n\r\n)
    paragrafos = re.split(r'\n\s*\n', texto)
    partes = []
    for p in paragrafos:
        p = p.strip()
        if not p:
            continue
        # Converte quebras simples em <br>
        with_br = p.replace('\n', '<br>')
        partes.append(f'<p>{with_br}</p>')
    return '\n'.join(partes)

# Carregar configuração baseada em FLASK_ENV
flask_env = os.getenv('FLASK_ENV', 'development')
app.config.from_object(config)

# ✅ CSRF Protection (Flask-WTF)
csrf = CSRFProtect(app)

# Validar produção
if flask_env == 'production':
    config.validate()


def _configurar_logging_estruturado():
    return configurar_logging_estruturado(app, flask_env, logging, RotatingFileHandler)


_configurar_logging_estruturado()


ratelimit_storage_uri = os.getenv('RATELIMIT_STORAGE_URI', 'memory://')

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    storage_uri=ratelimit_storage_uri,
    enabled=(flask_env != 'testing'),
)
limiter.init_app(app)


def _aplicar_limite_endpoint(endpoint, regra):
    if endpoint in app.view_functions:
        app.view_functions[endpoint] = limiter.limit(regra)(app.view_functions[endpoint])


_aplicar_limite_endpoint('auth.login', '5 per minute')
_aplicar_limite_endpoint('auth.cadastro', '5 per hour')
_aplicar_limite_endpoint('auth.reenviar_confirmacao', '5 per hour')
_aplicar_limite_endpoint('auth.esqueci_senha', '5 per hour')
_aplicar_limite_endpoint('chat.enviar_mensagem', '20 per minute')
_aplicar_limite_endpoint('chat.api_enviar_mensagem', '30 per minute')
_aplicar_limite_endpoint('imoveis.salvar', '10 per hour')
_aplicar_limite_endpoint('imoveis.adicionar_fotos', '20 per hour')
_aplicar_limite_endpoint('billing.assinatura_checkout', '10 per hour')
_aplicar_limite_endpoint('public.denunciar_abuso', '5 per hour')
_registrar_alias_endpoints_auth()
_registrar_alias_endpoints_imoveis()
_registrar_alias_endpoints_core()
_registrar_alias_endpoints_crm()

if flask_env == 'production' and ratelimit_storage_uri == 'memory://':
    app.logger.warning(
        'Flask-Limiter em modo memory://. Configure RATELIMIT_STORAGE_URI para Redis em producao.'
    )


def _origens_cors_permitidas():
    permitidas = set()

    app_url = (app.config.get('APP_URL') or '').strip()
    if app_url:
        parsed = urlparse(app_url)
        if parsed.scheme and parsed.netloc:
            permitidas.add(f'{parsed.scheme}://{parsed.netloc}')

    hosts_raw = os.getenv('ALLOWED_HOSTS', '')
    for host in hosts_raw.split(','):
        item = host.strip()
        if not item:
            continue
        if item.startswith('http://') or item.startswith('https://'):
            permitidas.add(item.rstrip('/'))
        else:
            permitidas.add(f'https://{item}')
            permitidas.add(f'http://{item}')

    if flask_env != 'production':
        permitidas.update({
            'http://localhost:5000',
            'http://127.0.0.1:5000',
            'http://localhost:3000',
            'http://127.0.0.1:3000',
        })

    return permitidas

# Security Headers
@app.after_request
def set_security_headers(response):
    if request.path.startswith('/api/'):
        origin = (request.headers.get('Origin') or '').rstrip('/')
        if origin and origin in _origens_cors_permitidas():
            response.headers['Access-Control-Allow-Origin'] = origin
            response.headers['Access-Control-Allow-Credentials'] = 'true'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-CSRFToken'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
            response.headers['Vary'] = 'Origin'

    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response
# Configuração do Banco de Dados (já carregada de config.py)

# Configuração de Email (já carregada de config.py)

mail.init_app(app)

# Configuração de Uploads
UPLOAD_FOLDER = app.config['UPLOAD_FOLDER']
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg', 'tiff', 'ico', 'heic', 'heif'}
MAX_FILE_SIZE = app.config['MAX_CONTENT_LENGTH']

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Inicializar banco de dados
db.init_app(app)


def _garantir_colunas_usuario():
    return garantir_colunas_usuario(db, StripeEventoWebhook)


def _deve_executar_bootstrap_db():
    return deve_executar_bootstrap_db(flask_env)


def _marcar_admin_proprietario():
    return marcar_admin_proprietario(Usuario, db, app.logger)


def _cloudinary_configurado():
    return cloudinary_configurado()


def _cloudinary_uploader():
    return cloudinary_uploader()


def _foto_eh_url(valor):
    return foto_eh_url(valor)


def _foto_url(valor, external=False):
    return foto_url(valor, external=external)


def _url_cloudinary_og(url):
    return url_cloudinary_og(url)


def _arquivo_upload_existe(valor):
    return arquivo_upload_existe(valor)


def _resolver_foto_preview(imovel):
    return resolver_foto_preview(imovel, _url_publica)


def _canonical_url_atual():
    """Monta canonical removendo parâmetros de rastreamento e paginação redundante."""
    if not has_request_context():
        return _url_publica('index')

    parametros_filtrados = []
    parametros_removiveis = {
        'gclid',
        'fbclid',
        'yclid',
        'msclkid',
        'ref',
        'source',
    }

    for chave, valor in request.args.items(multi=True):
        chave_normalizada = (chave or '').strip().lower()
        if chave_normalizada.startswith('utm_') or chave_normalizada in parametros_removiveis:
            continue
        if chave_normalizada == 'pagina' and str(valor).strip() in {'', '1'}:
            continue
        parametros_filtrados.append((chave, valor))

    query = urlencode(parametros_filtrados, doseq=True)
    caminho = request.path
    if query:
        caminho = f'{caminho}?{query}'

    base = (app.config.get('APP_URL') or '').strip().rstrip('/')
    if has_request_context() and (not base or 'localhost' in base or '127.0.0.1' in base):
        proto = (request.headers.get('X-Forwarded-Proto') or request.scheme or 'https').split(',')[0].strip()
        host = (request.headers.get('X-Forwarded-Host') or request.host or '').split(',')[0].strip()
        if host:
            return f'{proto}://{host}{caminho}'

    if base:
        return f'{base}{caminho}'
    return _url_publica('index')


def _seo_defaults():
    """Define metadados padrão de SEO por endpoint."""
    endpoint = (request.endpoint or '').strip().lower() if has_request_context() else ''
    aba_atual = (request.args.get('aba', 'buscar') if has_request_context() else 'buscar').strip().lower()
    cidade_busca = (request.args.get('cidade', '') if has_request_context() else '').strip()

    seo_title = 'Radar Imoveis Pro | Imoveis em Barreiras e Oeste da Bahia'
    seo_description = (
        'Encontre imoveis para compra e aluguel em Barreiras e no Oeste da Bahia. '
        'Anuncie com alcance regional e contato direto via WhatsApp.'
    )
    seo_robots = 'index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1'
    seo_keywords = (
        'imoveis em barreiras, imobiliaria barreiras, casas em barreiras, apartamentos barreiras, '
        'imoveis oeste da bahia, aluguel barreiras, compra de imoveis bahia'
    )

    if endpoint in {'imoveis.index', 'index'}:
        if aba_atual == 'oportunidades':
            seo_title = 'Oportunidades de Imoveis em Barreiras e Regiao | Radar Imoveis Pro'
            seo_description = (
                'Descubra imoveis com preco competitivo em Barreiras e no Oeste da Bahia. '
                'Radar de oportunidades com comparativo local de valores.'
            )
        elif aba_atual == 'anunciar':
            seo_title = 'Anunciar Imovel em Barreiras e Oeste da Bahia | Radar Imoveis Pro'
            seo_description = (
                'Publique seu imovel em Barreiras e alcance compradores e locatarios de toda a regiao. '
                'Anuncio rapido com fotos, chat e WhatsApp.'
            )
            seo_robots = 'noindex,nofollow,noarchive'

        if cidade_busca:
            seo_title = f'Imoveis em {cidade_busca} | Radar Imoveis Pro'
            seo_description = (
                f'Veja anuncios de imoveis em {cidade_busca} com filtros por tipo, preco e bairro. '
                'Radar Imoveis Pro com foco em Barreiras e Oeste da Bahia.'
            )

    if endpoint in {'billing.planos'}:
        seo_title = 'Planos para Anunciar Imoveis | Radar Imoveis Pro'
        seo_description = (
            'Compare os planos da Radar Imoveis Pro e anuncie com mais alcance em Barreiras '
            'e no Oeste da Bahia.'
        )

    if endpoint in {'public.faq_ajuda', 'public.termos_uso', 'public.politica_privacidade'}:
        seo_robots = 'index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1'

    if endpoint in {
        'auth.login',
        'login',
        'auth.cadastro',
        'cadastro',
        'auth.esqueci_senha',
        'esqueci_senha',
        'auth.redefinir_senha',
        'redefinir_senha',
        'auth.verificar_2fa',
        'verificar_2fa',
        'auth.configuracoes_conta',
        'configuracoes_conta',
        'core.dashboard',
        'dashboard',
        'chat.chat',
        'chat',
        'chat.conversa',
        'conversa',
        'imoveis.meus_anuncios',
        'meus_anuncios',
        'imoveis.editar_imovel',
        'editar_imovel',
        'imoveis.adicionar_fotos',
        'adicionar_fotos',
        'admin.admin_planos',
        'admin_planos',
    }:
        seo_robots = 'noindex,nofollow,noarchive'

    seo_canonical_url = _canonical_url_atual()
    seo_og_image = _url_publica('og_placeholder', tipo='Radar Imoveis Pro', cidade='Barreiras')

    return {
        'seo_site_name': 'Radar Imoveis Pro',
        'seo_locale': 'pt_BR',
        'seo_title': seo_title,
        'seo_description': seo_description,
        'seo_robots': seo_robots,
        'seo_keywords': seo_keywords,
        'seo_canonical_url': seo_canonical_url,
        'seo_og_type': 'website',
        'seo_og_image': seo_og_image,
        'seo_twitter_card': 'summary_large_image',
    }


@app.context_processor
def inject_template_helpers():
    """Disponibiliza helpers e contadores globais para templates."""
    mensagens_nao_lidas = 0
    usuario_admin = False
    usuario_id = session.get('usuario_id')

    if usuario_id:
        try:
            mensagens_nao_lidas = Mensagem.query.filter_by(
                destinatario_id=usuario_id,
                lida=False,
            ).count()
            usuario_atual = Usuario.query.get(usuario_id)
            usuario_admin = _usuario_eh_admin(usuario_atual)
        except Exception:
            mensagens_nao_lidas = 0
            usuario_admin = False

    seo_contexto = _seo_defaults()

    return {
        'foto_url': _foto_url,
        'url_publica': _url_publica,
        'mensagens_nao_lidas': mensagens_nao_lidas,
        'usuario_admin': usuario_admin,
        **seo_contexto,
    }


# Criar tabelas automaticamente em desenvolvimento (ou quando explicitamente habilitado)
if _deve_executar_bootstrap_db():
    with app.app_context():
        db.create_all()
        _garantir_colunas_usuario()
        garantir_tabelas_crm(db, CRMLead, CRMLeadHistorico)

# Em produção, executa apenas migração leve de colunas já existentes (sem create_all)
# para evitar quebra após deploy quando novas colunas são adicionadas ao modelo.
if flask_env == 'production':
    with app.app_context():
        try:
            _garantir_colunas_usuario()
            garantir_tabelas_crm(db, CRMLead, CRMLeadHistorico)
            _marcar_admin_proprietario()
        except Exception as e:
            app.logger.warning('Falha ao garantir colunas em produção: %s', str(e), exc_info=True)

OPORTUNIDADE_DESCONTO_MINIMO = 0.10
OPORTUNIDADE_AMOSTRA_MINIMA = 5
ITENS_POR_PAGINA = 12
LIMITES_ANUNCIOS_POR_PLANO = ASSINATURA_LIMITES_ANUNCIOS_POR_PLANO


def _status_assinatura_bloqueada(status_assinatura):
    return status_assinatura_bloqueada(status_assinatura)


def _pausar_todos_anuncios_usuario(usuario_id):
    return pausar_todos_anuncios_usuario(usuario_id, Imovel)


def _reativar_todos_anuncios_usuario(usuario_id):
    return reativar_todos_anuncios_usuario(usuario_id, Imovel)


def _emails_admin_configurados():
    return emails_admin_configurados()


def _usuario_eh_admin(usuario):
    return usuario_eh_admin(usuario)


def _normalizar_plano(plano):
    return normalizar_plano(plano, LIMITES_ANUNCIOS_POR_PLANO)


def _limite_anuncios_usuario(usuario):
    return limite_anuncios_usuario(usuario, LIMITES_ANUNCIOS_POR_PLANO)


def _contar_anuncios_ativos(usuario_id):
    return contar_anuncios_ativos(usuario_id, Imovel)


def _resumo_limite_anuncios(usuario):
    return resumo_limite_anuncios(usuario, Imovel, LIMITES_ANUNCIOS_POR_PLANO)


def _smtp_configurado():
    return smtp_configurado(app.config)


def _permitir_fallback_reset_local():
    """Permite bypass de email em dev apenas quando explicitamente habilitado."""
    return os.getenv('ALLOW_DEV_PASSWORD_RESET_FALLBACK', '0').strip().lower() in {'1', 'true', 'yes', 'on'}


def _reset_email_assincrono_habilitado():
    """Controla envio assíncrono no esqueci-senha."""
    return os.getenv('PASSWORD_RESET_ASYNC', '0').strip().lower() in {'1', 'true', 'yes', 'on'}


def _confirmacao_email_obrigatoria():
    """Define se confirmação de email é obrigatória para permitir login."""
    valor = os.getenv('REQUIRE_EMAIL_CONFIRMATION', '').strip().lower()
    if valor in {'1', 'true', 'yes', 'on'}:
        return True
    if valor in {'0', 'false', 'no', 'off'}:
        return False
    return _smtp_configurado()


def _enviar_email_com_status(funcao_envio, *args):
    return enviar_email_com_status(app, funcao_envio, *args)


def _disparar_email_assincrono(funcao_envio, *args):
    return disparar_email_assincrono(app, funcao_envio, *args)


def _validar_whatsapp(whatsapp):
    """Valida WhatsApp brasileiro com 10 ou 11 dígitos (DDD + número)."""
    digitos = re.sub(r'\D', '', whatsapp or '')
    if len(digitos) not in (10, 11):
        return None
    return digitos


def _serializer_tokens():
    return serializer_tokens(app.config['SECRET_KEY'])


def _gerar_token_email(email, objetivo):
    return gerar_token_email(app.config['SECRET_KEY'], email, objetivo)


def _validar_token_email(token, objetivo, max_age=3600):
    return validar_token_email(app.config['SECRET_KEY'], token, objetivo, max_age=max_age)


def _paginar_lista(itens, pagina, por_pagina):
    """Pagina uma lista em memória sem depender de `query.paginate`."""
    total = len(itens)
    total_paginas = max(1, math.ceil(total / por_pagina)) if total else 1
    pagina = max(1, min(pagina, total_paginas))

    inicio = (pagina - 1) * por_pagina
    fim = inicio + por_pagina
    return itens[inicio:fim], total, total_paginas, pagina


def _url_publica(endpoint, **values):
    """Monta URL pública usando APP_URL ou host da requisição atual."""
    caminho = url_for(endpoint, _external=False, **values)
    base = (app.config.get('APP_URL') or '').strip().rstrip('/')

    # Em produção, se APP_URL não estiver configurado (localhost), usa host/protocolo reais.
    if has_request_context() and (not base or 'localhost' in base or '127.0.0.1' in base):
        proto = (request.headers.get('X-Forwarded-Proto') or request.scheme or 'https').split(',')[0].strip()
        host = (request.headers.get('X-Forwarded-Host') or request.host or '').split(',')[0].strip()
        if host:
            return f"{proto}://{host}{caminho}"

    if base:
        return f"{base}{caminho}"
    return url_for(endpoint, _external=True, **values)

def allowed_file(filename):
    """Verifica se o arquivo é permitido."""
    return media_allowed_file(filename, ALLOWED_EXTENSIONS)


def processar_imagem(arquivo):
    """Processa upload de imagem preservando a configuração atual do app."""
    return media_processar_imagem(arquivo, ALLOWED_EXTENSIONS)

def get_usuario_logado():
    """Retorna o usuário logado ou None"""
    usuario_id = session.get('usuario_id')
    if usuario_id:
        return Usuario.query.get(usuario_id)
    return None


def _normalizar_texto(valor):
    return normalizar_texto_imovel(valor)


def _normalizar_negocio(valor):
    return normalizar_negocio_imovel(valor)


def _negocio_canonico(valor):
    return negocio_canonico_imovel(valor)


def _padronizar_negocio_imovel(imovel):
    return padronizar_negocio_imovel(imovel)


def _padronizar_negocio_imoveis(imoveis):
    return padronizar_negocio_imoveis(imoveis)


def aplicar_radar_oportunidades(imoveis):
    return aplicar_radar_oportunidades_imoveis(
        imoveis,
        OPORTUNIDADE_AMOSTRA_MINIMA,
        OPORTUNIDADE_DESCONTO_MINIMO,
    )

# ============================================
# TRATAMENTO DE ERROS
# ============================================

@app.errorhandler(404)
def pagina_nao_encontrada(e):
    """Página não encontrada"""
    return redirect(url_for('index', aba='buscar'))

@app.errorhandler(429)
def rate_limit_excedido(e):
    """Resposta amigavel quando o limite de tentativas e excedido."""
    if request.path.startswith('/api/'):
        return jsonify({
            'ok': False,
            'erro': 'muitas_tentativas',
            'mensagem': 'Muitas tentativas em pouco tempo. Tente novamente em alguns instantes.',
        }), 429

    flash('Muitas tentativas em pouco tempo. Aguarde um pouco e tente novamente.', 'error')
    destino = url_for('index', aba='buscar')
    if request.referrer and not request.referrer.endswith(request.path):
        destino = request.referrer
    return redirect(destino)


@app.errorhandler(500)
def erro_interno(e):
    """Erro interno do servidor"""
    flash('Erro interno do servidor. Tente novamente.', 'error')
    return redirect(url_for('index', aba='buscar'))

def create_app(config_override=None):
    """Retorna a aplicação Flask já inicializada, com overrides opcionais."""
    if config_override:
        app.config.update(config_override)
    return app

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)
