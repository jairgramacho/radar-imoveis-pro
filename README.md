# Radar Imóveis Pro

<!--
PENDENTE (Jair): frase de propósito do projeto.
A versão anterior dizia "publicacao, descoberta de oportunidades e relacionamento
entre anunciante e interessado" — termo removido com o filtro de oportunidades.
Aguardando a redação aprovada para substituir o trecho abaixo.
-->

Plataforma web de anúncios de imóveis em Barreiras e no Oeste da Bahia.
**<< FRASE DE PROPÓSITO — PENDENTE >>**

Construído para operação real em produção: domínio próprio, email transacional,
assinaturas recorrentes e CRM de atendimento.

> **Origem.** O projeto nasceu de uma inquietação prototipada em **Streamlit**:
> quem procura imóvel na região não tinha onde comparar preços de forma
> informada, e quem anunciava dependia de canais onde o anúncio desaparecia em
> dias. O Streamlit provou que a ideia funcionava; não podia entregar produto —
> sem SEO, sem domínio, sem autenticação adequada. A migração para Flask é a
> razão de o repositório ter começado com um `app.py` e um banco em arquivo de
> texto. O histórico completo está em [`docs/historico/`](docs/historico/LEIA-ME.md).

---

## Capacidades

**Busca e descoberta**
- Busca de imóveis com filtros por tipo de negócio, tipo de imóvel, localização, preço e bairro
- Página de detalhe do imóvel com galeria, atributos e contato direto
- SEO técnico: sitemap dinâmico, `robots.txt`, canonical, Open Graph e JSON-LD (`WebSite`, `RealEstateAgent`)

**Anúncios**
- Publicação e gestão de anúncios com múltiplas fotos
- Processamento de imagens (incluindo HEIC/HEIF) e upload persistente via Cloudinary
- Planos com limite de anúncios (Free, Pro e Empresa)

**Relacionamento e atendimento**
- Chat entre usuários com contexto por imóvel e indicador de mensagens não lidas
- **CRM nativo**: captura de lead por WhatsApp, funil e dashboard de acompanhamento
- Sistema de avaliações de anunciante

**Conta e segurança**
- Cadastro, login, confirmação de email e redefinição de senha por token
- Autenticação de dois fatores (2FA/TOTP)
- Configurações de conta e exclusão de conta
- Hardening: LGPD, CSRF, rate limiting em endpoints críticos, validação de entrada com Pydantic, sanitização de HTML e audit log

**Assinaturas**
- Fluxo Stripe com webhook, status de assinatura e limites por plano

**Integrações**
- Exportação de imóveis em JSON com token para automações (n8n)

---

## Stack

| Camada | Tecnologia |
|---|---|
| Backend | Flask 3.1 |
| ORM | SQLAlchemy 3.1 + Flask-Migrate (Alembic) |
| Banco | PostgreSQL (produção) · SQLite (desenvolvimento) |
| Frontend | Jinja2 + Bootstrap 5 + CSS |
| Email | Resend (com fallback SMTP) |
| Upload | Cloudinary |
| Pagamentos | Stripe |
| Servidor | Gunicorn (2 workers) atrás de nginx |
| Python | 3.11+ (CI roda em 3.12) |

---

## Arquitetura

O código de aplicação vive em `radar_app/`, organizado em camadas:

```text
radar_app/
├── blueprints/          Rotas HTTP (core, imoveis, auth, chat, crm, billing, admin, public)
├── imoveis/             Domínio de imóveis — repository, service, avaliacao_repository
├── auth/                Domínio de autenticação — repository, service
├── assinatura/          Domínio de assinaturas
├── services/            Serviços de aplicação (email, media, tokens, bootstrap)
├── infra/               Infraestrutura (bootstrap, email, media)
├── security/            Rate limiting, sanitização, schemas de validação
└── legacy_app.py        Fábrica da aplicação e compatibilidade
```

**Modelos** (`models.py`): `Usuario`, `Imovel`, `FotoImovel`, `Avaliacao`,
`Mensagem`, `CRMLead`, `CRMLeadHistorico`, `Notificacao`,
`StripeEventoWebhook`, `ConsentimentoUsuario`, `AuditLog`, `TokenDoisFatores`.

**Rotas principais:**

| Rota | O que serve |
|---|---|
| `/` | Home — landing page |
| `/?aba=buscar` | Busca de imóveis |
| `/?aba=anunciar` | Publicação de anúncio |
| `/imovel/<id>` | Detalhe do imóvel |
| `/crm` | Dashboard do CRM e funil de leads |
| `/chat` | Chat entre usuários |
| `/dashboard` | Painel do anunciante |
| `/planos` | Planos e checkout |
| `/healthz` · `/healthz/ready` | Healthcheck e readiness |
| `/sitemap.xml` · `/robots.txt` | SEO |
| `/api/public/imoveis` | Exportação JSON (autenticada por token) |
| `/webhooks/stripe` | Webhook de assinaturas |

