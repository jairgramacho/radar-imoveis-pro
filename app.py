import os
import re
import math
import io
import importlib
from threading import Thread
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_cors import CORS
from sqlalchemy import case, func, inspect, text
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from PIL import Image
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
import pillow_heif
from models import db, Usuario, Imovel, FotoImovel, Avaliacao, Mensagem, Notificacao

load_dotenv()

from email_utils import mail, enviar_email_confirmacao_cadastro, enviar_email_redefinicao_senha
from config import config

# Registrar conversor HEIC para PIL
pillow_heif.register_heif_opener()

app = Flask(__name__)


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

    for comando in comandos:
        db.session.execute(text(comando))

    if comandos:
        db.session.commit()


def _deve_executar_bootstrap_db():
    """Controla bootstrap automático do banco para evitar travas no boot em produção."""
    override = os.getenv('RUN_DB_BOOTSTRAP')
    if override is not None:
        return override.strip().lower() in {'1', 'true', 'yes', 'on'}
    return flask_env != 'production'


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


@app.context_processor
def inject_template_helpers():
    """Disponibiliza helpers e contadores globais para templates."""
    mensagens_nao_lidas = 0
    usuario_id = session.get('usuario_id')

    if usuario_id:
        try:
            mensagens_nao_lidas = Mensagem.query.filter_by(
                destinatario_id=usuario_id,
                lida=False,
            ).count()
        except Exception:
            mensagens_nao_lidas = 0

    return {
        'foto_url': _foto_url,
        'mensagens_nao_lidas': mensagens_nao_lidas,
    }


# Criar tabelas automaticamente em desenvolvimento (ou quando explicitamente habilitado)
if _deve_executar_bootstrap_db():
    with app.app_context():
        db.create_all()
        _garantir_colunas_usuario()

OPORTUNIDADE_DESCONTO_MINIMO = 0.10
OPORTUNIDADE_AMOSTRA_MINIMA = 5
ITENS_POR_PAGINA = 12


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
    """Monta URL pública usando APP_URL para links enviados por email."""
    caminho = url_for(endpoint, _external=False, **values)
    base = (app.config.get('APP_URL') or '').strip().rstrip('/')
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
# ROTAS DE AUTENTICAÇÃO
# ============================================

