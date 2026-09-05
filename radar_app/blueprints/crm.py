"""CRM nativo do Radar Imoveis Pro."""

import secrets
from datetime import datetime
from urllib.parse import quote

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from models import CRMLead, CRMLeadHistorico, Imovel, Usuario, db
from radar_app.auth import UsuarioRepository
from radar_app.imoveis import ImovelRepository


crm_bp = Blueprint('crm', __name__)

ETAPAS_CRM = ['novo', 'contato', 'visita', 'proposta', 'fechado', 'perdido']
MOTIVOS_PERDA = ['preco', 'documentacao', 'financiamento', 'desistencia', 'imovel_indisponivel', 'outro']


def _usuario_repo():
    return UsuarioRepository(db, Usuario)


def _imovel_repo():
    return ImovelRepository(db, Imovel)


def _usuario_logado():
    usuario_id = session.get('usuario_id')
    if usuario_id:
        return _usuario_repo().buscar_por_id(usuario_id)
    return None


def _eh_admin(usuario):
    return bool(usuario and getattr(usuario, 'is_admin', False))


def _visitor_key():
    chave = session.get('crm_visitor_key')
    if not chave:
        chave = secrets.token_urlsafe(16)
        session['crm_visitor_key'] = chave
    return chave


def _limpar_whatsapp(whatsapp):
    return ''.join(ch for ch in (whatsapp or '') if ch.isdigit())


def _codigo_lead(lead_id):
    return f'RLP-{lead_id:06d}'


def _registrar_historico(lead, acao, usuario=None, de_status=None, para_status=None, nota=None):
    historico = CRMLeadHistorico(
        lead=lead,
        usuario_id=getattr(usuario, 'id', None),
        acao=acao,
        de_status=de_status,
        para_status=para_status,
        nota=nota,
    )
    db.session.add(historico)
    return historico


def _obter_ou_criar_lead(imovel, anunciante, usuario=None, origem='whatsapp', origem_url=None):
    agora = datetime.utcnow()
    visitante = _visitor_key()

    lead = None
    if usuario:
        lead = CRMLead.query.filter_by(
            anunciante_id=anunciante.id,
            imovel_id=imovel.id,
            interessado_usuario_id=usuario.id,
        ).order_by(CRMLead.criado_em.desc()).first()

    if lead is None:
        lead = CRMLead.query.filter_by(
            anunciante_id=anunciante.id,
            imovel_id=imovel.id,
            visitor_key=visitante,
        ).order_by(CRMLead.criado_em.desc()).first()

    if lead is None:
        lead = CRMLead(
            codigo='tmp',
            anunciante_id=anunciante.id,
            imovel_id=imovel.id,
            interessado_usuario_id=getattr(usuario, 'id', None),
            origem=origem,
            status='novo',
            # NÃO grava o número do anunciante como beingdo o lead (evita lead fantasma).
            # O whatsapp real do interessado é capturado via formulário (POST).
            whatsapp=None,
            origem_url=origem_url,
            visitor_key=visitante,
            ultima_interacao_em=agora,
        )
        db.session.add(lead)
        db.session.flush()
        lead.codigo = _codigo_lead(lead.id)
        _registrar_historico(lead, 'criado', usuario=usuario, para_status='novo', nota=f'Origem {origem}')
        return lead

    lead.interessado_usuario_id = lead.interessado_usuario_id or getattr(usuario, 'id', None)
    lead.origem = lead.origem or origem
    lead.visitor_key = lead.visitor_key or visitante
    lead.ultima_interacao_em = agora
    if origem_url and not lead.origem_url:
        lead.origem_url = origem_url
    return lead


def registrar_interacao_chat(usuario_origem, usuario_destino, imovel, mensagem):
    if not usuario_origem or not usuario_destino or not imovel:
        return None

    lead = _obter_ou_criar_lead(
        imovel=imovel,
        anunciante=usuario_destino,
        usuario=usuario_origem,
        origem='chat',
        origem_url=url_for('detalhe_imovel', id=imovel.id, _external=True),
    )
    if lead.primeiro_contato_em is None:
        lead.primeiro_contato_em = datetime.utcnow()
    _registrar_historico(lead, 'mensagem_chat', usuario=usuario_origem, nota='Mensagem enviada no chat interno')
    return lead


