import os
from threading import Thread


def smtp_configurado(app_config):
    """Verifica se há provedor de email configurado (Resend API ou SMTP)."""
    resend_api_key = (app_config.get('RESEND_API_KEY') or '').strip().lower()
    resend_placeholders = {
        '',
        'your-resend-api-key',
        'sua-chave-resend',
    }
    if resend_api_key not in resend_placeholders:
        return True

    username = (app_config.get('MAIL_USERNAME') or '').strip().lower()
    password = (app_config.get('MAIL_PASSWORD') or '').strip().lower()

    placeholders = {
        '',
        'seu-email@gmail.com',
        'sua-senha-app',
        'your-email@gmail.com',
        'your-app-password',
    }
    return username not in placeholders and password not in placeholders


def enviar_email_com_status(flask_app, funcao_envio, *args):
    """Executa envio de email e retorna (sucesso, mensagem_erro)."""
    if not smtp_configurado(flask_app.config):
        return False, 'Envio de email não configurado no servidor (configure RESEND_API_KEY ou SMTP).'

    timeout_segundos = int(os.getenv('EMAIL_SEND_TIMEOUT', '12'))
    resultado = {'enviado': False, 'erro': None}

    def _worker_envio():
        with flask_app.app_context():
            try:
                resultado['enviado'] = bool(funcao_envio(*args))
            except Exception as error:
                resultado['erro'] = str(error)
                resultado['enviado'] = False

    try:
        thread = Thread(target=_worker_envio, daemon=True)
        thread.start()
        thread.join(timeout=timeout_segundos)

        if thread.is_alive():
            flask_app.logger.warning('Timeout no envio de email após %ss', timeout_segundos)
            return False, 'Timeout no envio de email. Tente novamente em alguns instantes.'

        enviado = resultado['enviado']
    except Exception:
        enviado = False

    if resultado['erro']:
        flask_app.logger.warning('Falha no envio de email: %s', resultado['erro'])

    if not enviado:
        return False, 'Não foi possível enviar email no momento.'

    return True, None


def disparar_email_assincrono(flask_app, funcao_envio, *args):
    """Dispara envio de email sem bloquear a requisição do usuário."""
    if not smtp_configurado(flask_app.config):
        return False

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
