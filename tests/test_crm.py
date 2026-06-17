from models import CRMLead, CRMLeadHistorico, Mensagem


def test_whatsapp_tracking_cria_lead_e_redireciona(client, user_factory, imovel_factory):
    anunciante = user_factory(email='anunciante-crm@example.com', whatsapp='(77) 99999-1111')
    imovel = imovel_factory(anunciante.id)

    response = client.get(f'/crm/whatsapp/{imovel.id}', follow_redirects=False)

    assert response.status_code == 302
    assert 'wa.me/5577999991111' in response.headers['Location']
    lead = CRMLead.query.filter_by(imovel_id=imovel.id, anunciante_id=anunciante.id).first()
    assert lead is not None
    assert lead.codigo.startswith('RLP-')
    assert CRMLeadHistorico.query.filter_by(lead_id=lead.id).count() >= 1


def test_chat_cria_lead_para_imovel(client, user_factory, login_as, imovel_factory):
    anunciante = user_factory(email='anunciante-chat@example.com')
    interessado = user_factory(email='interessado-chat@example.com')
    imovel = imovel_factory(anunciante.id)
    login_as(interessado.id, interessado.nome)

    response = client.post(
        f'/enviar-mensagem/{anunciante.id}',
        data={'imovel_id': imovel.id, 'titulo': 'Quero saber mais', 'mensagem': 'Olá, ainda está disponível?'},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert Mensagem.query.filter_by(remetente_id=interessado.id, destinatario_id=anunciante.id).count() == 1
    assert CRMLead.query.filter_by(imovel_id=imovel.id, anunciante_id=anunciante.id, interessado_usuario_id=interessado.id).count() == 1


def test_crm_dashboard_lista_leads_do_usuario(client, user_factory, login_as, imovel_factory):
    anunciante = user_factory(email='anunciante-dashboard@example.com', whatsapp='(77) 99999-2222')
    interessado = user_factory(email='interessado-dashboard@example.com')
    imovel = imovel_factory(anunciante.id)

    login_as(interessado.id, interessado.nome)
    client.get(f'/crm/whatsapp/{imovel.id}')

    login_as(anunciante.id, anunciante.nome)
    response = client.get('/crm')
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'CRM Radar' in html
    assert f'{imovel.tipo} em {imovel.cidade}' in html


def test_crm_atualiza_status_e_proxima_acao(client, user_factory, login_as, imovel_factory):
    anunciante = user_factory(email='anunciante-status@example.com', whatsapp='(77) 99999-3333')
    imovel = imovel_factory(anunciante.id)
    client.get(f'/crm/whatsapp/{imovel.id}')

    lead = CRMLead.query.filter_by(imovel_id=imovel.id, anunciante_id=anunciante.id).first()
    login_as(anunciante.id, anunciante.nome)

    response = client.post(
        f'/crm/leads/{lead.id}/status',
        data={
            'status': 'contato',
            'observacoes': 'Ligação feita',
            'proxima_acao_em': '2026-06-16T09:00',
            'perda_motivo': '',
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    lead_atualizado = CRMLead.query.get(lead.id)
    assert lead_atualizado.status == 'contato'
    assert lead_atualizado.primeiro_contato_em is not None
    assert lead_atualizado.observacoes == 'Ligação feita'