"""Blueprint de autenticacao e conta."""

from datetime import datetime
import secrets
import string

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from pydantic import ValidationError
import pyotp

from models import Avaliacao, AuditLog, ConsentimentoUsuario, Imovel, Mensagem, Notificacao, TokenDoisFatores, Usuario, db
from radar_app.auth import UsuarioRepository
from radar_app.security.sanitization import sanitizar_nome, sanitizar_email
from radar_app.security.validation_schemas import UsuarioCadastroSchema, UsuarioLoginSchema, ConfiguracaoContaSchema


auth_bp = Blueprint('auth', __name__)


def _repo():
    return UsuarioRepository(
        db, Usuario,
        imovel_model=Imovel,
        avaliacao_model=Avaliacao,
        mensagem_model=Mensagem,
        notificacao_model=Notificacao,
    )


def _legacy():
    # Import local para evitar ciclo de import em tempo de modulo.
    from radar_app import legacy_app

    return legacy_app


def _registrar_consentimento(usuario_id, tipo, aceito, versao='1.0'):
    """✅ Registra consentimento LGPD do usuário (discreto)."""
    try:
        consentimento = ConsentimentoUsuario(
            usuario_id=usuario_id,
            tipo=tipo,
            aceito=aceito,
            data_consentimento=datetime.utcnow(),
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent', '')[:500],
            versao_documento=versao,
        )
        db.session.add(consentimento)
        db.session.flush()
    except Exception as e:
        current_app.logger.warning(f"Erro ao registrar consentimento: {e}")


def _registrar_audit_log(usuario_id, acao, entidade, entidade_id=None, detalhes=None):
    """✅ Registra auditoria (LGPD compliance)."""
    try:
        audit = AuditLog(
            usuario_id=usuario_id,
            acao=acao,
            entidade=entidade,
            entidade_id=entidade_id,
            detalhes=detalhes,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent', '')[:500],
        )
        db.session.add(audit)
        db.session.flush()
    except Exception as e:
        current_app.logger.warning(f"Erro ao registrar audit log: {e}")


def _gerar_backup_codes(quantidade=8, tamanho=10):
    alfabeto = string.ascii_uppercase + string.digits
    return [''.join(secrets.choice(alfabeto) for _ in range(tamanho)) for _ in range(quantidade)]


def _normalizar_codigo_2fa(codigo):
    return ''.join((codigo or '').strip().split()).upper()


def _codigo_totp_valido(secret, codigo):
    if not secret:
        return False
    totp = pyotp.TOTP(secret)
    return bool(totp.verify(codigo, valid_window=1))


