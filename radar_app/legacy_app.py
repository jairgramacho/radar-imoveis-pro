import os
import re
import math
import io
import importlib
import logging
from logging.handlers import RotatingFileHandler
from threading import Thread
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, Response, has_request_context
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from sqlalchemy import case, func, inspect, text
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
# import pillow_heif  # Comentado: trava no Codespace
from models import db, Usuario, Imovel, FotoImovel, Avaliacao, Mensagem, Notificacao, StripeEventoWebhook

load_dotenv()

from email_utils import mail, enviar_email_confirmacao_cadastro, enviar_email_redefinicao_senha
from config import config
from radar_app.blueprints import public_bp, billing_bp, chat_bp, admin_bp, auth_bp, imoveis_bp
from radar_app.blueprints.billing import _stripe_checkout_habilitado

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


def _registrar_alias_endpoints_auth():
    aliases = [
        ('cadastro', '/cadastro', ['GET', 'POST'], 'auth.cadastro'),
        ('login', '/login', ['GET', 'POST'], 'auth.login'),
        ('logout', '/logout', ['GET'], 'auth.logout'),
        ('confirmar_email', '/confirmar-email/<token>', ['GET'], 'auth.confirmar_email'),
        ('reenviar_confirmacao', '/reenviar-confirmacao', ['POST'], 'auth.reenviar_confirmacao'),
        ('esqueci_senha', '/esqueci-senha', ['GET', 'POST'], 'auth.esqueci_senha'),
        ('redefinir_senha', '/redefinir-senha/<token>', ['GET', 'POST'], 'auth.redefinir_senha'),
        ('configuracoes_conta', '/configuracoes-conta', ['GET', 'POST'], 'auth.configuracoes_conta'),
        ('excluir_conta', '/excluir-conta', ['POST'], 'auth.excluir_conta'),
    ]

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


def _registrar_alias_endpoints_imoveis():
    aliases = [
        ('index', '/', ['GET'], 'imoveis.index'),
        ('salvar', '/salvar', ['POST'], 'imoveis.salvar'),
        ('meus_anuncios', '/meus-anuncios', ['GET'], 'imoveis.meus_anuncios'),
        ('detalhe_imovel', '/imovel/<int:id>', ['GET'], 'imoveis.detalhe_imovel'),
        ('deletar_imovel', '/deletar-imovel/<int:id>', ['POST'], 'imoveis.deletar_imovel'),
        ('editar_imovel', '/editar-imovel/<int:id>', ['GET', 'POST'], 'imoveis.editar_imovel'),
    ]

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
    except Exception as e:
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
    """Retorna True quando as credenciais do Cloudinary estão configuradas."""
    return all([
        os.getenv('CLOUDINARY_CLOUD_NAME', '').strip(),
        os.getenv('CLOUDINARY_API_KEY', '').strip(),
        os.getenv('CLOUDINARY_API_SECRET', '').strip(),
    ])


def _cloudinary_uploader():
    """Carrega uploader do Cloudinary sob demanda para evitar hard dependency em dev."""
    if not _cloudinary_configurado():
        return None

    try:
        cloudinary_module = importlib.import_module('cloudinary')
        uploader_module = importlib.import_module('cloudinary.uploader')
        cloudinary_module.config(
            cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME', ''),
            api_key=os.getenv('CLOUDINARY_API_KEY', ''),
            api_secret=os.getenv('CLOUDINARY_API_SECRET', ''),
            secure=True,
        )
        return uploader_module
    except Exception as e:
        app.logger.warning('Cloudinary indisponível no ambiente: %s', str(e))
        return None


def _foto_eh_url(valor):
    """Identifica se o valor já é uma URL externa."""
    texto = (valor or '').strip().lower()
    return texto.startswith('http://') or texto.startswith('https://')


def _foto_url(valor, external=False):
    """Resolve URL de foto para arquivos locais e URLs externas."""
    if not valor:
        return url_for('static', filename='css/style.css', _external=external)
    if _foto_eh_url(valor):
        return valor
    return url_for('static', filename='uploads/' + valor, _external=external)


