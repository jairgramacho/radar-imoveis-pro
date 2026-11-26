# QUICKSTART - Radar Imoveis Pro

Guia rapido para desenvolvimento local e deploy da aplicacao em producao na
VPS Hetzner. O Render foi aposentado.

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

Acesse `http://localhost:5000`.

## 2) Deploy na Hetzner

O deploy de producao e feito manualmente na VPS:

1. Envie o commit para `main` e aguarde o workflow **Testes** passar.
2. Acesse a VPS Hetzner por SSH.
3. Execute `sudo /var/www/radarimoveispro/deploy.sh`.
4. Confira `sudo systemctl is-active radar` e os logs com
   `sudo journalctl -u radar -n 100 --no-pager`.
5. Valide `https://www.radarimoveispro.com.br/healthz`.

O push ao GitHub e o CI nao fazem deploy automatico para a Hetzner. Para
confirmar que uma revisao especifica chegou a VPS, compare o SHA esperado com
`git -C /var/www/radarimoveispro rev-parse HEAD`.

Consulte [DEPLOYMENT.md](DEPLOYMENT.md) para detalhes, verificacoes e
troubleshooting.
