def test_dashboard_redireciona_quando_nao_autenticado(client):
    response = client.get('/dashboard', follow_redirects=False)

    assert response.status_code == 302
    assert '/login' in response.headers['Location']


def test_login_valido_cria_sessao_e_dashboard_renderiza(client, user_factory):
    usuario = user_factory(
        email='integracao-login-ok@example.com',
        senha='abc12345',
        nome='Ana Integracao',
    )

    response_login = client.post(
        '/login',
        data={'email': usuario.email, 'senha': 'abc12345'},
        follow_redirects=False,
    )

    assert response_login.status_code == 302

    with client.session_transaction() as sess:
        assert sess.get('usuario_id') == usuario.id

    response_dashboard = client.get('/dashboard')

    assert response_dashboard.status_code == 200
    assert 'Painel de Controle' in response_dashboard.get_data(as_text=True)


def test_login_invalido_nao_permite_acesso_dashboard(client, user_factory):
    user_factory(email='integracao-login-fail@example.com', senha='senha-correta')

    response_login = client.post(
        '/login',
        data={'email': 'integracao-login-fail@example.com', 'senha': 'senha-errada'},
        follow_redirects=False,
    )

    assert response_login.status_code == 200

    response_dashboard = client.get('/dashboard', follow_redirects=False)

    assert response_dashboard.status_code == 302
    assert '/login' in response_dashboard.headers['Location']


def test_dashboard_exibe_checkout_quando_stripe_habilitado(client, app, user_factory, login_as):
    app.config.update(
        STRIPE_SECRET_KEY='sk_test_123',
        STRIPE_PRICE_PRO='price_pro_123',
        STRIPE_PRICE_EMPRESA='price_empresa_123',
    )

    usuario = user_factory(email='integracao-stripe-on@example.com')
    login_as(usuario.id, usuario.nome)

    response = client.get('/dashboard')
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'action="/assinatura/checkout"' in html
    assert 'Pagamento indisponível no momento' not in html


def test_dashboard_oculta_checkout_quando_stripe_desabilitado(client, app, user_factory, login_as):
    app.config.update(
        STRIPE_SECRET_KEY='',
        STRIPE_PRICE_PRO='',
        STRIPE_PRICE_EMPRESA='',
    )

    usuario = user_factory(email='integracao-stripe-off@example.com')
    login_as(usuario.id, usuario.nome)

    response = client.get('/dashboard')
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'Pagamento indisponível no momento' in html
    assert 'action="/assinatura/checkout"' not in html
