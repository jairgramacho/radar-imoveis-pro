"""Blueprint de autenticacao e conta."""

from datetime import datetime

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for

from models import Avaliacao, Imovel, Mensagem, Notificacao, Usuario, db


auth_bp = Blueprint('auth', __name__)


def _legacy():
    # Import local para evitar ciclo de import em tempo de modulo.
    from radar_app import legacy_app

    return legacy_app


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

            if not all([nome, email, senha, whatsapp]):
                flash('Todos os campos sao obrigatorios!', 'error')
                return redirect(url_for('cadastro'))

            if len(senha) < 6:
                flash('Senha deve ter no minimo 6 caracteres!', 'error')
                return redirect(url_for('cadastro'))

            whatsapp_validado = legacy._validar_whatsapp(whatsapp)
            if not whatsapp_validado:
                flash('WhatsApp invalido. Informe DDD + numero (10 ou 11 digitos).', 'error')
                return redirect(url_for('cadastro'))

            if Usuario.query.filter_by(email=email).first():
                flash('Este e-mail ja esta cadastrado!', 'error')
                return redirect(url_for('cadastro'))

            if Usuario.query.filter_by(whatsapp=whatsapp_validado).first():
                flash('Este WhatsApp ja esta cadastrado! Use outro numero.', 'error')
                return redirect(url_for('cadastro'))

            exigir_confirmacao = legacy._confirmacao_email_obrigatoria()
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
                token_confirmacao = legacy._gerar_token_email(novo_usuario.email, 'confirmar-email')
                link_confirmacao = legacy._url_publica('confirmar_email', token=token_confirmacao)
                enviado, erro_envio = legacy._enviar_email_com_status(
                    legacy.enviar_email_confirmacao_cadastro,
                    novo_usuario.email,
                    novo_usuario.nome,
                    link_confirmacao,
                )

                if enviado:
                    flash('Cadastro realizado! Enviamos um email para confirmacao da sua conta.', 'success')
                else:
                    flash(
                        'Cadastro realizado, mas o email de confirmacao nao foi enviado agora. '
                        f'{erro_envio} Configure RESEND_API_KEY ou MAIL_USERNAME/MAIL_PASSWORD e tente reenviar na tela de login.',
                        'error'
                    )
            else:
                flash(
                    'Cadastro realizado! Como o envio de email nao esta configurado, sua conta foi liberada automaticamente.',
                    'success'
                )
            return redirect(url_for('login'))

        except Exception as e:
            db.session.rollback()
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

            if not email or not senha:
                flash('E-mail e senha sao obrigatorios!', 'error')
                return redirect(url_for('login'))

            usuario = Usuario.query.filter_by(email=email).first()

            if usuario and usuario.check_password(senha):
                if not getattr(usuario, 'email_confirmado', True) and not legacy._confirmacao_email_obrigatoria():
                    usuario.email_confirmado = True
                    if not getattr(usuario, 'confirmado_em', None):
                        usuario.confirmado_em = datetime.utcnow()
                    db.session.commit()

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

                session['usuario_id'] = usuario.id
                session['usuario_nome'] = usuario.nome
                flash(f'Bem-vindo, {usuario.nome}!', 'success')
                return redirect(url_for('index', aba='buscar'))

            flash('E-mail ou senha incorretos!', 'error')

        except Exception as e:
            flash(f'Erro ao fazer login: {str(e)}', 'error')

    return render_template('login.html')


@auth_bp.route('/logout')
def logout():
    """Logout do usuario."""
    session.clear()
    flash('Voce foi desconectado!', 'success')
    return redirect(url_for('index', aba='buscar'))


@auth_bp.route('/confirmar-email/<token>')
def confirmar_email(token):
    """Confirma o email da conta usando token assinado."""
    legacy = _legacy()

    email, erro = legacy._validar_token_email(token, 'confirmar-email', max_age=60 * 60 * 24)
    if erro:
        flash('Link de confirmacao invalido ou expirado.', 'error')
        return redirect(url_for('login'))

    usuario = Usuario.query.filter_by(email=email).first()
    if not usuario:
        flash('Conta nao encontrada para este link.', 'error')
        return redirect(url_for('login'))

    if not usuario.email_confirmado:
        usuario.email_confirmado = True
        usuario.confirmado_em = datetime.utcnow()
        db.session.commit()

    flash('Email confirmado com sucesso! Agora voce ja pode entrar.', 'success')
    return redirect(url_for('login'))


