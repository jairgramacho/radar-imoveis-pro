"""Repositório de usuários — centraliza queries SQLAlchemy de Usuario."""


class UsuarioRepository:
    def __init__(self, db, usuario_model, imovel_model=None, avaliacao_model=None,
                 mensagem_model=None, notificacao_model=None):
        self.db = db
        self.model = usuario_model
        self.imovel_model = imovel_model
        self.avaliacao_model = avaliacao_model
        self.mensagem_model = mensagem_model
        self.notificacao_model = notificacao_model

    def buscar_por_email(self, email):
        """Retorna o usuário com o email dado, ou None."""
        return self.model.query.filter_by(email=email).first()

    def buscar_por_whatsapp(self, whatsapp):
        """Retorna o usuário com o whatsapp dado, ou None."""
        return self.model.query.filter_by(whatsapp=whatsapp).first()

    def buscar_por_stripe_subscription_id(self, subscription_id):
        """Retorna o usuário com o stripe_subscription_id dado, ou None."""
        return self.model.query.filter_by(stripe_subscription_id=subscription_id).first()

    def buscar_por_stripe_customer_id(self, customer_id):
        """Retorna o usuário com o stripe_customer_id dado, ou None."""
        return self.model.query.filter_by(stripe_customer_id=customer_id).first()

    def buscar_por_id(self, usuario_id):
        """Retorna o usuário pelo id, ou None."""
        return self.db.session.get(self.model, usuario_id)

    def buscar_por_id_ou_404(self, usuario_id):
        """Retorna o usuário pelo id, ou aborta com 404."""
        from flask import abort
        usuario = self.db.session.get(self.model, usuario_id)
        if usuario is None:
            abort(404)
        return usuario

    def email_em_uso_por_outro(self, email, usuario_id_atual):
        """Retorna True se o email já está em uso por outro usuário."""
        return self.model.query.filter(
            self.model.email == email,
            self.model.id != usuario_id_atual,
        ).first() is not None

    def listar_todos(self):
        """Retorna todos os usuários."""
        return self.model.query.all()

    def salvar(self, usuario):
        """Persiste um novo usuário e faz commit."""
        self.db.session.add(usuario)
        self.db.session.commit()

    def commit(self):
        """Persiste alterações já feitas na sessão."""
        self.db.session.commit()

    def rollback(self):
        """Desfaz alterações pendentes na sessão."""
        self.db.session.rollback()

    def excluir_com_dados(self, usuario):
        """Remove um usuário e todos os seus dados associados (cascade manual)."""
        usuario_id = usuario.id

        if self.mensagem_model:
            self.mensagem_model.query.filter(
                (self.mensagem_model.remetente_id == usuario_id)
                | (self.mensagem_model.destinatario_id == usuario_id)
            ).delete(synchronize_session=False)

        if self.avaliacao_model:
            self.avaliacao_model.query.filter(
                (self.avaliacao_model.usuario_id == usuario_id)
                | (self.avaliacao_model.avaliador_id == usuario_id)
            ).delete(synchronize_session=False)

        if self.notificacao_model:
            self.notificacao_model.query.filter_by(usuario_id=usuario_id).delete(
                synchronize_session=False
            )

        if self.imovel_model:
            for imovel in self.imovel_model.query.filter_by(usuario_id=usuario_id).all():
                self.db.session.delete(imovel)

        self.db.session.delete(usuario)
        self.db.session.commit()
