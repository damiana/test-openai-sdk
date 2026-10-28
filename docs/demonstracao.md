# Roteiro de demonstração

Use a interface local conforme o [README](../README.md#como-executar-localmente).
O endereço publicado está na [seção Demonstração](../README.md#demonstração);
a versão hospedada pode diferir desta branch.

## Validar consultas e pagamentos

1. Consulte o saldo e os boletos: uma sessão nova começa com R$ 350,00.
2. Peça um planejamento. A simulação seleciona energia, de R$ 280,00,
   e projeta R$ 70,00 restantes. Planejar não executa pagamentos.
3. Peça “Pague o boleto de energia BOL-001”. Antes de decidir no cartão,
   o pagamento deve estar interrompido e o saldo deve permanecer intacto.
4. Clique em **Rejeitar**. Consulte novamente: o saldo continua R$ 350,00
   e o boleto permanece pendente.
5. Solicite o mesmo pagamento e clique manualmente em **Aprovar**.
   O cartão só deve confirmar sucesso após o resultado da ferramenta.
   Consulte o saldo: deve ser R$ 70,00.
6. Tente pagar a energia novamente: não deve haver novo débito.
   Tente pagar a internet: os R$ 70,00 restantes são insuficientes.
7. Abra uma janela anônima e consulte o saldo: a sessão independente
   deve começar com R$ 350,00.

Mantenha a mesma página nos passos 1 a 6. Atualizá-la inicia outra sessão.
Ao solicitar vários pagamentos, cada cartão exige sua própria decisão.
Em caso de erro de retomada, consulte saldo e boletos antes de tentar novamente.

## Perguntas para experimentar

| Objetivo | Pergunta | O que conferir |
| --- | --- | --- |
| Consultar saldo | “Qual é meu saldo disponível?” | Saldo inicial de R$ 350,00 |
| Listar boletos | “Quais boletos estão pendentes? Mostre os valores e os IDs.” | Energia BOL-001: R$ 280,00; internet BOL-002: R$ 149,90; água BOL-003: R$ 92,50 |
| Planejar sem pagar | “Monte um plano de pagamentos com meu saldo atual, priorizando os vencimentos.” | Na sessão inicial, energia selecionada e sobra de R$ 70,00; nenhum pagamento executado |
| Verificar o total | “Meu saldo é suficiente para pagar todos os boletos?” | Total inicial de R$ 522,40, acima do saldo disponível |
| Testar HITL | “Quero pagar o boleto de energia BOL-001.” | Cartão para aprovar ou rejeitar antes da execução |
| Conferir rejeição | “Qual é meu saldo e quais boletos continuam pendentes?” | Após rejeitar, saldo e boletos não mudam |
| Testar duplicidade | “Pague novamente o boleto BOL-001.” | Após um pagamento aprovado, não pode haver novo débito |
| Testar saldo insuficiente | “Quero pagar a internet BOL-002.” | Após pagar energia, não pode debitar os R$ 149,90 do saldo de R$ 70,00 |
| Testar vários pedidos | “Quero pagar BOL-001, BOL-002 e BOL-003.” | Em uma sessão nova, decisões individuais; rejeite todos para preservar o saldo |

As respostas são geradas pelo modelo e podem variar de texto. Confira os valores,
os resultados das ferramentas e o fluxo de aprovação, não uma frase exata.

**Limites da demonstração:** o estado financeiro é isolado por sessão e mantido em
memória. Atualizar a página inicia uma nova sessão; reiniciar o backend perde as
conversas e o estado da simulação. A chave OpenAI permanece exclusivamente no
backend. As chamadas ao modelo consomem a API OpenAI. Não use dados pessoais reais.


Para entender interrupção e retomada, consulte o [guia de arquitetura](arquitetura.md).
