# Z.PAY SDK Python · 0.1.0

Cliente para Python 3.10+, sem dependências de execução, com anotações de tipos. Usa somente a biblioteca padrão. As 46 operações são equivalentes às do SDK JavaScript: Pix, conta/tarifas, doações, checkout, saques, envios Pix, reembolsos, transferências internas, boletos, MEDs, subcontas, splits e cripto Purin.

## Instalação

**Ainda não publicado no PyPI.** Instale a versão publicada no GitHub:

```sh
python -m pip install https://github.com/Felix404snow/zpay-sdk-python/releases/download/v0.1.0/zpay_sdk-0.1.0-py3-none-any.whl
```

Fontes e versões: https://github.com/Felix404snow/zpay-sdk-python.
A partir do código fonte local:

```sh
python -m pip install ./sdk/python
```

Ou instale a distribuição wheel desta versão:

```sh
python -m pip install ./zpay_sdk-0.1.0-py3-none-any.whl
```

O identificador de distribuição preparado é `zpay-sdk`; o módulo importado é `zpay`. Não use `pip install zpay-sdk` como se esta versão já estivesse no registro público.

## Criar Pix

```python
import os
from zpay import ZPay, ZPayError

client = ZPay(os.environ['ZPAY_CLIENT_ID'], os.environ['ZPAY_CLIENT_SECRET'])
payment = client.payments.create({
    'amount': 19.90,
    'payerName': 'Cliente',
    'description': 'Pedido 123',
    'idempotencyKey': 'pedido-123',
})
print(payment['paymentId'], payment.get('copyPaste'))
current = client.payments.get(payment['paymentId'])
```

Use chaves somente no servidor. As respostas são dicionários com os campos originais da API, não objetos com nomes convertidos. Dados enviados mantêm nomes da API: `payerName`, `idempotencyKey`, `requestId` etc.

## Recursos

- `client.account.stats()` e `client.account.fees()`.
- `client.payments.create(dados)`, `.get(id)` e `.payer(id)`.
- `client.donations.list(filtros)` e `.top(filtros)`.
- `client.checkouts.create(dados)` e `.get(id)`.
- `client.withdrawals.create(dados)`, `.get(id_ou_referencia)` e `.list(filtros)`.
- `client.cashouts.create(dados)` e `.get(id)`; `client.refunds.create({'transactionId': id})`.
- `client.transfers.recipient(destino)` e `.create(dados)`.
- `client.boletos.create(dados)`; `client.bill_payments.preview(dados)`, `.create(dados)`, `.list(filtros)`, `.get(id)`.
- `client.meds.list(filtros)` e `.get(id)`.
- `client.subaccounts.create(dados)`, `.list()`, `.get(id)`, `.update(id, dados)`, `.block(id)`, `.unblock(id)`, `.delete(id)`, `.transactions(id, filtros)`, `.fund(id, dados)`, `.transfer(id, dados)`, `.payout(id, dados)`, `.withdraw(id, dados)`.
- `client.splits.create(dados)`, `.pix(dados)`, `.get(id)`.
- `client.crypto.create_payment(dados)`, `.get_payment(payment_id)`, `.balance()`, `.summary()`, `.operation(id)`, `.swap(dados)`, `.withdraw(dados)`.

As assinaturas completas estão em `src/zpay/resources.py`. Filtros de listas usam `page`, `limit`, `status`, `date`, `hour`, `from`, `to` e `when` conforme suporte de cada endpoint.

## LTC e swap

```python
charge = client.crypto.create_payment({
    'requestId': 'ltc-pedido-123', 'amount': 50,
    'currency': 'brl', 'payCurrency': 'ltc',
})
print(charge['payAddress'], charge['payAmount'])

# Execute somente após confirmação do usuário sobre destino, rede e cotação.
swap = client.crypto.swap({
    'requestId': 'swap-pedido-456', 'amount': 100,
    'address': carteira_confirmada_pelo_usuario,
    'confirmNotCoinbase': True, 'acceptProviderRate': True,
    # 'totpCode': codigo_da_conta,
})
print(client.crypto.operation(swap['id']))
```

Recebimentos novos são LTC; swap converte BRL em USDT BEP20, não LTC em USDT. A cotação é definida pela Purin no envio. Custos, KYC, telefone, 2FA, limites e disponibilidade são definidos pela API e conta do provedor. Saldo USDT legado permanece separado.

## Falhas

```python
try:
    result = client.withdrawals.create({'amount': 50, 'idempotencyKey': 'saque-pedido-123'})
except ZPayError as error:
    print(error.status, error.code, error.retry_after)
    if error.outcome_unknown:
        result = client.withdrawals.get('saque-pedido-123')
```

Não há reenvio automático, nem polling ou paginação automática. Salve referências antes do envio. Timeout não significa recusa. HTTP 202 ou `pending` não confirma recebimento. Checkouts/splits não oferecem idempotência de criação nesta versão; reembolsos usam a transação original. Cada método financeiro com campo de referência suportado exige `idempotencyKey` ou `requestId` explícito.

`amount` é em reais, exceto saque LTC. Splits usam campos em centavos conforme a API. O SDK não converte unidades. `base_url` padrão é `https://zpaysolution.com/api/v1`; timeout padrão de 30 segundos. Redirecionamentos são bloqueados. Para testes, injete `transport` no construtor; nunca use chaves reais nos testes.

## Testar

No repositório deste SDK, execute `python -m pip install .` e `python -m unittest discover -s tests -v`. No projeto completo Z.PAY, use `python -m unittest discover -s sdk/python/tests -v`. Os testes usam mocks e servidor HTTP local.
