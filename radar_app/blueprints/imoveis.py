"""Blueprint para leitura e listagem de imoveis."""

from flask import Blueprint, render_template, request, redirect, flash, url_for

from models import Imovel


imoveis_bp = Blueprint('imoveis', __name__)


def _legacy():
    from radar_app import legacy_app

    return legacy_app


@imoveis_bp.route('/')
def index():
    """Pagina principal com abas de busca e anuncio."""
    legacy = _legacy()
    usuario = legacy.get_usuario_logado()
    limite_anuncios = legacy._resumo_limite_anuncios(usuario) if usuario else None
    aba = request.args.get('aba', 'buscar')
    filtros = request.args.to_dict()
    pagina = request.args.get('pagina', 1, type=int)

    query = Imovel.query.filter_by(ativo=True).order_by(Imovel.criado_em.desc())

    if filtros.get('negocio'):
        negocio_filtro = filtros['negocio']
        if negocio_filtro == 'Venda':
            query = query.filter(Imovel.negocio.in_(['Venda', 'Compra']))
        else:
            query = query.filter_by(negocio=negocio_filtro)

    if filtros.get('tipo'):
        query = query.filter_by(tipo=filtros['tipo'])

    if filtros.get('estado'):
        query = query.filter_by(estado=filtros['estado'])

    if filtros.get('cidade'):
        query = query.filter(Imovel.cidade.ilike(f"%{filtros['cidade']}%"))

    if filtros.get('preco_max'):
        try:
            preco_max = float(filtros['preco_max'].replace('R$', '').replace('.', '').replace(',', '.').strip())
            query = query.filter(Imovel.preco <= preco_max)
        except Exception:
            pass

    imoveis = query.all()
    legacy.aplicar_radar_oportunidades(imoveis)

    oportunidades = [imovel for imovel in imoveis if getattr(imovel, 'eh_oportunidade', False)]
    oportunidades.sort(key=lambda item: item.desconto_oportunidade or 0, reverse=True)

    if filtros.get('somente_oportunidades') == '1':
        imoveis = [imovel for imovel in imoveis if getattr(imovel, 'eh_oportunidade', False)]

    imoveis_pagina, imoveis_total, imoveis_total_paginas, pagina_ajustada = legacy._paginar_lista(
        imoveis,
        pagina,
        legacy.ITENS_POR_PAGINA,
    )
    oportunidades_pagina, oportunidades_total, oportunidades_total_paginas, pagina_oportunidades = legacy._paginar_lista(
        oportunidades,
        pagina,
        legacy.ITENS_POR_PAGINA,
    )

    argumentos_base = {k: v for k, v in filtros.items() if k != 'pagina'}
    argumentos_base['aba'] = aba
    total_paginas = imoveis_total_paginas if aba == 'buscar' else oportunidades_total_paginas
    pagina_corrente = pagina_ajustada if aba == 'buscar' else pagina_oportunidades
    links_paginacao = {
        p: url_for('index', **{**argumentos_base, 'pagina': p})
        for p in range(1, total_paginas + 1)
    }

    return render_template(
        'index.html',
        imoveis=imoveis_pagina,
        imoveis_total=imoveis_total,
        oportunidades=oportunidades_pagina,
        oportunidades_total=oportunidades_total,
        aba=aba,
        busca=filtros,
        pagina_atual=pagina_corrente,
        total_paginas=total_paginas,
        links_paginacao=links_paginacao,
        limite_anuncios=limite_anuncios,
        usuario=usuario,
    )


@imoveis_bp.route('/meus-anuncios')
def meus_anuncios():
    """Lista os anuncios do usuario logado."""
    legacy = _legacy()
    usuario = legacy.get_usuario_logado()

    if not usuario:
        flash('Você precisa estar logado!', 'error')
        return redirect(url_for('login'))

    imoveis = Imovel.query.filter_by(usuario_id=usuario.id).order_by(Imovel.criado_em.desc()).all()
    legacy._padronizar_negocio_imoveis(imoveis)

    return render_template('meus_anuncios.html', imoveis=imoveis, usuario=usuario)


@imoveis_bp.route('/imovel/<int:id>')
def detalhe_imovel(id):
    """Pagina de detalhe do imovel."""
    legacy = _legacy()
    usuario = legacy.get_usuario_logado()
    imovel = Imovel.query.get_or_404(id)
    legacy._padronizar_negocio_imovel(imovel)

    imovel.visualizacoes = (imovel.visualizacoes or 0) + 1
    legacy.db.session.commit()

    descricao_base = (imovel.descricao or '').strip()
    if not descricao_base:
        descricao_base = f"{imovel.tipo} em {imovel.cidade}/{imovel.estado}, no bairro {imovel.bairro}."
    descricao_meta = f"{descricao_base[:140]} | Preço: R$ {legacy.moeda_brl(imovel.preco)}"

    foto_preview = legacy._resolver_foto_preview(imovel)
    marca_tempo = int((imovel.atualizado_em or imovel.criado_em).timestamp())
    separador = '&' if '?' in foto_preview else '?'
    foto_preview = f"{foto_preview}{separador}v={marca_tempo}"

    return render_template(
        'detalhe_imovel.html',
        imovel=imovel,
        usuario=usuario,
        descricao_meta=descricao_meta,
        foto_preview=foto_preview,
    )