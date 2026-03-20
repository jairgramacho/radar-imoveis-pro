import os
from datetime import timedelta
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


def _env_bool(name, default=False):
    """Converte variável de ambiente para booleano de forma segura."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def _build_database_uri(default_uri, force_ssl=False):
    """Normaliza DATABASE_URL para SQLAlchemy e aplica sslmode quando necessário."""
    database_url = os.getenv('DATABASE_URL', default_uri).strip()
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)

    if not force_ssl or not database_url.startswith('postgresql://'):
        return database_url

    parsed = urlparse(database_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.setdefault('sslmode', 'require')
    new_query = urlencode(query)
    return urlunparse(parsed._replace(query=new_query))


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
    SQLALCHEMY_DATABASE_URI = _build_database_uri('sqlite:///imoveis.db', force_ssl=False)
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }
    SESSION_COOKIE_SECURE = False
    TESTING = False

class ProductionConfig(Config):
    """Configurações para produção"""
    DEBUG = False
    TESTING = False
    
    # Database obrigatório em produção
    SQLALCHEMY_DATABASE_URI = _build_database_uri(
        'postgresql://user:password@localhost/radar_imoveis',
        force_ssl=True,
    )
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 180,
        'pool_timeout': 30,
    }

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