@crm_bp.route('/crm/whatsapp/<int:imovel_id>', methods=['GET', 'POST'])
def rastrear_whatsapp(imovel_id):
    imovel = _imovel_repo().buscar_por_id_ou_404(imovel_id)
    anunciante = imovel.anunciante

    if not anunciante or not anunciante.whatsapp:
        flash('Este anúncio não possui WhatsApp configurado.', 'error')
        return redirect(url_for('detalhe_imovel', id=imovel.id))

    usuario = _usuario_logado()
    origem_url = url_for('detalhe_imovel', id=imovel.id, _external=True)

    if request.method == 'POST':
        # Captura o dado REAL do interessado (nome + whatsapp informados no modal),
        # em vez de gravar o número do anunciante (que poluia o CRM com leads fantasma).
        nome = (request.form.get('nome') or '').strip()[:120]
        whatsapp = _limpar_whatsapp(request.form.get('whatsapp') or '')

        lead = _obter_ou_criar_lead(
            imovel=imovel,
            anunciante=anunciante,
            usuario=usuario,
            origem='whatsapp',
            origem_url=origem_url,
        )
        if nome:
            lead.nome = nome
        if whatsapp:
            lead.whatsapp = whatsapp
        if lead.primeiro_contato_em is None:
            lead.primeiro_contato_em = datetime.utcnow()
        lead.ultima_interacao_em = datetime.utcnow()
        _registrar_historico(
            lead,
            'whatsapp_click',
            usuario=usuario,
            nota=f'Interessado: {nome or "(sem nome)"} - {whatsapp or "(sem whatsapp)"}',
        )
        db.session.commit()

        cumprimento = nome.split(' ')[0] if nome else ''
        mensagem = f'Olá{(", " + cumprimento) if cumprimento else ""}! Vi seu anúncio de {imovel.tipo} em {imovel.cidade} no Radar Imóveis Pro e quero saber mais. Código: {_codigo_lead(lead.id)}.'
        destino = _limpar_whatsapp(anunciante.whatsapp)
        return redirect(f'https://wa.me/55{destino}?text={quote(mensagem)}')

    # GET (clique direto, sem o modal) — mantém o comportamento antigo, mas sem poluir:
    # registra a interação apenas, sem sobrescrever com o número do anunciante.
    lead = _obter_ou_criar_lead(
        imovel=imovel,
        anunciante=anunciante,
        usuario=usuario,
        origem='whatsapp',
        origem_url=origem_url,
    )
    if lead.whatsapp is None or lead.whatsapp == _limpar_whatsapp(anunciante.whatsapp):
        # Não grava o número do corretor como sendo do lead; deixa aberto p/ captura real.
        lead.whatsapp = None
    lead.ultima_interacao_em = datetime.utcnow()
    _registrar_historico(lead, 'whatsapp_click', usuario=usuario, nota='Clique no botão de WhatsApp (sem captura de contato)')
    db.session.commit()

    mensagem = (
        f'Olá, vi seu anúncio de {imovel.tipo} em {imovel.cidade} no Radar Imóveis Pro. '
        f'Código do lead: {_codigo_lead(lead.id)}. '
        f'Anúncio: {origem_url}'
    )
    destino = _limpar_whatsapp(anunciante.whatsapp)
    return redirect(f'https://wa.me/55{destino}?text={quote(mensagem)}')


@crm_bp.route('/crm')
def crm_dashboard():
    usuario = _usuario_logado()
    if not usuario:
        flash('Você precisa estar logado!', 'error')
        return redirect(url_for('login'))

    now = datetime.utcnow()

    consulta = CRMLead.query
    if not _eh_admin(usuario):
        consulta = consulta.filter_by(anunciante_id=usuario.id)

    leads = consulta.order_by(CRMLead.ultima_interacao_em.desc().nullslast(), CRMLead.criado_em.desc()).all()
    agora = datetime.utcnow()
    resumo = {
        'total': len(leads),
        'novo': sum(1 for lead in leads if lead.status == 'novo'),
        'em_andamento': sum(1 for lead in leads if lead.status in {'contato', 'visita', 'proposta'}),
        'fechado': sum(1 for lead in leads if lead.status == 'fechado'),
        'perdido': sum(1 for lead in leads if lead.status == 'perdido'),
        'pendencias': sum(1 for lead in leads if lead.proxima_acao_em and lead.proxima_acao_em <= agora and lead.status not in {'fechado', 'perdido'}),
    }

    # Imóveis do usuário para o cadastro manual de lead
    imoveis_do_usuario = _imovel_repo().listar_por_usuario(usuario.id)
    origens_dev = ['instagram', 'whatsapp', 'olx', 'indicacao', 'site', 'manual']

    return render_template(
        'crm_dashboard.html',
        usuario=usuario,
        leads=leads,
        resumo=resumo,
        etapas=ETAPAS_CRM,
        motivos_perda=MOTIVOS_PERDA,
        imoveis_do_usuario=imoveis_do_usuario,
        origens_dev=origens_dev,
        now=now,
    )


