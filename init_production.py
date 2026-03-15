#!/usr/bin/env python
"""
Script de preparo e diagnóstico para produção.
Uso:
    python init_production.py
"""

import os
import secrets
import smtplib
from pathlib import Path

from dotenv import load_dotenv

def generate_secret_key(length=32):
    """Gera chave secreta aleatória"""
    return secrets.token_hex(length)

def init_env():
    """Verifica e inicializa .env"""
    env_path = Path('.env')
    env_example = Path('.env.example')
    
    if not env_path.exists():
        if env_example.exists():
            print("📋 Criando .env a partir de .env.example...")
            with open(env_example) as f:
                content = f.read()
            with open(env_path, 'w') as f:
                f.write(content)
            print(f"✅ Arquivo .env criado. Edite com suas credenciais.")
        else:
            print("❌ Erro: .env.example não encontrado!")
            return False
    else:
        print("✅ Arquivo .env já existe")
    
    return True

def generate_keys():
    """Gera chaves de segurança"""
    secret = generate_secret_key()
    print(f"\n🔐 SECRET_KEY gerada:")
    print(f"   {secret}")
    print(f"\n   Cole isto no seu .env:")
    print(f"   SECRET_KEY={secret}")
    return secret

def check_requirements():
    """Verifica se requirements estão instalados"""
    try:
        import flask
        import flask_sqlalchemy
        print("✅ Dependências OK")
        return True
    except ImportError as e:
        print(f"❌ Erro: {e}")
        print("   Execute: pip install -r requirements.txt")
        return False


def check_env_production_ready():
    """Valida variáveis críticas para produção."""
    print("\n🔎 Validando variáveis para produção...")
    required_vars = [
        'FLASK_ENV',
        'SECRET_KEY',
        'DATABASE_URL',
        'MAIL_SERVER',
        'MAIL_PORT',
        'MAIL_USERNAME',
        'MAIL_PASSWORD',
        'MAIL_DEFAULT_SENDER',
        'APP_URL',
    ]

    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        print(f"❌ Variáveis ausentes: {', '.join(missing)}")
        return False

    if os.getenv('FLASK_ENV') != 'production':
        print("⚠️  FLASK_ENV não está como production")

    secret = os.getenv('SECRET_KEY', '')
    if len(secret) < 32 or 'dev-secret-key-change-in-production' in secret:
        print("❌ SECRET_KEY fraca para produção")
        return False

    app_url = os.getenv('APP_URL', '')
    if not app_url.startswith('https://'):
        print("❌ APP_URL deve começar com https:// em produção")
        return False

    print("✅ Variáveis de produção OK")
    return True


def check_database_connection():
    """Valida conexão com banco via SQLAlchemy da aplicação."""
    print("\n🗄️  Testando conexão com banco...")
    try:
        from app import app, db
        from sqlalchemy import text

        with app.app_context():
            db.session.execute(text('SELECT 1'))
        print("✅ Conexão com banco OK")
        return True
    except Exception as e:
        print(f"❌ Falha ao conectar no banco: {e}")
        return False


def check_smtp_connection():
    """Valida autenticação SMTP sem enviar email."""
    print("\n📧 Testando SMTP...")
    server = os.getenv('MAIL_SERVER', '')
    port = int(os.getenv('MAIL_PORT', '587'))
    username = os.getenv('MAIL_USERNAME', '')
    password = os.getenv('MAIL_PASSWORD', '')
    use_tls = str(os.getenv('MAIL_USE_TLS', 'True')).strip().lower() in {'1', 'true', 'yes', 'on'}

    if not all([server, port, username, password]):
        print("❌ SMTP incompleto. Configure MAIL_SERVER/PORT/USERNAME/PASSWORD")
        return False

    try:
        with smtplib.SMTP(server, port, timeout=15) as smtp:
            smtp.ehlo()
            if use_tls:
                smtp.starttls()
                smtp.ehlo()
            smtp.login(username, password)
        print("✅ SMTP autenticado com sucesso")
        return True
    except Exception as e:
        print(f"❌ Falha no SMTP: {e}")
        return False


def smoke_test_routes():
    """Executa smoke test das rotas públicas críticas."""
    print("\n🌐 Smoke test de rotas...")
    try:
        from app import app

        client = app.test_client()
        paths = ['/', '/login', '/cadastro', '/politica-de-privacidade', '/faq-ajuda', '/healthz']
        ok = True

        for path in paths:
            response = client.get(path, follow_redirects=False)
            status = response.status_code
            print(f"   {path} -> {status}")
            if status >= 500:
                ok = False

        if ok:
            print("✅ Smoke test OK")
        else:
            print("❌ Smoke test encontrou erro 5xx")
        return ok
    except Exception as e:
        print(f"❌ Erro no smoke test: {e}")
        return False

def init_database():
    """Inicializa banco de dados"""
    try:
        from app import app, db
        
        with app.app_context():
            print("\n📊 Inicializando banco de dados...")
            db.create_all()
            print("✅ Banco de dados criado com sucesso!")
            return True
    except Exception as e:
        print(f"❌ Erro ao criar banco: {e}")
        return False

def main():
    print("🚀 CHECKLIST DE PRONTIDÃO - RADAR IMÓVEIS")
    print("=" * 50)

    load_dotenv()
    
    # 1. Verificar requirements
    print("\n1️⃣  Verificando dependências...")
    if not check_requirements():
        return False
    
    # 2. Criar .env
    print("\n2️⃣  Verificando/criando .env...")
    if not init_env():
        return False
    
    # 3. Ambiente
    print("\n3️⃣  Ambiente...")
    env = os.getenv('FLASK_ENV', 'development')
    print(f"   FLASK_ENV = {env}")

    if env != 'production':
        print("   ⚠️  Ambiente atual não é produção. Ajuste no .env quando for publicar.")

    # 4. Inicializar BD
    print("\n4️⃣  Inicializando banco de dados...")
    init_database()

    # 5. Validar prontidão de produção
    print("\n5️⃣  Validações de prontidão...")
    env_ok = check_env_production_ready()
    db_ok = check_database_connection()
    smtp_ok = check_smtp_connection()
    routes_ok = smoke_test_routes()
    
    print("\n" + "=" * 50)
    if all([env_ok, db_ok, smtp_ok, routes_ok]):
        print("✅ PRONTO PARA PRODUÇÃO")
    else:
        print("⚠️  AINDA NÃO PRONTO PARA PRODUÇÃO")

    print("\nPróximos passos:")
    print("1. Corrigir itens com ❌ acima")
    print("2. Rodar novamente: python init_production.py")
    print("3. Publicar somente quando o checklist estiver todo OK")

    if env != 'production':
        print("\nDica: para gerar uma SECRET_KEY forte use:")
        print("python -c \"import secrets; print(secrets.token_hex(32))\"")

if __name__ == '__main__':
    main()
