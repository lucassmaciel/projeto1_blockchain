# block.py
# Bloco da blockchain. Baseado no block_class.py do professor, com dois ajustes:
#  1) os dados do bloco (uma transação) são serializados em JSON canônico
#     (chaves ordenadas), para que o hash seja sempre o mesmo para os mesmos dados;
#  2) o bloco pode ser convertido de/para dicionário, permitindo salvar a cadeia em disco.
import hashlib
import json
import time


def json_canonico(dados):
    """Serialização determinística: mesma entrada -> mesma string -> mesmo hash."""
    return json.dumps(dados, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


class Block:
    def __init__(self, index, timestamp, previous_hash, data, nonce=0, hash=None):
        """
        :param index: posição do bloco na cadeia
        :param timestamp: momento de criação (segundos desde 1970)
        :param previous_hash: hash do bloco anterior (None no gênesis)
        :param data: conteúdo do bloco (dicionário com a transação)
        """
        self.index = index
        self.timestamp = timestamp
        self.previous_hash = previous_hash
        self.data = data
        self.nonce = nonce
        self.hash = hash if hash is not None else self.calculate_hash()

    def calculate_hash(self):
        """SHA-256 sobre índice, timestamp, hash anterior, dados e nonce."""
        conteudo = f"{self.index}{self.timestamp}{self.previous_hash}{json_canonico(self.data)}{self.nonce}"
        return hashlib.sha256(conteudo.encode("utf-8")).hexdigest()

    def proof_of_work(self, difficulty):
        """Prova de trabalho: incrementa o nonce até o hash começar com `difficulty` zeros."""
        alvo = "0" * difficulty
        self.nonce = 0
        self.hash = self.calculate_hash()
        while not self.hash.startswith(alvo):
            self.nonce += 1
            self.hash = self.calculate_hash()

    def to_dict(self):
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "previous_hash": self.previous_hash,
            "data": self.data,
            "nonce": self.nonce,
            "hash": self.hash,
        }

    @staticmethod
    def from_dict(d):
        return Block(d["index"], d["timestamp"], d["previous_hash"], d["data"], d["nonce"], d["hash"])

    def __str__(self):
        return (f"Block #{self.index} [previousHash: {self.previous_hash}, "
                f"timestamp: {time.ctime(self.timestamp)}, nonce: {self.nonce}, "
                f"data: {json_canonico(self.data)}, hash: {self.hash}]")
