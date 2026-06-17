import os

from sqlalchemy import inspect, text


def configurar_logging_estruturado(app, flask_env, logging_module, rotating_file_handler_class):
    """Configura logging consistente para facilitar diagnostico em producao."""
    if flask_env == 'testing':
        return

    formatter = logging_module.Formatter(
        '%(asctime)s %(levelname)s %(name)s: %(message)s [%(pathname)s:%(lineno)d]'
    )

    app.logger.setLevel(logging_module.INFO)

    for handler in app.logger.handlers:
        handler.setFormatter(formatter)

    if not app.debug:
        os.makedirs('logs', exist_ok=True)
        if not any(isinstance(handler, rotating_file_handler_class) for handler in app.logger.handlers):
            file_handler = rotating_file_handler_class(
                'logs/radar.log',
                maxBytes=10 * 1024 * 1024,
                backupCount=10,
            )
            file_handler.setLevel(logging_module.INFO)
            file_handler.setFormatter(formatter)
            app.logger.addHandler(file_handler)

    app.logger.info('Radar Imoveis Pro startup - env=%s', flask_env)


def garantir_colunas_usuario(db, stripe_evento_webhook_model):
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

    if 'plano' not in colunas:
        comandos.append("ALTER TABLE usuarios ADD COLUMN plano VARCHAR(20) NOT NULL DEFAULT 'free'")

    if 'limite_anuncios' not in colunas:
        comandos.append("ALTER TABLE usuarios ADD COLUMN limite_anuncios INTEGER NOT NULL DEFAULT 0")

    if 'is_admin' not in colunas:
        if dialect == 'sqlite':
            comandos.append("ALTER TABLE usuarios ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0")
        else:
            comandos.append("ALTER TABLE usuarios ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT FALSE")

    try:
        db.session.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_usuarios_whatsapp ON usuarios(whatsapp)"))
    except Exception:
        pass

    if 'status_assinatura' not in colunas:
        comandos.append("ALTER TABLE usuarios ADD COLUMN status_assinatura VARCHAR(20) NOT NULL DEFAULT 'ativa'")

    if 'assinatura_renova_em' not in colunas:
        if dialect == 'sqlite':
            comandos.append("ALTER TABLE usuarios ADD COLUMN assinatura_renova_em DATETIME")
        else:
            comandos.append("ALTER TABLE usuarios ADD COLUMN assinatura_renova_em TIMESTAMP")

    if 'stripe_customer_id' not in colunas:
        comandos.append("ALTER TABLE usuarios ADD COLUMN stripe_customer_id VARCHAR(120)")

    if 'stripe_subscription_id' not in colunas:
        comandos.append("ALTER TABLE usuarios ADD COLUMN stripe_subscription_id VARCHAR(120)")

    for comando in comandos:
        db.session.execute(text(comando))

    if comandos:
        db.session.commit()

    stripe_evento_webhook_model.__table__.create(bind=db.engine, checkfirst=True)


def garantir_tabelas_crm(db, crm_lead_model, crm_lead_historico_model):
    """Cria as tabelas do CRM quando o banco já existe sem migração."""
    crm_lead_model.__table__.create(bind=db.engine, checkfirst=True)
    crm_lead_historico_model.__table__.create(bind=db.engine, checkfirst=True)


def deve_executar_bootstrap_db(flask_env):
    """Controla bootstrap automático do banco para evitar travas no boot em produção."""
    override = os.getenv('RUN_DB_BOOTSTRAP')
    if override is not None:
        return override.strip().lower() in {'1', 'true', 'yes', 'on'}
    return flask_env != 'production'


def marcar_admin_proprietario(usuario_model, db, logger, email_admin='jairgramacho82160@gmail.com'):
    """Marca o email do proprietário como admin para limite ilimitado."""
    try:
        usuario = usuario_model.query.filter_by(email=email_admin).first()
        if usuario and not usuario.is_admin:
            usuario.is_admin = True
            db.session.commit()
            logger.info('Conta %s marcada como admin', email_admin)
    except Exception as error:
        logger.warning('Erro ao marcar admin: %s', str(error))
