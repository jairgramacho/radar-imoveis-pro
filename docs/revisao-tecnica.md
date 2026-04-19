# Revisao Tecnica - Guardrails de Manutenibilidade

Objetivo: reduzir risco de mudancas sem entendimento completo do codigo.

## 1) Entendimento minimo antes de aprovar

- Identificar entrada, processamento e saida do fluxo alterado.
- Confirmar pre-condicoes e pos-condicoes da regra de negocio.
- Verificar efeitos colaterais em sessoes, banco e integracoes externas.

## 2) Checklist de risco

- Seguranca: autenticacao, autorizacao, exposicao de dados.
- Integridade: escrita em banco, idempotencia, rollback.
- Confiabilidade: tratamento de erro, timeouts, retentativas.
- Operacao: logs uteis e sinais para troubleshooting.

## 3) Evidencias obrigatorias

- Teste automatizado cobrindo caminho feliz e falha principal.
- Resultado de execucao local dos testes.
- Descricao de como validar manualmente em ambiente real.

## 4) Regra para mudanca assistida por IA

- Nao aprovar apenas por "parece correto".
- Todo trecho alterado deve ter explicacao funcional no PR.
- Em caso de duvida de regra de negocio, bloquear merge ate alinhar.

## 5) Qualidade minima no CI

- Lint critico (erros de sintaxe e referencias invalidas).
- Suite de testes verde.

## 6) Sinais de alerta

- Constantes divergentes entre tela, backend e testes.
- Testes quebrando por expectativa desatualizada de regra.
- Logica complexa sem cobertura de teste.
