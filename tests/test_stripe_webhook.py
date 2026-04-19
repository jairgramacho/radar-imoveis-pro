import json

import app as app_module
from models import Imovel, StripeEventoWebhook, Usuario


class FakeSignatureError(Exception):
    pass


class FakeStripeErrorNamespace:
    SignatureVerificationError = FakeSignatureError


class FakeWebhook:
    def __init__(self, events):
        self._events = list(events)

    def construct_event(self, payload, signature, webhook_secret):
        if signature == 'invalid':
            raise FakeSignatureError('assinatura invalida')
        if not self._events:
            raise ValueError('sem evento')
        return self._events.pop(0)


class FakeSubscription:
    @staticmethod
    def retrieve(subscription_id):
        return {'id': subscription_id, 'current_period_end': 2_000_000_000}


class FakeStripeClient:
    def __init__(self, events):
        self.api_key = ''
        self.error = FakeStripeErrorNamespace
        self.Webhook = FakeWebhook(events)
        self.Subscription = FakeSubscription


def _post_webhook(client, payload=b'{}', signature='valid'):
    return client.post(
        '/webhooks/stripe',
        data=payload,
        headers={'Stripe-Signature': signature},
    )


def test_webhook_rejeita_assinatura_invalida(client, app, monkeypatch):
    app.config.update(
        STRIPE_SECRET_KEY='sk_test_123',
        STRIPE_WEBHOOK_SECRET='whsec_123',
    )
    monkeypatch.setattr(app_module, '_stripe_client', lambda: FakeStripeClient(events=[]))

    response = _post_webhook(client, signature='invalid')

    assert response.status_code == 400
    assert response.get_json()['erro'] == 'assinatura_invalida'


def test_checkout_completed_atualiza_plano_e_respeita_idempotencia(
    client,
    app,
    user_factory,
    imovel_factory,
    monkeypatch,
):
    usuario = user_factory(
        email='stripe-checkout@example.com',
        plano='free',
        limite_anuncios=3,
        status_assinatura='ativa',
    )
    imovel = imovel_factory(usuario.id, ativo=False)

    app.config.update(
        STRIPE_SECRET_KEY='sk_test_123',
        STRIPE_WEBHOOK_SECRET='whsec_123',
    )

    evento_checkout = {
        'id': 'evt_checkout_1',
        'type': 'checkout.session.completed',
        'data': {
            'object': {
                'metadata': {'usuario_id': str(usuario.id), 'plano': 'pro'},
                'client_reference_id': str(usuario.id),
                'customer': 'cus_001',
                'subscription': 'sub_001',
            }
        },
    }

    fake_client = FakeStripeClient(events=[evento_checkout, evento_checkout])
    monkeypatch.setattr(app_module, '_stripe_client', lambda: fake_client)

    response = _post_webhook(client)
    assert response.status_code == 200
    assert response.get_json()['ok'] is True

    usuario_atualizado = Usuario.query.get(usuario.id)
    imovel_atualizado = Imovel.query.get(imovel.id)
    assert usuario_atualizado.plano == 'pro'
    assert usuario_atualizado.limite_anuncios == 15
    assert usuario_atualizado.status_assinatura == 'ativa'
    assert usuario_atualizado.stripe_customer_id == 'cus_001'
    assert usuario_atualizado.stripe_subscription_id == 'sub_001'
    assert usuario_atualizado.assinatura_renova_em is not None
    assert imovel_atualizado.ativo is True

    # Mesmo evento processado de novo deve ser ignorado por idempotencia.
    response_duplicado = _post_webhook(client)
    assert response_duplicado.status_code == 200
    assert response_duplicado.get_json()['duplicado'] is True
    assert StripeEventoWebhook.query.filter_by(stripe_event_id='evt_checkout_1').count() == 1


def test_invoice_failed_pausa_e_payment_succeeded_reativa(
    client,
    app,
    user_factory,
    imovel_factory,
    monkeypatch,
):
    usuario = user_factory(
        email='stripe-invoice@example.com',
        plano='pro',
        limite_anuncios=15,
        status_assinatura='ativa',
    )
    usuario.stripe_customer_id = 'cus_002'
    usuario.stripe_subscription_id = 'sub_002'
    imovel = imovel_factory(usuario.id, ativo=True)

    app.config.update(
        STRIPE_SECRET_KEY='sk_test_123',
        STRIPE_WEBHOOK_SECRET='whsec_123',
    )

    evento_failed = {
        'id': 'evt_invoice_failed_1',
        'type': 'invoice.payment_failed',
        'data': {'object': {'customer': 'cus_002', 'subscription': 'sub_002'}},
    }
    evento_succeeded = {
        'id': 'evt_invoice_succeeded_1',
        'type': 'invoice.payment_succeeded',
        'data': {'object': {'customer': 'cus_002', 'subscription': 'sub_002'}},
    }

    fake_client = FakeStripeClient(events=[evento_failed, evento_succeeded])
    monkeypatch.setattr(app_module, '_stripe_client', lambda: fake_client)

    response_failed = _post_webhook(client)
    assert response_failed.status_code == 200
    assert response_failed.get_json()['ok'] is True

    usuario_failed = Usuario.query.get(usuario.id)
    imovel_failed = Imovel.query.get(imovel.id)
    assert usuario_failed.status_assinatura == 'inadimplente'
    assert imovel_failed.ativo is False

    response_succeeded = _post_webhook(client, payload=json.dumps({'tipo': 'qualquer'}).encode())
    assert response_succeeded.status_code == 200
    assert response_succeeded.get_json()['ok'] is True

    usuario_succeeded = Usuario.query.get(usuario.id)
    imovel_succeeded = Imovel.query.get(imovel.id)
    assert usuario_succeeded.status_assinatura == 'ativa'
    assert imovel_succeeded.ativo is True