---

## Ambiente local

### Requisitos

- Python 3.11+
- pip

### Instalar e executar

```bash
git clone https://github.com/jairgramacho/radar-imoveis-pro.git
cd radar-imoveis-pro

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
python app.py
```

Aplicação local:

```text
http://localhost:5000
```

---

## Variáveis de ambiente

Use `.env.example` como base. As obrigatórias em produção são validadas na
inicialização (`config.py`) — a aplicação recusa subir sem elas.

**Obrigatórias em produção:**

- `SECRET_KEY` — mínimo 32 caracteres, aleatória
- `DATABASE_URL` — PostgreSQL
- `APP_URL` — precisa começar com `https://`
- `MAIL_DEFAULT_SENDER`

**Email** (uma das duas vias é obrigatória):

- Resend: `RESEND_API_KEY`, `RESEND_FROM`, `RESEND_TIMEOUT`
- SMTP: `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_SERVER`, `MAIL_PORT`

**Demais blocos:**

- Upload: `UPLOAD_FOLDER`, `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`
- Aplicação: `FLASK_ENV`, `ALLOWED_HOSTS`, `ADMIN_EMAILS`, `REQUIRE_EMAIL_CONFIRMATION`
- Stripe: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_PRO`, `STRIPE_PRICE_EMPRESA`
- Integração n8n: `IMOVEIS_EXPORT_API_TOKEN`
- Desenvolvimento: `ALLOW_DEV_PASSWORD_RESET_FALLBACK`

---

## Stripe (assinaturas)

Fluxo implementado no backend:

1. Usuário inicia checkout para Pro ou Empresa
2. Stripe confirma o pagamento e envia eventos para o webhook
3. Sistema atualiza status de assinatura e limites de anúncios
4. Em inadimplência ou cancelamento, anúncios podem ser pausados conforme regra de negócio

Eventos tratados:

- `checkout.session.completed`
- `customer.subscription.created`
- `customer.subscription.updated`
- `customer.subscription.deleted`
- `invoice.payment_failed`
- `invoice.payment_succeeded`

Endpoint do webhook:

```text
/webhooks/stripe
```

---

## Deploy (Hetzner)

Produção roda em VPS Hetzner sob systemd + nginx + gunicorn.

| Componente | Papel |
|---|---|
| `radar.service` | Aplicação — gunicorn com 2 workers em `127.0.0.1:8000` |
| `radar-whatsapp-api.service` | Webhook Cloud API (WhatsApp oficial) |
| `radar-whatsapp-watcher.service` | Watcher de atendimento |
| nginx | TLS e proxy reverso |
| `deploy.sh` | Pull, instala dependências, ajusta permissões e reinicia |

**Caminhos:**

- Código: `/var/www/radarimoveispro`
- Logs: `/var/log/radar/`
- Ambiente: `/var/www/radarimoveispro/.env`

**Push para o GitHub:** o remote é SSH e a chave não é a default. Use:

```bash
export GIT_SSH_COMMAND="ssh -i /root/.ssh/jair_key -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20"
git push origin main
```

> O deploy no **Render** foi aposentado em 25/09/2026. Guias e artefatos
> originais preservados em [`docs/historico/`](docs/historico/LEIA-ME.md).

---

## Qualidade

Guardrails adotados para reduzir risco de mudança sem entendimento completo:

- CI com lint crítico (ruff, regras E9/F63/F7/F82) em `.github/workflows/tests.yml`
- CI com typecheck gradual (mypy) para módulos priorizados
- CI com auditoria de vulnerabilidades de dependências (pip-audit)
- Template obrigatório de PR em `.github/pull_request_template.md`
- Checklist de revisão técnica em `docs/revisao-tecnica.md`

**Testes** (`tests/`, 33 testes): smoke, CSRF regression, CRM, Stripe webhook,
dashboard, conta e permissões.

Comandos recomendados antes de abrir PR:

```bash
pip-audit -r requirements.txt
mypy --config-file mypy.ini config.py email_utils.py
PYTHONPATH=. pytest -q
```

---

## Roadmap

- Melhorias de onboarding e ativação de usuário
- Observabilidade: logs e monitoramento mais detalhados
- Metadata de SEO expandida e acompanhamento no Search Console
- Evolução de planos e relatórios para anunciantes

---

## Licença

**Proprietária — todos os direitos reservados.** Titular: Jair Ricardo de
Oliveira Gramacho. O texto completo está em [`LICENSE`](LICENSE).

O uso, a cópia, a modificação e a distribuição do software dependem de
autorização prévia e por escrito do titular.

> A v1 deste README (15/03/2026) afirmava licença MIT e apontava para um arquivo
> `LICENSE` que nunca existiu em nenhum commit. A licença oficial nunca havia
> sido fixada até 25/09/2026.
