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
    limite_anuncios = db.Column(db.Integer, nullable=False, default=3)
    status_assinatura = db.Column(db.String(20), nullable=False, default='ativa')
    assinatura_renova_em = db.Column(db.DateTime, nullable=True)
    senha = db.Column(db.String(255), nullable=False)
    whatsapp = db.Column(db.String(20), nullable=False)
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

