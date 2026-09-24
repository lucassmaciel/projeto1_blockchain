# transacao.py
# Uma transação é um pedido assinado para executar uma operação do contrato.
# O que é assinado: tipo + remetente + chave pública + nonce + timestamp + payload.
# Qualquer alteração em qualquer campo invalida a assinatura.
import time

from block import json_canonico

CAMPOS = ("tipo", "remetente", "chave_publica", "nonce", "timestamp", "payload", "assinatura")


def mensagem_para_assinar(tx):
    return json_canonico({k: tx[k] for k in CAMPOS if k != "assinatura"})


def criar_transacao(carteira, tipo, payload, nonce, timestamp=None):
    tx = {
        "tipo": tipo,
        "remetente": carteira.endereco,
        "chave_publica": carteira.chave_publica,
        "nonce": nonce,
        "timestamp": timestamp if timestamp is not None else time.time(),
        "payload": payload,
    }
    tx["assinatura"] = carteira.assinar(mensagem_para_assinar(tx))
    return tx