def _url_cloudinary_og(url):
    """Retorna URL Cloudinary otimizada para cards sociais em formato retrato."""
    if not url:
        return url

    texto = (url or '').strip()
    if 'res.cloudinary.com' not in texto or '/image/upload/' not in texto:
        return texto

    if '/image/upload/c_fill,w_1080,h_1350,q_auto,f_auto/' in texto:
        return texto

    return texto.replace(
        '/image/upload/',
        '/image/upload/c_fill,w_1080,h_1350,q_auto,f_auto/',
        1,
    )


def _arquivo_upload_existe(valor):
    """Valida se arquivo local de upload existe no disco."""
    if not valor or _foto_eh_url(valor):
        return True
    caminho = os.path.join(app.config['UPLOAD_FOLDER'], valor)
    return os.path.exists(caminho)


def _resolver_foto_preview(imovel):
    """Escolhe a melhor foto válida para preview social."""
    candidatas = []
    if imovel.foto:
        candidatas.append(imovel.foto)
    if imovel.fotos:
        candidatas.extend([foto.arquivo for foto in imovel.fotos if foto.arquivo])

    for foto_base in candidatas:
        if not _arquivo_upload_existe(foto_base):
            continue
        if _foto_eh_url(foto_base):
            return _url_cloudinary_og(foto_base)
        return _url_publica('static', filename='uploads/' + foto_base)

    return _url_publica('og_placeholder', tipo=imovel.tipo, cidade=imovel.cidade)


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
LIMITES_ANUNCIOS_POR_PLANO = {
    'free': 3,
    'pro': 15,
    'empresa': 50,
}


def _status_assinatura_bloqueada(status_assinatura):
    status = (status_assinatura or '').strip().lower()
    return status in {'vencida', 'cancelada', 'inadimplente', 'incompleta'}


def _pausar_todos_anuncios_usuario(usuario_id):
    Imovel.query.filter_by(usuario_id=usuario_id, ativo=True).update({Imovel.ativo: False}, synchronize_session=False)


def _reativar_todos_anuncios_usuario(usuario_id):
    Imovel.query.filter_by(usuario_id=usuario_id, ativo=False).update({Imovel.ativo: True}, synchronize_session=False)


def _emails_admin_configurados():
    """Retorna conjunto de emails administradores definidos em ADMIN_EMAILS."""
    bruto = os.getenv('ADMIN_EMAILS', '')
    emails = {
        item.strip().lower()
        for item in bruto.split(',')
        if item.strip()
    }
    return emails


def _usuario_eh_admin(usuario):
    """Verifica se o usuário atual está autorizado como administrador."""
    if not usuario:
        return False

    return (usuario.email or '').strip().lower() in _emails_admin_configurados()


def _normalizar_plano(plano):
    plano_normalizado = (plano or 'free').strip().lower()
    return plano_normalizado if plano_normalizado in LIMITES_ANUNCIOS_POR_PLANO else 'free'


def _limite_anuncios_usuario(usuario):
    if not usuario:
        return LIMITES_ANUNCIOS_POR_PLANO['free']

    # Admin tem limite ilimitado
    if getattr(usuario, 'is_admin', False):
        return 999999

    limite_custom = getattr(usuario, 'limite_anuncios', None)
    if isinstance(limite_custom, int) and limite_custom > 0:
        return limite_custom

    return LIMITES_ANUNCIOS_POR_PLANO[_normalizar_plano(getattr(usuario, 'plano', 'free'))]


def _contar_anuncios_ativos(usuario_id):
    return Imovel.query.filter_by(usuario_id=usuario_id, ativo=True).count()


