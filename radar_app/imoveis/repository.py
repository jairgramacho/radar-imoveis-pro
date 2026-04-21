"""Repositório de imóveis — centraliza todas as queries SQLAlchemy de Imovel."""
from sqlalchemy import case, func


class ImovelRepository:
    def __init__(self, db, model):
        self.db = db
        self.model = model

    def listar_ativos(self, filtros=None):
        """Retorna imóveis ativos, com filtros opcionais de cidade/bairro/tipo/negocio."""
        q = self.model.query.filter_by(ativo=True).order_by(self.model.criado_em.desc())
        if filtros:
            if filtros.get('cidade'):
                q = q.filter_by(cidade=filtros['cidade'])
            if filtros.get('bairro'):
                q = q.filter_by(bairro=filtros['bairro'])
            if filtros.get('tipo'):
                q = q.filter_by(tipo=filtros['tipo'])
            if filtros.get('negocio'):
                q = q.filter_by(negocio=filtros['negocio'])
        return q.all()

    def buscar(self, filtros=None):
        """Busca imóveis ativos com filtros avançados (negocio Venda/Compra, cidade ilike, preco_max)."""
        q = self.model.query.filter_by(ativo=True).order_by(self.model.criado_em.desc())
        if filtros:
            negocio = filtros.get('negocio')
            if negocio:
                if negocio == 'Venda':
                    q = q.filter(self.model.negocio.in_(['Venda', 'Compra']))
                else:
                    q = q.filter_by(negocio=negocio)
            if filtros.get('tipo'):
                q = q.filter_by(tipo=filtros['tipo'])
            if filtros.get('estado'):
                q = q.filter_by(estado=filtros['estado'])
            if filtros.get('cidade'):
                q = q.filter(self.model.cidade.ilike(f"%{filtros['cidade']}%"))
            if filtros.get('preco_max'):
                try:
                    preco_max = float(
                        filtros['preco_max'].replace('R$', '').replace('.', '').replace(',', '.').strip()
                    )
                    q = q.filter(self.model.preco <= preco_max)
                except Exception:
                    pass
        return q.all()

    def buscar_por_id_ou_404(self, id):
        """Retorna um imóvel pelo id, ou aborta com 404 se não encontrado."""
        from flask import abort
        imovel = self.db.session.get(self.model, id)
        if imovel is None:
            abort(404)
        return imovel

    def listar_por_usuario(self, usuario_id):
        """Retorna todos os imóveis de um usuário, do mais recente ao mais antigo."""
        return (
            self.model.query
            .filter_by(usuario_id=usuario_id)
            .order_by(self.model.criado_em.desc())
            .all()
        )

    def buscar_por_id(self, id):
        """Retorna um imóvel pelo id, ou None se não encontrado."""
        return self.db.session.get(self.model, id)

    def contar_ativos_por_usuario(self, usuario_id):
        """Conta imóveis com status ativo de um usuário."""
        return (
            self.model.query
            .filter_by(usuario_id=usuario_id, ativo=True)
            .count()
        )

    def estatisticas_preco_por_grupo(self):
        """Retorna média de preço e contagem por grupo (negocio, cidade, bairro, tipo, quartos).

        Usada pelo algoritmo Radar de Oportunidades para identificar imóveis
        com preço abaixo da média do grupo comparável.
        """
        negocio_agrupado = case(
            (func.lower(func.trim(self.model.negocio)) == 'compra', 'venda'),
            else_=func.lower(func.trim(self.model.negocio)),
        )

        return (
            self.db.session.query(
                negocio_agrupado.label('negocio'),
                func.lower(func.trim(self.model.cidade)).label('cidade'),
                func.lower(func.trim(self.model.bairro)).label('bairro'),
                func.lower(func.trim(self.model.tipo)).label('tipo'),
                self.model.quartos.label('quartos'),
                func.avg(self.model.preco).label('preco_medio'),
                func.count(self.model.id).label('total_imoveis'),
            )
            .filter(self.model.ativo.is_(True))
            .group_by(
                negocio_agrupado,
                func.lower(func.trim(self.model.cidade)),
                func.lower(func.trim(self.model.bairro)),
                func.lower(func.trim(self.model.tipo)),
                self.model.quartos,
            )
            .all()
        )
