"""Repositório de avaliações de anunciantes."""


class AvaliacaoRepository:
    def __init__(self, db, avaliacao_model, usuario_model):
        self.db = db
        self.avaliacao_model = avaliacao_model
        self.usuario_model = usuario_model

    def buscar_usuario_por_id_ou_404(self, usuario_id):
        """Retorna um usuário pelo id, ou aborta com 404."""
        from flask import abort
        usuario = self.db.session.get(self.usuario_model, usuario_id)
        if usuario is None:
            abort(404)
        return usuario

    def salvar(self, avaliacao):
        """Persiste uma avaliação e faz commit."""
        self.db.session.add(avaliacao)
        self.db.session.commit()

    def rollback(self):
        """Desfaz alterações pendentes na sessão."""
        self.db.session.rollback()
