"""Smoke test HTTPS real da PoC. Nunca aprova ou executa pagamentos."""
import argparse
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[2]


def main():
    service = json.loads((ROOT / '.deploy/aws-service.json').read_text())
    deployment = json.loads((ROOT / '.deploy/aws-deployment.json').read_text())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local', action='store_true', help='Testa somente http://127.0.0.1:18080')
    args = parser.parse_args()
    base = 'http://127.0.0.1:18080' if args.local else service['url'].rstrip('/')
    transport = 'HTTP local' if args.local else 'HTTPS público'
    code = deployment['containers']['finai']['environment']['DEMO_ACCESS_CODE']

    def request(path, payload=None, token=None, headers=None):
        h = {'Content-Type': 'application/json', **(headers or {})}
        if token:
            h['Authorization'] = 'Bearer ' + token
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(base + path, data=data, headers=h)
        with urllib.request.urlopen(req, timeout=100) as response:
            content = response.read().decode()
            if 'text/event-stream' in response.headers.get('Content-Type', ''):
                events = []
                for line in content.splitlines():
                    if line.startswith('data:'):
                        value = line[5:].strip()
                        if value and value != '[DONE]':
                            events.append(json.loads(value))
                if any(event.get('type') == 'error' or event.get('type', '').endswith('.error') for event in events):
                    raise RuntimeError('O stream retornou erro; conferir o backend sem expor credenciais.')
                return events
            return json.loads(content)

    def create_session():
        return request('/session', {}, headers={'X-Demo-Code': code})['token']

    def message(text, token, thread_id=None):
        params = {'input': {'content': [{'type': 'input_text', 'text': text}],
                            'attachments': [], 'inference_options': {}}}
        operation = 'threads.create'
        if thread_id:
            operation = 'threads.add_user_message'
            params['thread_id'] = thread_id
        events = request('/chatkit', {'type': operation, 'params': params}, token)
        if not events:
            raise RuntimeError('O backend não retornou eventos SSE.')
        if thread_id is None:
            thread_id = next(event['thread']['id'] for event in events if event.get('type') == 'thread.created')
        return events, thread_id

    def aprovacao_atual(events):
        def find_action(value):
            if isinstance(value, dict):
                if value.get('type') == 'rejeitar_pagamento' and isinstance(value.get('payload'), dict):
                    return {'type': 'rejeitar_pagamento', 'payload': value['payload']}
                for child in value.values():
                    found = find_action(child)
                    if found:
                        return found
            if isinstance(value, list):
                for child in value:
                    found = find_action(child)
                    if found:
                        return found
            return None
        for event in reversed(events):
            item = event.get('item', {})
            if item.get('type') == 'widget':
                action = find_action(item.get('widget'))
                if action:
                    return {'item_id': item['id'], 'action': action}
        return None

    def assert_saldo(events):
        text = json.dumps(events, ensure_ascii=False)
        if '350,00' not in text and '350.00' not in text:
            raise AssertionError('Saldo inicial não confirmado no widget.')

    token_a, token_b = create_session(), create_session()
    events, thread_a = message('Qual é meu saldo disponível?', token_a)
    assert_saldo(events)
    print('Saldo com LLM e widget via ' + transport + ': OK', flush=True)
    threads_b = request('/chatkit', {'type': 'threads.list', 'params': {'limit': 10, 'order': 'desc'}}, token_b)
    if thread_a in json.dumps(threads_b):
        raise AssertionError('Conversa de outra sessão acessível.')
    print('Conversas isoladas entre sessões: OK', flush=True)
    events, _ = message('Quais boletos estão pendentes?', token_a, thread_a)
    text = json.dumps(events, ensure_ascii=False).lower()
    if not all(word in text for word in ['energia', 'internet']):
        raise AssertionError('Lista de boletos não confirmada.')
    print('Boletos e widget via ' + transport + ': OK', flush=True)
    events, _ = message('Monte um planejamento para pagar meus boletos.', token_a, thread_a)
    text = json.dumps(events, ensure_ascii=False).lower()
    if '70,00' not in text and '70.00' not in text:
        raise AssertionError('Planejamento não confirmado.')
    print('Planejamento com LLM via ' + transport + ': OK', flush=True)
    events, thread_payment = message('Pague meu boleto de energia elétrica.', token_a)
    text = json.dumps(events, ensure_ascii=False)
    if 'aprovar_pagamento' not in text or 'rejeitar_pagamento' not in text:
        raise AssertionError('Widget HITL não confirmado.')
    print('Pagamento interrompido e widget HITL exibido: OK', flush=True)
    approval = aprovacao_atual(events)
    if approval is None:
        raise AssertionError('Identificador da aprovação não encontrado.')
    events = request('/chatkit', {'type': 'threads.custom_action', 'params': {
        'thread_id': thread_payment, **approval}}, token_a)
    if 'rejeitado' not in json.dumps(events, ensure_ascii=False).lower():
        raise AssertionError('Rejeição não confirmada.')
    print('Rejeição e retomada via ' + transport + ': OK', flush=True)
    events, _ = message('Qual é meu saldo disponível?', token_a, thread_payment)
    assert_saldo(events)
    events, _ = message('Qual é meu saldo disponível?', token_b)
    assert_saldo(events)
    print('Saldo preservado após rejeição e segunda sessão independente: OK', flush=True)
    events, thread_many = message('Pague os boletos BOL-001, BOL-002 e BOL-003. Cada pagamento precisa de aprovação humana.', token_a)
    count = 0
    while (approval := aprovacao_atual(events)) is not None:
        count += 1
        if count > 6:
            raise AssertionError('O agente repetiu aprovações após as rejeições.')
        events = request('/chatkit', {'type': 'threads.custom_action', 'params': {
            'thread_id': thread_many, **approval}}, token_a)
    if count < 2:
        raise AssertionError('O teste não exercitou múltiplas aprovações.')
    print(f'Múltiplos pagamentos: {count} rejeições individuais, sem erro SSE: OK', flush=True)
    events, _ = message('Qual é meu saldo disponível?', token_a, thread_many)
    assert_saldo(events)
    print('Nenhum pagamento aprovado automaticamente.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Exceções remotas podem conter detalhes privados: não imprimir o corpo ou headers.
        print('Validação não concluída: ' + type(error).__name__ + '. Revisar diagnóstico privado do backend.')
        raise SystemExit(1)
