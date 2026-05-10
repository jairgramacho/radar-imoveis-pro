# Migração Radar Imóveis Pro → Koyeb

## Pré-requisitos

1. Conta no [Koyeb](https://app.koyeb.com) (grátis, precisa de email)
2. Acesso ao [Registro.br](https://registro.br) (DNS do domínio)

## Passo 1 - Criar banco PostgreSQL no Koyeb

1. Dashboard Koyeb > Database > Create Database
2. Escolher PostgreSQL (free tier)
3. Anotar a URL de conexão gerada

## Passo 2 - Migrar dados do Render para o novo banco

**Exportar do Render (uma vez):**
```bash
# Via terminal com a DATABASE_URL do Render
pg_dump "POSTGRESQL_URL_DO_RENDER" > radar_backup.sql
```

**Importar no Koyeb:**
```bash
psql "NOVA_URL_DO_KOYEB" < radar_backup.sql
```

## Passo 3 - Criar Web Service no Koyeb

1. Koyeb > Create App > Docker
2. Conectar repositório GitHub: `jairgramacho/radar-imoveis-pro`
3. Koyeb detecta Dockerfile automaticamente
4. Porta: 8000
5. Adicionar variáveis de ambiente (ver planilha abaixo)

## Passo 4 - Variáveis de ambiente

| Variável | De onde pegar |
|----------|--------------|
| `SECRET_KEY` | **MANTER A MESMA** do Render (senão perde sessões) |
| `DATABASE_URL` | URL do banco criado no Koyeb |
| `APP_URL` | `https://www.radarimoveispro.com.br` |
| `ALLOWED_HOSTS` | `www.radarimoveispro.com.br,radarimoveispro.com.br` |
| `CLOUDINARY_CLOUD_NAME` | Mesmo do Render |
| `CLOUDINARY_API_KEY` | Mesmo do Render |
| `CLOUDINARY_API_SECRET` | Mesmo do Render |
| `STRIPE_SECRET_KEY` | Mesmo do Render |
| `STRIPE_WEBHOOK_SECRET` | Mesmo do Render (ou recriar webhook) |
| `STRIPE_PRICE_PRO` | Mesmo do Render |
| `STRIPE_PRICE_EMPRESA` | Mesmo do Render |
| `RESEND_API_KEY` | Mesmo do Render |
| `RESEND_FROM` | `Radar Imóveis Pro <noreply@radarimoveispro.com.br>` |
| `MAIL_DEFAULT_SENDER` | `Radar Imóveis Pro <noreply@radarimoveispro.com.br>` |
| `REQUIRE_EMAIL_CONFIRMATION` | `1` |

## Passo 5 - Testar

1. Koyeb dá uma URL tipo `radar-imoveis-pro.koyeb.app`
2. Testar navegação, login, busca
3. Se tudo ok, ir pro DNS

## Passo 6 - Trocar DNS

1. Entrar no [Registro.br](https://registro.br)
2. Ir em DNS > Editar zona
3. Trocar CNAME `www` de `radar-imoveis-pro.onrender.com` para `radar-imoveis-pro.koyeb.app`
4. Aguardar propagação (5-60 min)

## Passo 7 - Atualizar Webhook Stripe

1. Stripe Dashboard > Webhooks
2. Atualizar endpoint URL: `https://www.radarimoveispro.com.br/webhooks/stripe`
3. Se recriar, copiar novo `STRIPE_WEBHOOK_SECRET`

## Passo 8 - Desativar Render (opcional)

Após confirmar que tudo funciona pelo Koyeb:
- Deletar/deixar serviço no Render (já que não vai mais pagar)
