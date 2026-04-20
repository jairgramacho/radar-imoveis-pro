from flask import Blueprint, flash, redirect, render_template, request, url_for

public_bp = Blueprint('public', __name__)


def _usuario_logado_atual():
    # Import local evita acoplamento circular no bootstrap do app.
    from radar_app.legacy_app import get_usuario_logado

    return get_usuario_logado()


@public_bp.route('/termos-de-uso')
def termos_uso():
    """Pagina de termos de uso."""
    usuario = _usuario_logado_atual()
    return render_template('termos_uso.html', usuario=usuario)


@public_bp.route('/politica-de-privacidade')
def politica_privacidade():
    """Pagina de politica de privacidade."""
    usuario = _usuario_logado_atual()
    return render_template('politica_privacidade.html', usuario=usuario)


@public_bp.route('/denunciar-abuso', methods=['GET', 'POST'])
def denunciar_abuso():
    """Pagina de denuncia de abuso."""
    usuario = _usuario_logado_atual()

    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        email = request.form.get('email', '').strip()
        motivo = request.form.get('motivo', '').strip()
        mensagem = request.form.get('mensagem', '').strip()

        if not all([nome, email, motivo, mensagem]):
            flash('Preencha todos os campos para enviar a denuncia.', 'error')
            return redirect(url_for('public.denunciar_abuso'))

        flash('Denuncia recebida com sucesso. Nossa equipe ira analisar o caso.', 'success')
        return redirect(url_for('public.denunciar_abuso'))

    return render_template('denunciar_abuso.html', usuario=usuario)


@public_bp.route('/faq-ajuda')
def faq_ajuda():
    """Pagina de FAQ e ajuda."""
    usuario = _usuario_logado_atual()
    return render_template('faq_ajuda.html', usuario=usuario)
