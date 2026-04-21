from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer


def serializer_tokens(secret_key):
    return URLSafeTimedSerializer(secret_key)


def gerar_token_email(secret_key, email, objetivo):
    """Gera token assinado para confirmação de email e reset de senha."""
    return serializer_tokens(secret_key).dumps({'email': email, 'objetivo': objetivo}, salt='radar-imoveis-auth')


def validar_token_email(secret_key, token, objetivo, max_age=3600):
    """Valida token assinado e objetivo esperado."""
    try:
        payload = serializer_tokens(secret_key).loads(token, salt='radar-imoveis-auth', max_age=max_age)
    except SignatureExpired:
        return None, 'expirado'
    except BadSignature:
        return None, 'invalido'

    if payload.get('objetivo') != objetivo:
        return None, 'invalido'

    return payload.get('email'), None