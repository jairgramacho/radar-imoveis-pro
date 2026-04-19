## Contexto

Descreva o problema de negocio/tecnico que esta mudanca resolve.

## O que foi alterado

Liste os pontos principais da implementacao.

## Compreensao da mudanca (obrigatorio)

Explique com suas palavras:
- fluxo principal da mudanca
- regras de negocio envolvidas
- pontos de falha conhecidos

## Riscos e impacto

- [ ] impacto em autenticacao/autorizacao
- [ ] impacto em pagamentos/assinatura
- [ ] impacto em dados/migracoes
- [ ] impacto em performance

Detalhe riscos residuais e impacto esperado.

## Validacao executada

- [ ] testes automatizados locais
- [ ] smoke manual do fluxo alterado
- [ ] logs/erros revisados

Comandos executados e resultado:

```bash
# exemplo
PYTHONPATH=. pytest -q
```

## Plano de rollback

Descreva como desfazer rapidamente em caso de incidente.

## Checklist de revisao

- [ ] li e segui o guia em docs/revisao-tecnica.md
- [ ] nao deixei regra de negocio duplicada/inconsistente
- [ ] adicionei/atualizei testes para comportamento novo
- [ ] documentacao atualizada quando necessario