@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    """Página de cadastro de novo usuário"""
    if request.method == 'POST':
        try:
            nome = request.form.get('nome', '').strip()
            email = request.form.get('email', '').strip()
            senha = request.form.get('senha', '')
            whatsapp = request.form.get('whatsapp', '').strip()
            
            # Validações
            if not all([nome, email, senha, whatsapp]):
                flash('Todos os campos são obrigatórios!', 'error')
                return redirect(url_for('cadastro'))
            
            if len(senha) < 6:
                flash('Senha deve ter no mínimo 6 caracteres!', 'error')
                return redirect(url_for('cadastro'))

            whatsapp_validado = _validar_whatsapp(whatsapp)
            if not whatsapp_validado:
                flash('WhatsApp inválido. Informe DDD + número (10 ou 11 dígitos).', 'error')
                return redirect(url_for('cadastro'))
            
            # Verificar se email já existe
            if Usuario.query.filter_by(email=email).first():
                flash('Este e-mail já está cadastrado!', 'error')
                return redirect(url_for('cadastro'))
            
            # Criar novo usuário
            exigir_confirmacao = _confirmacao_email_obrigatoria()
            novo_usuario = Usuario(
                nome=nome,
                email=email,
                whatsapp=whatsapp_validado,
                email_confirmado=not exigir_confirmacao,
                confirmado_em=(datetime.utcnow() if not exigir_confirmacao else None),
            )
            novo_usuario.set_password(senha)
            db.session.add(novo_usuario)
            db.session.commit()

            if exigir_confirmacao:
                token_confirmacao = _gerar_token_email(novo_usuario.email, 'confirmar-email')
                link_confirmacao = _url_publica('confirmar_email', token=token_confirmacao)
                enviado, erro_envio = _enviar_email_com_status(
                    enviar_email_confirmacao_cadastro,
                    novo_usuario.email,
                    novo_usuario.nome,
                    link_confirmacao,
                )

                if enviado:
                    flash('Cadastro realizado! Enviamos um email para confirmação da sua conta.', 'success')
                else:
                    flash(
                        'Cadastro realizado, mas o email de confirmação não foi enviado agora. '
                        f'{erro_envio} Configure RESEND_API_KEY ou MAIL_USERNAME/MAIL_PASSWORD e tente reenviar na tela de login.',
                        'error'
                    )
            else:
                flash(
                    'Cadastro realizado! Como o envio de email não está configurado, sua conta foi liberada automaticamente.',
                    'success'
                )
            return redirect(url_for('login'))
        
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao cadastrar: {str(e)}', 'error')
    
    return render_template('cadastro.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Página de login"""
    if request.method == 'POST':
        try:
            email = request.form.get('email', '').strip()
            senha = request.form.get('senha', '')
            
            if not email or not senha:
                flash('E-mail e senha são obrigatórios!', 'error')
                return redirect(url_for('login'))
            
            # Buscar usuário
            usuario = Usuario.query.filter_by(email=email).first()
            
            if usuario and usuario.check_password(senha):
                if not getattr(usuario, 'email_confirmado', True) and not _confirmacao_email_obrigatoria():
                    usuario.email_confirmado = True
                    if not getattr(usuario, 'confirmado_em', None):
                        usuario.confirmado_em = datetime.utcnow()
                    db.session.commit()

                if not getattr(usuario, 'email_confirmado', True):
                    token_confirmacao = _gerar_token_email(usuario.email, 'confirmar-email')
                    link_confirmacao = _url_publica('confirmar_email', token=token_confirmacao)
                    enviado, erro_envio = _enviar_email_com_status(
                        enviar_email_confirmacao_cadastro,
                        usuario.email,
                        usuario.nome,
                        link_confirmacao,
                    )
                    if enviado:
                        flash('Confirme seu email antes de entrar. Um novo link foi enviado.', 'error')
                    else:
                        flash(
                            'Confirme seu email antes de entrar. '
                            f'Não foi possível reenviar o link agora: {erro_envio}',
                            'error'
                        )
                    return redirect(url_for('login'))

                session['usuario_id'] = usuario.id
                session['usuario_nome'] = usuario.nome
                flash(f'Bem-vindo, {usuario.nome}!', 'success')
                return redirect(url_for('index', aba='buscar'))
            else:
                flash('E-mail ou senha incorretos!', 'error')
        
        except Exception as e:
            flash(f'Erro ao fazer login: {str(e)}', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Logout do usuário"""
    session.clear()
    flash('Você foi desconectado!', 'success')
    return redirect(url_for('index', aba='buscar'))


@app.route('/confirmar-email/<token>')
def confirmar_email(token):
    """Confirma o email da conta usando token assinado."""
    email, erro = _validar_token_email(token, 'confirmar-email', max_age=60 * 60 * 24)
    if erro:
        flash('Link de confirmação inválido ou expirado.', 'error')
        return redirect(url_for('login'))

    usuario = Usuario.query.filter_by(email=email).first()
    if not usuario:
        flash('Conta não encontrada para este link.', 'error')
        return redirect(url_for('login'))

    if not usuario.email_confirmado:
        usuario.email_confirmado = True
        usuario.confirmado_em = datetime.utcnow()
        db.session.commit()

    flash('Email confirmado com sucesso! Agora você já pode entrar.', 'success')
    return redirect(url_for('login'))


@app.route('/reenviar-confirmacao', methods=['POST'])
def reenviar_confirmacao():
    """Reenvia email de confirmação da conta."""
    email = request.form.get('email', '').strip()
    usuario = Usuario.query.filter_by(email=email).first() if email else None

    if usuario and not getattr(usuario, 'email_confirmado', True):
        token_confirmacao = _gerar_token_email(usuario.email, 'confirmar-email')
        link_confirmacao = _url_publica('confirmar_email', token=token_confirmacao)
        enviado, erro_envio = _enviar_email_com_status(
            enviar_email_confirmacao_cadastro,
            usuario.email,
            usuario.nome,
            link_confirmacao,
        )
        if not enviado:
            flash(f'Não foi possível reenviar o email agora: {erro_envio}', 'error')
            return redirect(url_for('login'))

    flash('Se o email informado existir e estiver pendente, um novo link foi enviado.', 'success')
    return redirect(url_for('login'))


@app.route('/esqueci-senha', methods=['GET', 'POST'])
def esqueci_senha():
    """Solicita redefinição de senha por email."""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        usuario = Usuario.query.filter_by(email=email).first() if email else None

        if usuario:
            token_reset = _gerar_token_email(usuario.email, 'reset-senha')
            link_reset = _url_publica('redefinir_senha', token=token_reset)
            if flask_env != 'production' and _permitir_fallback_reset_local() and not _smtp_configurado():
                flash('Email não configurado neste ambiente. Você será redirecionado para redefinir a senha agora.', 'success')
                return redirect(url_for('redefinir_senha', token=token_reset))

            if _reset_email_assincrono_habilitado():
                disparado = _disparar_email_assincrono(
                    enviar_email_redefinicao_senha,
                    usuario.email,
                    usuario.nome,
                    link_reset,
                )
                if not disparado:
                    app.logger.warning('Falha ao iniciar envio assíncrono de reset para %s', usuario.email)
            else:
                enviado, erro_envio = _enviar_email_com_status(
                    enviar_email_redefinicao_senha,
                    usuario.email,
                    usuario.nome,
                    link_reset,
                )
                if not enviado:
                    flash(f'Não foi possível enviar o email de recuperação agora: {erro_envio}', 'error')
                    return redirect(url_for('esqueci_senha'))

        flash('Se o email informado existir, você receberá instruções para redefinir a senha.', 'success')
        return redirect(url_for('login'))

    return render_template('esqueci_senha.html')


@app.route('/redefinir-senha/<token>', methods=['GET', 'POST'])
def redefinir_senha(token):
    """Tela de redefinição de senha via token."""
    email, erro = _validar_token_email(token, 'reset-senha', max_age=60 * 60)
    if erro:
        flash('Link de redefinição inválido ou expirado.', 'error')
        return redirect(url_for('esqueci_senha'))

    usuario = Usuario.query.filter_by(email=email).first()
    if not usuario:
        flash('Conta não encontrada.', 'error')
        return redirect(url_for('esqueci_senha'))

    if request.method == 'POST':
        senha = request.form.get('senha', '')
        confirmar_senha = request.form.get('confirmar_senha', '')

        if len(senha) < 6:
            flash('A nova senha deve ter no mínimo 6 caracteres.', 'error')
            return redirect(url_for('redefinir_senha', token=token))

        if senha != confirmar_senha:
            flash('A confirmação da senha não confere.', 'error')
            return redirect(url_for('redefinir_senha', token=token))

        usuario.set_password(senha)
        db.session.commit()

        flash('Senha redefinida com sucesso! Faça login com a nova senha.', 'success')
        return redirect(url_for('login'))

    return render_template('redefinir_senha.html', token=token)


@app.route('/configuracoes-conta', methods=['GET', 'POST'])
def configuracoes_conta():
    """Permite ao usuário editar dados de conta e senha."""
    usuario = get_usuario_logado()

    if not usuario:
        flash('Você precisa estar logado!', 'error')
        return redirect(url_for('login'))

    if request.method == 'POST':
        try:
            nome = request.form.get('nome', '').strip()
            email = request.form.get('email', '').strip()
            whatsapp = request.form.get('whatsapp', '').strip()

            senha_atual = request.form.get('senha_atual', '')
            nova_senha = request.form.get('nova_senha', '')
            confirmar_senha = request.form.get('confirmar_senha', '')

            if not all([nome, email, whatsapp]):
                flash('Nome, e-mail e WhatsApp são obrigatórios.', 'error')
                return redirect(url_for('configuracoes_conta'))

            whatsapp_validado = _validar_whatsapp(whatsapp)
            if not whatsapp_validado:
                flash('WhatsApp inválido. Informe DDD + número (10 ou 11 dígitos).', 'error')
                return redirect(url_for('configuracoes_conta'))

            email_em_uso = Usuario.query.filter(
                Usuario.email == email,
                Usuario.id != usuario.id
            ).first()

            if email_em_uso:
                flash('Este e-mail já está em uso por outra conta.', 'error')
                return redirect(url_for('configuracoes_conta'))

            if senha_atual or nova_senha or confirmar_senha:
                if not usuario.check_password(senha_atual):
                    flash('Senha atual incorreta.', 'error')
                    return redirect(url_for('configuracoes_conta'))

                if len(nova_senha) < 6:
                    flash('A nova senha deve ter no mínimo 6 caracteres.', 'error')
                    return redirect(url_for('configuracoes_conta'))

                if nova_senha != confirmar_senha:
                    flash('A confirmação da nova senha não confere.', 'error')
                    return redirect(url_for('configuracoes_conta'))

                usuario.set_password(nova_senha)

            usuario.nome = nome
            usuario.email = email
            usuario.whatsapp = whatsapp_validado

            db.session.commit()

            session['usuario_nome'] = usuario.nome
            flash('Configurações atualizadas com sucesso!', 'success')
            return redirect(url_for('configuracoes_conta'))

        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao atualizar configurações: {str(e)}', 'error')
            return redirect(url_for('configuracoes_conta'))

    return render_template('configuracoes_conta.html', usuario=usuario)

# ============================================
# ROTAS PRINCIPAIS
# ============================================

@app.route('/')
def index():
    """Página principal com abas de busca e anúncio"""
    usuario = get_usuario_logado()
    aba = request.args.get('aba', 'buscar')
    filtros = request.args.to_dict()
    pagina = request.args.get('pagina', 1, type=int)
    
    # Buscar imóveis
    query = Imovel.query.filter_by(ativo=True).order_by(Imovel.criado_em.desc())
    
    # Aplicar filtros
    if filtros.get('negocio'):
        negocio_filtro = filtros['negocio']
        if negocio_filtro == 'Venda':
            # Compatibilidade com registros legados que podem usar "Compra"
            query = query.filter(Imovel.negocio.in_(['Venda', 'Compra']))
        else:
            query = query.filter_by(negocio=negocio_filtro)
    
    if filtros.get('tipo'):
        query = query.filter_by(tipo=filtros['tipo'])
    
    if filtros.get('estado'):
        query = query.filter_by(estado=filtros['estado'])
    
    if filtros.get('cidade'):
        query = query.filter(Imovel.cidade.ilike(f"%{filtros['cidade']}%"))
    
    if filtros.get('preco_max'):
        try:
            preco_max = float(filtros['preco_max'].replace('R$','').replace('.','').replace(',','.').strip())
            query = query.filter(Imovel.preco <= preco_max)
        except:
            pass
    
    imoveis = query.all()
    aplicar_radar_oportunidades(imoveis)

    oportunidades = [imovel for imovel in imoveis if getattr(imovel, 'eh_oportunidade', False)]
    oportunidades.sort(key=lambda item: item.desconto_oportunidade or 0, reverse=True)

    if filtros.get('somente_oportunidades') == '1':
        imoveis = [imovel for imovel in imoveis if getattr(imovel, 'eh_oportunidade', False)]

    imoveis_pagina, imoveis_total, imoveis_total_paginas, pagina_ajustada = _paginar_lista(
        imoveis,
        pagina,
        ITENS_POR_PAGINA,
    )
    oportunidades_pagina, oportunidades_total, oportunidades_total_paginas, pagina_oportunidades = _paginar_lista(
        oportunidades,
        pagina,
        ITENS_POR_PAGINA,
    )

    argumentos_base = {k: v for k, v in filtros.items() if k != 'pagina'}
    argumentos_base['aba'] = aba
    total_paginas = imoveis_total_paginas if aba == 'buscar' else oportunidades_total_paginas
    pagina_corrente = pagina_ajustada if aba == 'buscar' else pagina_oportunidades
    links_paginacao = {
        p: url_for('index', **{**argumentos_base, 'pagina': p})
        for p in range(1, total_paginas + 1)
    }
    
    return render_template('index.html', 
                         imoveis=imoveis_pagina,
                         imoveis_total=imoveis_total,
                         oportunidades=oportunidades_pagina,
                         oportunidades_total=oportunidades_total,
                         aba=aba, 
                         busca=filtros,
                         pagina_atual=pagina_corrente,
                         total_paginas=total_paginas,
                         links_paginacao=links_paginacao,
                         usuario=usuario)

@app.route('/salvar', methods=['POST'])
def salvar():
    """Salva um novo anúncio de imóvel"""
    usuario = get_usuario_logado()
    
    # Verificar autenticação
    if not usuario:
        flash('Você precisa estar logado para anunciar!', 'error')
        return redirect(url_for('login'))
    
    try:
        f = request.form
        
        # Validação de campos obrigatórios
        campos_obrigatorios = ['estado', 'cidade', 'bairro', 'tipo', 'negocio', 'valor']
        for campo in campos_obrigatorios:
            if not f.get(campo):
                flash(f'Campo obrigatório não preenchido: {campo}', 'error')
                return redirect(url_for('index', aba='anunciar'))
        
        # Converter preço
        try:
            preco = float(f.get('valor').replace('R$','').replace('.','').replace(',','.').strip())
        except:
            flash('Preço inválido!', 'error')
            return redirect(url_for('index', aba='anunciar'))
        
        # Processar fotos (agora aceita múltiplas e converte HEIC)
        arquivos = request.files.getlist('foto')
        nome_foto_principal = None
        
        if arquivos and arquivos[0].filename:
            # Usar apenas a primeira foto como principal
            arq_principal = arquivos[0]
            if arq_principal and allowed_file(arq_principal.filename):
                nome_arquivo, sucesso = processar_imagem(arq_principal)
                if sucesso and nome_arquivo:
                    nome_foto_principal = nome_arquivo
        
        # Converter valores numéricos
        quartos = int(f.get('quartos', 0)) if f.get('quartos') else None
        vagas = int(f.get('vagas', 0)) if f.get('vagas') else None
        area = float(f.get('area', 0)) if f.get('area') else None
        
        # Criar novo imóvel
        imovel = Imovel(
            usuario_id=usuario.id,
            estado=f.get('estado'),
            cidade=f.get('cidade'),
            bairro=f.get('bairro'),
            tipo=f.get('tipo'),
            negocio=_negocio_canonico(f.get('negocio')),
            quartos=quartos,
            vagas=vagas,
            area=area,
            preco=preco,
            descricao=f.get('descricao', ''),
            foto=nome_foto_principal
        )
        
        db.session.add(imovel)
        db.session.commit()
        
        # Adicionar fotos adicionais (as demais além da principal e converte HEIC)
        for idx, arq in enumerate(arquivos[1:], start=1):
            if arq and allowed_file(arq.filename):
                nome_arquivo, sucesso = processar_imagem(arq)
                
                if sucesso and nome_arquivo:
                    foto = FotoImovel(
                        imovel_id=imovel.id,
                        arquivo=nome_arquivo,
                        ordem=idx
                    )
                    db.session.add(foto)
        
        db.session.commit()
        
        flash('Anúncio publicado com sucesso! Você pode adicionar mais fotos se desejar.', 'success')
        return redirect(url_for('detalhe_imovel', id=imovel.id))
    
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao publicar anúncio: {str(e)}', 'error')
        return redirect(url_for('index', aba='anunciar'))

@app.route('/meus-anuncios')
def meus_anuncios():
    """Lista os anúncios do usuário logado"""
    usuario = get_usuario_logado()
    
    if not usuario:
        flash('Você precisa estar logado!', 'error')
        return redirect(url_for('login'))
    
    imoveis = Imovel.query.filter_by(usuario_id=usuario.id).order_by(Imovel.criado_em.desc()).all()
    _padronizar_negocio_imoveis(imoveis)
    
    return render_template('meus_anuncios.html', imoveis=imoveis, usuario=usuario)

@app.route('/imovel/<int:id>')
def detalhe_imovel(id):
    """Página de detalhe do imóvel"""
    usuario = get_usuario_logado()
    imovel = Imovel.query.get_or_404(id)
    _padronizar_negocio_imovel(imovel)

    descricao_base = (imovel.descricao or '').strip()
    if not descricao_base:
        descricao_base = f"{imovel.tipo} em {imovel.cidade}/{imovel.estado}, no bairro {imovel.bairro}."
    descricao_meta = f"{descricao_base[:140]} | Preço: R$ {moeda_brl(imovel.preco)}"
    
    return render_template('detalhe_imovel.html', imovel=imovel, usuario=usuario, descricao_meta=descricao_meta)

@app.route('/deletar-imovel/<int:id>', methods=['POST'])
def deletar_imovel(id):
    """Deleta um anúncio (apenas o dono pode)"""
    usuario = get_usuario_logado()
    
    if not usuario:
        flash('Você precisa estar logado!', 'error')
        return redirect(url_for('login'))
    
    imovel = Imovel.query.get_or_404(id)
    
    if imovel.usuario_id != usuario.id:
        flash('Você não tem permissão para deletar este anúncio!', 'error')
        return redirect(url_for('index'))
    
    try:
        # Deletar foto se existir
        if imovel.foto and not _foto_eh_url(imovel.foto):
            caminho_foto = os.path.join(app.config['UPLOAD_FOLDER'], imovel.foto)
            if os.path.exists(caminho_foto):
                os.remove(caminho_foto)
        
        db.session.delete(imovel)
        db.session.commit()
        
        flash('Anúncio deletado com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao deletar: {str(e)}', 'error')
    
    return redirect(url_for('meus_anuncios'))

@app.route('/editar-imovel/<int:id>', methods=['GET', 'POST'])
def editar_imovel(id):
    """Edita um anúncio (apenas o dono pode)"""
    usuario = get_usuario_logado()
    
    if not usuario:
        flash('Você precisa estar logado!', 'error')
        return redirect(url_for('login'))
    
    imovel = Imovel.query.get_or_404(id)
    
    if imovel.usuario_id != usuario.id:
        flash('Você não tem permissão para editar este anúncio!', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        try:
            f = request.form
            
            # Validação de campos obrigatórios
            campos_obrigatorios = ['estado', 'cidade', 'bairro', 'tipo', 'negocio', 'valor']
            for campo in campos_obrigatorios:
                if not f.get(campo):
                    flash(f'Campo obrigatório não preenchido: {campo}', 'error')
                    return redirect(url_for('editar_imovel', id=id))
            
            # Converter preço
            try:
                preco = float(f.get('valor').replace('R$','').replace('.','').replace(',','.').strip())
            except:
                flash('Preço inválido!', 'error')
                return redirect(url_for('editar_imovel', id=id))
            
            # Processar foto se uma nova foi enviada (converte HEIC se necessário)
            arq = request.files.get('foto')
            if arq and arq.filename:
                if allowed_file(arq.filename):
                    # Deletar foto antiga se existir
                    if imovel.foto and not _foto_eh_url(imovel.foto):
                        caminho_foto = os.path.join(app.config['UPLOAD_FOLDER'], imovel.foto)
                        if os.path.exists(caminho_foto):
                            os.remove(caminho_foto)
                    
                    nome_foto, sucesso = processar_imagem(arq)
                    if sucesso and nome_foto:
                        imovel.foto = nome_foto
            
            # Converter valores numéricos
            quartos = int(f.get('quartos', 0)) if f.get('quartos') else None
            vagas = int(f.get('vagas', 0)) if f.get('vagas') else None
            area = float(f.get('area', 0)) if f.get('area') else None
            
            # Atualizar imóvel
            imovel.estado = f.get('estado')
            imovel.cidade = f.get('cidade')
            imovel.bairro = f.get('bairro')
            imovel.tipo = f.get('tipo')
            imovel.negocio = _negocio_canonico(f.get('negocio'))
            imovel.quartos = quartos
            imovel.vagas = vagas
            imovel.area = area
            imovel.preco = preco
            imovel.descricao = f.get('descricao', '')
            
            db.session.commit()
            
            flash('Anúncio atualizado com sucesso!', 'success')
            return redirect(url_for('meus_anuncios'))
        
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao atualizar anúncio: {str(e)}', 'error')
            return redirect(url_for('editar_imovel', id=id))
    
    _padronizar_negocio_imovel(imovel)
    return render_template('editar_imovel.html', imovel=imovel, usuario=usuario)


# ============================================
# PÁGINAS INSTITUCIONAIS
# ============================================

@app.route('/termos-de-uso')
def termos_uso():
    """Página de termos de uso"""
    usuario = get_usuario_logado()
    return render_template('termos_uso.html', usuario=usuario)


@app.route('/politica-de-privacidade')
def politica_privacidade():
    """Página de política de privacidade"""
    usuario = get_usuario_logado()
    return render_template('politica_privacidade.html', usuario=usuario)


@app.route('/denunciar-abuso', methods=['GET', 'POST'])
def denunciar_abuso():
    """Página de denúncia de abuso"""
    usuario = get_usuario_logado()

    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        email = request.form.get('email', '').strip()
        motivo = request.form.get('motivo', '').strip()
        mensagem = request.form.get('mensagem', '').strip()

        if not all([nome, email, motivo, mensagem]):
            flash('Preencha todos os campos para enviar a denúncia.', 'error')
            return redirect(url_for('denunciar_abuso'))

        flash('Denúncia recebida com sucesso. Nossa equipe irá analisar o caso.', 'success')
        return redirect(url_for('denunciar_abuso'))

    return render_template('denunciar_abuso.html', usuario=usuario)


@app.route('/faq-ajuda')
def faq_ajuda():
    """Página de FAQ e ajuda"""
    usuario = get_usuario_logado()
    return render_template('faq_ajuda.html', usuario=usuario)

# ============================================
# TRATAMENTO DE ERROS
# ============================================

@app.errorhandler(404)
def pagina_nao_encontrada(e):
    """Página não encontrada"""
    return redirect(url_for('index', aba='buscar')), 404

@app.errorhandler(500)
def erro_interno(e):
    """Erro interno do servidor"""
    flash('Erro interno do servidor. Tente novamente.', 'error')
    return redirect(url_for('index', aba='buscar')), 500

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
                          mensagens_nao_lidas=mensagens_nao_lidas,
                          ultimos_imoveis=ultimos_imoveis,
                          imoveis_populares=imoveis_populares)

# ============================================
# CHAT ENTRE USUÁRIOS
# ============================================

@app.route('/chat')
def chat():
    """Inbox de conversas com painel da conversa selecionada."""
    usuario = get_usuario_logado()
    
    if not usuario:
        flash('Você precisa estar logado!', 'error')
        return redirect(url_for('login'))
    
    # Buscar todas as mensagens do usuário, da mais recente para a mais antiga.
    mensagens_usuario = Mensagem.query.filter(
        (Mensagem.remetente_id == usuario.id) | (Mensagem.destinatario_id == usuario.id)
    ).order_by(Mensagem.criado_em.desc()).all()

    # Compilar conversas únicas por usuário + imóvel.
    conversas = {}

    for msg in mensagens_usuario:
        if msg.destinatario_id == usuario.id:
            outro_usuario = msg.remetente
        else:
            outro_usuario = msg.destinatario

        chave = (outro_usuario.id, msg.imovel_id)
        if chave not in conversas:
            conversas[chave] = {
                'outro_usuario': outro_usuario,
                'imovel': msg.imovel,
                'imovel_id': msg.imovel_id,
                'ultima_msg': msg,
                'nao_lidas': 0,
            }

        if msg.destinatario_id == usuario.id and not msg.lida:
            conversas[chave]['nao_lidas'] += 1

    # Ordenar pela última mensagem
    conversas_lista = sorted(conversas.values(), key=lambda x: x['ultima_msg'].criado_em, reverse=True)

    usuario_id_selecionado = request.args.get('usuario_id', type=int)
    imovel_id_param = request.args.get('imovel_id', '').strip().lower()
    imovel_id_selecionado = None
    if imovel_id_param and imovel_id_param not in {'none', 'null'}:
        try:
            imovel_id_selecionado = int(imovel_id_param)
        except ValueError:
            imovel_id_selecionado = None

    conversa_ativa = None
    mensagens_ativas = []

    if usuario_id_selecionado:
        for conversa in conversas_lista:
            if conversa['outro_usuario'].id != usuario_id_selecionado:
                continue

            if imovel_id_param:
                if conversa['imovel_id'] == imovel_id_selecionado:
                    conversa_ativa = conversa
                    break
                continue

            conversa_ativa = conversa
            break

    if not conversa_ativa and conversas_lista:
        conversa_ativa = conversas_lista[0]

    if conversa_ativa:
        mensagens_query = Mensagem.query.filter(
            ((Mensagem.remetente_id == usuario.id) & (Mensagem.destinatario_id == conversa_ativa['outro_usuario'].id)) |
            ((Mensagem.remetente_id == conversa_ativa['outro_usuario'].id) & (Mensagem.destinatario_id == usuario.id))
        )

        if conversa_ativa['imovel_id'] is None:
            mensagens_query = mensagens_query.filter(Mensagem.imovel_id.is_(None))
        else:
            mensagens_query = mensagens_query.filter(Mensagem.imovel_id == conversa_ativa['imovel_id'])

        mensagens_ativas = mensagens_query.order_by(Mensagem.criado_em.asc()).all()

        alterou_leitura = False
        for msg in mensagens_ativas:
            if msg.destinatario_id == usuario.id and not msg.lida:
                msg.lida = True
                alterou_leitura = True
        if alterou_leitura:
            db.session.commit()

        # Recalcula badge da conversa ativa após marcar como lida.
        conversa_ativa['nao_lidas'] = 0

    return render_template(
        'chat.html',
        usuario=usuario,
        conversas=conversas_lista,
        conversa_ativa=conversa_ativa,
        mensagens_ativas=mensagens_ativas,
    )

@app.route('/chat/<int:usuario_id>')
def conversa(usuario_id):
    """Compatibilidade: redireciona conversa para o inbox em /chat."""
    return redirect(url_for('chat', usuario_id=usuario_id))

@app.route('/enviar-mensagem/<int:usuario_id>', methods=['POST'])
def enviar_mensagem(usuario_id):
    """Envia uma mensagem para outro usuário"""
    usuario = get_usuario_logado()
    
    if not usuario:
        flash('Você precisa estar logado!', 'error')
        return redirect(url_for('login'))
    
    Usuario.query.get_or_404(usuario_id)

    imovel_id = request.form.get('imovel_id', type=int)
    if imovel_id and not Imovel.query.get(imovel_id):
        imovel_id = None
    texto = request.form.get('mensagem', '').strip()
    
    if not texto:
        flash('Mensagem não pode estar vazia!', 'error')
        return redirect(url_for('chat', usuario_id=usuario_id))
    
    try:
        msg = Mensagem(
            remetente_id=usuario.id,
            destinatario_id=usuario_id,
            imovel_id=imovel_id,
            titulo=f"Mensagem de {usuario.nome}",
            mensagem=texto
        )
        
        db.session.add(msg)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao enviar mensagem: {str(e)}', 'error')
    
    return redirect(url_for('chat', usuario_id=usuario_id, imovel_id=imovel_id))


@app.route('/api/conversa/<int:usuario_id>', methods=['GET'])
def api_conversa(usuario_id):
    """Retorna mensagens da conversa em JSON e marca mensagens recebidas como lidas."""
    usuario = get_usuario_logado()
    if not usuario:
        return jsonify({'ok': False, 'erro': 'nao_autenticado'}), 401

    Usuario.query.get_or_404(usuario_id)

    imovel_id_param = request.args.get('imovel_id', '').strip().lower()
    imovel_id = None
    if imovel_id_param and imovel_id_param not in {'none', 'null'}:
        try:
            imovel_id = int(imovel_id_param)
        except ValueError:
            return jsonify({'ok': False, 'erro': 'imovel_invalido'}), 400

    mensagens_query = Mensagem.query.filter(
        ((Mensagem.remetente_id == usuario.id) & (Mensagem.destinatario_id == usuario_id)) |
        ((Mensagem.remetente_id == usuario_id) & (Mensagem.destinatario_id == usuario.id))
    )

    if imovel_id is None:
        mensagens_query = mensagens_query.filter(Mensagem.imovel_id.is_(None))
    else:
        mensagens_query = mensagens_query.filter(Mensagem.imovel_id == imovel_id)

    mensagens = mensagens_query.order_by(Mensagem.criado_em.asc()).all()

    alterou_leitura = False
    for msg in mensagens:
        if msg.destinatario_id == usuario.id and not msg.lida:
            msg.lida = True
            alterou_leitura = True

    if alterou_leitura:
        db.session.commit()

    payload = []
    for msg in mensagens:
        payload.append({
            'id': msg.id,
            'mensagem': msg.mensagem,
            'enviada_por_mim': msg.remetente_id == usuario.id,
            'lida': bool(msg.lida),
            'hora': msg.criado_em.strftime('%H:%M'),
            'data': msg.criado_em.strftime('%d/%m/%Y %H:%M'),
        })

    return jsonify({'ok': True, 'mensagens': payload})


@app.route('/api/enviar-mensagem/<int:usuario_id>', methods=['POST'])
def api_enviar_mensagem(usuario_id):
    """Envia mensagem em JSON para o mini chat."""
    usuario = get_usuario_logado()
    if not usuario:
        return jsonify({'ok': False, 'erro': 'nao_autenticado'}), 401

    if usuario.id == usuario_id:
        return jsonify({'ok': False, 'erro': 'destinatario_invalido'}), 400

    Usuario.query.get_or_404(usuario_id)

    texto = ''
    imovel_id = None
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        texto = (payload.get('mensagem') or '').strip()
        imovel_id = payload.get('imovel_id')
    else:
        texto = request.form.get('mensagem', '').strip()
        imovel_id = request.form.get('imovel_id')

    if imovel_id in {'', None, 'none', 'null'}:
        imovel_id = None
    elif isinstance(imovel_id, str):
        try:
            imovel_id = int(imovel_id)
        except ValueError:
            return jsonify({'ok': False, 'erro': 'imovel_invalido'}), 400

    if imovel_id and not Imovel.query.get(imovel_id):
        return jsonify({'ok': False, 'erro': 'imovel_invalido'}), 400

    if not texto:
        return jsonify({'ok': False, 'erro': 'mensagem_vazia'}), 400

    try:
        msg = Mensagem(
            remetente_id=usuario.id,
            destinatario_id=usuario_id,
            imovel_id=imovel_id,
            titulo=f"Mensagem de {usuario.nome}",
            mensagem=texto,
        )
        db.session.add(msg)
        db.session.commit()
        return jsonify({'ok': True, 'id': msg.id})
    except Exception as e:
        db.session.rollback()
        app.logger.warning('Erro ao enviar mensagem via API: %s', str(e), exc_info=True)
        return jsonify({'ok': False, 'erro': 'falha_envio'}), 500

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

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)