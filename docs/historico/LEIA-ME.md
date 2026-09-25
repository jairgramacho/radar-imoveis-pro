# Histórico — Radar Imóveis Pro

Arquivo morto. Nada aqui é usado em produção. Este diretório guarda a
memória de como o projeto começou e o que foi aposentado pelo caminho.

---

## 1. As seis versões do README

O README evoluiu em 6 versões entre março e maio de 2026. Cada arquivo é a
versão exata como estava no repositório naquele commit.

| Arquivo | Data | Commit | O que a versão representava |
|---|---|---|---|
| `README_2026-03-15_v1-inicial.md` | 15/03/2026 | `6ffdd43` | Versão de nascimento. Descreve o projeto como **marketplace**, com banco em **arquivo de texto** (`banco_imoveis.txt`) e o **Radar de Oportunidades** como funcionalidade de destaque. |
| `README_2026-04-09_v2-arquitetura-producao.md` | 09/04/2026 | `a128866` | Primeira virada: de produto para documentação de arquitetura de produção. |
| `README_2026-04-19_v3-guardrails.md` | 19/04/2026 | `f329fef` | Entram os guardrails de revisão e os quality gates de CI. |
| `README_2026-04-19_v4-ci-typecheck.md` | 19/04/2026 | `07dfcec` | CI ganha typecheck (mypy) e auditoria de dependências (pip-audit). |
| `README_2026-05-08_v5-marketplace-para-plataforma.md` | 08/05/2026 | `9190348` | Última mudança de posicionamento: "marketplace" → "plataforma". |
| `README_2026-05-25_v6-export-n8n.md` | 25/05/2026 | `a4e80a4` | Última atualização de conteúdo. Documenta a exportação para n8n. Depois disso o README ficou parado. |

**Como recuperar qualquer versão direto do git:**

```bash
git log --follow --format="%h | %ad | %s" --date=short -- README.md
git show <commit>:README.md
```

---

## 2. Radar de Oportunidades — aposentado em 25/09/2026

O "Radar de Oportunidades" foi uma das funcionalidades fundadoras do projeto.
Na v1 do README ele era seção de destaque:

> **🎯 Radar de Oportunidades**
> - Detecção de imóveis abaixo da média de comparáveis
> - Critério de oportunidade por desconto percentual mínimo
> - Exibição em aba dedicada para facilitar descoberta

**O que era:** um filtro que marcava imóveis com preço 10% ou mais abaixo da
média de imóveis comparáveis da mesma região (mesmo negócio, cidade, bairro,
tipo e número de quartos). Exibia badge "Oportunidade" no card, percentual de
desconto e uma aba dedicada (`?aba=oportunidades`).

**Por que saiu:** a funcionalidade implicava a plataforma opinar sobre o preço
dos imóveis — o que cria ambiguidade quanto ao papel da Radar na
comercialização. A remoção foi decisão tomada para zerar o risco jurídico
operacional no modelo de conformidade.

**Removido em:** commit `79a48b7` — 226 linhas entre back-end, front-end e
sitemap. A URL `?aba=oportunidades` agora responde **301** para a busca,
preservando os filtros da query.

**O que sobrou:** nada em código ativo. A palavra "oportunidade" existe apenas
no próprio redirect, como nome da URL antiga.

---

## 3. Deploy no Render — aposentado em 25/09/2026

O projeto foi construído para deploy no **Render** (PaaS). Em setembro de 2026
migrou para **VPS Hetzner** com systemd + gunicorn + nginx.

O Render foi aposentado porque o projeto passou a exigir controle que um PaaS
não dá: acesso ao servidor, systemd próprio, nginx, controle de disco e a
possibilidade de rodar serviços auxiliares (webhook e watcher do WhatsApp) no
mesmo host.

Artefatos preservados aqui:

| Arquivo | O que era |
|---|---|
| `DEPLOYMENT_render_integral.md` | Guia completo de deploy no Render, com web service, PostgreSQL gerenciado e DNS. |
| `QUICKSTART_render_integral.md` | Guia rápido de subida local + preparação de deploy no Render. |
| `Procfile_render.txt` | `web: gunicorn --bind 0.0.0.0:$PORT app:app` — formato de procfile do Render. |
| `runtime_render.txt` | `python-3.11.9` — fixação de versão exigida pelo Render. |
| `workflows/deploy-render.yml.txt` | GitHub Action que disparava o deploy hook do Render após CI verde. |

**O que ficou ativo do período Render:** o `Dockerfile` (útil para qualquer
container), o `gunicorn` como servidor WSGI e as variáveis de ambiente — que
continuam as mesmas, só mudaram de painel.

**O que foi desativado:** o workflow `deploy-render.yml` **não foi removido**
do GitHub Actions, mas depende do secret `RENDER_DEPLOY_HOOK_URL`, que não
existe mais. Sem o secret, o workflow apenas registra aviso e não faz nada.
Vale remover quando convier.

---

## 4. Linha do tempo do projeto

| Período | Marcos |
|---|---|
| **06/03/2026** | `Initial commit` — projeto nasce. |
| **15/03/2026** | MVP para lançamento: autenticação, recuperação de senha, Radar de Oportunidades. |
| **20–23/03/2026** | Batalha do email transacional: SMTP → Resend, timeouts, user-agent do Resend, contexto Flask em threads. |
| **30/03–01/04/2026** | Detalhe do imóvel ganha botão de mensagem; rodapé recebe contato real. |
| **09–19/04/2026** | Virada de maturidade: arquitetura de produção documentada, guardrails de revisão, CI com lint + typecheck + pip-audit. |
| **Abril/2026** | **99 commits** — o mês mais intenso do projeto. |
| **08/05/2026** | "marketplace" → "plataforma". |
| **25/05/2026** | Exportação JSON para n8n. Última atualização do README. |
| **Junho–Agosto/2026** | Refatoração em camadas: repositórios, serviços, blueprints, segurança (LGPD, CSRF, rate limit, 2FA), CRM, migração para Hetzner. |
| **25/09/2026** | Conformidade CRECI, limpeza de vocabulário, remoção do Radar de Oportunidades, aposentadoria do Render, README reescrito. |

**Números do repositório (25/09/2026):** 139 commits · 35 módulos Python em
`radar_app/` · ~4.832 linhas de Python · 27 templates · 74 rotas · 33 testes.

---

## 5. Origem: a inquietação no Streamlit

O Radar Imóveis Pro não nasceu como projeto web. Nasceu de uma inquietação
prática, prototipada em **Streamlit**.

A ideia original era simples e incômoda: quem procura imóvel em Barreiras não
tinha onde comparar preços de forma minimamente informada, e quem anunciava
dependia de canais onde o anúncio desaparecia em dias. O primeiro protótipo
foi feito em Streamlit — rápido de escrever, mas limitado demais para virar
produto: sem SEO, sem controle de layout, sem autenticação adequada, sem
domínio próprio.

O que o Streamlit provou foi que **a ideia funcionava**. O que ele não podia
entregar foi o produto. A migração para Flask aconteceu justamente aí — e é a
razão de o repositório ter começado com `app.py` + `banco_imoveis.txt`, sem
banco relacional, em março de 2026.

Essa origem explica escolhas que ainda estão no código: a simplicidade do
modelo de dados, a prioridade em busca e comparação, e a insistência em
contato direto entre interessado e anunciante — que era o gargalo que o
Streamlit já tentava resolver.
