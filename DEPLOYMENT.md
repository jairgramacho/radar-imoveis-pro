# DEPLOYMENT - Radar Imoveis Pro (Render)

Guia oficial de deploy em producao, alinhado com a arquitetura atual do projeto.

## 1) Requisitos

- Repositorio atualizado no GitHub
- Conta no Render
- Banco PostgreSQL no Render
- Dominio configurado e verificado no Render
- Dominio de envio verificado no Resend
- Conta Stripe em modo producao (quando assinaturas estiverem ativas)

## 2) Criar Web Service no Render

1. New + > Web Service
2. Conectar repositorio `radar-imoveis-pro`
3. Runtime: Python
4. Build command:

```bash
pip install -r requirements.txt
```

5. Start command:

```bash
gunicorn app:app
```

## 3) Variaveis de ambiente (Render)

Minimas para producao:

- FLASK_ENV=production
- SECRET_KEY=(chave forte)
- DATABASE_URL=(PostgreSQL do Render)
- APP_URL=https://www.radarimoveispro.com.br
- ALLOWED_HOSTS=www.radarimoveispro.com.br,radarimoveispro.com.br

Email/Resend:

- RESEND_API_KEY
- RESEND_FROM=Radar Imoveis Pro <noreply@radarimoveispro.com.br>
- MAIL_DEFAULT_SENDER=Radar Imoveis Pro <noreply@radarimoveispro.com.br>
- REQUIRE_EMAIL_CONFIRMATION=1

Cloudinary:

- CLOUDINARY_CLOUD_NAME
- CLOUDINARY_API_KEY
- CLOUDINARY_API_SECRET

Stripe (quando habilitado):

- STRIPE_SECRET_KEY
- STRIPE_WEBHOOK_SECRET
- STRIPE_PRICE_PRO
- STRIPE_PRICE_EMPRESA

## 4) Dominio e DNS

Registros esperados:

- A `radarimoveispro.com.br` -> `216.24.57.1`
- CNAME `www.radarimoveispro.com.br` -> `radar-imoveis-pro.onrender.com`

No Render, os dois devem aparecer como `Verified`.

## 5) Resend

1. Adicionar dominio no Resend
2. Publicar registros DNS solicitados (SPF/DKIM)
3. Aguardar status `Verified`
4. Validar envio real de:

- confirmacao de conta
- redefinicao de senha

## 6) Stripe

1. Criar produtos/price IDs (Pro e Empresa)
2. Criar webhook endpoint:

```text
https://www.radarimoveispro.com.br/webhooks/stripe
```

3. Eventos:

- checkout.session.completed
- customer.subscription.created
- customer.subscription.updated
- customer.subscription.deleted
- invoice.payment_failed
- invoice.payment_succeeded

4. Copiar signing secret (`whsec_...`) para `STRIPE_WEBHOOK_SECRET`

## 7) Smoke test de producao

Testar obrigatoriamente:

1. Home abre sem erro
2. Cadastro + confirmacao de email
3. Login
4. Esqueci senha
5. Publicar anuncio
6. Chat
7. Abertura do checkout Stripe

## 8) Troubleshooting rapido

### Erro de coluna inexistente no login

Se ocorrer apos deploy, confirme que o app iniciou com `FLASK_ENV=production` e finalize novo deploy.
O projeto possui migracao leve de colunas no boot.

### Redirect loop no dominio

1. Verifique DNS de raiz e `www`
2. Verifique se ambos estao `Verified` no Render
3. Limpe cache/cookies/HSTS local do navegador

### Email nao chega

1. Validar dominio no Resend
2. Conferir `RESEND_FROM` e `MAIL_DEFAULT_SENDER`
3. Conferir logs do Render
