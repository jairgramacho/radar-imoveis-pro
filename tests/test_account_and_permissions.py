import app as app_module
from models import Imovel, Usuario


def test_redefinir_senha_com_token_valido_atualiza_hash(client, user_factory):
    usuario = user_factory(email='reset@example.com', senha='senha-antiga')
    token = app_module._gerar_token_email(usuario.email, 'reset-senha')

    response = client.post(
        f'/redefinir-senha/{token}',
        data={
            'senha': 'nova-senha-123',
            'confirmar_senha': 'nova-senha-123',
        },
    )

    assert response.status_code == 302
    assert '/login' in response.headers['Location']

    usuario_atualizado = Usuario.query.get(usuario.id)
    assert usuario_atualizado.check_password('nova-senha-123')


def test_esqueci_senha_nao_vaza_existencia_email(client, user_factory):
    user_factory(email='existente@example.com')

    response_existente = client.post('/esqueci-senha', data={'email': 'existente@example.com'})
    response_inexistente = client.post('/esqueci-senha', data={'email': 'inexistente@example.com'})

    assert response_existente.status_code == 302
    assert response_inexistente.status_code == 302
    assert '/login' in response_existente.headers['Location']
    assert '/login' in response_inexistente.headers['Location']


def test_editar_imovel_bloqueia_usuario_que_nao_eh_dono(client, user_factory, login_as, imovel_factory):
    dono = user_factory(email='dono@example.com')
    invasor = user_factory(email='invasor@example.com')
    imovel = imovel_factory(dono.id)
    login_as(invasor.id, invasor.nome)

    response = client.get(f'/editar-imovel/{imovel.id}')

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/')


def test_deletar_imovel_bloqueia_usuario_que_nao_eh_dono(client, user_factory, login_as, imovel_factory):
    dono = user_factory(email='proprietario@example.com')
    invasor = user_factory(email='nao-proprietario@example.com')
    imovel = imovel_factory(dono.id)
    login_as(invasor.id, invasor.nome)

    before_count = Imovel.query.count()
    response = client.post(f'/deletar-imovel/{imovel.id}')
    after_count = Imovel.query.count()

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/')
    assert before_count == after_count