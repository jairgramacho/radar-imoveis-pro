from sqlalchemy import case, func

from models import Imovel, db


def normalizar_texto(valor):
    """Normaliza texto para comparação entre imóveis semelhantes."""
    return (valor or '').strip().lower()


def normalizar_negocio(valor):
    """Converte valores legados de negócio para uma chave canônica."""
    negocio = normalizar_texto(valor)
    if negocio == 'compra':
        return 'venda'
    return negocio


def negocio_canonico(valor):
    """Retorna o valor canônico de negócio para persistência e exibição."""
    negocio = normalizar_negocio(valor)
    if negocio == 'venda':
        return 'Venda'
    if negocio == 'aluguel':
        return 'Aluguel'
    return (valor or '').strip()


def padronizar_negocio_imovel(imovel):
    """Padroniza o negócio apenas em memória para exibição consistente."""
    if imovel:
        imovel.negocio = negocio_canonico(imovel.negocio)
    return imovel


def padronizar_negocio_imoveis(imoveis):
    """Padroniza o negócio em listas de imóveis."""
    for imovel in imoveis:
        padronizar_negocio_imovel(imovel)
    return imoveis


def aplicar_radar_oportunidades(imoveis, oportunidade_amostra_minima, oportunidade_desconto_minimo):
    """Marca imóveis com preço pelo menos X% abaixo da média do grupo comparável."""
    if not imoveis:
        return

    negocio_agrupado = case(
        (func.lower(func.trim(Imovel.negocio)) == 'compra', 'venda'),
        else_=func.lower(func.trim(Imovel.negocio)),
    )

    estatisticas = (
        db.session.query(
            negocio_agrupado.label('negocio'),
            func.lower(func.trim(Imovel.cidade)).label('cidade'),
            func.lower(func.trim(Imovel.bairro)).label('bairro'),
            func.lower(func.trim(Imovel.tipo)).label('tipo'),
            Imovel.quartos.label('quartos'),
            func.avg(Imovel.preco).label('preco_medio'),
            func.count(Imovel.id).label('total_imoveis'),
        )
        .filter(Imovel.ativo.is_(True))
        .group_by(
            negocio_agrupado,
            func.lower(func.trim(Imovel.cidade)),
            func.lower(func.trim(Imovel.bairro)),
            func.lower(func.trim(Imovel.tipo)),
            Imovel.quartos,
        )
        .all()
    )

    mapa_medias = {
        (item.negocio, item.cidade, item.bairro, item.tipo, item.quartos): (item.preco_medio, item.total_imoveis)
        for item in estatisticas
    }

    for imovel in imoveis:
        padronizar_negocio_imovel(imovel)
        imovel.eh_oportunidade = False
        imovel.preco_medio_regiao = None
        imovel.desconto_oportunidade = None
        imovel.total_comparaveis = 0

        chave = (
            normalizar_negocio(imovel.negocio),
            normalizar_texto(imovel.cidade),
            normalizar_texto(imovel.bairro),
            normalizar_texto(imovel.tipo),
            imovel.quartos,
        )

        comparativo = mapa_medias.get(chave)
        if not comparativo:
            continue

        preco_medio, total_imoveis = comparativo
        if not preco_medio or total_imoveis < oportunidade_amostra_minima:
            continue

        desconto = (preco_medio - imovel.preco) / preco_medio
        imovel.preco_medio_regiao = float(preco_medio)
        imovel.desconto_oportunidade = float(desconto)
        imovel.total_comparaveis = int(total_imoveis)
        imovel.eh_oportunidade = desconto >= oportunidade_desconto_minimo
