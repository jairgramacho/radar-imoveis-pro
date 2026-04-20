"""Blueprint de chat entre usuarios."""

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, session, url_for

from email_utils import enviar_email_nova_mensagem
from models import Imovel, Mensagem, Usuario, db


chat_bp = Blueprint('chat', __name__)


def _usuario_logado_atual():
    usuario_id = session.get('usuario_id')
    if usuario_id:
        return Usuario.query.get(usuario_id)
    return None


@chat_bp.route('/chat')
def chat():
    """Inbox de conversas com painel da conversa selecionada."""
    usuario = _usuario_logado_atual()

    if not usuario:
        flash('Voce precisa estar logado!', 'error')
        return redirect(url_for('login'))

    mensagens_usuario = Mensagem.query.filter(
        (Mensagem.remetente_id == usuario.id) | (Mensagem.destinatario_id == usuario.id)
    ).order_by(Mensagem.criado_em.desc()).all()

    conversas = {}

    for msg in mensagens_usuario:
        if msg.destinatario_id == usuario.id:
            outro_usuario = msg.remetente
        else:
            outro_usuario = msg.destinatario

        chave = (outro_usuario.id, msg.imovel_id)
        if chave not in conversas:
            conversas[chave] = {
                'outro_usuario': outro_usuario,
                'imovel': msg.imovel,
                'imovel_id': msg.imovel_id,
                'ultima_msg': msg,
                'nao_lidas': 0,
            }

        if msg.destinatario_id == usuario.id and not msg.lida:
            conversas[chave]['nao_lidas'] += 1

    conversas_lista = sorted(conversas.values(), key=lambda x: x['ultima_msg'].criado_em, reverse=True)

    usuario_id_selecionado = request.args.get('usuario_id', type=int)
    imovel_id_param = request.args.get('imovel_id', '').strip().lower()
    imovel_id_selecionado = None
    if imovel_id_param and imovel_id_param not in {'none', 'null'}:
        try:
            imovel_id_selecionado = int(imovel_id_param)
        except ValueError:
            imovel_id_selecionado = None

    conversa_ativa = None
    mensagens_ativas = []

    if usuario_id_selecionado:
        for conversa in conversas_lista:
            if conversa['outro_usuario'].id != usuario_id_selecionado:
                continue

            if imovel_id_param:
                if conversa['imovel_id'] == imovel_id_selecionado:
                    conversa_ativa = conversa
                    break
                continue

            conversa_ativa = conversa
            break

    if not conversa_ativa and conversas_lista:
        conversa_ativa = conversas_lista[0]

    if conversa_ativa:
        mensagens_query = Mensagem.query.filter(
            ((Mensagem.remetente_id == usuario.id) & (Mensagem.destinatario_id == conversa_ativa['outro_usuario'].id)) |
            ((Mensagem.remetente_id == conversa_ativa['outro_usuario'].id) & (Mensagem.destinatario_id == usuario.id))
        )

        if conversa_ativa['imovel_id'] is None:
            mensagens_query = mensagens_query.filter(Mensagem.imovel_id.is_(None))
        else:
            mensagens_query = mensagens_query.filter(Mensagem.imovel_id == conversa_ativa['imovel_id'])

        mensagens_ativas = mensagens_query.order_by(Mensagem.criado_em.asc()).all()

        alterou_leitura = False
        for msg in mensagens_ativas:
            if msg.destinatario_id == usuario.id and not msg.lida:
                msg.lida = True
                alterou_leitura = True
        if alterou_leitura:
            db.session.commit()

        conversa_ativa['nao_lidas'] = 0

    return render_template(
        'chat.html',
        usuario=usuario,
        conversas=conversas_lista,
        conversa_ativa=conversa_ativa,
        mensagens_ativas=mensagens_ativas,
    )


@chat_bp.route('/chat/<int:usuario_id>')
def conversa(usuario_id):
    """Compatibilidade: redireciona conversa para o inbox em /chat."""
    return redirect(url_for('chat.chat', usuario_id=usuario_id))


@chat_bp.route('/enviar-mensagem/<int:usuario_id>', methods=['POST'])
def enviar_mensagem(usuario_id):
    """Envia uma mensagem para outro usuario."""
    usuario = _usuario_logado_atual()

    if not usuario:
        flash('Voce precisa estar logado!', 'error')
        return redirect(url_for('login'))

    Usuario.query.get_or_404(usuario_id)

    imovel_id = request.form.get('imovel_id', type=int)
    if imovel_id and not Imovel.query.get(imovel_id):
        imovel_id = None
    texto = request.form.get('mensagem', '').strip()

    if not texto:
        flash('Mensagem nao pode estar vazia!', 'error')
        return redirect(url_for('chat.chat', usuario_id=usuario_id))

    try:
        msg = Mensagem(
            remetente_id=usuario.id,
            destinatario_id=usuario_id,
            imovel_id=imovel_id,
            titulo=f"Mensagem de {usuario.nome}",
            mensagem=texto
        )

        db.session.add(msg)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao enviar mensagem: {str(e)}', 'error')

    return redirect(url_for('chat.chat', usuario_id=usuario_id, imovel_id=imovel_id))


