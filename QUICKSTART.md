# ⚡ DEPLOYMENT RÁPIDO - RADAR IMÓVEIS

## Para Lançar em 5 minutos

### 1. Preparar código

```bash
# Dentro do projeto
cp .env.example .env

# Editar .env com suas credenciais
nano .env
```

### 2. Gerar SECRET_KEY

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Copia o resultado e cola em `SECRET_KEY=` do `.env`

### 3. Criar conta Railway (2 min)

1. Vai em [Railway.app](https://railway.app)
2. Login com GitHub
3. Create New Project → Deploy from GitHub Repo
4. Seleciona "radar-imoveis-pro"

### 4. Configurar variáveis no Railway

Dashboard → Project Settings → Variables

```
FLASK_ENV = production
SECRET_KEY = (cola a chave que gerou)
DATABASE_URL = (Railway cria automaticamente)
MAIL_USERNAME = seu-email@gmail.com  
MAIL_PASSWORD = sua-app-password (do Gmail)
MAIL_SERVER = smtp.gmail.com
MAIL_PORT = 587
MAIL_DEFAULT_SENDER = seu-email@gmail.com
```

### 5. Checklist rápido antes do push

```bash
# Smoke test local
source .venv/bin/activate
python - <<'PY'
from app import app
client = app.test_client()
for p in ['/', '/login', '/politica-de-privacidade', '/faq-ajuda']:
    r = client.get(p, follow_redirects=False)
    print(p, r.status_code)
PY
```

Se os endpoints públicos retornarem 200, pode seguir.

### 5.1 Checklist automatizado de prontidão

```bash
source .venv/bin/activate
python init_production.py
```

Só publique quando os blocos de validação estiverem todos OK.

### 6. Deploy automático

```bash
# Volta ao terminal, no seu projeto
git add .
git commit -m "Preparar lançamento MVP"
git push origin main
```

Railway faz deploy automaticamente.

### 7. Pegar URL da aplicação

Railway Dashboard → Deployments → URL

Seu site tá online! 🚀

---

## Testar Email (Gmmail)

1. Gmail: Ativa 2FA
2. Gera "App Password": https://myaccount.google.com/apppasswords
3. Cola a senha em MAIL_PASSWORD

Pronto! Email funciona.

---

## Domínio Próprio (Barreiras)

1. Compra em Namecheap/Hostinger: `radarbarreirasimoveis.com.br`
2. Railway → Project Settings → Domains
3. Copia DNS records
4. Cola na Registradora (Namecheap/Hostinger)
5. Aguarda 24h

---

## Verificar Logs

```bash
npm install -g @railway/cli
railway login
railway logs
```

---

## Pronto! 🎉

Site rodando em produção, com HTTPS automático, banco PostgreSQL, email funcionando.

Próximo: Compartilha link em Whatsapp com corretores de Barreiras!

---

## Dúvidas?

- Erro no deploy? Vê em Railway Dashboard → Deployments → View logs
- Email não funciona? Verifica App Password do Gmail
- Site offline? Reset do Railway (Settings → Reset)

**Avisa se travar!**
