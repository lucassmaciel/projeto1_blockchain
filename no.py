# no.py
# NÓ LOCAL da rede: junta a blockchain (blocos + mineração) ao contrato inteligente.
#
# Fluxo de uma operação:
#   interface -> transação assinada -> contrato valida regras
#       -> rejeitada: registrada no log de rejeições, NÃO entra na cadeia
#       -> aceita:    vira um bloco, é minerado (PoW), estado atualizado, salvo em disco
import json
import os
import time

from blockchain import Blockchain
from carteira import Carteira, carregar_carteiras, salvar_carteiras
from contrato import ContratoCertificados, ErroContrato
from transacao import criar_transacao

CONTAS_PADRAO = [
    "Reitoria UEA (administrador)",
    "Secretaria Acadêmica EST/UEA",
    "Secretaria Acadêmica ESA/UEA",
    "Carlos — aluno (sem permissão)",
]


class No:
    def __init__(self, pasta_dados="dados", dificuldade=4):
        self.pasta = pasta_dados
        self.dificuldade = dificuldade
        self.arq_cadeia = os.path.join(pasta_dados, "blockchain.json")
        self.arq_carteiras = os.path.join(pasta_dados, "carteiras.json")
        self.arq_rejeitadas = os.path.join(pasta_dados, "rejeitadas.json")

        if os.path.exists(self.arq_carteiras):
            self.carteiras = carregar_carteiras(self.arq_carteiras)
        else:
            self.carteiras = [Carteira(nome) for nome in CONTAS_PADRAO]
            salvar_carteiras(self.carteiras, self.arq_carteiras)

        self.rejeitadas = []
        if os.path.exists(self.arq_rejeitadas):
            with open(self.arq_rejeitadas, encoding="utf-8") as f:
                self.rejeitadas = json.load(f)

        if os.path.exists(self.arq_cadeia):
            self.restaurar_do_disco()
        else:
            admin = self.carteiras[0].endereco
            self.cadeia = Blockchain(dificuldade, genesis_data={
                "tipo": "GENESIS", "rede": "CertChain UEA", "admin": admin,
                "descricao": "Registro de certificados acadêmicos"})
            self.contrato = ContratoCertificados(admin)
            self.cadeia.save(self.arq_cadeia)

    # ------------------------------------------------------------ estado
    @staticmethod
    def reconstruir_estado(cadeia):
        """Reexecuta todas as transações desde o gênesis para obter o estado do contrato."""
        contrato = ContratoCertificados(cadeia.blocks[0].data["admin"])
        for bloco in cadeia.blocks[1:]:
            contrato.executar(bloco.data, bloco.index)
        return contrato

    def restaurar_do_disco(self):
        self.cadeia = Blockchain.load(self.arq_cadeia)
        valida, indice, motivo = self.cadeia.validate()
        if not valida:
            raise RuntimeError(f"Arquivo da blockchain corrompido no bloco {indice}: {motivo}")
        self.contrato = self.reconstruir_estado(self.cadeia)

    def carteira(self, endereco):
        return next((c for c in self.carteiras if c.endereco == endereco), None)

    # ------------------------------------------------------------ operações
    def enviar(self, endereco_remetente, tipo, payload):
        """Assina com a carteira local indicada e submete (conveniência para a interface)."""
        carteira = self.carteira(endereco_remetente)
        tx = criar_transacao(carteira, tipo, payload, self.contrato.proximo_nonce(carteira.endereco))
        return self.submeter(tx)

    def submeter(self, tx):
        """Submete uma transação já assinada. Retorna dict com ok/bloco ou ok/erro."""
        valida, indice, motivo = self.cadeia.validate()
        if not valida:
            return self._rejeitar(tx, "N1", f"nó recusou: blockchain corrompida no bloco {indice} ({motivo})")
        bloco = self.cadeia.new_block(tx)
        try:
            self.contrato.executar(tx, bloco.index)
        except ErroContrato as e:
            return self._rejeitar(tx, e.regra, e.mensagem)
        inicio = time.time()
        self.cadeia.add_block(bloco)  # mineração (prova de trabalho)
        self.cadeia.save(self.arq_cadeia)
        return {"ok": True, "bloco": bloco.to_dict(), "tempo_mineracao": time.time() - inicio}

    def _rejeitar(self, tx, regra, mensagem):
        registro = {"timestamp": time.time(), "tipo": tx.get("tipo") if isinstance(tx, dict) else None,
                    "remetente": tx.get("remetente") if isinstance(tx, dict) else None,
                    "regra": regra, "motivo": mensagem}
        self.rejeitadas.append(registro)
        with open(self.arq_rejeitadas, "w", encoding="utf-8") as f:
            json.dump(self.rejeitadas, f, ensure_ascii=False, indent=2)
        return {"ok": False, "regra": regra, "erro": mensagem}

    # ------------------------------------------------------------ demonstração
    def adulterar_bloco(self, indice, campo, valor):
        """APENAS PARA DEMONSTRAÇÃO: altera um bloco em memória para mostrar que a validação detecta."""
        self.cadeia.blocks[indice].data["payload"][campo] = valor
