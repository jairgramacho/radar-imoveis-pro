from flask_mail import Mail, Message, current_app

mail = Mail()


def _app_url(path=''):
    base = (current_app.config.get('APP_URL') or 'http://localhost:5000').rstrip('/')
    if path and not path.startswith('/'):
        path = f'/{path}'
    return f"{base}{path}"

def enviar_email_notificacao(usuario_email, titulo, corpo, tipo='info'):
    """
    Envia email de notificação para o usuário
    
    Tipos: 'nova_mensagem', 'novo_interessado', 'avaliacao_recebida'
    """
    try:
        msg = Message(
            subject=titulo,
            recipients=[usuario_email],
            body=corpo,
            html=corpo
        )
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Erro ao enviar email: {str(e)}")
        return False

def enviar_email_nova_mensagem(usuario_email, remetente_nome, imovel_tipo=''):
    """Notifica sobre nova mensagem recebida"""
    titulo = f"Nova mensagem de {remetente_nome}"
    
    corpo = f"""
    <html>
        <body style="font-family: Arial, sans-serif; background-color: #f5f5f5; padding: 20px;">
            <div style="background-color: white; padding: 30px; border-radius: 8px; max-width: 600px; margin: 0 auto;">
                <h2 style="color: #f39233;">Nova Mensagem Recebida!</h2>
                
                <p>Olá,</p>
                
                <p>Você recebeu uma nova mensagem de <strong>{remetente_nome}</strong>.</p>
                
                {f'<p>Assunto: <strong>{imovel_tipo}</strong></p>' if imovel_tipo else ''}
                
                <p>
                    <a href="{_app_url('/chat')}" style="display: inline-block; background-color: #f39233; color: white; padding: 12px 24px; border-radius: 5px; text-decoration: none; font-weight: bold;">
                        Ver Mensagem
                    </a>
                </p>
                
                <p>Att,<br>Radar Imóveis</p>
            </div>
        </body>
    </html>
    """
    
    return enviar_email_notificacao(usuario_email, titulo, corpo)

def enviar_email_avaliacao(usuario_email, avaliador_nome, estrelas):
    """Notifica sobre nova avaliação"""
    titulo = f"{avaliador_nome} deixou uma avaliação ⭐"
    
    corpo = f"""
    <html>
        <body style="font-family: Arial, sans-serif; background-color: #f5f5f5; padding: 20px;">
            <div style="background-color: white; padding: 30px; border-radius: 8px; max-width: 600px; margin: 0 auto;">
                <h2 style="color: #f39233;">Você Recebeu Uma Avaliação!</h2>
                
                <p>Olá,</p>
                
                <p><strong>{avaliador_nome}</strong> deixou uma avaliação:</p>
                
                <div style="background-color: #f9f9f9; padding: 20px; border-radius: 5px; margin: 20px 0;">
                    <p style="font-size: 24px; color: #ffc107;">
                        {'⭐' * estrelas}
                    </p>
                </div>
                
                <p>
                    <a href="{_app_url('/meus-anuncios')}" style="display: inline-block; background-color: #f39233; color: white; padding: 12px 24px; border-radius: 5px; text-decoration: none; font-weight: bold;">
                        Ver Avaliação
                    </a>
                </p>
                
                <p>Att,<br>Radar Imóveis</p>
            </div>
        </body>
    </html>
    """
    
    return enviar_email_notificacao(usuario_email, titulo, corpo)

def enviar_email_confirmacao_cadastro(usuario_email, usuario_nome, link_confirmacao=None):
    """Envia email de boas-vindas com confirmação de endereço de email."""
    titulo = "Confirme seu email no Radar Imóveis"

    bloco_confirmacao = ""
    if link_confirmacao:
        bloco_confirmacao = f"""
            <p>Antes de começar, confirme seu endereço de email:</p>

            <p>
                <a href=\"{link_confirmacao}\" style=\"display: inline-block; background-color: #1f3a7d; color: white; padding: 12px 24px; border-radius: 5px; text-decoration: none; font-weight: bold;\">
                    Confirmar email
                </a>
            </p>
        """
    
    corpo = f"""
    <html>
        <body style="font-family: Arial, sans-serif; background-color: #f5f5f5; padding: 20px;">
            <div style="background-color: white; padding: 30px; border-radius: 8px; max-width: 600px; margin: 0 auto;">
                <h2 style="color: #f39233;">Bem-vindo ao Radar Imóveis! 🎉</h2>
                
                <p>Olá <strong>{usuario_nome}</strong>,</p>
                
                <p>Sua conta foi criada com sucesso! Agora você pode:</p>

                {bloco_confirmacao}
                
                <ul style="line-height: 1.8;">
                    <li>✓ Publicar seus anúncios de imóveis</li>
                    <li>✓ Gerenciar seus anúncios</li>
                    <li>✓ Receber mensagens de interessados</li>
                    <li>✓ Ver avaliações dos compradores</li>
                </ul>
                
                <p>
                    <a href="{_app_url('/?aba=anunciar')}" style="display: inline-block; background-color: #f39233; color: white; padding: 12px 24px; border-radius: 5px; text-decoration: none; font-weight: bold;">
                        Publicar Primeiro Anúncio
                    </a>
                </p>
                
                <p>Att,<br>Radar Imóveis</p>
            </div>
        </body>
    </html>
    """
    
    return enviar_email_notificacao(usuario_email, titulo, corpo)


def enviar_email_redefinicao_senha(usuario_email, usuario_nome, link_redefinicao):
    """Envia link seguro para redefinição de senha."""
    titulo = "Redefinição de senha - Radar Imóveis"

    corpo = f"""
    <html>
        <body style="font-family: Arial, sans-serif; background-color: #f5f5f5; padding: 20px;">
            <div style="background-color: white; padding: 30px; border-radius: 8px; max-width: 600px; margin: 0 auto;">
                <h2 style="color: #f39233;">Solicitação de redefinição de senha</h2>

                <p>Olá <strong>{usuario_nome}</strong>,</p>

                <p>Recebemos uma solicitação para redefinir sua senha. Clique no botão abaixo:</p>

                <p>
                    <a href="{link_redefinicao}" style="display: inline-block; background-color: #f39233; color: white; padding: 12px 24px; border-radius: 5px; text-decoration: none; font-weight: bold;">
                        Redefinir minha senha
                    </a>
                </p>

                <p style="color: #6c757d;">Este link expira em 1 hora.</p>
                <p style="color: #6c757d;">Se você não solicitou, ignore este email.</p>

                <p>Att,<br>Radar Imóveis</p>
            </div>
        </body>
    </html>
    """

    return enviar_email_notificacao(usuario_email, titulo, corpo)
