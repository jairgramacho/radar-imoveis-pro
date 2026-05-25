import app as app_module
from models import Imovel


def test_healthcheck_ok(client):
    response = client.get('/healthz')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['status'] == 'ok'
    assert payload['database'] == 'ok'


def test_nao_existe_rate_limit_global_bloqueando_navegacao():
    limites_globais = [str(limit.limit) for limit in app_module.limiter.limit_manager.default_limits]

    assert limites_globais == []


def test_readiness_check_ok(client):
    response = client.get('/healthz/ready')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['status'] == 'ready'
    assert payload['database'] == 'ok'
    assert payload['email'] in {'ok', 'unconfigured'}
    assert payload['stripe'] in {'ok', 'unconfigured'}


def test_api_publica_imoveis_retorna_503_sem_token_configurado(client):
    response = client.get('/api/public/imoveis')

    assert response.status_code == 503
    payload = response.get_json()
    assert payload['ok'] is False
    assert payload['erro'] == 'token_nao_configurado'


def test_api_publica_imoveis_retorna_401_com_token_invalido(client, app):
    app.config.update(IMOVEIS_EXPORT_API_TOKEN='token-correto')

    response = client.get('/api/public/imoveis', headers={'X-API-Key': 'token-errado'})

    assert response.status_code == 401
    payload = response.get_json()
    assert payload['ok'] is False
    assert payload['erro'] == 'nao_autorizado'


def test_api_publica_imoveis_retorna_apenas_ativos(client, app, user_factory, imovel_factory):
    app.config.update(IMOVEIS_EXPORT_API_TOKEN='token-n8n')
    usuario = user_factory(email='api-imoveis@example.com')

    ativo = imovel_factory(usuario.id, ativo=True)
    imovel_factory(usuario.id, ativo=False)

    response = client.get('/api/public/imoveis', headers={'X-API-Key': 'token-n8n'})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['ok'] is True
    assert payload['total'] == 1
    assert len(payload['imoveis']) == 1

    imovel_payload = payload['imoveis'][0]
    assert imovel_payload['id'] == ativo.id
    assert imovel_payload['negocio'] == 'Venda'
    assert imovel_payload['preco'] == ativo.preco
    assert imovel_payload['url'].endswith(f'/imovel/{ativo.id}')


def test_robots_txt_disponivel(client):
    response = client.get('/robots.txt')
    conteudo = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'User-agent:' in conteudo
    assert 'Sitemap:' in conteudo


def test_sitemap_xml_disponivel(client):
    response = client.get('/sitemap.xml')
    conteudo = response.get_data(as_text=True)

    assert response.status_code == 200
    assert '<urlset' in conteudo
    assert '/planos' in conteudo


def test_dashboard_exige_login(client):
    response = client.get('/dashboard')

    assert response.status_code == 302
    assert '/login' in response.headers['Location']


def test_login_com_credenciais_validas_cria_sessao(client, user_factory):
    usuario = user_factory(email='login@example.com', senha='abc12345')

    response = client.post(
        '/login',
        data={'email': 'login@example.com', 'senha': 'abc12345'},
    )

    assert response.status_code == 302
    assert '/?aba=buscar' in response.headers['Location']

    with client.session_transaction() as sess:
        assert sess['usuario_id'] == usuario.id


def test_salvar_bloqueia_quando_atingiu_limite(client, app, user_factory, login_as, imovel_factory):
    usuario = user_factory(
        email='limite@example.com',
        limite_anuncios=1,
        plano='free',
        status_assinatura='ativa',
    )
    imovel_factory(usuario.id, ativo=True)
    login_as(usuario.id, usuario.nome)

    before_count = Imovel.query.filter_by(usuario_id=usuario.id).count()

    response = client.post(
        '/salvar',
        data={
            'estado': 'SP',
            'cidade': 'Sao Paulo',
            'bairro': 'Centro',
            'tipo': 'Apartamento',
            'negocio': 'Venda',
            'valor': '450000',
            'descricao': 'Teste de limite',
        },
    )

    after_count = Imovel.query.filter_by(usuario_id=usuario.id).count()

    assert response.status_code == 302
    assert '/?aba=anunciar' in response.headers['Location']
    assert before_count == after_count

    # Bloqueio de novo anúncio não pode alterar anúncios já publicados.
    assert Imovel.query.filter_by(usuario_id=usuario.id, ativo=True).count() == 1


def test_salvar_permite_admin_ilimitado_mesmo_no_plano_free(client, user_factory, login_as):
    usuario = user_factory(
        email='admin-ilimitado@example.com',
        plano='free',
        limite_anuncios=0,
        status_assinatura='ativa',
    )
    usuario.is_admin = True
    from models import db
    db.session.commit()

    login_as(usuario.id, usuario.nome)
    before_count = Imovel.query.filter_by(usuario_id=usuario.id).count()

    response = client.post(
        '/salvar',
        data={
            'estado': 'SP',
            'cidade': 'Sao Paulo',
            'bairro': 'Centro',
            'tipo': 'Apartamento',
            'negocio': 'Venda',
            'valor': '450000',
            'descricao': 'Teste admin ilimitado',
        },
    )

    after_count = Imovel.query.filter_by(usuario_id=usuario.id).count()

    assert response.status_code == 302
    assert '/imovel/' in response.headers['Location']
    assert after_count == before_count + 1