def _resumo_limite_anuncios(usuario):
    usados = _contar_anuncios_ativos(usuario.id)
    limite = _limite_anuncios_usuario(usuario)
    disponiveis = max(0, limite - usados)
    return {
        'plano': _normalizar_plano(getattr(usuario, 'plano', 'free')),
        'usados': usados,
        'limite': limite,
        'disponiveis': disponiveis,
        'atingiu_limite': usados >= limite,
    }


def _smtp_configurado():
    """Verifica se há provedor de email configurado (Resend API ou SMTP)."""
    resend_api_key = (app.config.get('RESEND_API_KEY') or '').strip().lower()
    resend_placeholders = {
        '',
        'your-resend-api-key',
        'sua-chave-resend',
    }
    if resend_api_key not in resend_placeholders:
        return True

    username = (app.config.get('MAIL_USERNAME') or '').strip().lower()
    password = (app.config.get('MAIL_PASSWORD') or '').strip().lower()

    placeholders = {
        '',
        'seu-email@gmail.com',
        'sua-senha-app',
        'your-email@gmail.com',
        'your-app-password',
    }
    return username not in placeholders and password not in placeholders


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
    """Executa envio de email e retorna (sucesso, mensagem_erro)."""
    if not _smtp_configurado():
        return False, 'Envio de email não configurado no servidor (configure RESEND_API_KEY ou SMTP).'

    timeout_segundos = int(os.getenv('EMAIL_SEND_TIMEOUT', '12'))
    resultado = {'enviado': False, 'erro': None}
    flask_app = app

    def _worker_envio():
        with flask_app.app_context():
            try:
                resultado['enviado'] = bool(funcao_envio(*args))
            except Exception as e:
                resultado['erro'] = str(e)
                resultado['enviado'] = False

    try:
        thread = Thread(target=_worker_envio, daemon=True)
        thread.start()
        thread.join(timeout=timeout_segundos)

        if thread.is_alive():
            app.logger.warning('Timeout no envio de email após %ss', timeout_segundos)
            return False, 'Timeout no envio de email. Tente novamente em alguns instantes.'

        enviado = resultado['enviado']
    except Exception:
        enviado = False

    if resultado['erro']:
        app.logger.warning('Falha no envio de email: %s', resultado['erro'])

    if not enviado:
        return False, 'Não foi possível enviar email no momento.'

    return True, None


def _disparar_email_assincrono(funcao_envio, *args):
    """Dispara envio de email sem bloquear a requisição do usuário."""
    if not _smtp_configurado():
        return False

    flask_app = app

    def _worker_envio():
        with flask_app.app_context():
            try:
                funcao_envio(*args)
            except Exception:
                flask_app.logger.warning('Falha ao enviar email em background.', exc_info=True)

    try:
        Thread(target=_worker_envio, daemon=True).start()
        return True
    except Exception:
        return False


@app.route('/healthz')
def healthcheck():
    """Healthcheck simples para monitoramento do serviço."""
    try:
        db.session.execute(text('SELECT 1'))
        db_status = 'ok'
    except Exception:
        db_status = 'error'

    payload = {
        'status': 'ok' if db_status == 'ok' else 'degraded',
        'service': 'radar-imoveis-pro',
        'database': db_status,
        'email_configurado': _smtp_configurado(),
        'smtp_configurado': _smtp_configurado(),
    }
    return jsonify(payload), (200 if db_status == 'ok' else 503)


@app.route('/healthz/ready', methods=['GET'])
def readiness_check():
    """Verifica se o app esta pronto para receber requisicoes."""
    try:
        db.session.execute(text('SELECT 1'))

        payload = {
            'status': 'ready',
            'service': 'radar-imoveis-pro',
            'database': 'ok',
            'email': 'ok' if _smtp_configurado() else 'unconfigured',
            'stripe': 'ok' if _stripe_checkout_habilitado() else 'unconfigured',
        }
        return jsonify(payload), 200
    except Exception as e:
        app.logger.error('Readiness check falhou: %s', str(e), exc_info=True)
        return jsonify({'status': 'not_ready', 'erro': str(e)}), 503


