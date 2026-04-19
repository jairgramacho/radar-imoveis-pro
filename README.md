# Radar Imoveis Pro

Plataforma web para anuncios imobiliarios com foco em publicacao, descoberta de oportunidades e relacionamento entre anunciante e interessado.

O projeto foi construido para operacao real em producao, com dominio proprio, envio de emails transacionais e assinaturas recorrentes.

## Visao Geral

Principais capacidades da plataforma:

- Busca e filtros de imoveis (compra, venda e aluguel)
- Publicacao e gestao de anuncios com multiplas fotos
- Processamento de imagens (incluindo HEIC/HEIF)
- Chat entre usuarios com contexto por imovel
- Indicador de mensagens nao lidas na navegacao
- Sistema de avaliacoes
- Confirmacao de email e redefinicao de senha por token
- Configuracoes de conta e exclusao de conta
- Planos com limite de anuncios (Free, Pro e Empresa)
- Fluxo de assinatura Stripe com webhook e automacoes de status

## Stack

- Backend: Flask
- ORM: SQLAlchemy
- Banco de dados: PostgreSQL (producao) e SQLite (desenvolvimento)
- Frontend: Jinja2 + Bootstrap 5 + CSS
- Email transacional: Resend (com fallback SMTP)
- Upload persistente: Cloudinary
- Pagamentos: Stripe

## Ambiente Local

### Requisitos

- Python 3.10+
- pip

### Instalar e executar

```bash
git clone https://github.com/jairgramacho/radar-imoveis-pro.git
cd radar-imoveis-pro

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
python app.py
```

Aplicacao local:

```text
http://localhost:5000
```

## Variaveis de Ambiente

Use o arquivo .env.example como base.

Blocos mais importantes:

- Aplicacao e seguranca: SECRET_KEY, APP_URL, FLASK_ENV
- Banco: DATABASE_URL
- Email (Resend): RESEND_API_KEY, RESEND_FROM
- Email (fallback): MAIL_DEFAULT_SENDER, MAIL_USERNAME, MAIL_PASSWORD
- Cloudinary: CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET
- Confirmacao de email: REQUIRE_EMAIL_CONFIRMATION
- Stripe:
    - STRIPE_SECRET_KEY
    - STRIPE_WEBHOOK_SECRET
    - STRIPE_PRICE_PRO
    - STRIPE_PRICE_EMPRESA

## Stripe (Assinaturas)

Fluxo implementado no backend:

1. Usuario inicia checkout para Pro ou Empresa
2. Stripe confirma pagamento e envia eventos para webhook
3. Sistema atualiza status de assinatura e limites de anuncios
4. Em inadimplencia/cancelamento, anuncios podem ser pausados conforme regra de negocio

Eventos utilizados:

- checkout.session.completed
- customer.subscription.created
- customer.subscription.updated
- customer.subscription.deleted
- invoice.payment_failed
- invoice.payment_succeeded

Endpoint webhook:

```text
/webhooks/stripe
```

## Deploy

Projeto preparado para deploy no Render.

Checklist rapido:

1. Configurar variaveis de ambiente
2. Garantir dominio e DNS ativos
3. Validar dominio no Resend
4. Configurar webhook Stripe
5. Executar smoke test (login, cadastro, email, checkout)

Arquivos de apoio:

- DEPLOYMENT.md
- QUICKSTART.md

## Qualidade e Revisao

Guardrails adotados para reduzir risco de mudancas sem entendimento completo:

- CI com lint critico e testes automatizados em .github/workflows/tests.yml
- Template obrigatorio de PR em .github/pull_request_template.md
- Checklist de revisao tecnica em docs/revisao-tecnica.md

Comando local recomendado antes de abrir PR:

```bash
PYTHONPATH=. pytest -q
```

## Estrutura Principal

```text
radar-imoveis-pro/
├── app.py
├── config.py
├── models.py
├── email_utils.py
├── requirements.txt
├── templates/
├── static/
└── .env.example
```

## Roadmap

- Melhorias de onboarding e ativacao de usuario
- Observabilidade (logs e monitoramento mais detalhados)
- SEO tecnico (sitemap, Search Console e metadata expandida)
- Evolucao de planos e relatorios para anunciantes

## Licenca

Definir licenca oficial do projeto (ex.: MIT) e adicionar arquivo LICENSE.
