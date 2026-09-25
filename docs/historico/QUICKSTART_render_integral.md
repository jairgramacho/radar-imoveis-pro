# QUICKSTART - Radar Imoveis Pro

Guia de inicio rapido para subir o projeto localmente e preparar deploy no Render.

## 1) Rodar local

```bash
git clone https://github.com/jairgramacho/radar-imoveis-pro.git
cd radar-imoveis-pro

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
python app.py
```

Acesse:

```text
http://localhost:5000
```

## 2) Variaveis minimas de producao

No Render, configure pelo menos:

- FLASK_ENV=production
- SECRET_KEY=(chave aleatoria forte)
- DATABASE_URL=(PostgreSQL do Render)
- APP_URL=https://seu-dominio
- RESEND_API_KEY
- RESEND_FROM=Radar Imoveis Pro <noreply@seu-dominio>
- MAIL_DEFAULT_SENDER=Radar Imoveis Pro <noreply@seu-dominio>
- REQUIRE_EMAIL_CONFIRMATION=1

Se Stripe estiver ativo:

- STRIPE_SECRET_KEY
- STRIPE_WEBHOOK_SECRET
- STRIPE_PRICE_PRO
- STRIPE_PRICE_EMPRESA

## 3) Deploy no Render

1. Conecte o repositorio no Render (Web Service).
2. Build command: `pip install -r requirements.txt`
3. Start command: `gunicorn app:app`
4. Salve variaveis de ambiente.
5. Deploy.

## 4) Smoke test (producao)

Valide estes fluxos:

1. Home abre sem erro
2. Cadastro + confirmacao de email
3. Login
4. Esqueci senha
5. Publicar anuncio
6. Abrir checkout Stripe (se habilitado)

## 5) Se algo falhar

1. Abra logs no Render e verifique traceback.
2. Confirme variaveis obrigatorias.
3. Verifique DNS e APP_URL.
4. Verifique dominio no Resend (status verified).
