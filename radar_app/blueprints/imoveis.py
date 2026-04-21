"""Blueprint para operacoes de imoveis."""

from flask import Blueprint, render_template, request, redirect, flash, url_for

from models import Avaliacao, FotoImovel, Imovel, Usuario


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
            descricao=f.get('descricao', ''),
            foto=nome_foto_principal,
        )

        legacy.db.session.add(imovel)
        legacy.db.session.commit()

        for idx, arq in enumerate(arquivos[1:], start=1):
            if arq and legacy.allowed_file(arq.filename):
                nome_arquivo, sucesso = legacy.processar_imagem(arq)

                if sucesso and nome_arquivo:
                    foto = FotoImovel(
                        imovel_id=imovel.id,
                        arquivo=nome_arquivo,
                        ordem=idx,
                    )
                    legacy.db.session.add(foto)

        legacy.db.session.commit()

        flash('Anúncio publicado com sucesso! Você pode adicionar mais fotos se desejar.', 'success')
        return redirect(url_for('detalhe_imovel', id=imovel.id))

    except Exception as e:
        legacy.db.session.rollback()
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


@imoveis_bp.route('/deletar-imovel/<int:id>', methods=['POST'])
def deletar_imovel(id):
    """Deleta um anuncio (apenas o dono pode)."""
    legacy = _legacy()
    usuario = legacy.get_usuario_logado()

    if not usuario:
        flash('Você precisa estar logado!', 'error')
        return redirect(url_for('login'))

    imovel = Imovel.query.get_or_404(id)

    if imovel.usuario_id != usuario.id:
        flash('Você não tem permissão para deletar este anúncio!', 'error')
        return redirect(url_for('index'))

    try:
        if imovel.foto and not legacy._foto_eh_url(imovel.foto):
            caminho_foto = legacy.os.path.join(legacy.app.config['UPLOAD_FOLDER'], imovel.foto)
            if legacy.os.path.exists(caminho_foto):
                legacy.os.remove(caminho_foto)

        legacy.db.session.delete(imovel)
        legacy.db.session.commit()

        flash('Anúncio deletado com sucesso!', 'success')
    except Exception as e:
        legacy.db.session.rollback()
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

    imovel = Imovel.query.get_or_404(id)

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
            imovel.descricao = f.get('descricao', '')

            legacy.db.session.commit()

            flash('Anúncio atualizado com sucesso!', 'success')
            return redirect(url_for('meus_anuncios'))

        except Exception as e:
            legacy.db.session.rollback()
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

    anunciante = Usuario.query.get_or_404(usuario_id)

    if request.method == 'POST':
        try:
            estrelas = int(request.form.get('estrelas', 5))
            comentario = request.form.get('comentario', '').strip()
            imovel_id = request.form.get('imovel_id')

            if estrelas < 1 or estrelas > 5:
                flash('Avaliação deve ser entre 1 e 5 estrelas!', 'error')
                return redirect(url_for('avaliar_anunciante', usuario_id=usuario_id))

            avaliacao = Avaliacao(
                usuario_id=usuario_id,
                imovel_id=imovel_id,
                avaliador_id=usuario_logado.id,
                estrelas=estrelas,
                comentario=comentario,
            )

            legacy.db.session.add(avaliacao)
            legacy.db.session.commit()

            flash('Avaliação enviada com sucesso!', 'success')
            return redirect(url_for('detalhe_imovel', id=imovel_id) if imovel_id else url_for('index', aba='buscar'))

        except Exception as e:
            legacy.db.session.rollback()
            flash(f'Erro ao enviar avaliação: {str(e)}', 'error')

    imovel_id = request.args.get('imovel_id')
    imovel = None
    if imovel_id:
        imovel = Imovel.query.get(imovel_id)
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

    imovel = Imovel.query.get_or_404(id)
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
            for arq in files:
                if arq and legacy.allowed_file(arq.filename):
                    nome_arquivo, sucesso = legacy.processar_imagem(arq)

                    if sucesso and nome_arquivo:
                        foto = FotoImovel(
                            imovel_id=id,
                            arquivo=nome_arquivo,
                            ordem=len(imovel.fotos),
                        )
                        legacy.db.session.add(foto)

            legacy.db.session.commit()
            flash(f'{len(files)} foto(s) adicionada(s) com sucesso!', 'success')

        except Exception as e:
            legacy.db.session.rollback()
            flash(f'Erro ao adicionar fotos: {str(e)}', 'error')

        return redirect(url_for('detalhe_imovel', id=id))

    return render_template('adicionar_fotos.html', usuario=usuario, imovel=imovel)