@chat_bp.route('/api/conversa/<int:usuario_id>', methods=['GET'])
def api_conversa(usuario_id):
    """Retorna mensagens da conversa em JSON e marca mensagens recebidas como lidas."""
    usuario = _usuario_logado_atual()
    if not usuario:
        return jsonify({'ok': False, 'erro': 'nao_autenticado'}), 401

    Usuario.query.get_or_404(usuario_id)

    imovel_id_param = request.args.get('imovel_id', '').strip().lower()
    imovel_id = None
    if imovel_id_param and imovel_id_param not in {'none', 'null'}:
        try:
            imovel_id = int(imovel_id_param)
        except ValueError:
            return jsonify({'ok': False, 'erro': 'imovel_invalido'}), 400

    mensagens_query = Mensagem.query.filter(
        ((Mensagem.remetente_id == usuario.id) & (Mensagem.destinatario_id == usuario_id)) |
        ((Mensagem.remetente_id == usuario_id) & (Mensagem.destinatario_id == usuario.id))
    )

    if imovel_id is None:
        mensagens_query = mensagens_query.filter(Mensagem.imovel_id.is_(None))
    else:
        mensagens_query = mensagens_query.filter(Mensagem.imovel_id == imovel_id)

    mensagens = mensagens_query.order_by(Mensagem.criado_em.asc()).all()

    alterou_leitura = False
    for msg in mensagens:
        if msg.destinatario_id == usuario.id and not msg.lida:
            msg.lida = True
            alterou_leitura = True

    if alterou_leitura:
        db.session.commit()

    payload = []
    for msg in mensagens:
        payload.append({
            'id': msg.id,
            'mensagem': msg.mensagem,
            'enviada_por_mim': msg.remetente_id == usuario.id,
            'lida': bool(msg.lida),
            'hora': msg.criado_em.strftime('%H:%M'),
            'data': msg.criado_em.strftime('%d/%m/%Y %H:%M'),
        })

    return jsonify({'ok': True, 'mensagens': payload})


@chat_bp.route('/api/enviar-mensagem/<int:usuario_id>', methods=['POST'])
def api_enviar_mensagem(usuario_id):
    """Envia mensagem em JSON para o mini chat."""
    usuario = _usuario_logado_atual()
    if not usuario:
        return jsonify({'ok': False, 'erro': 'nao_autenticado'}), 401

    if usuario.id == usuario_id:
        return jsonify({'ok': False, 'erro': 'destinatario_invalido'}), 400

    Usuario.query.get_or_404(usuario_id)

    texto = ''
    imovel_id = None
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        texto = (payload.get('mensagem') or '').strip()
        imovel_id = payload.get('imovel_id')
    else:
        texto = request.form.get('mensagem', '').strip()
        imovel_id = request.form.get('imovel_id')

    if imovel_id in {'', None, 'none', 'null'}:
        imovel_id = None
    elif isinstance(imovel_id, str):
        try:
            imovel_id = int(imovel_id)
        except ValueError:
            return jsonify({'ok': False, 'erro': 'imovel_invalido'}), 400

    if imovel_id and not Imovel.query.get(imovel_id):
        return jsonify({'ok': False, 'erro': 'imovel_invalido'}), 400

    if not texto:
        return jsonify({'ok': False, 'erro': 'mensagem_vazia'}), 400

    try:
        msg = Mensagem(
            remetente_id=usuario.id,
            destinatario_id=usuario_id,
            imovel_id=imovel_id,
            titulo=f"Mensagem de {usuario.nome}",
            mensagem=texto,
        )
        db.session.add(msg)
        db.session.commit()

        destinatario = Usuario.query.get(usuario_id)
        if destinatario and destinatario.email:
            imovel_tipo = ''
            if imovel_id:
                imovel = Imovel.query.get(imovel_id)
                if imovel:
                    imovel_tipo = imovel.tipo

            contact_email = current_app.config.get('CONTACT_EMAIL', 'contato@radarimoveispro.com.br')
            enviar_email_nova_mensagem(
                destinatario.email,
                usuario.nome,
                imovel_tipo,
                from_email_override=contact_email
            )

        return jsonify({'ok': True, 'id': msg.id})
    except Exception as e:
        db.session.rollback()
        current_app.logger.warning('Erro ao enviar mensagem via API: %s', str(e), exc_info=True)
        return jsonify({'ok': False, 'erro': 'falha_envio'}), 500