@auth_bp.route('/reenviar-confirmacao', methods=['POST'])
def reenviar_confirmacao():
    """Reenvia email de confirmacao da conta."""
    legacy = _legacy()

    email = request.form.get('email', '').strip()
    usuario = Usuario.query.filter_by(email=email).first() if email else None

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
        usuario = Usuario.query.filter_by(email=email).first() if email else None

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

    usuario = Usuario.query.filter_by(email=email).first()
    if not usuario:
        flash('Conta nao encontrada.', 'error')
        return redirect(url_for('esqueci_senha'))

    if request.method == 'POST':
        senha = request.form.get('senha', '')
        confirmar_senha = request.form.get('confirmar_senha', '')

        if len(senha) < 6:
            flash('A nova senha deve ter no minimo 6 caracteres.', 'error')
            return redirect(url_for('redefinir_senha', token=token))

        if senha != confirmar_senha:
            flash('A confirmacao da senha nao confere.', 'error')
            return redirect(url_for('redefinir_senha', token=token))

        usuario.set_password(senha)
        db.session.commit()

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

            if not all([nome, email, whatsapp]):
                flash('Nome, e-mail e WhatsApp sao obrigatorios.', 'error')
                return redirect(url_for('configuracoes_conta'))

            whatsapp_validado = legacy._validar_whatsapp(whatsapp)
            if not whatsapp_validado:
                flash('WhatsApp invalido. Informe DDD + numero (10 ou 11 digitos).', 'error')
                return redirect(url_for('configuracoes_conta'))

            email_em_uso = Usuario.query.filter(
                Usuario.email == email,
                Usuario.id != usuario.id
            ).first()

            if email_em_uso:
                flash('Este e-mail ja esta em uso por outra conta.', 'error')
                return redirect(url_for('configuracoes_conta'))

            if senha_atual or nova_senha or confirmar_senha:
                if not usuario.check_password(senha_atual):
                    flash('Senha atual incorreta.', 'error')
                    return redirect(url_for('configuracoes_conta'))

                if len(nova_senha) < 6:
                    flash('A nova senha deve ter no minimo 6 caracteres.', 'error')
                    return redirect(url_for('configuracoes_conta'))

                if nova_senha != confirmar_senha:
                    flash('A confirmacao da nova senha nao confere.', 'error')
                    return redirect(url_for('configuracoes_conta'))

                usuario.set_password(nova_senha)

            usuario.nome = nome
            usuario.email = email
            usuario.whatsapp = whatsapp_validado

            db.session.commit()

            session['usuario_nome'] = usuario.nome
            flash('Configuracoes atualizadas com sucesso!', 'success')
            return redirect(url_for('configuracoes_conta'))

        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao atualizar configuracoes: {str(e)}', 'error')
            return redirect(url_for('configuracoes_conta'))

    return render_template('configuracoes_conta.html', usuario=usuario)


@auth_bp.route('/excluir-conta', methods=['POST'])
def excluir_conta():
    """Exclui a conta do usuario logado e seus dados associados."""
    legacy = _legacy()
    usuario = legacy.get_usuario_logado()

    if not usuario:
        flash('Voce precisa estar logado!', 'error')
        return redirect(url_for('login'))

    senha_confirmacao = request.form.get('senha_confirmacao', '')
    confirmacao_texto = (request.form.get('confirmacao_texto') or '').strip().upper()

    if not usuario.check_password(senha_confirmacao):
        flash('Senha incorreta. Nao foi possivel excluir sua conta.', 'error')
        return redirect(url_for('configuracoes_conta'))

    if confirmacao_texto != 'EXCLUIR':
        flash('Confirmacao invalida. Digite EXCLUIR para confirmar.', 'error')
        return redirect(url_for('configuracoes_conta'))

    try:
        usuario_id = usuario.id

        Mensagem.query.filter(
            (Mensagem.remetente_id == usuario_id) | (Mensagem.destinatario_id == usuario_id)
        ).delete(synchronize_session=False)

        Avaliacao.query.filter(
            (Avaliacao.usuario_id == usuario_id) | (Avaliacao.avaliador_id == usuario_id)
        ).delete(synchronize_session=False)

        Notificacao.query.filter_by(usuario_id=usuario_id).delete(synchronize_session=False)

        imoveis_usuario = Imovel.query.filter_by(usuario_id=usuario_id).all()
        for imovel in imoveis_usuario:
            db.session.delete(imovel)

        db.session.delete(usuario)
        db.session.commit()

        session.clear()
        flash('Sua conta foi excluida com sucesso.', 'success')
        return redirect(url_for('index', aba='buscar'))
    except Exception as e:
        db.session.rollback()
        current_app.logger.warning('Erro ao excluir conta do usuario %s: %s', usuario.id, str(e), exc_info=True)
        flash('Nao foi possivel excluir sua conta agora. Tente novamente em instantes.', 'error')
        return redirect(url_for('configuracoes_conta'))