@crm_bp.route('/crm/leads/novo', methods=['POST'])
def criar_lead_manual():
    """Cria um lead manualmente (captação por Instagram, WhatsApp direto, OLX, indicação etc.)."""
    usuario = _usuario_logado()
    if not usuario:
        flash('Você precisa estar logado!', 'error')
        return redirect(url_for('login'))

    nome = (request.form.get('nome') or '').strip()[:120]
    whatsapp = _limpar_whatsapp(request.form.get('whatsapp') or '')
    origem = ((request.form.get('origem') or 'manual').strip().lower() or 'manual')[:20]
    observacoes = (request.form.get('observacoes') or '').strip()
    imovel_id_raw = (request.form.get('imovel_id') or '').strip()

    if not nome and not whatsapp:
        flash('Informe ao menos o nome ou o WhatsApp do contato.', 'error')
        return redirect(url_for('crm.crm_dashboard'))

    imovel = None
    if imovel_id_raw.isdigit():
        imovel = _imovel_repo().buscar_por_id(int(imovel_id_raw))
        # Só aceita imóvel que pertença ao usuário logado (ou admin)
        if imovel and not _eh_admin(usuario) and imovel.usuario_id != usuario.id:
            imovel = None

    agora = datetime.utcnow()
    lead = CRMLead(
        codigo='tmp',
        anunciante_id=usuario.id,
        imovel_id=imovel.id if imovel else None,
        origem=origem,
        status='novo',
        nome=nome or None,
        whatsapp=whatsapp or None,
        observacoes=observacoes or None,
        primeiro_contato_em=agora,
        ultima_interacao_em=agora,
    )
    db.session.add(lead)
    db.session.flush()
    lead.codigo = _codigo_lead(lead.id)
    _registrar_historico(lead, 'criado', usuario=usuario, para_status='novo', nota=f'Cadastro manual (origem {origem})"')
    db.session.commit()

    flash(f'Lead {lead.codigo} cadastrado com sucesso!', 'success')
    return redirect(url_for('crm.crm_dashboard'))


@crm_bp.route('/crm/leads/<int:lead_id>/status', methods=['POST'])
def atualizar_lead_status(lead_id):
    usuario = _usuario_logado()
    if not usuario:
        flash('Você precisa estar logado!', 'error')
        return redirect(url_for('login'))

    lead = db.session.get(CRMLead, lead_id)
    if not lead:
        flash('Lead não encontrado.', 'error')
        return redirect(url_for('crm.crm_dashboard'))

    if not _eh_admin(usuario) and lead.anunciante_id != usuario.id:
        flash('Você não tem permissão para alterar este lead.', 'error')
        return redirect(url_for('crm.crm_dashboard'))

    status_anterior = lead.status
    novo_status = (request.form.get('status') or lead.status).strip().lower()
    if novo_status not in ETAPAS_CRM:
        novo_status = lead.status

    lead.status = novo_status
    lead.observacoes = (request.form.get('observacoes') or lead.observacoes or '').strip() or None
    proxima_acao_em_raw = (request.form.get('proxima_acao_em') or '').strip()
    if proxima_acao_em_raw:
        try:
            lead.proxima_acao_em = datetime.fromisoformat(proxima_acao_em_raw)
        except ValueError:
            lead.proxima_acao_em = None
    else:
        lead.proxima_acao_em = None

    perda_motivo = (request.form.get('perda_motivo') or '').strip().lower()
    lead.perda_motivo = perda_motivo if perda_motivo in MOTIVOS_PERDA else None
    if novo_status == 'contato' and lead.primeiro_contato_em is None:
        lead.primeiro_contato_em = datetime.utcnow()
    lead.status_alterado_em = datetime.utcnow()
    lead.ultima_interacao_em = datetime.utcnow()

    _registrar_historico(
        lead,
        'status',
        usuario=usuario,
        de_status=status_anterior,
        para_status=novo_status,
        nota=lead.observacoes,
    )
    db.session.commit()
    flash('Lead atualizado com sucesso.', 'success')
    return redirect(url_for('crm.crm_dashboard'))