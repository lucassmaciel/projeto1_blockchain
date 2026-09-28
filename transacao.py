# transacao.py
# Uma transação é o pedido de uma operação ao contrato: quem pediu (remetente),
# o tipo da operação, quando foi pedida e os dados (payload).
# O nó passa a transação pelo contrato e, se ela for aceita, grava no bloco.
import time


def criar_transacao(remetente, tipo, payload, timestamp=None):
    return {
        "tipo": tipo,
        "remetente": remetente,
        "timestamp": timestamp if timestamp is not None else time.time(),
        "payload": payload,
    }
