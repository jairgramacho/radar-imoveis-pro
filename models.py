from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()

class Usuario(db.Model):
    """Modelo de Usuário"""
    __tablename__ = 'usuarios'
    
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    email_confirmado = db.Column(db.Boolean, nullable=False, default=True)
    confirmado_em = db.Column(db.DateTime, nullable=True)
    plano = db.Column(db.String(20), nullable=False, default='free', index=True)
    limite_anuncios = db.Column(db.Integer, nullable=False, default=0)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    status_assinatura = db.Column(db.String(20), nullable=False, default='ativa')
    assinatura_renova_em = db.Column(db.DateTime, nullable=True)
    stripe_customer_id = db.Column(db.String(120), nullable=True, index=True)
    stripe_subscription_id = db.Column(db.String(120), nullable=True, index=True)
    senha = db.Column(db.String(255), nullable=False)
    whatsapp = db.Column(db.String(20), unique=True, nullable=False, index=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relacionamentos
    imoveis = db.relationship('Imovel', backref='anunciante', lazy=True, cascade='all, delete-orphan')
    avaliacoes_recebidas = db.relationship('Avaliacao', foreign_keys='Avaliacao.usuario_id', backref='usuario', lazy=True)
    mensagens_enviadas = db.relationship('Mensagem', foreign_keys='Mensagem.remetente_id', backref='remetente', lazy=True)
    mensagens_recebidas = db.relationship('Mensagem', foreign_keys='Mensagem.destinatario_id', backref='destinatario', lazy=True)
    
    def set_password(self, senha):
        """Define a senha (com hash seguro)"""
        self.senha = generate_password_hash(senha)
    
    def check_password(self, senha):
        """Valida a senha"""
        return check_password_hash(self.senha, senha)
    
    def get_rating(self):
        """Calcula a média de avaliações. Novos usuários começam com 4.0 de rating."""
        if not self.avaliacoes_recebidas:
            return 4.0
        total = sum(a.estrelas for a in self.avaliacoes_recebidas)
        return round(total / len(self.avaliacoes_recebidas), 1)
    
    def get_total_avaliacoes(self):
        """Retorna o total de avaliações"""
        return len(self.avaliacoes_recebidas)
    
    def __repr__(self):
        return f'<Usuario {self.nome}>'


class Imovel(db.Model):
    """Modelo de Imóvel"""
    __tablename__ = 'imoveis'
    
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False, index=True)
    
    # Localização
    estado = db.Column(db.String(2), nullable=False, index=True)
    cidade = db.Column(db.String(120), nullable=False, index=True)
    bairro = db.Column(db.String(120), nullable=False)
    
    # Tipo e Negócio
    tipo = db.Column(db.String(50), nullable=False, index=True)
    negocio = db.Column(db.String(20), nullable=False, index=True)
    
    # Características
    quartos = db.Column(db.Integer)
    vagas = db.Column(db.Integer)
    area = db.Column(db.Float)
    
    # Preço
    preco = db.Column(db.Float, nullable=False, index=True)
    
    # Descrição e Foto Principal
    descricao = db.Column(db.Text)
    foto = db.Column(db.String(255))  # Foto principal (compatibilidade com sistema antigo)
    
    # Visualizações e Status
    visualizacoes = db.Column(db.Integer, default=0)
    ativo = db.Column(db.Boolean, default=True, index=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relacionamentos
    fotos = db.relationship('FotoImovel', backref='imovel', lazy=True, cascade='all, delete-orphan')
    avaliacoes = db.relationship('Avaliacao', backref='imovel', lazy=True, cascade='all, delete-orphan')
    
    def get_foto_principal(self):
        """Retorna a primeira foto ou a foto legada"""
        if self.fotos:
            return self.fotos[0].arquivo
        return self.foto
    
    def get_total_fotos(self):
        """Retorna o total de fotos"""
        return len(self.fotos)
    
    def __repr__(self):
        return f'<Imovel {self.tipo} em {self.cidade}>'


class FotoImovel(db.Model):
    """Modelo para múltiplas fotos por imóvel"""
    __tablename__ = 'fotos_imovel'
    
    id = db.Column(db.Integer, primary_key=True)
    imovel_id = db.Column(db.Integer, db.ForeignKey('imoveis.id'), nullable=False, index=True)
    arquivo = db.Column(db.String(255), nullable=False)
    ordem = db.Column(db.Integer, default=0)  # Para ordenar as fotos
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<FotoImovel {self.arquivo}>'


class Avaliacao(db.Model):
    """Modelo de Avaliação com Comentários"""
    __tablename__ = 'avaliacoes'
    
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False, index=True)
    imovel_id = db.Column(db.Integer, db.ForeignKey('imoveis.id'), nullable=False)
    avaliador_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    
    estrelas = db.Column(db.Integer, nullable=False)  # 1-5
    comentario = db.Column(db.Text)  # Novo! Comentários
    criado_em = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    # Relacionamento com quem avaliou
    avaliador = db.relationship('Usuario', foreign_keys=[avaliador_id], backref='avaliacoes_feitas')
    
    def __repr__(self):
        return f'<Avaliacao {self.estrelas} estrelas>'


