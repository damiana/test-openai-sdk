"""Validações locais de regras e HITL, sem rede nem aprovação automática."""
import asyncio
from decimal import Decimal
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents import Model, ModelResponse, RunConfig, Runner, SQLiteSession, Usage
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage
from configuracao import agent
from ContextoFinanceiro import ContextoFinanceiro
from evals import avaliar_pagamento_duplicado
from financeiro import estado_financeiro, obter_boletos, obter_saldo, planejar_pagamentos
from hitl import resolver_aprovacoes


class ModeloPagamento(Model):
    """Emite uma chamada conhecida para testar o bloqueio real do SDK."""

    async def get_response(self, *args, **kwargs):
        items = kwargs.get('input', args[1] if len(args) > 1 else [])
        if any(isinstance(item, dict) and item.get('type') == 'function_call_output' for item in items):
            output = [ResponseOutputMessage(
                id='msg_local', type='message', role='assistant', status='completed',
                content=[{'type': 'output_text', 'text': 'Pagamento rejeitado.', 'annotations': []}],
            )]
        else:
            output = [ResponseFunctionToolCall(
                id='fc_local', call_id='call_local', type='function_call',
                name='pagar_boleto', arguments='{"boleto_id":"BOL-001"}',
            )]
        return ModelResponse(output=output, usage=Usage(), response_id=None)

    async def stream_response(self, *args, **kwargs):
        raise NotImplementedError
        yield


class RefatoracaoTests(unittest.TestCase):
    def setUp(self):
        self.saldo = estado_financeiro['saldo']
        self.pagos = estado_financeiro['pagamentos_realizados'].copy()
        estado_financeiro['saldo'] = Decimal('350.00')
        estado_financeiro['pagamentos_realizados'].clear()

    def tearDown(self):
        estado_financeiro['saldo'] = self.saldo
        estado_financeiro['pagamentos_realizados'].clear()
        estado_financeiro['pagamentos_realizados'].update(self.pagos)

    def test_plano(self):
        plano = planejar_pagamentos(obter_saldo(), obter_boletos())
        self.assertEqual([b['id'] for b in plano['boletos_selecionados']], ['BOL-001'])
        self.assertEqual([b['id'] for b in plano['boletos_nao_selecionados']], ['BOL-003', 'BOL-002'])
        self.assertEqual(plano['total_pendente'], '522.40')
        self.assertEqual(plano['saldo_restante'], '70.00')
        self.assertFalse(plano['saldo_suficiente'])
        self.assertEqual(estado_financeiro['saldo'], Decimal('350.00'))

    def test_duplicidade_existente(self):
        self.assertTrue(avaliar_pagamento_duplicado())

    def test_hitl_interrompe_e_rejeita_com_sessao(self):
        # O agente de produção permanece com seu modelo configurado.
        agente_local = agent.clone(model=ModeloPagamento())
        contexto = ContextoFinanceiro()
        with tempfile.TemporaryDirectory() as tmp:
            session = SQLiteSession('teste-hitl', str(Path(tmp) / 'sessao.db'))
            try:
                result = Runner.run_sync(
                    agente_local, 'Pague o boleto de energia.', context=contexto,
                    session=session, max_turns=5, run_config=RunConfig(tracing_disabled=True),
                )
                self.assertEqual([i.name for i in result.interruptions], ['pagar_boleto'])
                self.assertEqual(estado_financeiro['saldo'], Decimal('350.00'))
                self.assertEqual(estado_financeiro['pagamentos_realizados'], set())
                with patch('builtins.input', return_value='n'), patch('agents.Runner.run_sync', wraps=Runner.run_sync) as run:
                    # Desabilita apenas a exportação de traces deste teste local.
                    from agents import set_tracing_disabled
                    set_tracing_disabled(True)
                    try:
                        resumed = resolver_aprovacoes(agente_local, result, contexto, session)
                    finally:
                        set_tracing_disabled(False)
                    self.assertEqual(run.call_count, 1)
                self.assertFalse(resumed.interruptions)
                self.assertEqual(estado_financeiro['saldo'], Decimal('350.00'))
                self.assertEqual(estado_financeiro['pagamentos_realizados'], set())
                self.assertTrue(asyncio.run(session.get_items()))
            finally:
                session.close()

    def test_inicio_terminal(self):
        entry = Path(__file__).resolve().parents[1] / 'agent.py'
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run([sys.executable, str(entry)], input='sair\n',
                                    text=True, capture_output=True, cwd=tmp, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('ASSISTENTE FINANCEIRO', result.stdout)
            self.assertIn('Encerrando...', result.stdout)


if __name__ == '__main__':
    unittest.main()
