# 🚀 GUIA DE DEPLOYMENT - RADAR IMÓVEIS

## 1️⃣ PRÉ-DEPLOYMENT (Local)

### Preparar variáveis de ambiente

```bash
cp .env.example .env
```

Editar `.env` com suas credenciais:

```env
FLASK_ENV=production
SECRET_KEY=gerar-chave-aleatoria-aqui (use: python -c "import secrets; print(secrets.token_hex(32))")
DATABASE_URL=seu-banco-de-dados-url
MAIL_USERNAME=seu-email@gmail.com
MAIL_PASSWORD=sua-app-password
```

### Testar aplicação em modo produção

```bash
FLASK_ENV=production python app.py
```

---

## 2️⃣ ESCOLHER PLATAFORMA DE DEPLOY

### ⭐ Recomendado: **Railway.app** (mais fácil)

**Por quê?**
- 1-click deploy com Git
- PostgreSQL incluído
- Suporte a variáveis de ambiente
- Grátis até R$ 100/mês (~5GB dados)
- Ideal para MVP

**Setup:**

1. Criar conta em [railway.app](https://railway.app)
2. Conectar GitHub
3. Selecionar repositório
4. Railway detecta Flask automaticamente
5. Definir variáveis de ambiente no dashboard
6. Deploy automático a cada git push

---

### Alternativa: **Render.com** (muito bom)

- 1-click deploy
- PostgreSQL gratuito
- Ideal pra começar
- Site: https://render.com

---

### Alternativa: **Heroku** (descontinuado plano free, mas funciona)

- Plano pago: USD 7/mês
- Funciona bem
- Histórico de deploy

---

### Alternativa: **PythonAnywhere** (compartilhado)

- Ideal pra aprender
- Plano free limitado
- Domínio grátis: seu-usuario.pythonanywhere.com

---

## 3️⃣ DEPLOY PASSO A PASSO (RAILWAY)

### Para Linux/Mac:

```bash
# 1. Instalar CLI do Railway
npm install -g @railway/cli

# 2. Login
railway login

# 3. Criar projeto no Railway
railway init

# 4. Configurar variáveis de ambiente
railway variable set FLASK_ENV production
railway variable set SECRET_KEY $(python -c "import secrets; print(secrets.token_hex(32))")
railway variable set DATABASE_URL postgresql://...

# 5. Deploy
railway up
```

### Para Windows (mais fácil via GitHub):

1. **Push código para GitHub**
   ```bash
   git add .
   git commit -m "Deploy prep"
   git push origin main
   ```

2. **Acesse Railway.app**
   - New Project → Deploy from GitHub
   - Selecione repositório
   - Railway cria banco automaticamente

3. **Configure variáveis no Railway Dashboard**
   - Settings → Environment
   - Cole suas variáveis do .env

---

## 4️⃣ CONFIGURAR BANCO DE DADOS

### PostgreSQL em Produção

Railway/Render criam bank automaticamente. Vê o link em:

```bash
# No terminal do Railway
railway variable list
# Copia o DATABASE_URL
```

Se usar banco manual:

```bash
# Criar banco PostgreSQL localmente para teste
sudo apt-get install postgresql
createdb radar_imoveis
```

---

## 5️⃣ MIGRAÇÕES (Primeiras vezes)

```bash
# Em produção, rodar no terminal do Railway:
railway run bash

# Dentro do bash:
python -c "from app import app, db; app.app_context().push(); db.create_all()"
```

Ou via **script de inicialização**:

Criar `init_db.py`:
```python
from app import app, db

with app.app_context():
    db.create_all()
    print("✅ Database initialized!")
```

Railway cria hooks para rodar antes do deploy.

---

## 6️⃣ CONFIGURAR DOMÍNIO

### Usar domínio próprio (Barreiras)

1. **Registrar domínio** em Namecheap/Hostinger (~R$30/ano)
   - Exemplo: `radarbarreirasimoveis.com.br`

2. **Railway/Render** → Settings → Domains
   - Adicionar domínio
   - Copiar DNS records

3. **Registradora de domínio** → DNS
   - Colar records do Railway
   - Aguardar ~24h para propagar

---

## 7️⃣ EMAIL EM PRODUÇÃO

### Gmail (mais simples)

1. Ativar 2FA em https://myaccount.google.com/security
2. Gerar "App Password": https://myaccount.google.com/apppasswords
3. Usar essa senha no .env

### SendGrid (recomendado para volume)

1. Criar conta em sendgrid.com
2. Obter API key
3. Usar em MAIL_USERNAME/PASSWORD

```env
MAIL_SERVER=smtp.sendgrid.net
MAIL_PORT=587
MAIL_USERNAME=apikey
MAIL_PASSWORD=SG.xxxxxxxxxxxxx
```

---

## 8️⃣ HTTPS + CERTIFICADO SSL

Railway/Render incluem HTTPS automaticamente ✅

Seu site:
- `https://radarbarreirasimoveis.com.br` ✅
- Certificado renovado automaticamente

---

## 9️⃣ MONITORING + LOGS

### Ver logs do servidor

```bash
# Railway CLI
railway logs

# Ou via dashboard Railway → Deployments → View logs
```

### Adicionar monitoramento básico

Criar `app/logging_config.py`:

```python
import logging
from pythonanywhere import wsgi_handler

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)
```

---

## 🔟 CHECKLIST FINAL

- ✅ `.env` com todas variáveis preenchidas
- ✅ `FLASK_ENV=production`
- ✅ `SECRET_KEY` gerada aleatoriamente
- ✅ PostgreSQL configurado
- ✅ Email testado (enviar email de teste)
- ✅ Upload de arquivos funciona
- ✅ HTTPS ativado
- ✅ Domínio apontado
- ✅ Backup do banco automatizado
- ✅ Monitoramento de erros

---

## ⚠️ SEGURANÇA CHECKLIST

### Antes de lançar:

1. **Mudar todas senhas padrão** ✅
2. **HTTPS ativado** ✅
3. **SECRET_KEY aleatória** ✅
4. **DEBUG=False em produção** ✅
5. **Validar todos inputs** ✅
6. **Rate limiting** (implementar depois)
7. **Backup diário** (Railway/Render faz auto)

---

## 🆘 TROUBLESHOOTING

### "ModuleNotFoundError"
```bash
railway run pip install -r requirements.txt
```

### "DATABASE_URL not found"
```bash
railway variable set DATABASE_URL postgresql://...
```

### "Port binding error"
Flask usa port 5000, mas Railway/Render usam PORT=8000
- Já configurado no Procfile

### Criar Procfile

```
web: gunicorn --bind 0.0.0.0:$PORT app:app
```

---

## 📊 PRIMEIRA EXECUÇÃO

1. Deploy código
2. Ver logs: `railway logs`
3. Acessar URL: https://seu-projeto.railway.app
4. Testar:
   - Login/Cadastro
   - Upload de foto
   - Chat
   - Ver anúncio

---

## 💰 CUSTOS ESTIMADOS (Mensal)

| Item | Railway | Render | Heroku |
|------|---------|--------|--------|
| Servidor | Grátis até $5 | Grátis até $5 | $7 |
| Banco | Incluído | Incluído | +$9 |
| Email | Grátis* | Grátis* | Grátis* |
| Domínio | - | - | - |
| **Total** | ~$5 | ~$5 | ~$16 |

*Gmail/SendGrid têm free tier

---

## 🎯 PRÓXIMOS PASSOS

1. Deploy em Railway/Render hoje
2. Testar em produção
3. Distribuir link em Whatsapp para corretores de Barreiras
4. Coletar feedback
5. Iterar

---

## 📝 REFERÊNCIAS

- [Railway Docs](https://docs.railway.app)
- [Render Docs](https://render.com/docs)
- [Flask Production](https://flask.palletsprojects.com/en/2.3.x/deploying/)
- [PostgreSQL](https://www.postgresql.org/docs/)

---

**Dúvidas? Avisa que ajudo! 🚀**
