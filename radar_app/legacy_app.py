import os
import re
import math
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from flask import Flask, request, redirect, url_for, flash, session, jsonify, has_request_context
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from sqlalchemy import case, func, inspect, text
from dotenv import load_dotenv
# import pillow_heif  # Comentado: trava no Codespace
from models import db, Usuario, Imovel, Mensagem, StripeEventoWebhook

load_dotenv()

from email_utils import mail, enviar_email_confirmacao_cadastro, enviar_email_redefinicao_senha
from config import config
from radar_app.blueprints import public_bp, billing_bp, chat_bp, admin_bp, auth_bp, imoveis_bp, core_bp
from radar_app.services.media import (
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
from radar_app.services.auth_tokens import (
    gerar_token_email,
    serializer_tokens,
    validar_token_email,
)
from radar_app.services.email_delivery import (
    disparar_email_assincrono,
    enviar_email_com_status,
    smtp_configurado,
)
from radar_app.services.assinatura import (
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

# Registrar conversor HEIC para PIL
# pillow_heif.register_heif_opener()  # Comentado: trava no Codespace

PROJECT_ROOT = Path(__file__).resolve().parent.parent

app = Flask(
    __name__,
    template_folder=str(PROJECT_ROOT / 'templates'),
    static_folder=str(PROJECT_ROOT / 'static'),
)
app.register_blueprint(public_bp)
app.register_blueprint(billing_bp)
app.register_blueprint(chat_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(imoveis_bp)
app.register_blueprint(core_bp)


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


@app.template_filter('moeda_brl')
def moeda_brl(valor):
    """Formata números no padrão brasileiro: 500.000,00."""
    try:
        numero = float(valor or 0)
    except (TypeError, ValueError):
        numero = 0.0

    formatado = f"{numero:,.2f}"
    return formatado.replace(',', '_').replace('.', ',').replace('_', '.')

# Carregar configuração baseada em FLASK_ENV
flask_env = os.getenv('FLASK_ENV', 'development')
app.config.from_object(config)

# Validar produção
if flask_env == 'production':
    config.validate()

# CORS - apenas domínios autorizados em produção
if flask_env == 'production':
    CORS(app, resources={r"/api/*": {"origins": os.getenv('ALLOWED_HOSTS', 'localhost').split(',')}})
else:
    CORS(app, origins="*")


def _configurar_logging_estruturado():
    """Configura logging consistente para facilitar diagnostico em producao."""
    if flask_env == 'testing':
        return

    formatter = logging.Formatter(
        '%(asctime)s %(levelname)s %(name)s: %(message)s [%(pathname)s:%(lineno)d]'
    )

    app.logger.setLevel(logging.INFO)

    for handler in app.logger.handlers:
        handler.setFormatter(formatter)

    if not app.debug:
        os.makedirs('logs', exist_ok=True)
        if not any(isinstance(handler, RotatingFileHandler) for handler in app.logger.handlers):
            file_handler = RotatingFileHandler(
                'logs/radar.log',
                maxBytes=10 * 1024 * 1024,
                backupCount=10,
            )
            file_handler.setLevel(logging.INFO)
            file_handler.setFormatter(formatter)
            app.logger.addHandler(file_handler)

    app.logger.info('Radar Imoveis Pro startup - env=%s', flask_env)


_configurar_logging_estruturado()


ratelimit_storage_uri = os.getenv('RATELIMIT_STORAGE_URI', 'memory://')

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    storage_uri=ratelimit_storage_uri,
    enabled=(flask_env != 'testing'),
)
limiter.init_app(app)
app.view_functions['auth.login'] = limiter.limit('5 per minute')(app.view_functions['auth.login'])
app.view_functions['chat.enviar_mensagem'] = limiter.limit('20 per minute')(app.view_functions['chat.enviar_mensagem'])
app.view_functions['chat.api_enviar_mensagem'] = limiter.limit('30 per minute')(app.view_functions['chat.api_enviar_mensagem'])
_registrar_alias_endpoints_auth()
_registrar_alias_endpoints_imoveis()
_registrar_alias_endpoints_core()

if flask_env == 'production' and ratelimit_storage_uri == 'memory://':
    app.logger.warning(
        'Flask-Limiter em modo memory://. Configure RATELIMIT_STORAGE_URI para Redis em producao.'
    )

# Security Headers
@app.after_request
def set_security_headers(response):
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
    """Adiciona colunas novas em `usuarios` quando o banco já existia sem migração."""
    inspetor = inspect(db.engine)
    colunas = {coluna['name'] for coluna in inspetor.get_columns('usuarios')}
    dialect = db.engine.dialect.name

    comandos = []
    if 'email_confirmado' not in colunas:
        if dialect == 'sqlite':
            comandos.append("ALTER TABLE usuarios ADD COLUMN email_confirmado BOOLEAN NOT NULL DEFAULT 1")
        else:
            comandos.append("ALTER TABLE usuarios ADD COLUMN email_confirmado BOOLEAN NOT NULL DEFAULT TRUE")

    if 'confirmado_em' not in colunas:
        if dialect == 'sqlite':
            comandos.append("ALTER TABLE usuarios ADD COLUMN confirmado_em DATETIME")
        else:
            comandos.append("ALTER TABLE usuarios ADD COLUMN confirmado_em TIMESTAMP")

    if 'plano' not in colunas:
        if dialect == 'sqlite':
            comandos.append("ALTER TABLE usuarios ADD COLUMN plano VARCHAR(20) NOT NULL DEFAULT 'free'")
        else:
            comandos.append("ALTER TABLE usuarios ADD COLUMN plano VARCHAR(20) NOT NULL DEFAULT 'free'")

    if 'limite_anuncios' not in colunas:
        if dialect == 'sqlite':
            comandos.append("ALTER TABLE usuarios ADD COLUMN limite_anuncios INTEGER NOT NULL DEFAULT 3")
        else:
            comandos.append("ALTER TABLE usuarios ADD COLUMN limite_anuncios INTEGER NOT NULL DEFAULT 3")

    if 'is_admin' not in colunas:
        if dialect == 'sqlite':
            comandos.append("ALTER TABLE usuarios ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0")
        else:
            comandos.append("ALTER TABLE usuarios ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT FALSE")

    # Criar índice único no campo whatsapp (se não existir)
    try:
        if dialect == 'sqlite':
            db.session.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_usuarios_whatsapp ON usuarios(whatsapp)"))
        else:
            db.session.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_usuarios_whatsapp ON usuarios(whatsapp)"))
    except Exception:
        pass  # Índice pode já existir

    if 'status_assinatura' not in colunas:
        if dialect == 'sqlite':
            comandos.append("ALTER TABLE usuarios ADD COLUMN status_assinatura VARCHAR(20) NOT NULL DEFAULT 'ativa'")
        else:
            comandos.append("ALTER TABLE usuarios ADD COLUMN status_assinatura VARCHAR(20) NOT NULL DEFAULT 'ativa'")

    if 'assinatura_renova_em' not in colunas:
        if dialect == 'sqlite':
            comandos.append("ALTER TABLE usuarios ADD COLUMN assinatura_renova_em DATETIME")
        else:
            comandos.append("ALTER TABLE usuarios ADD COLUMN assinatura_renova_em TIMESTAMP")

    if 'stripe_customer_id' not in colunas:
        if dialect == 'sqlite':
            comandos.append("ALTER TABLE usuarios ADD COLUMN stripe_customer_id VARCHAR(120)")
        else:
            comandos.append("ALTER TABLE usuarios ADD COLUMN stripe_customer_id VARCHAR(120)")

    if 'stripe_subscription_id' not in colunas:
        if dialect == 'sqlite':
            comandos.append("ALTER TABLE usuarios ADD COLUMN stripe_subscription_id VARCHAR(120)")
        else:
            comandos.append("ALTER TABLE usuarios ADD COLUMN stripe_subscription_id VARCHAR(120)")

    for comando in comandos:
        db.session.execute(text(comando))

    if comandos:
        db.session.commit()

    StripeEventoWebhook.__table__.create(bind=db.engine, checkfirst=True)


def _deve_executar_bootstrap_db():
    """Controla bootstrap automático do banco para evitar travas no boot em produção."""
    override = os.getenv('RUN_DB_BOOTSTRAP')
    if override is not None:
        return override.strip().lower() in {'1', 'true', 'yes', 'on'}
    return flask_env != 'production'


def _marcar_admin_proprietario():
    """Marca o email do proprietário como admin para limite ilimitado."""
    email_admin = 'jairgramacho82160@gmail.com'
    try:
        usuario = Usuario.query.filter_by(email=email_admin).first()
        if usuario and not usuario.is_admin:
            usuario.is_admin = True
            db.session.commit()
            app.logger.info(f'Conta {email_admin} marcada como admin')
    except Exception as e:
        app.logger.warning(f'Erro ao marcar admin: {str(e)}')


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

    return {
        'foto_url': _foto_url,
        'mensagens_nao_lidas': mensagens_nao_lidas,
        'usuario_admin': usuario_admin,
    }


# Criar tabelas automaticamente em desenvolvimento (ou quando explicitamente habilitado)
if _deve_executar_bootstrap_db():
    with app.app_context():
        db.create_all()
        _garantir_colunas_usuario()

# Em produção, executa apenas migração leve de colunas já existentes (sem create_all)
# para evitar quebra após deploy quando novas colunas são adicionadas ao modelo.
if flask_env == 'production':
    with app.app_context():
        try:
            _garantir_colunas_usuario()
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
    """Normaliza texto para comparação entre imóveis semelhantes."""
    return (valor or '').strip().lower()


def _normalizar_negocio(valor):
    """Converte valores legados de negócio para uma chave canônica."""
    negocio = _normalizar_texto(valor)
    if negocio == 'compra':
        return 'venda'
    return negocio


def _negocio_canonico(valor):
    """Retorna o valor canônico de negócio para persistência e exibição."""
    negocio = _normalizar_negocio(valor)
    if negocio == 'venda':
        return 'Venda'
    if negocio == 'aluguel':
        return 'Aluguel'
    return (valor or '').strip()


def _padronizar_negocio_imovel(imovel):
    """Padroniza o negócio apenas em memória para exibição consistente."""
    if imovel:
        imovel.negocio = _negocio_canonico(imovel.negocio)
    return imovel


def _padronizar_negocio_imoveis(imoveis):
    """Padroniza o negócio em listas de imóveis."""
    for imovel in imoveis:
        _padronizar_negocio_imovel(imovel)
    return imoveis


def aplicar_radar_oportunidades(imoveis):
    """Marca imóveis com preço pelo menos 10% abaixo da média do grupo comparável."""
    if not imoveis:
        return

    negocio_agrupado = case(
        (func.lower(func.trim(Imovel.negocio)) == 'compra', 'venda'),
        else_=func.lower(func.trim(Imovel.negocio))
    )

    estatisticas = (
        db.session.query(
            negocio_agrupado.label('negocio'),
            func.lower(func.trim(Imovel.cidade)).label('cidade'),
            func.lower(func.trim(Imovel.bairro)).label('bairro'),
            func.lower(func.trim(Imovel.tipo)).label('tipo'),
            Imovel.quartos.label('quartos'),
            func.avg(Imovel.preco).label('preco_medio'),
            func.count(Imovel.id).label('total_imoveis')
        )
        .filter(Imovel.ativo.is_(True))
        .group_by(
            negocio_agrupado,
            func.lower(func.trim(Imovel.cidade)),
            func.lower(func.trim(Imovel.bairro)),
            func.lower(func.trim(Imovel.tipo)),
            Imovel.quartos,
        )
        .all()
    )

    mapa_medias = {
        (item.negocio, item.cidade, item.bairro, item.tipo, item.quartos): (item.preco_medio, item.total_imoveis)
        for item in estatisticas
    }

    for imovel in imoveis:
        _padronizar_negocio_imovel(imovel)
        imovel.eh_oportunidade = False
        imovel.preco_medio_regiao = None
        imovel.desconto_oportunidade = None
        imovel.total_comparaveis = 0

        chave = (
            _normalizar_negocio(imovel.negocio),
            _normalizar_texto(imovel.cidade),
            _normalizar_texto(imovel.bairro),
            _normalizar_texto(imovel.tipo),
            imovel.quartos,
        )

        comparativo = mapa_medias.get(chave)
        if not comparativo:
            continue

        preco_medio, total_imoveis = comparativo
        if not preco_medio or total_imoveis < OPORTUNIDADE_AMOSTRA_MINIMA:
            continue

        desconto = (preco_medio - imovel.preco) / preco_medio
        imovel.preco_medio_regiao = float(preco_medio)
        imovel.desconto_oportunidade = float(desconto)
        imovel.total_comparaveis = int(total_imoveis)
        imovel.eh_oportunidade = desconto >= OPORTUNIDADE_DESCONTO_MINIMO

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