import os
from datetime import timedelta


def _env_bool(name, default=False):
    """Converte variável de ambiente para booleano de forma segura."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


class Config:
    """Configurações gerais"""
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

    # Database
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Session
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # Upload
    UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', 'static/uploads')
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB

    # URL pública da aplicação (usada em emails)
    APP_URL = os.getenv('APP_URL', 'http://localhost:5000').rstrip('/')

    # Email
    MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.getenv('MAIL_PORT', 587))
    MAIL_USE_TLS = _env_bool('MAIL_USE_TLS', True)
    MAIL_USERNAME = os.getenv('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD', '')
    MAIL_DEFAULT_SENDER = os.getenv('MAIL_DEFAULT_SENDER', 'noreply@radarimovei.com')

class DevelopmentConfig(Config):
    """Configurações para desenvolvimento"""
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.getenv(
        'DATABASE_URL',
        'sqlite:///imoveis.db'
    )
    SESSION_COOKIE_SECURE = False
    TESTING = False

class ProductionConfig(Config):
    """Configurações para produção"""
    DEBUG = False
    TESTING = False
    
    # Database obrigatório em produção
    SQLALCHEMY_DATABASE_URI = os.getenv(
        'DATABASE_URL',
        'postgresql://user:password@localhost/radar_imoveis'
    )

    PREFERRED_URL_SCHEME = 'https'
    
    # Validar variáveis críticas
    @classmethod
    def validate(cls):
        required_vars = ['SECRET_KEY', 'MAIL_USERNAME', 'MAIL_PASSWORD', 'DATABASE_URL', 'APP_URL', 'MAIL_DEFAULT_SENDER']
        missing = [var for var in required_vars if not os.getenv(var)]
        if missing:
            raise ValueError(f"Variáveis de ambiente obrigatórias não configuradas: {', '.join(missing)}")

        secret = os.getenv('SECRET_KEY', '')
        if len(secret) < 32 or 'dev-secret-key-change-in-production' in secret:
            raise ValueError('SECRET_KEY insegura para produção. Use uma chave aleatória com pelo menos 32 caracteres.')

        app_url = os.getenv('APP_URL', '')
        if not app_url.startswith('https://'):
            raise ValueError('APP_URL deve usar HTTPS em produção (ex.: https://radarimoveis.com).')

class TestingConfig(Config):
    """Configurações para testes"""
    DEBUG = True
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SESSION_COOKIE_SECURE = False

# Selecionar config baseada na variável de ambiente
config_name = os.getenv('FLASK_ENV', 'development')
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig
}.get(config_name, DevelopmentConfig)
