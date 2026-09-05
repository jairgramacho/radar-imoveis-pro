"""Blueprint para operacoes de imoveis."""

from flask import Blueprint, render_template, request, redirect, flash, url_for
from pydantic import ValidationError

from models import Avaliacao, FotoImovel, Imovel, Usuario
from radar_app.imoveis import ImovelRepository
from radar_app.imoveis.avaliacao_repository import AvaliacaoRepository
from radar_app.security.sanitization import sanitizar_descricao, sanitizar_mensagem_chat
from radar_app.security.validation_schemas import ImovelDescricaoSchema, AvaliacaoSchema


imoveis_bp = Blueprint('imoveis', __name__)


def _repo():
    from models import db
    return ImovelRepository(db, Imovel)


def _avaliacao_repo():
    from models import db
    return AvaliacaoRepository(db, Avaliacao, Usuario)


def _legacy():
    from radar_app import legacy_app

    return legacy_app


@imoveis_bp.route('/')
def index():
    """Pagina principal — landing page por padrao, abas busca/oportunidades/anunciar."""
    legacy = _legacy()
    usuario = legacy.get_usuario_logado()
    aba = request.args.get('aba', 'inicio')

    # Landing page padrao
    if aba == 'inicio':
        from radar_app.legacy_app import moeda_brl
        ativos = _repo().listar_ativos()
        imoveis_recentes = ativos[:6]
        for im in imoveis_recentes:
            im.preco_formatado = moeda_brl(im.preco) if im.preco else ''
        # Total de visualizacoes acumuladas (campo existente no modelo)
        total_visualizacoes = sum((im.visualizacoes or 0) for im in ativos)
        # Bairros distintos considerando os imoveis ativos (normaliza caixa/acentos p/ nao contar duplicidade por digitacao)
        def _norm(s):
            import unicodedata
            s = (s or '').strip().lower()
            return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
        total_bairros = len({_norm(im.bairro) for im in ativos if im.bairro and _norm(im.bairro)})
        return render_template(
            'landing.html',
            usuario=usuario,
            imoveis_destaque=imoveis_recentes,
            total_imoveis=len(ativos),
            total_bairros=total_bairros,
            total_visualizacoes=total_visualizacoes,
            foto_url=legacy._foto_url,
            seo_title='Radar Imoveis Pro | Imoveis em Barreiras e Oeste da Bahia',
            seo_description='Encontre imoveis para compra e aluguel em Barreiras e regiao com busca inteligente e contato direto com o corretor.',
        )

    limite_anuncios = legacy._resumo_limite_anuncios(usuario) if usuario else None
    filtros = request.args.to_dict()
    pagina = request.args.get('pagina', 1, type=int)

    imoveis = _repo().buscar(filtros)
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

    seo_prev_url = None
    seo_next_url = None
    if total_paginas > 1 and pagina_corrente > 1:
        seo_prev_url = legacy._url_publica('index', **{**argumentos_base, 'pagina': pagina_corrente - 1})
    if total_paginas > 1 and pagina_corrente < total_paginas:
        seo_next_url = legacy._url_publica('index', **{**argumentos_base, 'pagina': pagina_corrente + 1})

    cidade_seo = (filtros.get('cidade') or '').strip()
    estado_seo = (filtros.get('estado') or '').strip()
    local_seo = cidade_seo if not estado_seo else f'{cidade_seo}/{estado_seo}' if cidade_seo else estado_seo

    if aba == 'oportunidades':
        seo_title = 'Oportunidades de Imoveis em Barreiras e Oeste da Bahia | Radar Imoveis Pro'
        seo_description = (
            'Encontre oportunidades de compra e aluguel com comparativo de preco local '
            'em Barreiras e no Oeste da Bahia.'
        )
    elif aba == 'anunciar':
        seo_title = 'Anunciar Imovel em Barreiras e Oeste da Bahia | Radar Imoveis Pro'
        seo_description = (
            'Publique seu imovel e alcance compradores e locatarios em Barreiras e em toda '
            'a regiao oeste da Bahia.'
        )
    else:
        seo_title = 'Imoveis em Barreiras e Oeste da Bahia | Radar Imoveis Pro'
        seo_description = (
            'Busque imoveis por tipo, bairro e preco em Barreiras e no Oeste da Bahia. '
            'Plataforma com contato direto e anuncios atualizados.'
        )

    if local_seo and aba != 'anunciar':
        seo_title = f'Imoveis em {local_seo} | Radar Imoveis Pro'
        seo_description = (
            f'Anuncios de imoveis em {local_seo} para compra e aluguel com filtros por tipo, '
            'preco e bairro na Radar Imoveis Pro.'
        )

    seo_json_ld_list = []
    if aba in {'buscar', 'oportunidades'}:
        seo_json_ld_list = [
            {
                '@context': 'https://schema.org',
                '@type': 'WebSite',
                'name': 'Radar Imoveis Pro',
                'url': legacy._url_publica('index'),
                'inLanguage': 'pt-BR',
                'potentialAction': {
                    '@type': 'SearchAction',
                    'target': f"{legacy._url_publica('index')}?aba=buscar&cidade={{search_term_string}}",
                    'query-input': 'required name=search_term_string',
                },
            },
            {
                '@context': 'https://schema.org',
                '@type': 'RealEstateAgent',
                'name': 'Radar Imoveis Pro',
                'url': legacy._url_publica('index'),
                'areaServed': ['Barreiras', 'Oeste da Bahia'],
            },
        ]

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
        seo_title=seo_title,
        seo_description=seo_description,
        seo_robots=('noindex,nofollow,noarchive' if aba == 'anunciar' else None),
        seo_prev_url=seo_prev_url,
        seo_next_url=seo_next_url,
        seo_json_ld_list=seo_json_ld_list,
    )