class Mensagem(db.Model):
    """Modelo de Chat entre Usuários"""
    __tablename__ = 'mensagens'
    
    id = db.Column(db.Integer, primary_key=True)
    remetente_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False, index=True)
    destinatario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False, index=True)
    imovel_id = db.Column(db.Integer, db.ForeignKey('imoveis.id'), nullable=True, index=True)  # Sobre qual imóvel
    
    titulo = db.Column(db.String(200))  # Assunto da conversa
    mensagem = db.Column(db.Text, nullable=False)
    lida = db.Column(db.Boolean, default=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    # Relacionamento com imóvel (opcional)
    imovel = db.relationship('Imovel')
    
    def __repr__(self):
        return f'<Mensagem de {self.remetente_id} para {self.destinatario_id}>'


class CRMLead(db.Model):
    """Lead de CRM gerado a partir de WhatsApp, chat ou cadastro manual."""
    __tablename__ = 'crm_leads'

    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(24), nullable=False, unique=True, index=True)
    anunciante_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False, index=True)
    imovel_id = db.Column(db.Integer, db.ForeignKey('imoveis.id'), nullable=True, index=True)
    interessado_usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True, index=True)

    origem = db.Column(db.String(20), nullable=False, default='whatsapp', index=True)
    status = db.Column(db.String(30), nullable=False, default='novo', index=True)
    nome = db.Column(db.String(120), nullable=True)
    email = db.Column(db.String(120), nullable=True, index=True)
    whatsapp = db.Column(db.String(20), nullable=True, index=True)
    origem_url = db.Column(db.String(500), nullable=True)
    visitor_key = db.Column(db.String(64), nullable=True, index=True)
    observacoes = db.Column(db.Text, nullable=True)
    perda_motivo = db.Column(db.String(120), nullable=True)
    proxima_acao_em = db.Column(db.DateTime, nullable=True, index=True)
    primeiro_contato_em = db.Column(db.DateTime, nullable=True)
    ultima_interacao_em = db.Column(db.DateTime, nullable=True, index=True)
    status_alterado_em = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    anunciante = db.relationship('Usuario', foreign_keys=[anunciante_id], backref='crm_leads_recebidos')
    interessado = db.relationship('Usuario', foreign_keys=[interessado_usuario_id], backref='crm_leads_gerados')
    imovel = db.relationship('Imovel', backref='crm_leads')
    historicos = db.relationship('CRMLeadHistorico', backref='lead', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<CRMLead {self.codigo}>'


class CRMLeadHistorico(db.Model):
    """Histórico de mudanças e interações do lead no CRM."""
    __tablename__ = 'crm_lead_historicos'

    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey('crm_leads.id'), nullable=False, index=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True, index=True)
    acao = db.Column(db.String(30), nullable=False, default='status', index=True)
    de_status = db.Column(db.String(30), nullable=True)
    para_status = db.Column(db.String(30), nullable=True)
    nota = db.Column(db.Text, nullable=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    autor = db.relationship('Usuario', backref='crm_lead_historicos')

    def __repr__(self):
        return f'<CRMLeadHistorico lead_id={self.lead_id} acao={self.acao}>'


class Notificacao(db.Model):
    """Modelo de Notificações por Email"""
    __tablename__ = 'notificacoes'
    
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False, index=True)
    tipo = db.Column(db.String(50), nullable=False)  # 'novo_anuncio', 'nova_mensagem', 'avaliacao'
    titulo = db.Column(db.String(200), nullable=False)
    descricao = db.Column(db.Text)
    
    lida = db.Column(db.Boolean, default=False)
    enviada_email = db.Column(db.Boolean, default=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    usuario = db.relationship('Usuario', backref='notificacoes')
    
    def __repr__(self):
        return f'<Notificacao {self.tipo}>'


class StripeEventoWebhook(db.Model):
    """Idempotência de eventos Stripe para evitar processamento duplicado."""
    __tablename__ = 'stripe_eventos_webhook'

    id = db.Column(db.Integer, primary_key=True)
    stripe_event_id = db.Column(db.String(120), nullable=False, unique=True, index=True)
    tipo = db.Column(db.String(80), nullable=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    def __repr__(self):
        return f'<StripeEventoWebhook {self.stripe_event_id}>'


class ConsentimentoUsuario(db.Model):
    """Registro LGPD de Consentimentos do Usuário"""
    __tablename__ = 'consentimentos_usuario'
    
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False, index=True)
    tipo = db.Column(db.String(50), nullable=False)  # 'termos', 'politica_privacidade', 'marketing_email'
    aceito = db.Column(db.Boolean, nullable=False, default=False)
    data_consentimento = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    ip_address = db.Column(db.String(45), nullable=True)  # IPv4 ou IPv6
    user_agent = db.Column(db.String(500), nullable=True)  # Browser info
    versao_documento = db.Column(db.String(20), nullable=True)  # ex: "1.0", "1.1"
    criado_em = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    usuario = db.relationship('Usuario', backref='consentimentos')
    
    def __repr__(self):
        return f'<ConsentimentoUsuario {self.tipo}>'


class AuditLog(db.Model):
    """Registro de Auditoria (LGPD Compliance)"""
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True, index=True)
    acao = db.Column(db.String(100), nullable=False)  # 'login', 'logout', 'deletar_conta', 'exportar_dados'
    entidade = db.Column(db.String(50), nullable=False)  # 'usuario', 'imovel', 'mensagem'
    entidade_id = db.Column(db.Integer, nullable=True)  # ID da entidade afetada
    detalhes = db.Column(db.JSON, nullable=True)  # Dados adicionais
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(500), nullable=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    usuario = db.relationship('Usuario', backref='audit_logs')
    
    def __repr__(self):
        return f'<AuditLog {self.acao}>'


class TokenDoisFatores(db.Model):
    """Tokens para Autenticação de Dois Fatores (2FA)"""
    __tablename__ = 'tokens_2fa'
    
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False, index=True, unique=True)
    secret = db.Column(db.String(32), nullable=False)  # TOTP secret (base32)
    habilitado = db.Column(db.Boolean, nullable=False, default=False)
    backup_codes = db.Column(db.JSON, nullable=True)  # Lista de códigos de recuperação
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    usuario = db.relationship('Usuario', backref='token_2fa', uselist=False)
    
    def __repr__(self):
        return f'<TokenDoisFatores usuario_id={self.usuario_id}>'