@auth_bp.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    """Pagina de cadastro de novo usuario."""
    legacy = _legacy()

    if request.method == 'POST':
        try:
            nome = request.form.get('nome', '').strip()
            email = request.form.get('email', '').strip()
            senha = request.form.get('senha', '')
            whatsapp = request.form.get('whatsapp', '').strip()
            consent_terms = request.form.get('consent_terms') == 'on'

            # ✅ VALIDAÇÃO COM PYDANTIC (input validation + força de senha)
            try:
                form_data = UsuarioCadastroSchema(
                    nome=nome,
                    email=email,
                    senha=senha,
                    whatsapp=whatsapp,
                    consent_terms=consent_terms,
                )
            except ValidationError as e:
                erros = ', '.join([f"{err['loc'][0]}: {err['msg']}" for err in e.errors()])
                flash(f'Validação falhou: {erros}', 'error')
                return redirect(url_for('cadastro'))

            # ✅ SANITIZAR ENTRADA (XSS Protection)
            nome_sanitizado = sanitizar_nome(form_data.nome)
            email_sanitizado = sanitizar_email(form_data.email)

            whatsapp_validado = legacy._validar_whatsapp(form_data.whatsapp)
            if not whatsapp_validado:
                flash('WhatsApp inválido. Informe DDD + número (10 ou 11 dígitos).', 'error')
                return redirect(url_for('cadastro'))

            if _repo().buscar_por_email(email_sanitizado):
                flash('Este e-mail já está cadastrado!', 'error')
                return redirect(url_for('cadastro'))

            if _repo().buscar_por_whatsapp(whatsapp_validado):
                flash('Este WhatsApp já está cadastrado! Use outro número.', 'error')
                return redirect(url_for('cadastro'))

            exigir_confirmacao = legacy._confirmacao_email_obrigatoria()
            novo_usuario = Usuario(
                nome=nome_sanitizado,
                email=email_sanitizado,
                whatsapp=whatsapp_validado,
                email_confirmado=not exigir_confirmacao,
                confirmado_em=(datetime.utcnow() if not exigir_confirmacao else None),
            )
            novo_usuario.set_password(form_data.senha)
            _repo().salvar(novo_usuario)

            # ✅ REGISTRAR CONSENTIMENTO LGPD
            _registrar_consentimento(novo_usuario.id, 'termos_privacidade', True, versao='1.0')

            # ✅ REGISTRAR AUDIT LOG
            _registrar_audit_log(novo_usuario.id, 'cadastro', 'usuario', novo_usuario.id)

            if exigir_confirmacao:
                token_confirmacao = legacy._gerar_token_email(novo_usuario.email, 'confirmar-email')
                link_confirmacao = legacy._url_publica('confirmar_email', token=token_confirmacao)
                enviado, erro_envio = legacy._enviar_email_com_status(
                    legacy.enviar_email_confirmacao_cadastro,
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
            _repo().rollback()
            current_app.logger.error(f"Erro ao cadastrar: {e}", exc_info=True)
            flash(f'Erro ao cadastrar: {str(e)}', 'error')

    return render_template('cadastro.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Pagina de login."""
    legacy = _legacy()

    if request.method == 'POST':
        try:
            email = request.form.get('email', '').strip()
            senha = request.form.get('senha', '')

            # ✅ VALIDAÇÃO COM PYDANTIC
            try:
                form_data = UsuarioLoginSchema(email=email, senha=senha)
            except ValidationError as e:
                erros = ', '.join([f"{err['loc'][0]}: {err['msg']}" for err in e.errors()])
                flash(f'Validação falhou: {erros}', 'error')
                return redirect(url_for('login'))

            # ✅ SANITIZAR EMAIL
            email_sanitizado = sanitizar_email(form_data.email)

            usuario = _repo().buscar_por_email(email_sanitizado)

            if usuario and usuario.check_password(form_data.senha):
                if not getattr(usuario, 'email_confirmado', True) and not legacy._confirmacao_email_obrigatoria():
                    usuario.email_confirmado = True
                    if not getattr(usuario, 'confirmado_em', None):
                        usuario.confirmado_em = datetime.utcnow()
                    _repo().commit()

                if not getattr(usuario, 'email_confirmado', True):
                    token_confirmacao = legacy._gerar_token_email(usuario.email, 'confirmar-email')
                    link_confirmacao = legacy._url_publica('confirmar_email', token=token_confirmacao)
                    enviado, erro_envio = legacy._enviar_email_com_status(
                        legacy.enviar_email_confirmacao_cadastro,
                        usuario.email,
                        usuario.nome,
                        link_confirmacao,
                    )
                    if enviado:
                        flash('Confirme seu email antes de entrar. Um novo link foi enviado.', 'error')
                    else:
                        flash(
                            'Confirme seu email antes de entrar. '
                            f'Nao foi possivel reenviar o link agora: {erro_envio}',
                            'error'
                        )
                    return redirect(url_for('login'))

                token_2fa = TokenDoisFatores.query.filter_by(usuario_id=usuario.id, habilitado=True).first()
                if token_2fa:
                    session['2fa_pending_user_id'] = usuario.id
                    session['2fa_pending_nome'] = usuario.nome
                    flash('Digite o código do autenticador para concluir o login.', 'success')
                    return redirect(url_for('auth.verificar_2fa'))

                session['usuario_id'] = usuario.id
                session['usuario_nome'] = usuario.nome
                
                # ✅ REGISTRAR AUDIT LOG (login bem-sucedido)
                _registrar_audit_log(usuario.id, 'login', 'usuario', usuario.id)
                
                flash(f'Bem-vindo, {usuario.nome}!', 'success')
                return redirect(url_for('index', aba='buscar'))

            # ✅ REGISTRAR TENTATIVA DE LOGIN FALHADA
            if usuario:
                _registrar_audit_log(None, 'login_falho', 'usuario', detalhes={'email': email})
            
            flash('E-mail ou senha incorretos!', 'error')

        except Exception as e:
            flash(f'Erro ao fazer login: {str(e)}', 'error')

    return render_template('login.html')


@auth_bp.route('/logout')
def logout():
    """Logout do usuario."""
    usuario_id = session.get('usuario_id')
    
    # ✅ REGISTRAR AUDIT LOG (logout)
    if usuario_id:
        _registrar_audit_log(usuario_id, 'logout', 'usuario', usuario_id)
    
    session.clear()
    flash('Você foi desconectado!', 'success')
    return redirect(url_for('index', aba='buscar'))


@auth_bp.route('/verificar-2fa', methods=['GET', 'POST'])
def verificar_2fa():
    """Valida o segundo fator (TOTP ou código de backup) durante login."""
    pending_user_id = session.get('2fa_pending_user_id')
    pending_nome = session.get('2fa_pending_nome', '')

    if not pending_user_id:
        flash('Sessão de verificação expirada. Faça login novamente.', 'error')
        return redirect(url_for('login'))

    usuario = _repo().buscar_por_id(pending_user_id)
    if not usuario:
        session.pop('2fa_pending_user_id', None)
        session.pop('2fa_pending_nome', None)
        flash('Usuário não encontrado para validação 2FA.', 'error')
        return redirect(url_for('login'))

    token_2fa = TokenDoisFatores.query.filter_by(usuario_id=usuario.id, habilitado=True).first()
    if not token_2fa:
        session.pop('2fa_pending_user_id', None)
        session.pop('2fa_pending_nome', None)
        flash('2FA não está habilitado para esta conta.', 'error')
        return redirect(url_for('login'))

    if request.method == 'POST':
        codigo = _normalizar_codigo_2fa(request.form.get('codigo_2fa', ''))
        if not codigo:
            flash('Informe o código do autenticador.', 'error')
            return redirect(url_for('auth.verificar_2fa'))

        valido = _codigo_totp_valido(token_2fa.secret, codigo)
        if not valido:
            backups = list(token_2fa.backup_codes or [])
            if codigo in backups:
                backups.remove(codigo)
                token_2fa.backup_codes = backups
                valido = True

        if not valido:
            flash('Código 2FA inválido.', 'error')
            return redirect(url_for('auth.verificar_2fa'))

        session['usuario_id'] = usuario.id
        session['usuario_nome'] = usuario.nome
        session.pop('2fa_pending_user_id', None)
        session.pop('2fa_pending_nome', None)

        _repo().commit()
        _registrar_audit_log(usuario.id, 'login_2fa_sucesso', 'usuario', usuario.id)

        flash(f'Bem-vindo, {usuario.nome}!', 'success')
        return redirect(url_for('index', aba='buscar'))

    return render_template('verificar_2fa.html', pending_nome=pending_nome)


@auth_bp.route('/confirmar-email/<token>')
def confirmar_email(token):
    """Confirma o email da conta usando token assinado."""
    legacy = _legacy()

    email, erro = legacy._validar_token_email(token, 'confirmar-email', max_age=60 * 60 * 24)
    if erro:
        flash('Link de confirmacao invalido ou expirado.', 'error')
        return redirect(url_for('login'))

    usuario = _repo().buscar_por_email(email)
    if not usuario:
        flash('Conta nao encontrada para este link.', 'error')
        return redirect(url_for('login'))

    if not usuario.email_confirmado:
        usuario.email_confirmado = True
        usuario.confirmado_em = datetime.utcnow()
        _repo().commit()

    flash('Email confirmado com sucesso! Agora voce ja pode entrar.', 'success')
    return redirect(url_for('login'))


@auth_bp.route('/reenviar-confirmacao', methods=['POST'])
def reenviar_confirmacao():
    """Reenvia email de confirmacao da conta."""
    legacy = _legacy()

    email = request.form.get('email', '').strip()
    usuario = _repo().buscar_por_email(email) if email else None

    if usuario and not getattr(usuario, 'email_confirmado', True):
        token_confirmacao = legacy._gerar_token_email(usuario.email, 'confirmar-email')
        link_confirmacao = legacy._url_publica('confirmar_email', token=token_confirmacao)
        enviado, erro_envio = legacy._enviar_email_com_status(
            legacy.enviar_email_confirmacao_cadastro,
            usuario.email,
            usuario.nome,
            link_confirmacao,
        )
        if not enviado:
            flash(f'Nao foi possivel reenviar o email agora: {erro_envio}', 'error')
            return redirect(url_for('login'))

    flash('Se o email informado existir e estiver pendente, um novo link foi enviado.', 'success')
    return redirect(url_for('login'))


@auth_bp.route('/esqueci-senha', methods=['GET', 'POST'])
def esqueci_senha():
    """Solicita redefinicao de senha por email."""
    legacy = _legacy()

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        usuario = _repo().buscar_por_email(email) if email else None

        if usuario:
            token_reset = legacy._gerar_token_email(usuario.email, 'reset-senha')
            link_reset = legacy._url_publica('redefinir_senha', token=token_reset)
            if legacy.flask_env != 'production' and legacy._permitir_fallback_reset_local() and not legacy._smtp_configurado():
                flash('Email nao configurado neste ambiente. Voce sera redirecionado para redefinir a senha agora.', 'success')
                return redirect(url_for('redefinir_senha', token=token_reset))

            if legacy._reset_email_assincrono_habilitado():
                disparado = legacy._disparar_email_assincrono(
                    legacy.enviar_email_redefinicao_senha,
                    usuario.email,
                    usuario.nome,
                    link_reset,
                )
                if not disparado:
                    current_app.logger.warning('Falha ao iniciar envio assincrono de reset para %s', usuario.email)
            else:
                enviado, erro_envio = legacy._enviar_email_com_status(
                    legacy.enviar_email_redefinicao_senha,
                    usuario.email,
                    usuario.nome,
                    link_reset,
                )
                if not enviado:
                    current_app.logger.warning(
                        'Falha ao enviar email de redefinicao para %s: %s',
                        usuario.email,
                        erro_envio,
                    )

        flash('Se o email informado existir, voce recebera instrucoes para redefinir a senha.', 'success')
        return redirect(url_for('login'))

    return render_template('esqueci_senha.html')


@auth_bp.route('/redefinir-senha/<token>', methods=['GET', 'POST'])
def redefinir_senha(token):
    """Tela de redefinicao de senha via token."""
    legacy = _legacy()

    email, erro = legacy._validar_token_email(token, 'reset-senha', max_age=60 * 60)
    if erro:
        flash('Link de redefinicao invalido ou expirado.', 'error')
        return redirect(url_for('esqueci_senha'))

    usuario = _repo().buscar_por_email(email)
    if not usuario:
        flash('Conta nao encontrada.', 'error')
        return redirect(url_for('esqueci_senha'))

    if request.method == 'POST':
        senha = request.form.get('senha', '')
        confirmar_senha = request.form.get('confirmar_senha', '')

        if len(senha) < 12:
            flash('A nova senha deve ter no mínimo 12 caracteres.', 'error')
            return redirect(url_for('redefinir_senha', token=token))

        if senha != confirmar_senha:
            flash('A confirmacao da senha nao confere.', 'error')
            return redirect(url_for('redefinir_senha', token=token))

        usuario.set_password(senha)
        _repo().commit()

        flash('Senha redefinida com sucesso! Faca login com a nova senha.', 'success')
        return redirect(url_for('login'))

    return render_template('redefinir_senha.html', token=token)


@auth_bp.route('/configuracoes-conta', methods=['GET', 'POST'])
def configuracoes_conta():
    """Permite ao usuario editar dados de conta e senha."""
    legacy = _legacy()
    usuario = legacy.get_usuario_logado()

    if not usuario:
        flash('Voce precisa estar logado!', 'error')
        return redirect(url_for('login'))

    if request.method == 'POST':
        try:
            nome = request.form.get('nome', '').strip()
            email = request.form.get('email', '').strip()
            whatsapp = request.form.get('whatsapp', '').strip()

            senha_atual = request.form.get('senha_atual', '')
            nova_senha = request.form.get('nova_senha', '')
            confirmar_senha = request.form.get('confirmar_senha', '')

            try:
                form_data = ConfiguracaoContaSchema(
                    nome=nome,
                    whatsapp=whatsapp,
                    nova_senha=nova_senha,
                )
            except ValidationError as e:
                erros = ', '.join([f"{err['loc'][0]}: {err['msg']}" for err in e.errors()])
                flash(f'Validação falhou: {erros}', 'error')
                return redirect(url_for('configuracoes_conta'))

            nome_sanitizado = sanitizar_nome(form_data.nome)
            try:
                email_schema = UsuarioLoginSchema(email=email, senha='x')
            except ValidationError:
                flash('E-mail inválido.', 'error')
                return redirect(url_for('configuracoes_conta'))

            email_sanitizado = sanitizar_email(email_schema.email)

            whatsapp_validado = legacy._validar_whatsapp(form_data.whatsapp)
            if not whatsapp_validado:
                flash('WhatsApp invalido. Informe DDD + numero (10 ou 11 digitos).', 'error')
                return redirect(url_for('configuracoes_conta'))

            if _repo().email_em_uso_por_outro(email_sanitizado, usuario.id):
                flash('Este e-mail ja esta em uso por outra conta.', 'error')
                return redirect(url_for('configuracoes_conta'))

            if senha_atual or nova_senha or confirmar_senha:
                if not usuario.check_password(senha_atual):
                    flash('Senha atual incorreta.', 'error')
                    return redirect(url_for('configuracoes_conta'))

                if len(nova_senha) < 12:
                    flash('A nova senha deve ter no mínimo 12 caracteres.', 'error')
                    return redirect(url_for('configuracoes_conta'))

                if nova_senha != confirmar_senha:
                    flash('A confirmacao da nova senha nao confere.', 'error')
                    return redirect(url_for('configuracoes_conta'))

                usuario.set_password(nova_senha)

            usuario.nome = nome_sanitizado
            usuario.email = email_sanitizado
            usuario.whatsapp = whatsapp_validado

            _repo().commit()

            session['usuario_nome'] = usuario.nome
            flash('Configuracoes atualizadas com sucesso!', 'success')
            return redirect(url_for('configuracoes_conta'))

        except Exception as e:
            _repo().rollback()
            flash(f'Erro ao atualizar configuracoes: {str(e)}', 'error')
            return redirect(url_for('configuracoes_conta'))

    token_2fa = TokenDoisFatores.query.filter_by(usuario_id=usuario.id).first()
    chave_2fa = None
    uri_2fa = None

    if token_2fa and not token_2fa.habilitado:
        chave_2fa = token_2fa.secret
        uri_2fa = pyotp.TOTP(token_2fa.secret).provisioning_uri(
            name=usuario.email,
            issuer_name='Radar Imoveis Pro'
        )

    return render_template(
        'configuracoes_conta.html',
        usuario=usuario,
        token_2fa=token_2fa,
        chave_2fa=chave_2fa,
        uri_2fa=uri_2fa,
    )


@auth_bp.route('/2fa/preparar', methods=['POST'])
def preparar_2fa():
    """Gera ou regenera chave secreta para ativação de 2FA."""
    legacy = _legacy()
    usuario = legacy.get_usuario_logado()

    if not usuario:
        flash('Voce precisa estar logado!', 'error')
        return redirect(url_for('login'))

    senha_confirmacao = request.form.get('senha_2fa', '')
    if not usuario.check_password(senha_confirmacao):
        flash('Senha incorreta para configurar 2FA.', 'error')
        return redirect(url_for('configuracoes_conta'))

    token_2fa = TokenDoisFatores.query.filter_by(usuario_id=usuario.id).first()
    if not token_2fa:
        token_2fa = TokenDoisFatores(usuario_id=usuario.id, secret='')
        db.session.add(token_2fa)

    token_2fa.secret = pyotp.random_base32()
    token_2fa.habilitado = False
    token_2fa.backup_codes = _gerar_backup_codes()

    _repo().commit()
    _registrar_audit_log(usuario.id, '2fa_preparado', 'usuario', usuario.id)

    flash('Chave 2FA gerada. Escaneie no app autenticador e confirme o código.', 'success')
    return redirect(url_for('configuracoes_conta'))


@auth_bp.route('/2fa/ativar', methods=['POST'])
def ativar_2fa():
    """Ativa 2FA após validar código TOTP."""
    legacy = _legacy()
    usuario = legacy.get_usuario_logado()

    if not usuario:
        flash('Voce precisa estar logado!', 'error')
        return redirect(url_for('login'))

    token_2fa = TokenDoisFatores.query.filter_by(usuario_id=usuario.id).first()
    if not token_2fa or not token_2fa.secret:
        flash('Prepare a chave 2FA antes de ativar.', 'error')
        return redirect(url_for('configuracoes_conta'))

    codigo = _normalizar_codigo_2fa(request.form.get('codigo_2fa', ''))
    if not _codigo_totp_valido(token_2fa.secret, codigo):
        flash('Código inválido. Tente novamente.', 'error')
        return redirect(url_for('configuracoes_conta'))

    token_2fa.habilitado = True
    _repo().commit()
    _registrar_audit_log(usuario.id, '2fa_ativado', 'usuario', usuario.id)

    flash('2FA ativado com sucesso.', 'success')
    return redirect(url_for('configuracoes_conta'))


@auth_bp.route('/2fa/desativar', methods=['POST'])
def desativar_2fa():
    """Desativa 2FA mediante senha e código TOTP/backup."""
    legacy = _legacy()
    usuario = legacy.get_usuario_logado()

    if not usuario:
        flash('Voce precisa estar logado!', 'error')
        return redirect(url_for('login'))

    token_2fa = TokenDoisFatores.query.filter_by(usuario_id=usuario.id, habilitado=True).first()
    if not token_2fa:
        flash('2FA não está ativo nesta conta.', 'error')
        return redirect(url_for('configuracoes_conta'))

    senha_confirmacao = request.form.get('senha_desativar_2fa', '')
    codigo = _normalizar_codigo_2fa(request.form.get('codigo_desativar_2fa', ''))

    if not usuario.check_password(senha_confirmacao):
        flash('Senha incorreta para desativar 2FA.', 'error')
        return redirect(url_for('configuracoes_conta'))

    valido = _codigo_totp_valido(token_2fa.secret, codigo)
    if not valido:
        backups = list(token_2fa.backup_codes or [])
        if codigo in backups:
            backups.remove(codigo)
            token_2fa.backup_codes = backups
            valido = True

    if not valido:
        flash('Código 2FA inválido para desativação.', 'error')
        return redirect(url_for('configuracoes_conta'))

    token_2fa.habilitado = False
    _repo().commit()
    _registrar_audit_log(usuario.id, '2fa_desativado', 'usuario', usuario.id)

    flash('2FA desativado com sucesso.', 'success')
    return redirect(url_for('configuracoes_conta'))


@auth_bp.route('/excluir-conta', methods=['POST'])
def excluir_conta():
    """Exclui a conta do usuario logado e seus dados associados (LGPD)."""
    legacy = _legacy()
    usuario = legacy.get_usuario_logado()

    if not usuario:
        flash('Você precisa estar logado!', 'error')
        return redirect(url_for('login'))

    senha_confirmacao = request.form.get('senha_confirmacao', '')
    confirmacao_texto = (request.form.get('confirmacao_texto') or '').strip().upper()

    if not usuario.check_password(senha_confirmacao):
        flash('Senha incorreta. Não foi possível excluir sua conta.', 'error')
        return redirect(url_for('configuracoes_conta'))

    if confirmacao_texto != 'EXCLUIR':
        flash('Confirmação inválida. Digite EXCLUIR para confirmar.', 'error')
        return redirect(url_for('configuracoes_conta'))

    try:
        # ✅ REGISTRAR AUDIT LOG ANTES DE DELETAR
        _registrar_audit_log(usuario.id, 'exclusao_conta', 'usuario', usuario.id, {
            'email': usuario.email,
            'nome': usuario.nome,
            'data_criacao': usuario.criado_em.isoformat() if usuario.criado_em else None,
        })
        
        _repo().excluir_com_dados(usuario)

        session.clear()
        flash('Sua conta foi excluída com sucesso. Seus dados serão removidos em breve.', 'success')
        return redirect(url_for('index', aba='buscar'))
    except Exception as e:
        _repo().rollback()
        current_app.logger.warning('Erro ao excluir conta do usuario %s: %s', usuario.id, str(e), exc_info=True)
        flash('Não foi possível excluir sua conta agora. Tente novamente em instantes.', 'error')
        return redirect(url_for('configuracoes_conta'))