@imoveis_bp.route('/salvar', methods=['POST'])
def salvar():
    """Salva um novo anuncio de imovel."""
    legacy = _legacy()
    usuario = legacy.get_usuario_logado()

    if not usuario:
        flash('Você precisa estar logado para anunciar!', 'error')
        return redirect(url_for('login'))

    if legacy._status_assinatura_bloqueada(getattr(usuario, 'status_assinatura', '')):
        flash('Sua assinatura está pendente. Regularize seu pagamento para voltar a publicar anúncios.', 'error')
        return redirect(url_for('dashboard'))

    resumo_limite = legacy._resumo_limite_anuncios(usuario)
    if resumo_limite['atingiu_limite']:
        plano_nome = resumo_limite['plano'].capitalize()
        if resumo_limite['plano'] == 'free':
            flash(
                'Seu plano Free não permite novos anúncios. Faça upgrade para o plano Pro ou Empresa para publicar.',
                'error',
            )
            return redirect(url_for('index', aba='anunciar'))
        flash(
            f"Limite atingido: seu plano {plano_nome} permite {resumo_limite['limite']} anúncio(s) ativo(s). "
            'Desative um anúncio ou faça upgrade para publicar mais.',
            'error',
        )
        return redirect(url_for('index', aba='anunciar'))

    try:
        f = request.form

        campos_obrigatorios = ['estado', 'cidade', 'bairro', 'tipo', 'negocio', 'valor']
        for campo in campos_obrigatorios:
            if not f.get(campo):
                flash(f'Campo obrigatório não preenchido: {campo}', 'error')
                return redirect(url_for('index', aba='anunciar'))

        try:
            preco = float(f.get('valor').replace('R$', '').replace('.', '').replace(',', '.').strip())
        except Exception:
            flash('Preço inválido!', 'error')
            return redirect(url_for('index', aba='anunciar'))

        arquivos = request.files.getlist('foto')
        nome_foto_principal = None

        if arquivos and arquivos[0].filename:
            arq_principal = arquivos[0]
            if arq_principal and legacy.allowed_file(arq_principal.filename):
                nome_arquivo, sucesso = legacy.processar_imagem(arq_principal)
                if sucesso and nome_arquivo:
                    nome_foto_principal = nome_arquivo

        quartos = int(f.get('quartos', 0)) if f.get('quartos') else None
        vagas = int(f.get('vagas', 0)) if f.get('vagas') else None
        area = float(f.get('area', 0)) if f.get('area') else None

        # ✅ VALIDAÇÃO E SANITIZAÇÃO DE DESCRIÇÃO (XSS Protection)
        descricao_raw = f.get('descricao', '').strip()
        try:
            if descricao_raw:
                schema_data = ImovelDescricaoSchema(descricao=descricao_raw)
                descricao_sanitizada = sanitizar_descricao(schema_data.descricao)
            else:
                descricao_sanitizada = ''
        except ValidationError as e:
            erros = ', '.join([f"{err['loc'][0]}: {err['msg']}" for err in e.errors()])
            flash(f'Descrição inválida: {erros}', 'error')
            return redirect(url_for('index', aba='anunciar'))

        imovel = Imovel(
            usuario_id=usuario.id,
            estado=f.get('estado'),
            cidade=f.get('cidade'),
            bairro=f.get('bairro'),
            tipo=f.get('tipo'),
            negocio=legacy._negocio_canonico(f.get('negocio')),
            quartos=quartos,
            vagas=vagas,
            area=area,
            preco=preco,
            descricao=descricao_sanitizada,
            foto=nome_foto_principal,
        )

        fotos_extras = []
        for idx, arq in enumerate(arquivos[1:], start=1):
            if arq and legacy.allowed_file(arq.filename):
                nome_arquivo, sucesso = legacy.processar_imagem(arq)
                if sucesso and nome_arquivo:
                    fotos_extras.append(FotoImovel(
                        imovel_id=None,  # preenchido após salvar
                        arquivo=nome_arquivo,
                        ordem=idx,
                    ))

        repo = _repo()
        repo.salvar(imovel)
        for foto in fotos_extras:
            foto.imovel_id = imovel.id
        if fotos_extras:
            repo.adicionar_fotos(fotos_extras)

        flash('Anúncio publicado com sucesso! Você pode adicionar mais fotos se desejar.', 'success')
        return redirect(url_for('detalhe_imovel', id=imovel.id))

    except Exception as e:
        _repo().rollback()
        flash(f'Erro ao publicar anúncio: {str(e)}', 'error')
        return redirect(url_for('index', aba='anunciar'))


