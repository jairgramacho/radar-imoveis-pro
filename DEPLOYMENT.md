# Deploy em producao (Hetzner)

A aplicacao de producao roda em uma VPS Hetzner, com systemd, nginx e Gunicorn.
Este guia descreve o deploy da aplicacao existente; o provisionamento inicial
da VPS, DNS, certificados TLS e credenciais deve ser feito separadamente.

## Arquitetura e caminhos

| Componente | Papel |
|---|---|
| `radar.service` | Aplicacao Flask servida por Gunicorn em `127.0.0.1:8000` |
| `radar-whatsapp-api.service` | Webhook da Cloud API do WhatsApp |
| `radar-whatsapp-watcher.service` | Watcher de atendimento |
| nginx | TLS e proxy reverso |
| `/var/www/radarimoveispro/deploy.sh` | Atualiza o checkout, dependencias e reinicia `radar` |

- Codigo: `/var/www/radarimoveispro`
- Ambiente: `/var/www/radarimoveispro/.env`
- Logs: `/var/log/radar/`

O arquivo `.env` e as credenciais de acesso nao devem ser versionados nem
copiados para logs ou mensagens.

## Fluxo de deploy

1. Envie o commit desejado para `main` no GitHub.
2. Aguarde o workflow **Testes** concluir com sucesso.
3. Acesse a VPS Hetzner por SSH.
4. Execute o script de deploy:

   ```bash
   sudo /var/www/radarimoveispro/deploy.sh
   ```

O script faz `git pull origin main`, instala as dependencias de
`requirements.txt`, ajusta as permissoes e reinicia `radar`. O deploy e manual:
um push e um CI verde, por si so, nao atualizam a VPS.

O script nao interrompe a execucao automaticamente quando um comando
intermediario falha. Portanto, a mensagem final "Deploy concluido" nao basta
para confirmar o resultado; confira o SHA, o estado do servico e os logs abaixo.

## Verificar o deploy

Na VPS, compare o commit do checkout com o SHA que deseja publicar:

```bash
git -C /var/www/radarimoveispro rev-parse HEAD
```

Verifique tambem o servico e os logs:

```bash
sudo systemctl is-active radar
sudo journalctl -u radar -n 100 --no-pager
```

Por fim, verifique a disponibilidade publica:

```bash
curl -fsS https://www.radarimoveispro.com.br/healthz
```

A resposta de `/healthz` confirma que a aplicacao e o banco respondem, mas nao
identifica a versao do codigo. Para comprovar que um commit especifico esta em
producao, compare seu SHA com o resultado de `git rev-parse HEAD` na VPS.

## CI e automacao

O workflow **Testes** executa lint, typecheck, auditoria de dependencias e
pytest. O workflow [Deploy Render](.github/workflows/deploy-render.yml) e
legado: ele tenta acionar um hook do Render, nao a VPS Hetzner. Sem
`RENDER_DEPLOY_HOOK_URL`, sua etapa de deploy e ignorada. O sucesso desse
workflow nao comprova um deploy em producao.

## Configuracao de producao

As variaveis obrigatorias sao validadas na inicializacao da aplicacao; consulte
`.env.example` e a secao de variaveis de ambiente do [README](README.md).
Mantenha os valores reais apenas no `.env` da VPS ou no gerenciador de segredos
apropriado.

Integrações externas que estejam habilitadas podem exigir configuracao propria:

- Email: Resend ou SMTP, com dominio de envio verificado
- Upload: credenciais do Cloudinary
- Pagamentos: chaves, precos e webhook do Stripe

## Smoke test

Depois de reiniciar o servico, valide:

1. `/healthz` retorna `status: ok` e `database: ok`.
2. A home e a busca de imoveis abrem.
3. Login, publicacao de anuncio e chat funcionam.
4. Email transacional e checkout Stripe funcionam, se habilitados.

## Troubleshooting

- **Servico inativo:** consulte `sudo journalctl -u radar -n 100 --no-pager`.
- **Erro de banco:** confirme `DATABASE_URL` no `.env` e a conectividade com o banco.
- **Erro de coluna apos deploy:** confirme as migracoes e a inicializacao da aplicacao.
- **Problema de dominio/TLS:** confira DNS e configuracao do nginx na VPS.
- **Email nao chega:** verifique as credenciais e o dominio no Resend ou SMTP.
