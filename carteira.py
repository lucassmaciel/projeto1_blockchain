# carteira.py
# Identidade de cada participante da rede: um par de chaves Ed25519.
#  - a chave PRIVADA assina as transações (só o dono tem);
#  - a chave PÚBLICA permite a qualquer um conferir a assinatura;
#  - o ENDEREÇO (0x + 40 hex) é derivado da chave pública, como no Ethereum.
# Obs.: nesta demo local as chaves ficam em dados/carteiras.json, como as
# "contas desbloqueadas" do Ganache/Hardhat. Em produção cada instituição
# guardaria a própria chave privada.
import hashlib
import json
import os

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


def endereco_de(chave_publica_hex):
    return "0x" + hashlib.sha256(bytes.fromhex(chave_publica_hex)).hexdigest()[:40]


def verificar_assinatura(chave_publica_hex, mensagem, assinatura_hex):
    try:
        chave = Ed25519PublicKey.from_public_bytes(bytes.fromhex(chave_publica_hex))
        chave.verify(bytes.fromhex(assinatura_hex), mensagem.encode("utf-8"))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


class Carteira:
    def __init__(self, nome, chave_privada=None):
        self.nome = nome
        self._privada = chave_privada or Ed25519PrivateKey.generate()
        self.chave_publica = self._privada.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
        self.endereco = endereco_de(self.chave_publica)

    def assinar(self, mensagem):
        return self._privada.sign(mensagem.encode("utf-8")).hex()

    def to_dict(self):
        privada = self._privada.private_bytes(
            serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
            serialization.NoEncryption()).hex()
        return {"nome": self.nome, "endereco": self.endereco, "chave_privada": privada}

    @staticmethod
    def from_dict(d):
        return Carteira(d["nome"], Ed25519PrivateKey.from_private_bytes(bytes.fromhex(d["chave_privada"])))


def salvar_carteiras(carteiras, caminho):
    os.makedirs(os.path.dirname(caminho) or ".", exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump([c.to_dict() for c in carteiras], f, ensure_ascii=False, indent=2)


def carregar_carteiras(caminho):
    with open(caminho, encoding="utf-8") as f:
        return [Carteira.from_dict(d) for d in json.load(f)]
