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