@imoveis_bp.route('/meus-anuncios')
def meus_anuncios():
    """Lista os anuncios do usuario logado."""
    legacy = _legacy()
    usuario = legacy.get_usuario_logado()

    if not usuario:
        flash('Você precisa estar logado!', 'error')
        return redirect(url_for('login'))

    imoveis = _repo().listar_por_usuario(usuario.id)
    legacy._padronizar_negocio_imoveis(imoveis)

    return render_template('meus_anuncios.html', imoveis=imoveis, usuario=usuario)


@imoveis_bp.route('/imovel/<int:id>')
def detalhe_imovel(id):
    """Pagina de detalhe do imovel."""
    legacy = _legacy()
    usuario = legacy.get_usuario_logado()
    imovel = _repo().buscar_por_id_ou_404(id)
    legacy._padronizar_negocio_imovel(imovel)

    imovel.visualizacoes = (imovel.visualizacoes or 0) + 1
    _repo().commit()

    descricao_base = (imovel.descricao or '').strip()
    if not descricao_base:
        descricao_base = f"{imovel.tipo} em {imovel.cidade}/{imovel.estado}, no bairro {imovel.bairro}."
    descricao_meta = f"{descricao_base[:140]} | Preço: R$ {legacy.moeda_brl(imovel.preco)}"

    foto_preview = legacy._resolver_foto_preview(imovel)
    marca_tempo = int((imovel.atualizado_em or imovel.criado_em).timestamp())
    separador = '&' if '?' in foto_preview else '?'
    foto_preview = f"{foto_preview}{separador}v={marca_tempo}"

    titulo_imovel = f"{imovel.tipo} em {imovel.cidade} - Radar Imoveis Pro"
    canonical_imovel = legacy._url_publica('detalhe_imovel', id=imovel.id)
    data_publicacao = (imovel.criado_em or imovel.atualizado_em)

    seo_json_ld_list = [
        {
            '@context': 'https://schema.org',
            '@type': 'RealEstateListing',
            'name': titulo_imovel,
            'description': descricao_meta,
            'url': canonical_imovel,
            'datePosted': data_publicacao.isoformat() if data_publicacao else None,
            'image': [foto_preview],
            'offers': {
                '@type': 'Offer',
                'price': float(imovel.preco or 0),
                'priceCurrency': 'BRL',
                'availability': 'https://schema.org/InStock',
            },
            'address': {
                '@type': 'PostalAddress',
                'streetAddress': imovel.bairro,
                'addressLocality': imovel.cidade,
                'addressRegion': imovel.estado,
                'addressCountry': 'BR',
            },
        },
        {
            '@context': 'https://schema.org',
            '@type': 'BreadcrumbList',
            'itemListElement': [
                {
                    '@type': 'ListItem',
                    'position': 1,
                    'name': 'Inicio',
                    'item': legacy._url_publica('index'),
                },
                {
                    '@type': 'ListItem',
                    'position': 2,
                    'name': 'Imovel',
                    'item': canonical_imovel,
                },
            ],
        },
    ]

    return render_template(
        'detalhe_imovel.html',
        imovel=imovel,
        usuario=usuario,
        descricao_meta=descricao_meta,
        foto_preview=foto_preview,
        seo_title=titulo_imovel,
        seo_description=descricao_meta,
        seo_canonical_url=canonical_imovel,
        seo_og_type='article',
        seo_og_image=foto_preview,
        seo_json_ld_list=seo_json_ld_list,
    )


