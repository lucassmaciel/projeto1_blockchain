# blockchain.py
# Cadeia de blocos. Baseado no blockchain.py do professor, com acréscimos:
#  - a validação também confere a prova de trabalho (hash com N zeros)
#    e informa QUAL bloco quebrou a cadeia e POR QUÊ;
#  - a cadeia é salva/carregada de um arquivo JSON, para sobreviver
#    ao reinício da aplicação (blockchain local persistente).
import json
import os
import time

from block import Block


class Blockchain:
    def __init__(self, difficulty=4, genesis_data=None):
        """
        :param difficulty: nº de zeros iniciais exigidos no hash (mineração)
        :param genesis_data: conteúdo do bloco gênesis (ex.: quem é o administrador)
        """
        self.difficulty = difficulty
        self.blocks = []
        if genesis_data is not None:
            self.create_genesis_block(genesis_data)

    # ------------------------------------------------------------ construção
    def create_genesis_block(self, data):
        genesis = Block(0, time.time(), None, data)
        genesis.proof_of_work(self.difficulty)
        self.blocks.append(genesis)

    def latest_block(self):
        return self.blocks[-1]

    def new_block(self, data):
        ultimo = self.latest_block()
        return Block(ultimo.index + 1, time.time(), ultimo.hash, data)

    def add_block(self, block):
        """Minera o bloco (prova de trabalho) e o anexa ao fim da cadeia."""
        if block:
            block.proof_of_work(self.difficulty)
            self.blocks.append(block)
        return block

    # ------------------------------------------------------------ validação
    def _erro_bloco(self, bloco, anterior):
        """Retorna o motivo pelo qual o bloco é inválido, ou None se estiver ok."""
        if anterior is None:
            if bloco.index != 0:
                return "gênesis com índice diferente de 0"
            if bloco.previous_hash is not None:
                return "gênesis não pode ter hash anterior"
        else:
            if anterior.index + 1 != bloco.index:
                return "índice fora de sequência"
            if bloco.previous_hash != anterior.hash:
                return "hash anterior não confere com o bloco anterior (elo quebrado)"
        if bloco.hash != bloco.calculate_hash():
            return "hash não confere com o conteúdo (dados adulterados)"
        if not bloco.hash.startswith("0" * self.difficulty):
            return "prova de trabalho inválida"
        return None

    def validate(self):
        """Percorre a cadeia inteira. Retorna (valida, indice_do_bloco_invalido, motivo)."""
        if not self.blocks:
            return False, None, "cadeia vazia"
        anterior = None
        for bloco in self.blocks:
            motivo = self._erro_bloco(bloco, anterior)
            if motivo:
                return False, bloco.index, motivo
            anterior = bloco
        return True, None, None

    def is_blockchain_valid(self):
        return self.validate()[0]

    # ------------------------------------------------------------ persistência
    def to_dict(self):
        return {"difficulty": self.difficulty, "blocks": [b.to_dict() for b in self.blocks]}

    @staticmethod
    def from_dict(d):
        chain = Blockchain(d["difficulty"])
        chain.blocks = [Block.from_dict(b) for b in d["blocks"]]
        return chain

    def save(self, caminho):
        pasta = os.path.dirname(caminho)
        if pasta:
            os.makedirs(pasta, exist_ok=True)
        tmp = caminho + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        os.replace(tmp, caminho)  # escrita atômica: não corrompe o arquivo se cair no meio

    @staticmethod
    def load(caminho):
        with open(caminho, encoding="utf-8") as f:
            return Blockchain.from_dict(json.load(f))

    def __str__(self):
        return "\n".join(str(b) for b in self.blocks)
