import os

import pytest

os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('SECRET_KEY', 'test-secret-key-1234567890')

from app import app as flask_app  # noqa: E402
from models import Imovel, Usuario, db  # noqa: E402


@pytest.fixture
def app():
    flask_app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        WTF_CSRF_ENABLED=False,
    )

    with flask_app.app_context():
        db.drop_all()
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def user_factory(app):
    _user_counter = {'count': 0}
    
    def _create_user(
        nome='Usuario Teste',
        email=None,
        senha='123456',
        whatsapp=None,
        plano='free',
        limite_anuncios=3,
        status_assinatura='ativa',
    ):
        # Gerar email e whatsapp únicos se não fornecidos
        _user_counter['count'] += 1
        if email is None:
            email = f'teste{_user_counter["count"]}@example.com'
        if whatsapp is None:
            whatsapp = f'1199999{_user_counter["count"]:04d}'
        
        usuario = Usuario(
            nome=nome,
            email=email,
            whatsapp=whatsapp,
            plano=plano,
            limite_anuncios=limite_anuncios,
            status_assinatura=status_assinatura,
            email_confirmado=True,
        )
        usuario.set_password(senha)
        db.session.add(usuario)
        db.session.commit()
        return usuario

    return _create_user


@pytest.fixture
def login_as(client):
    def _login(usuario_id, nome='Usuario Teste'):
        with client.session_transaction() as sess:
            sess['usuario_id'] = usuario_id
            sess['usuario_nome'] = nome

    return _login


@pytest.fixture
def imovel_factory(app):
    def _create_imovel(usuario_id, ativo=True):
        imovel = Imovel(
            usuario_id=usuario_id,
            estado='SP',
            cidade='Sao Paulo',
            bairro='Centro',
            tipo='Apartamento',
            negocio='Venda',
            preco=350000.0,
            ativo=ativo,
        )
        db.session.add(imovel)
        db.session.commit()
        return imovel

    return _create_imovel