def _validar_whatsapp(whatsapp):
    """Valida WhatsApp brasileiro com 10 ou 11 dígitos (DDD + número)."""
    digitos = re.sub(r'\D', '', whatsapp or '')
    if len(digitos) not in (10, 11):
        return None
    return digitos


def _serializer_tokens():
    return URLSafeTimedSerializer(app.config['SECRET_KEY'])


def _gerar_token_email(email, objetivo):
    """Gera token assinado para confirmação de email e reset de senha."""
    return _serializer_tokens().dumps({'email': email, 'objetivo': objetivo}, salt='radar-imoveis-auth')


def _validar_token_email(token, objetivo, max_age=3600):
    """Valida token assinado e objetivo esperado."""
    try:
        payload = _serializer_tokens().loads(token, salt='radar-imoveis-auth', max_age=max_age)
    except SignatureExpired:
        return None, 'expirado'
    except BadSignature:
        return None, 'invalido'

    if payload.get('objetivo') != objetivo:
        return None, 'invalido'

    return payload.get('email'), None


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
    """Verifica se o arquivo é permitido"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def processar_imagem(arquivo):
    """
    Processa a imagem: converte HEIC/HEIF para JPG se necessário
    Retorna: (nome_arquivo_processado, success)
    """
    try:
        if not arquivo or not arquivo.filename:
            return None, False
        
        # Obter extensão
        ext = arquivo.filename.rsplit('.', 1)[1].lower() if '.' in arquivo.filename else ''
        
        if ext not in ALLOWED_EXTENSIONS:
            return None, False
        
        nome_original = secure_filename(arquivo.filename)
        timestamp = int(datetime.utcnow().timestamp())
        
        # Se for HEIC/HEIF, converter para JPG
        if ext in ['heic', 'heif']:
            try:
                # Abrir imagem HEIC
                imagem = Image.open(arquivo.stream)
                
                # Converter para RGB (se necessário)
                if imagem.mode in ('RGBA', 'LA', 'P'):
                    imagem = imagem.convert('RGB')
                
                # Gerar nome em JPG
                nome_sem_ext = nome_original.rsplit('.', 1)[0]
                nome_novo = f"{timestamp}_{nome_sem_ext}.jpg"

                uploader = _cloudinary_uploader()
                if uploader:
                    buffer = io.BytesIO()
                    imagem.save(buffer, 'JPEG', quality=85, optimize=True)
                    buffer.seek(0)
                    upload_result = uploader.upload(
                        buffer,
                        folder='radar-imoveis-pro',
                        public_id=nome_novo.rsplit('.', 1)[0],
                        resource_type='image',
                        overwrite=False,
                    )
                    return upload_result.get('secure_url'), True

                caminho = os.path.join(app.config['UPLOAD_FOLDER'], nome_novo)

                # Salvar como JPG
                imagem.save(caminho, 'JPEG', quality=85, optimize=True)

                return nome_novo, True
            except Exception as e:
                app.logger.warning('Erro ao converter HEIC: %s', str(e))
                return None, False
        else:
            # Para outros formatos, enviar/salvar normalmente
            nome_novo = f"{timestamp}_{nome_original}"

            uploader = _cloudinary_uploader()
            if uploader:
                arquivo.stream.seek(0)
                upload_result = uploader.upload(
                    arquivo.stream,
                    folder='radar-imoveis-pro',
                    public_id=nome_novo.rsplit('.', 1)[0],
                    resource_type='image',
                    overwrite=False,
                )
                return upload_result.get('secure_url'), True

            caminho = os.path.join(app.config['UPLOAD_FOLDER'], nome_novo)
            arquivo.save(caminho)
            return nome_novo, True
    
    except Exception as e:
        app.logger.warning('Erro ao processar imagem: %s', str(e), exc_info=True)
        return None, False

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
# ROTAS PRINCIPAIS
# ============================================


@app.route('/robots.txt')
def robots_txt():
    """Serve robots.txt para orientar rastreadores."""
    return app.send_static_file('robots.txt')


@app.route('/sitemap.xml')
def sitemap_xml():
    """Gera sitemap dinamico com paginas principais e imoveis ativos."""
    urls = [
        {
            'loc': url_for('index', _external=True),
            'lastmod': datetime.utcnow().strftime('%Y-%m-%d'),
            'changefreq': 'hourly',
        },
        {
            'loc': url_for('billing.planos', _external=True),
            'lastmod': datetime.utcnow().strftime('%Y-%m-%d'),
            'changefreq': 'weekly',
        },
    ]

    imoveis_ativos = Imovel.query.filter_by(ativo=True).all()
    for imovel in imoveis_ativos:
        referencia_data = imovel.atualizado_em or imovel.criado_em or datetime.utcnow()
        urls.append({
            'loc': url_for('detalhe_imovel', id=imovel.id, _external=True),
            'lastmod': referencia_data.strftime('%Y-%m-%d'),
            'changefreq': 'daily',
        })

    xml = render_template('sitemap.xml', urls=urls)
    return Response(xml, mimetype='application/xml')

@app.route('/og-placeholder')
def og_placeholder():
    """Gera imagem de placeholder otimizada para Open Graph (1200x628)."""
    try:
        tipo = request.args.get('tipo', 'Imóvel')
        cidade = request.args.get('cidade', 'Brasil')
        
        # Limitar tamanho do texto
        tipo = tipo[:30] if tipo else 'Imóvel'
        cidade = cidade[:30] if cidade else 'Brasil'
        
        # Criar imagem com dimensões Open Graph ideais
        img = Image.new('RGB', (1200, 628), color=(45, 77, 144))  # Azul do brand
        
        try:
            draw = ImageDraw.Draw(img)
            
            # Tentar usar uma fonte disponível
            try:
                font_grande = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 80)
                font_pequena = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 40)
            except:
                font_grande = ImageFont.load_default()
                font_pequena = ImageFont.load_default()
            
            # Desenhar texto
            texto1 = tipo
            texto2 = f"em {cidade}"
            
            # Calcular posições centralizadas
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
            app.logger.debug('Erro ao desenhar texto no placeholder: %s', str(e))
            pass  # Retorna imagem sem texto se falhar
        
        # Retornar como PNG
        img_io = io.BytesIO()
        img.save(img_io, 'PNG')
        img_io.seek(0)
        
        return Response(img_io.getvalue(), mimetype='image/png', 
                       headers={'Cache-Control': 'public, max-age=86400'})
    except Exception as e:
        app.logger.error('Erro ao gerar placeholder: %s', str(e))
        # Retorna imagem azul simples em caso de erro
        img = Image.new('RGB', (1200, 628), color=(45, 77, 144))
        img_io = io.BytesIO()
        img.save(img_io, 'PNG')
        img_io.seek(0)
        return Response(img_io.getvalue(), mimetype='image/png')

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

# ============================================
# DASHBOARD
# ============================================

@app.route('/dashboard')
def dashboard():
    """Painel de controle do anunciante"""
    usuario = get_usuario_logado()
    
    if not usuario:
        flash('Você precisa estar logado!', 'error')
        return redirect(url_for('login'))
    
    # Compilar estatísticas
    imoveis = Imovel.query.filter_by(usuario_id=usuario.id).all()
    _padronizar_negocio_imoveis(imoveis)
    
    total_imoveis = len(imoveis)
    total_visualizacoes = sum(i.visualizacoes for i in imoveis)
    rating = usuario.get_rating()
    total_avaliacoes = usuario.get_total_avaliacoes()
    
    mensagens_nao_lidas = Mensagem.query.filter_by(
        destinatario_id=usuario.id, 
        lida=False
    ).count()
    limite_anuncios = _resumo_limite_anuncios(usuario)
    stripe_checkout_habilitado = _stripe_checkout_habilitado()
    
    # Últimos 5 anúncios
    ultimos_imoveis = sorted(imoveis, key=lambda x: x.criado_em, reverse=True)[:5]
    
    # Imóveis mais visualizados
    imoveis_populares = sorted(imoveis, key=lambda x: x.visualizacoes, reverse=True)[:5]
    
    return render_template('dashboard.html',
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
                          preco_pro_brl=app.config['PRECO_PRO_BRL'],
                          preco_empresa_brl=app.config['PRECO_EMPRESA_BRL'])

# ============================================
# AVALIAÇÕES
# ============================================

@app.route('/avaliar-anunciante/<int:usuario_id>', methods=['GET', 'POST'])
def avaliar_anunciante(usuario_id):
    """Avalia um anunciante"""
    usuario_logado = get_usuario_logado()
    
    if not usuario_logado:
        flash('Você precisa estar logado!', 'error')
        return redirect(url_for('login'))
    
    anunciante = Usuario.query.get_or_404(usuario_id)
    
    if request.method == 'POST':
        try:
            estrelas = int(request.form.get('estrelas', 5))
            comentario = request.form.get('comentario', '').strip()
            imovel_id = request.form.get('imovel_id')
            
            if estrelas < 1 or estrelas > 5:
                flash('Avaliação deve ser entre 1 e 5 estrelas!', 'error')
                return redirect(url_for('avaliar_anunciante', usuario_id=usuario_id))
            
            avaliacao = Avaliacao(
                usuario_id=usuario_id,
                imovel_id=imovel_id,
                avaliador_id=usuario_logado.id,
                estrelas=estrelas,
                comentario=comentario
            )
            
            db.session.add(avaliacao)
            db.session.commit()
            
            flash('Avaliação enviada com sucesso!', 'success')
            return redirect(url_for('detalhe_imovel', id=imovel_id) if imovel_id else url_for('index', aba='buscar'))
        
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao enviar avaliação: {str(e)}', 'error')
    
    imovel_id = request.args.get('imovel_id')
    imovel = None
    if imovel_id:
        imovel = Imovel.query.get(imovel_id)
        _padronizar_negocio_imovel(imovel)
    
    return render_template('avaliar.html', 
                          usuario=usuario_logado,
                          anunciante=anunciante,
                          imovel=imovel)

# ============================================
# MÚLTIPLAS FOTOS
# ============================================

@app.route('/imovel/<int:id>/adicionar-fotos', methods=['GET', 'POST'])
def adicionar_fotos(id):
    """Adiciona múltiplas fotos a um imóvel"""
    usuario = get_usuario_logado()
    
    if not usuario:
        flash('Você precisa estar logado!', 'error')
        return redirect(url_for('login'))
    
    imovel = Imovel.query.get_or_404(id)
    _padronizar_negocio_imovel(imovel)
    
    # Verificar se é o dono
    if imovel.usuario_id != usuario.id:
        flash('Você não tem permissão!', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        files = request.files.getlist('fotos')
        
        if not files:
            flash('Selecione pelo menos uma foto!', 'error')
            return redirect(url_for('adicionar_fotos', id=id))
        
        try:
            for arq in files:
                if arq and allowed_file(arq.filename):
                    nome_arquivo, sucesso = processar_imagem(arq)
                    
                    if sucesso and nome_arquivo:
                        foto = FotoImovel(
                            imovel_id=id,
                            arquivo=nome_arquivo,
                            ordem=len(imovel.fotos)
                        )
                        db.session.add(foto)
            
            db.session.commit()
            flash(f'{len(files)} foto(s) adicionada(s) com sucesso!', 'success')
        
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao adicionar fotos: {str(e)}', 'error')
        
        return redirect(url_for('detalhe_imovel', id=id))
    
    return render_template('adicionar_fotos.html', usuario=usuario, imovel=imovel)


def create_app(config_override=None):
    """Retorna a aplicação Flask já inicializada, com overrides opcionais."""
    if config_override:
        app.config.update(config_override)
    return app

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)