@imoveis_bp.route('/deletar-imovel/<int:id>', methods=['POST'])
def deletar_imovel(id):
    """Deleta um anuncio (apenas o dono pode)."""
    legacy = _legacy()
    usuario = legacy.get_usuario_logado()

    if not usuario:
        flash('Você precisa estar logado!', 'error')
        return redirect(url_for('login'))

    imovel = _repo().buscar_por_id_ou_404(id)

    if imovel.usuario_id != usuario.id:
        flash('Você não tem permissão para deletar este anúncio!', 'error')
        return redirect(url_for('index'))

    try:
        if imovel.foto and not legacy._foto_eh_url(imovel.foto):
            caminho_foto = legacy.os.path.join(legacy.app.config['UPLOAD_FOLDER'], imovel.foto)
            if legacy.os.path.exists(caminho_foto):
                legacy.os.remove(caminho_foto)

        _repo().deletar(imovel)

        flash('Anúncio deletado com sucesso!', 'success')
    except Exception as e:
        _repo().rollback()
        flash(f'Erro ao deletar: {str(e)}', 'error')

    return redirect(url_for('meus_anuncios'))


@imoveis_bp.route('/editar-imovel/<int:id>', methods=['GET', 'POST'])
def editar_imovel(id):
    """Edita um anuncio (apenas o dono pode)."""
    legacy = _legacy()
    usuario = legacy.get_usuario_logado()

    if not usuario:
        flash('Você precisa estar logado!', 'error')
        return redirect(url_for('login'))

    imovel = _repo().buscar_por_id_ou_404(id)

    if imovel.usuario_id != usuario.id:
        flash('Você não tem permissão para editar este anúncio!', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        try:
            f = request.form

            campos_obrigatorios = ['estado', 'cidade', 'bairro', 'tipo', 'negocio', 'valor']
            for campo in campos_obrigatorios:
                if not f.get(campo):
                    flash(f'Campo obrigatório não preenchido: {campo}', 'error')
                    return redirect(url_for('editar_imovel', id=id))

            try:
                preco = float(f.get('valor').replace('R$', '').replace('.', '').replace(',', '.').strip())
            except Exception:
                flash('Preço inválido!', 'error')
                return redirect(url_for('editar_imovel', id=id))

            arq = request.files.get('foto')
            if arq and arq.filename:
                if legacy.allowed_file(arq.filename):
                    if imovel.foto and not legacy._foto_eh_url(imovel.foto):
                        caminho_foto = legacy.os.path.join(legacy.app.config['UPLOAD_FOLDER'], imovel.foto)
                        if legacy.os.path.exists(caminho_foto):
                            legacy.os.remove(caminho_foto)

                    nome_foto, sucesso = legacy.processar_imagem(arq)
                    if sucesso and nome_foto:
                        imovel.foto = nome_foto

            quartos = int(f.get('quartos', 0)) if f.get('quartos') else None
            vagas = int(f.get('vagas', 0)) if f.get('vagas') else None
            area = float(f.get('area', 0)) if f.get('area') else None

            imovel.estado = f.get('estado')
            imovel.cidade = f.get('cidade')
            imovel.bairro = f.get('bairro')
            imovel.tipo = f.get('tipo')
            imovel.negocio = legacy._negocio_canonico(f.get('negocio'))
            imovel.quartos = quartos
            imovel.vagas = vagas
            imovel.area = area
            imovel.preco = preco

            # ✅ VALIDAÇÃO E SANITIZAÇÃO DE DESCRIÇÃO (XSS Protection)
            descricao_raw = f.get('descricao', '').strip()
            try:
                if descricao_raw:
                    schema_data = ImovelDescricaoSchema(descricao=descricao_raw)
                    imovel.descricao = sanitizar_descricao(schema_data.descricao)
                else:
                    imovel.descricao = ''
            except ValidationError as e:
                erros = ', '.join([f"{err['loc'][0]}: {err['msg']}" for err in e.errors()])
                flash(f'Descrição inválida: {erros}', 'error')
                return redirect(url_for('editar_imovel', id=id))

            _repo().commit()

            flash('Anúncio atualizado com sucesso!', 'success')
            return redirect(url_for('meus_anuncios'))

        except Exception as e:
            _repo().rollback()
            flash(f'Erro ao atualizar anúncio: {str(e)}', 'error')
            return redirect(url_for('editar_imovel', id=id))

    legacy._padronizar_negocio_imovel(imovel)
    return render_template('editar_imovel.html', imovel=imovel, usuario=usuario)


@imoveis_bp.route('/avaliar-anunciante/<int:usuario_id>', methods=['GET', 'POST'])
def avaliar_anunciante(usuario_id):
    """Avalia um anunciante."""
    legacy = _legacy()
    usuario_logado = legacy.get_usuario_logado()

    if not usuario_logado:
        flash('Você precisa estar logado!', 'error')
        return redirect(url_for('login'))

    anunciante = _avaliacao_repo().buscar_usuario_por_id_ou_404(usuario_id)

    if request.method == 'POST':
        try:
            estrelas = int(request.form.get('estrelas', 5))
            comentario = request.form.get('comentario', '').strip()
            imovel_id = request.form.get('imovel_id', type=int)

            try:
                payload = AvaliacaoSchema(estrelas=estrelas, comentario=comentario)
            except ValidationError as e:
                erros = ', '.join([f"{err['loc'][0]}: {err['msg']}" for err in e.errors()])
                flash(f'Validação falhou: {erros}', 'error')
                return redirect(url_for('avaliar_anunciante', usuario_id=usuario_id, imovel_id=imovel_id))

            comentario_sanitizado = sanitizar_mensagem_chat(payload.comentario)

            avaliacao = Avaliacao(
                usuario_id=usuario_id,
                imovel_id=imovel_id,
                avaliador_id=usuario_logado.id,
                estrelas=payload.estrelas,
                comentario=comentario_sanitizado,
            )

            _avaliacao_repo().salvar(avaliacao)

            flash('Avaliação enviada com sucesso!', 'success')
            return redirect(url_for('detalhe_imovel', id=imovel_id) if imovel_id else url_for('index', aba='buscar'))

        except Exception as e:
            _avaliacao_repo().rollback()
            flash(f'Erro ao enviar avaliação: {str(e)}', 'error')

    imovel_id = request.args.get('imovel_id')
    imovel = None
    if imovel_id:
        imovel = _repo().buscar_por_id(imovel_id)
        legacy._padronizar_negocio_imovel(imovel)

    return render_template(
        'avaliar.html',
        usuario=usuario_logado,
        anunciante=anunciante,
        imovel=imovel,
    )


@imoveis_bp.route('/imovel/<int:id>/adicionar-fotos', methods=['GET', 'POST'])
def adicionar_fotos(id):
    """Adiciona múltiplas fotos a um imóvel."""
    legacy = _legacy()
    usuario = legacy.get_usuario_logado()

    if not usuario:
        flash('Você precisa estar logado!', 'error')
        return redirect(url_for('login'))

    imovel = _repo().buscar_por_id_ou_404(id)
    legacy._padronizar_negocio_imovel(imovel)

    if imovel.usuario_id != usuario.id:
        flash('Você não tem permissão!', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        files = request.files.getlist('fotos')

        if not files:
            flash('Selecione pelo menos uma foto!', 'error')
            return redirect(url_for('adicionar_fotos', id=id))

        try:
            novas_fotos = []
            for arq in files:
                if arq and legacy.allowed_file(arq.filename):
                    nome_arquivo, sucesso = legacy.processar_imagem(arq)
                    if sucesso and nome_arquivo:
                        novas_fotos.append(FotoImovel(
                            imovel_id=id,
                            arquivo=nome_arquivo,
                            ordem=len(imovel.fotos) + len(novas_fotos),
                        ))

            _repo().adicionar_fotos(novas_fotos)
            flash(f'{len(novas_fotos)} foto(s) adicionada(s) com sucesso!', 'success')

        except Exception as e:
            _repo().rollback()
            flash(f'Erro ao adicionar fotos: {str(e)}', 'error')

        return redirect(url_for('detalhe_imovel', id=id))

    return render_template('adicionar_fotos.html', usuario=usuario, imovel=imovel)