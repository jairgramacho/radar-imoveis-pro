import re
from pathlib import Path

import pytest

from app import create_app
from models import Usuario, db


@pytest.fixture
def csrf_app():
    flask_app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'WTF_CSRF_ENABLED': True,
        'SESSION_COOKIE_SECURE': False,
    })

    with flask_app.app_context():
        db.drop_all()
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def csrf_client(csrf_app):
    return csrf_app.test_client()


def test_login_renderiza_input_hidden_csrf(csrf_client):
    response = csrf_client.get('/login')
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert '<input type="hidden" name="csrf_token" value="' in html



def test_login_post_com_csrf_valido_redireciona(csrf_client, csrf_app):
    with csrf_app.app_context():
        usuario = Usuario(
            nome='Teste CSRF',
            email='csrf-login@example.com',
            whatsapp='11999998888',
            email_confirmado=True,
        )
        usuario.set_password('abc12345')
        db.session.add(usuario)
        db.session.commit()

    html = csrf_client.get('/login').get_data(as_text=True)
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None

    response = csrf_client.post(
        '/login',
        data={
            'email': 'csrf-login@example.com',
            'senha': 'abc12345',
            'csrf_token': match.group(1),
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert '/?aba=buscar' in response.headers['Location']



def test_templates_nao_usam_csrf_standalone():
    templates_dir = Path(__file__).resolve().parent.parent / 'templates'
    standalone_pattern = re.compile(r'^\s*\{\{\s*csrf_token\(\)\s*\}\}\s*$', re.MULTILINE)

    html_files = sorted(templates_dir.glob('*.html'))
    assert html_files

    offenders = []
    for template_path in html_files:
        content = template_path.read_text(encoding='utf-8')
        if standalone_pattern.search(content):
            offenders.append(template_path.name)

    assert offenders == []
