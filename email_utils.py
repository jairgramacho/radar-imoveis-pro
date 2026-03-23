import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask_mail import Mail, Message, current_app

mail = Mail()


def _resend_configurado():
    """Retorna True quando a API do Resend está configurada para envio."""
    api_key = (current_app.config.get('RESEND_API_KEY') or '').strip()
    remetente = (current_app.config.get('RESEND_FROM') or current_app.config.get('MAIL_DEFAULT_SENDER') or '').strip().lower()

    placeholders = {
        '',
        'your-resend-api-key',
        'sua-chave-resend',
        'noreply@example.com',
    }
    return api_key.lower() not in placeholders and remetente not in placeholders


def _enviar_via_resend(usuario_email, titulo, corpo):
    """Envia email via API HTTP do Resend (evita bloqueio de SMTP no provedor)."""
    api_key = (current_app.config.get('RESEND_API_KEY') or '').strip()
    from_email = (current_app.config.get('RESEND_FROM') or current_app.config.get('MAIL_DEFAULT_SENDER') or '').strip()
    api_url = (current_app.config.get('RESEND_API_URL') or 'https://api.resend.com/emails').strip()
    timeout = int(current_app.config.get('RESEND_TIMEOUT', current_app.config.get('MAIL_TIMEOUT', 10)))

    # Converte HTML em texto simples para melhorar compatibilidade com alguns clientes.
    texto = re.sub(r'<[^>]+>', ' ', corpo or '')
    texto = re.sub(r'\s+', ' ', texto).strip()

    payload = {
        'from': from_email,
        'to': [usuario_email],
        'subject': titulo,
        'html': corpo,
        'text': texto,
    }

    req = Request(
        api_url,
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'User-Agent': 'radar-imoveis-pro/1.0',
        },
        method='POST',
    )

    try:
        with urlopen(req, timeout=timeout) as response:
            status = getattr(response, 'status', 200)
            if status >= 400:
                current_app.logger.warning('Resend retornou status HTTP %s para %s', status, usuario_email)
                return False

        current_app.logger.info('Email enviado via Resend para %s com assunto %s', usuario_email, titulo)
        return True
    except HTTPError as e:
        detalhe = ''
        try:
            detalhe = e.read().decode('utf-8', errors='ignore')
        except Exception:
            detalhe = str(e)
        current_app.logger.warning('Erro HTTP no Resend para %s: %s | %s', usuario_email, e, detalhe)
        return False
    except URLError as e:
        current_app.logger.warning('Erro de rede no Resend para %s: %s', usuario_email, e)
        return False
    except Exception as e:
        current_app.logger.warning('Erro inesperado no Resend para %s: %s', usuario_email, e, exc_info=True)
        return False


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
        if _resend_configurado():
            return _enviar_via_resend(usuario_email, titulo, corpo)

        msg = Message(
            subject=titulo,
            recipients=[usuario_email],
            body=corpo,
            html=corpo
        )
        mail.send(msg)
        current_app.logger.info('Email enviado para %s com assunto %s', usuario_email, titulo)
        return True
    except Exception as e:
        current_app.logger.warning('Erro ao enviar email para %s: %s', usuario_email, str(e), exc_info=True)
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
