"""Testes sem rede: isolamento, autorização e HITL sem aprovação automática."""
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'test-ui'), str(ROOT / 'assistente-organizacao-financeira'),
                str(ROOT / 'assistente-organizacao-financeira/tests')]

from agents import set_tracing_disabled
from chatkit.server import StreamingResult
from chatkit.store import NotFoundError
from chatkit.types import ThreadMetadata, UserMessageItem, Action
import api
from financeiro import (criar_estado_financeiro, estado_financeiro, obter_saldo,
                        obter_boletos, executar_pagamento_simulado)
from servidor_chatkit import ServidorFinanceiro, resultado_ferramenta, titulo_pagamento, widget_boletos
from store_memoria import StoreMemoria
from sessoes_web import SessoesWeb
from configuracao import agent
from test_refatoracao import ModeloPagamento


async def request(path, payload=None, token=None, headers=None, method='POST'):
    """Cliente ASGI mínimo; não requer servidor ou dependência de testes HTTP."""
    sent = []
    consumed = False
    async def receive():
        nonlocal consumed
        if not consumed:
            consumed = True
            return {'type': 'http.request', 'body': json.dumps(payload or {}).encode(), 'more_body': False}
        await asyncio.Event().wait()
    async def send(message):
        sent.append(message)
    h = {**(headers or {})}
    if token:
        h['Authorization'] = 'Bearer ' + token
    scope = {'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.4'},
             'http_version': '1.1', 'method': method, 'scheme': 'http', 'path': path,
             'raw_path': path.encode(), 'query_string': b'', 'root_path': '',
             'headers': [(k.lower().encode(), v.encode()) for k, v in h.items()],
             'client': ('127.0.0.1', 1234), 'server': ('test', 80)}
    await api.app(scope, receive, send)
    start = next(m for m in sent if m['type'] == 'http.response.start')
    body = b''.join(m.get('body', b'') for m in sent if m['type'] == 'http.response.body')
    return start['status'], body, dict(start['headers'])


class PublicacaoTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.registry = SessoesWeb(api.servidor.remover_usuario)
        self.registry_patch = patch.object(api, 'sessoes', self.registry)
        self.registry_patch.start()
        set_tracing_disabled(True)

    async def asyncTearDown(self):
        for sessao in list(self.registry.sessoes.values()):
            api.servidor.remover_usuario(sessao.user_id)
        self.registry_patch.stop()
        set_tracing_disabled(False)

    async def nova_sessao(self):
        status, body, headers = await request('/session')
        self.assertEqual(status, 200)
        self.assertEqual(headers[b'cache-control'], b'no-store')
        return json.loads(body)['token']

    async def test_credencial_e_saude(self):
        self.assertEqual((await request('/session'))[0], 200)
        self.assertEqual((await request('/chatkit'))[0], 401)
        self.assertEqual((await request('/health', method='GET'))[0], 200)

    async def test_estado_isolado_em_tasks_e_threads(self):
        a, b = criar_estado_financeiro(), criar_estado_financeiro()
        async def operar(estado, pagar):
            await asyncio.sleep(0)
            if pagar:
                # Regra pura, sem chamar/autorizar a ferramenta HITL.
                executar_pagamento_simulado('BOL-001', estado)
            return await asyncio.to_thread(obter_saldo, estado)
        self.assertEqual(await asyncio.gather(operar(a, True), operar(b, False)), [70.0, 350.0])
        self.assertEqual(a['pagamentos_realizados'], {'BOL-001'})
        self.assertEqual(b['pagamentos_realizados'], set())
        self.assertEqual(obter_saldo(), float(estado_financeiro['saldo']))

    async def test_conversas_e_acoes_de_outro_usuario_bloqueadas(self):
        ta, tb = await self.nova_sessao(), await self.nova_sessao()
        a, b = self.registry.obter('Bearer ' + ta), self.registry.obter('Bearer ' + tb)
        thread = ThreadMetadata(id='thread_owner', created_at=datetime.now(timezone.utc))
        await api.servidor.store.save_thread(thread, {'user_id': a.user_id})
        self.assertEqual((await api.servidor.store.load_threads(10, None, 'desc', {'user_id': b.user_id})).data, [])
        for op in ['threads.get_by_id', 'threads.custom_action', 'threads.delete']:
            status, _, _ = await request('/chatkit', {'type': op, 'params': {'thread_id': thread.id}}, tb)
            self.assertEqual(status, 404)
        with self.assertRaises(NotFoundError):
            await api.servidor.store.load_thread(thread.id, {'user_id': b.user_id})
        self.assertEqual((await request('/chatkit', {'type': 'threads.list', 'params': {'limit': 10, 'order': 'desc'}}, ta))[0], 200)

    async def test_sse_mantem_estado_isolado_e_libera_lock(self):
        ta, tb = await self.nova_sessao(), await self.nova_sessao()
        a = self.registry.obter('Bearer ' + ta)
        a.estado['saldo'] = Decimal('123.45')
        async def process(body, context):
            async def stream():
                await asyncio.sleep(0)
                yield f'data: {await asyncio.to_thread(obter_saldo, context["estado_financeiro"])}\n\n'.encode()
            return StreamingResult(stream())
        with patch.object(api.servidor, 'process', side_effect=process):
            ra, rb = await asyncio.gather(request('/chatkit', {}, ta), request('/chatkit', {}, tb))
        self.assertEqual(ra[1], b'data: 123.45\n\n')
        self.assertEqual(rb[1], b'data: 350.0\n\n')
        self.assertFalse(a.lock.locked())

    async def test_reinicio_e_expiracao_invalidam_sessoes(self):
        token = await self.nova_sessao()
        sessao = self.registry.obter('Bearer ' + token)
        thread = ThreadMetadata(id='thread_expira', created_at=datetime.now(timezone.utc))
        await api.servidor.store.save_thread(thread, {'user_id': sessao.user_id})
        sessao.criada_em -= self.registry.ttl + 1
        self.assertEqual((await request('/chatkit', {}, token))[0], 401)
        self.assertNotIn(thread.id, api.servidor.store.threads)
        token = await self.nova_sessao()
        self.registry.sessoes.clear()
        self.assertEqual((await request('/chatkit', {}, token))[0], 401)

    async def test_limite_concorrencia_cors_e_payload(self):
        token = await self.nova_sessao()
        sessao = self.registry.obter('Bearer ' + token)
        await sessao.lock.acquire()
        try:
            self.assertEqual((await request('/chatkit', {}, token))[0], 409)
        finally:
            sessao.lock.release()
        self.assertEqual((await request('/chatkit', {'x': 'a' * 262145}, token))[0], 413)
        allowed = await request('/chatkit', headers={'Origin': 'http://localhost:5173',
            'Access-Control-Request-Method': 'POST',
            'Access-Control-Request-Headers': 'authorization,content-type,x-chatkit-client,x-client-version'}, method='OPTIONS')
        blocked = await request('/chatkit', headers={'Origin': 'https://outro.example',
            'Access-Control-Request-Method': 'POST'}, method='OPTIONS')
        self.assertEqual(allowed[0], 200)
        self.assertEqual(allowed[2][b'access-control-allow-origin'], b'http://localhost:5173')
        self.assertIn(b'x-chatkit-client', allowed[2][b'access-control-allow-headers'])
        self.assertEqual(blocked[0], 400)
        sessao.total_requisicoes = 300
        self.assertEqual((await request('/chatkit', {}, token))[0], 429)

    async def test_hitl_widget_rejeicao_e_reenvio_sem_pagamento(self):
        server = ServidorFinanceiro(StoreMemoria())
        ctx = {'user_id': 'usuario-local'}
        thread = ThreadMetadata(id='thread_hitl', created_at=datetime.now(timezone.utc))
        await server.store.save_thread(thread, ctx)
        message = UserMessageItem(id='msg', thread_id=thread.id, created_at=datetime.now(timezone.utc),
                                  content=[{'type': 'input_text', 'text': 'Pague o boleto de energia.'}], inference_options={})
        estado = criar_estado_financeiro()
        modelo_local = agent.clone(model=ModeloPagamento())
        ctx["estado_financeiro"] = estado
        with patch('servidor_chatkit.agent', modelo_local):
            events = [event async for event in server.respond(thread, message, ctx)]
            self.assertTrue(events)
            self.assertIsNotNone(server.conversas[thread.id].estado)
            self.assertIsNotNone(server.conversas[thread.id].widget)
            self.assertEqual(estado['saldo'], Decimal('350.00'))
            rejeicao = Action(type='rejeitar_pagamento', payload={'approval_id': server.conversas[thread.id].aprovacao['approval_id']})
            events = [event async for event in server.action(thread, rejeicao, None, ctx)]
            self.assertTrue(events)
            self.assertIsNone(server.conversas[thread.id].estado)
            self.assertEqual(estado['saldo'], Decimal('350.00'))
            self.assertFalse(estado['pagamentos_realizados'])
            again = [event async for event in server.action(thread, rejeicao, None, ctx)]
            self.assertIn('Não existe uma aprovação', again[0].item.content[0].text)
        server.remover_thread(thread.id)

    async def verificar_multiplas_aprovacoes(self, boletos):
        from agents import ModelResponse, Runner, Usage
        from openai.types.responses import ResponseFunctionToolCall

        class ModeloVariosPagamentos(ModeloPagamento):
            async def get_response(self, *args, **kwargs):
                items = kwargs.get('input', args[1] if len(args) > 1 else [])
                if any(isinstance(i, dict) and i.get('type') == 'function_call_output' for i in items):
                    return await super().get_response(*args, **kwargs)
                calls = [ResponseFunctionToolCall(
                    id=f'fc_{i}', call_id=f'call_{i}', type='function_call', name='pagar_boleto',
                    arguments=json.dumps({'boleto_id': boleto}),
                ) for i, boleto in enumerate(boletos)]
                return ModelResponse(output=calls, usage=Usage(), response_id=None)

        server = ServidorFinanceiro(StoreMemoria())
        ctx = {'user_id': 'usuario-varios'}
        thread = ThreadMetadata(id='thread_varios', created_at=datetime.now(timezone.utc))
        await server.store.save_thread(thread, ctx)
        message = UserMessageItem(id='msg', thread_id=thread.id, created_at=datetime.now(timezone.utc),
                                  content=[{'type': 'input_text', 'text': 'Pague os boletos.'}], inference_options={})
        estado = criar_estado_financeiro()
        ctx["estado_financeiro"] = estado
        with patch('servidor_chatkit.agent', agent.clone(model=ModeloVariosPagamentos())):
            events = [e async for e in server.respond(thread, message, ctx)]
            self.assertTrue(events)
            self.assertEqual(len(server.conversas[thread.id].estado.get_interruptions()), len(boletos))
            stale_action = None
            for i, boleto in enumerate(boletos):
                ativa = server.conversas[thread.id].aprovacao
                self.assertEqual(ativa['boleto']['id'], boleto)
                self.assertEqual(estado['saldo'], Decimal('350.00'))
                self.assertFalse(estado['pagamentos_realizados'])
                # Um clique no widget anterior não pode decidir o pagamento atual.
                if stale_action is not None:
                    with patch('servidor_chatkit.Runner.run', wraps=Runner.run) as runner:
                        replay = [e async for e in server.action(thread, stale_action, None, ctx)]
                        runner.assert_not_called()
                    self.assertIn('não está mais ativa', replay[0].item.content[0].text)
                    self.assertEqual(server.conversas[thread.id].aprovacao['approval_id'], ativa['approval_id'])
                rejection = Action(type='rejeitar_pagamento', payload={'approval_id': ativa['approval_id']})
                events = [e async for e in server.action(thread, rejection, None, ctx)]
                self.assertEqual(events[0].type, 'thread.item.replaced')
                # Simula apenas clique antigo: o branch de aprovação não é alcançado.
                stale_action = Action(type='aprovar_pagamento', payload={'approval_id': ativa['approval_id']})
                if i + 1 < len(boletos):
                    self.assertEqual(len(server.conversas[thread.id].estado.get_interruptions()), len(boletos) - i - 1)
            self.assertIsNone(server.conversas[thread.id].estado)
            self.assertIsNone(server.conversas[thread.id].aprovacao)
            self.assertIsNone(server.conversas[thread.id].widget)
            self.assertEqual(estado['saldo'], Decimal('350.00'))
            self.assertFalse(estado['pagamentos_realizados'])
        server.remover_thread(thread.id)

    async def test_varios_pagamentos_rejeitados_individualmente_sem_erro(self):
        await self.verificar_multiplas_aprovacoes(['BOL-001', 'BOL-002', 'BOL-003'])

    async def test_chamadas_repetidas_do_mesmo_boleto_exigem_decisoes_distintas(self):
        await self.verificar_multiplas_aprovacoes(['BOL-001', 'BOL-001'])

    async def test_acao_sem_identificador_nao_decide_pagamento(self):
        from agents import Runner
        server = ServidorFinanceiro(StoreMemoria())
        ctx = {'user_id': 'usuario-id'}
        thread = ThreadMetadata(id='thread_id', created_at=datetime.now(timezone.utc))
        await server.store.save_thread(thread, ctx)
        message = UserMessageItem(id='msg', thread_id=thread.id, created_at=datetime.now(timezone.utc),
                                  content=[{'type': 'input_text', 'text': 'Pague energia.'}], inference_options={})
        estado = criar_estado_financeiro()
        ctx["estado_financeiro"] = estado
        with patch('servidor_chatkit.agent', agent.clone(model=ModeloPagamento())):
            _ = [e async for e in server.respond(thread, message, ctx)]
            with patch('servidor_chatkit.Runner.run', wraps=Runner.run) as runner:
                _ = [e async for e in server.action(thread, Action(type='aprovar_pagamento'), None, ctx)]
                runner.assert_not_called()
            self.assertIsNotNone(server.conversas[thread.id].estado)
            self.assertEqual(estado['saldo'], Decimal('350.00'))
        server.remover_thread(thread.id)

    async def test_boleto_ja_pago_ainda_tem_metadados_para_widget(self):
        server = ServidorFinanceiro(StoreMemoria())
        ctx = {'user_id': 'usuario-duplicidade'}
        thread = ThreadMetadata(id='thread_duplicidade', created_at=datetime.now(timezone.utc))
        await server.store.save_thread(thread, ctx)
        message = UserMessageItem(id='msg', thread_id=thread.id, created_at=datetime.now(timezone.utc),
                                  content=[{'type': 'input_text', 'text': 'Pague energia.'}], inference_options={})
        estado = criar_estado_financeiro()
        ctx["estado_financeiro"] = estado
        with patch('servidor_chatkit.agent', agent.clone(model=ModeloPagamento())):
            # Prepara o cenário por regra pura; não aprova uma chamada do agente.
            executar_pagamento_simulado('BOL-001', estado)
            events = [e async for e in server.respond(thread, message, ctx)]
            self.assertTrue(events)
            self.assertEqual(server.conversas[thread.id].aprovacao['boleto']['id'], 'BOL-001')
            rejection = Action(type='rejeitar_pagamento', payload={'approval_id': server.conversas[thread.id].aprovacao['approval_id']})
            _ = [e async for e in server.action(thread, rejection, None, ctx)]
            self.assertEqual(estado['saldo'], Decimal('70.00'))
            self.assertEqual(executar_pagamento_simulado('BOL-001', estado)['motivo'], 'Boleto já pago')
        server.remover_thread(thread.id)

    async def test_limite_buscas_reinicia_por_mensagem(self):
        from types import SimpleNamespace
        from resposta_agente import RespostaAgente
        server = ServidorFinanceiro(StoreMemoria())
        ctx = {'user_id': 'usuario-buscas', 'estado_financeiro': criar_estado_financeiro()}
        thread = ThreadMetadata(id='thread_buscas', created_at=datetime.now(timezone.utc))
        await server.store.save_thread(thread, ctx)
        message = UserMessageItem(id='msg', thread_id=thread.id, created_at=datetime.now(timezone.utc),
                                  content=[{'type': 'input_text', 'text': 'Busque boletos.'}], inference_options={})
        contexts = []
        async def run(*args, **kwargs):
            context = kwargs['context']
            self.assertEqual(context.quantidade_buscas, 0)
            context.quantidade_buscas = 2
            contexts.append(context)
            return SimpleNamespace(interruptions=[], new_items=[], final_output=RespostaAgente(tipo='resposta', mensagem='Busca concluída.'))
        with patch('servidor_chatkit.Runner.run', side_effect=run):
            for _ in range(3):
                _ = [e async for e in server.respond(thread, message, ctx)]
        self.assertEqual(len({id(c) for c in contexts}), 3)
        server.remover_thread(thread.id)

    async def test_widgets_saldo_e_boletos_com_tools_reais(self):
        from agents import ModelResponse, Usage
        from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage

        class ModeloConsulta(ModeloPagamento):
            def __init__(self, tool, visualizacao):
                self.tool, self.visualizacao = tool, visualizacao

            async def get_response(self, *args, **kwargs):
                items = kwargs.get('input', args[1] if len(args) > 1 else [])
                if any(isinstance(i, dict) and i.get('type') == 'function_call_output' for i in items):
                    text = json.dumps({'tipo': 'resposta', 'mensagem': 'Consulta concluída.',
                                       'visualizacao': self.visualizacao, 'campo_pendente': None,
                                       'saldo': 999 if self.visualizacao == 'saldo' else None})
                    output = [ResponseOutputMessage(id='msg_consulta', type='message', role='assistant',
                              status='completed', content=[{'type': 'output_text', 'text': text, 'annotations': []}])]
                else:
                    output = [ResponseFunctionToolCall(id='fc_consulta', call_id='call_consulta',
                              type='function_call', name=self.tool, arguments='{}')]
                return ModelResponse(output=output, usage=Usage(), response_id=None)

        for tool, visual in [('consultar_saldo', 'saldo'), ('listar_boletos_pendentes', 'lista_boletos')]:
            server = ServidorFinanceiro(StoreMemoria())
            ctx = {'user_id': 'usuario-widget'}
            thread = ThreadMetadata(id='thread_' + visual, created_at=datetime.now(timezone.utc))
            await server.store.save_thread(thread, ctx)
            message = UserMessageItem(id='msg', thread_id=thread.id, created_at=datetime.now(timezone.utc),
                                      content=[{'type': 'input_text', 'text': 'Consultar'}], inference_options={})
            ctx['estado_financeiro'] = criar_estado_financeiro()
            with patch('servidor_chatkit.agent', agent.clone(model=ModeloConsulta(tool, visual))):
                events = [event async for event in server.respond(thread, message, ctx)]
            self.assertTrue(any(getattr(getattr(e, 'item', None), 'type', '') == 'widget' for e in events))
            if visual == 'saldo':
                rendered = json.dumps([e.model_dump(mode='json') for e in events], ensure_ascii=False)
                self.assertIn('350,00', rendered)
                self.assertNotIn('999', rendered)
            self.assertIsNone(server.conversas[thread.id].estado)
            server.remover_thread(thread.id)

    async def test_falha_no_stream_libera_sessao_sem_repetir_operacao(self):
        token = await self.nova_sessao()
        sessao = self.registry.obter('Bearer ' + token)
        async def process(body, context):
            async def stream():
                yield b'data: inicio\n\n'
                raise RuntimeError('Falha de streaming simulada')
            return StreamingResult(stream())
        with patch.object(api.servidor, 'process', side_effect=process):
            with self.assertRaises(RuntimeError):
                await request('/chatkit', {}, token)
        self.assertFalse(sessao.lock.locked())
        self.assertEqual(sessao.estado['saldo'], Decimal('350.00'))

    async def test_configuracao_runtime_expoe_apenas_valores_publicos(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'segredo-nao-publico',
                                   'DEMO_ACCESS_CODE': 'codigo-nao-publico',
                                   'CHATKIT_DOMAIN_KEY': 'dominio-publico',
                                   'PUBLIC_CHATKIT_API_URL': '/chatkit'}):
            status, body, headers = await request('/config.js', method='GET')
        self.assertEqual(status, 200)
        self.assertIn(b'dominio-publico', body)
        self.assertIn(b'/chatkit', body)
        self.assertNotIn(b'segredo-nao-publico', body)
        self.assertNotIn(b'codigo-nao-publico', body)
        self.assertNotIn(b'OPENAI_API_KEY', body)
        self.assertEqual(headers[b'cache-control'], b'no-store')

    async def test_producao_recusa_configuracao_incompleta(self):
        with patch.dict(os.environ, {'APP_ENV': 'production', 'OPENAI_API_KEY': ''}):
            with self.assertRaises(RuntimeError):
                async with api.lifespan(api.app):
                    pass

    async def test_contexto_nativo_isola_tools_e_conserva_contratos(self):
        from agents.tool_context import ToolContext
        from ContextoFinanceiro import ContextoFinanceiro
        from ferramentas import consultar_saldo, buscar_boletos, pagar_boleto
        a, b = ContextoFinanceiro(), ContextoFinanceiro()
        a.estado['saldo'] = Decimal('123.45')
        resultados = await asyncio.gather(*[
            consultar_saldo.on_invoke_tool(ToolContext(ctx, tool_name='consultar_saldo', tool_call_id=f'consulta-{i}', tool_arguments='{}'), '{}') for i, ctx in enumerate((a, b))
        ])
        self.assertEqual(resultados, [123.45, 350.0])
        self.assertEqual(consultar_saldo.params_json_schema['properties'], {})
        self.assertEqual(set(buscar_boletos.params_json_schema['properties']), {'descricao'})
        self.assertEqual(set(pagar_boleto.params_json_schema['properties']), {'boleto_id'})
        self.assertIs(pagar_boleto.needs_approval, True)
        self.assertEqual(obter_saldo(), float(estado_financeiro['saldo']))

    async def test_confirmacao_visual_exige_sucesso_da_operacao_exata(self):
        # Somente apresentação: não decide ou executa nenhuma chamada financeira.
        self.assertEqual(titulo_pagamento({'status': 'PAGO', 'boleto_id': 'BOL-001'}, 'BOL-001'), 'Pagamento realizado')
        self.assertEqual(titulo_pagamento({'status': 'ERRO', 'motivo': 'Saldo insuficiente'}, 'BOL-001'), 'Pagamento não realizado')
        for output in (None, 'aprovado', {}, {'status': 'PAGO', 'boleto_id': 'BOL-002'}):
            self.assertEqual(titulo_pagamento(output, 'BOL-001'), 'Resultado não confirmado')

    async def test_resultados_associados_por_chamada_sem_parsing(self):
        from agents.items import ToolCallItem, ToolCallOutputItem
        from openai.types.responses import ResponseFunctionToolCall
        from types import SimpleNamespace
        def chamada(nome, call_id):
            return ToolCallItem(agent=agent, raw_item=ResponseFunctionToolCall(
                id=call_id, call_id=call_id, type='function_call', name=nome, arguments='{}'))
        def output(call_id, dados):
            return ToolCallOutputItem(agent=agent, raw_item={'type': 'function_call_output', 'call_id': call_id, 'output': ''}, output=dados)
        boletos = obter_boletos(criar_estado_financeiro())
        result = SimpleNamespace(new_items=[chamada('listar_boletos_pendentes', 'lista'),
            chamada('buscar_boletos', 'busca'), output('lista', boletos), output('busca', [])])
        self.assertIs(resultado_ferramenta(result, 'listar_boletos_pendentes'), boletos)
        self.assertIsNone(resultado_ferramenta(result, 'pagar_boleto', 'inexistente'))
        self.assertEqual(resultado_ferramenta(result, 'buscar_boletos'), [])
        result.new_items.append(output('lista', 'texto sem estrutura'))
        self.assertEqual(resultado_ferramenta(result, 'listar_boletos_pendentes'), 'texto sem estrutura')

    async def test_widget_lista_vazia_e_texto_escapado(self):
        vazio = widget_boletos([]).model_dump_json()
        self.assertIn('0 compromisso(s)', vazio)
        self.assertIn('0,00', vazio)
        boletos = obter_boletos(criar_estado_financeiro())
        boletos[0]['descricao'] = 'Energia "especial" \n residencial'
        rendered = widget_boletos(boletos).model_dump_json()
        self.assertIn('522,40', rendered)
        self.assertIn('especial', rendered)

    async def test_rejeicao_com_falha_consume_decisao_e_invalida_widget(self):
        server = ServidorFinanceiro(StoreMemoria())
        ctx = {'user_id': 'usuario-falha', 'estado_financeiro': criar_estado_financeiro()}
        thread = ThreadMetadata(id='thread_falha', created_at=datetime.now(timezone.utc))
        await server.store.save_thread(thread, ctx)
        message = UserMessageItem(id='msg', thread_id=thread.id, created_at=datetime.now(timezone.utc),
            content=[{'type': 'input_text', 'text': 'Pague energia.'}], inference_options={})
        with patch('servidor_chatkit.agent', agent.clone(model=ModeloPagamento())):
            _ = [e async for e in server.respond(thread, message, ctx)]
            conversa = server.conversas[thread.id]
            action = Action(type='rejeitar_pagamento', payload={'approval_id': conversa.aprovacao['approval_id']})
            # Uma mensagem nova não substitui a operação aguardando decisão.
            pending = [e async for e in server.respond(thread, message, ctx)]
            self.assertIn('aguardando sua decisão', pending[0].item.content[0].text)
            events = []
            with patch('servidor_chatkit.Runner.run', side_effect=RuntimeError('falha simulada')):
                with self.assertRaises(RuntimeError):
                    async for event in server.action(thread, action, None, ctx):
                        events.append(event)
            self.assertEqual(events[0].type, 'thread.item.replaced')
            self.assertEqual(events[0].item.copy_text, 'Resultado não confirmado. Consulte o saldo antes de tentar novamente.')
            self.assertIsNone(conversa.estado)
            with patch('servidor_chatkit.Runner.run') as runner:
                _ = [e async for e in server.action(thread, action, None, ctx)]
                runner.assert_not_called()
            self.assertEqual(ctx['estado_financeiro']['saldo'], Decimal('350.00'))
        server.remover_thread(thread.id)

    async def test_boleto_inexistente_pode_ser_rejeitado_sem_executar(self):
        class ModeloInexistente(ModeloPagamento):
            async def get_response(self, *args, **kwargs):
                resposta = await super().get_response(*args, **kwargs)
                for item in resposta.output:
                    if item.type == 'function_call':
                        item.arguments = '{"boleto_id":"BOL-999"}'
                return resposta
        server = ServidorFinanceiro(StoreMemoria())
        ctx = {'user_id': 'usuario-inexistente', 'estado_financeiro': criar_estado_financeiro()}
        thread = ThreadMetadata(id='thread_inexistente', created_at=datetime.now(timezone.utc))
        await server.store.save_thread(thread, ctx)
        message = UserMessageItem(id='msg', thread_id=thread.id, created_at=datetime.now(timezone.utc),
            content=[{'type': 'input_text', 'text': 'Pague BOL-999.'}], inference_options={})
        with patch('servidor_chatkit.agent', agent.clone(model=ModeloInexistente())):
            _ = [e async for e in server.respond(thread, message, ctx)]
            conversa = server.conversas[thread.id]
            self.assertIn('Não disponível', conversa.widget.model_dump_json())
            action = Action(type='rejeitar_pagamento', payload={'approval_id': conversa.aprovacao['approval_id']})
            _ = [e async for e in server.action(thread, action, None, ctx)]
            self.assertIsNone(conversa.estado)
            # O histórico SQLite continua disponível após a retomada.
            self.assertTrue(await conversa.sessao.get_items())
            _ = [e async for e in server.respond(thread, message, ctx)]
            self.assertIsNone(conversa.estado)
            self.assertEqual(ctx['estado_financeiro']['saldo'], Decimal('350.00'))
        server.remover_thread(thread.id)


if __name__ == '__main__':
    unittest.main()
