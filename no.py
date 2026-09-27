# no.py
# NÓ LOCAL da rede: junta a blockchain (blocos + mineração) ao contrato inteligente.
#
# Fluxo de uma operação:
#   login (autenticar) -> transação assinada -> contrato valida regras
#     -> rejeitada: registrada no log de rejeições, NÃO entra na cadeia
#     -> aceita: vira um bloco, é minerado (PoW), estado atualizado, salvo em disco
#
# IMPORTANTE sobre concorrência: em app.py, este `No` é criado com
# @st.cache_resource, ou seja, é UM ÚNICO objeto compartilhado por TODAS as
# sessões/usuários que acessarem o servidor Streamlit ao mesmo tempo. Por isso:
#   - `self.carteiras` guarda só carteiras BLOQUEADAS (nome/endereço/chave
#     pública, que é informação pública e segura de expor);
#   - `autenticar()` nunca desbloqueia esses objetos compartilhados: ele lê os
#     dados brutos e devolve uma CÓPIA NOVA, que a interface guarda no
#     `st.session_state` daquela sessão específica.
import json
import os
import time
from pathlib import Path

from blockchain import Blockchain
from carteira import Carteira, carregar_carteiras_bruto, salvar_carteiras
from contrato import AUTORIZAR_EMISSOR, ContratoCertificados, ErroContrato
from transacao import criar_transacao

ARQUIVO_CREDENCIAIS = Path(__file__).resolve().parent / "secrets" / "usuarios_demo.json"


CONTAS_PADRAO = [
    ("Reitoria UEA (administrador)", "reitoria123"),
    ("Secretaria Acadêmica EST/UEA", "est123"),
    ("Secretaria Acadêmica ESA/UEA", "esa123"),
    ("Caio", "caio123"),
]

# Alunos que já vêm cadastrados na demonstração. Caio também é a 4ª conta padrão
# (sem permissão no contrato); Lucas ganha a carteira quando o nó sincroniza os alunos.
ALUNOS_PADRAO = [
    {"nome": "Caio", "matricula": "2026001", "senha": "caio123", "tipo": "ALUNO"},
    {"nome": "Lucas", "matricula": "2026002", "senha": "lucas123", "tipo": "ALUNO"},
]


def alunos_padrao():
    return [dict(a) for a in ALUNOS_PADRAO]


def _escrever_credenciais_referencia():
    """Escreve secrets/usuarios_demo.json como REFERÊNCIA a partir de CONTAS_PADRAO.
    Este arquivo nunca é lido para obter senha. A fonte da verdade é CONTAS_PADRAO."""
    ARQUIVO_CREDENCIAIS.parent.mkdir(parents=True, exist_ok=True)
    with open(ARQUIVO_CREDENCIAIS, "w", encoding="utf-8") as f:
        json.dump({"usuarios": [{"nome": nome, "senha": senha} for nome, senha in CONTAS_PADRAO]},
                  f, ensure_ascii=False, indent=2)
    try:
        os.chmod(ARQUIVO_CREDENCIAIS, 0o600)
    except OSError:
        pass


_escrever_credenciais_referencia()


class No:
    def __init__(self, pasta_dados="dados", dificuldade=4):
        self.pasta = pasta_dados
        self.dificuldade = dificuldade
        self.arq_cadeia = os.path.join(pasta_dados, "blockchain.json")
        self.arq_carteiras = os.path.join(pasta_dados, "carteiras.json")
        self.arq_usuarios = os.path.join(pasta_dados, "usuarios.json")
        self.arq_rejeitadas = os.path.join(pasta_dados, "rejeitadas.json")

        os.makedirs(self.pasta, exist_ok=True)

        self.usuarios = self._carregar_usuarios()
        self._dados_carteiras = self._carregar_ou_criar_carteiras_demo()
        self.carteiras = [Carteira.from_dict(d) for d in self._dados_carteiras]

        self.rejeitadas = []
        if os.path.exists(self.arq_rejeitadas):
            with open(self.arq_rejeitadas, encoding="utf-8") as f:
                self.rejeitadas = json.load(f)

        if os.path.exists(self.arq_cadeia) and self._cadeia_compativel():
            self.restaurar_do_disco()
        else:
            self._resetar_demo()

        self._sincronizar_alunos()

    def _sincronizar_alunos(self):
        """Garante uma carteira para cada aluno cadastrado e grava o endereço dela em usuarios.json.
        Roda depois de as carteiras padrão estarem definitivas (inclusive após um reset)."""
        for usuario in self.usuarios:
            if str(usuario.get("tipo", "ALUNO")).upper() != "ALUNO":
                continue
            nome = (usuario.get("nome") or "").strip()
            if not nome:
                continue
            existente = next((d for d in self._dados_carteiras if d.get("nome") == nome), None)
            if existente:
                usuario["endereco"] = existente["endereco"]
                continue
            carteira = Carteira.criar(nome, str(usuario.get("senha") or ""))
            self._dados_carteiras.append(carteira.to_dict())
            self.carteiras.append(carteira)
            usuario["endereco"] = carteira.endereco
        salvar_carteiras([Carteira.from_dict(d) for d in self._dados_carteiras], self.arq_carteiras)
        with open(self.arq_usuarios, "w", encoding="utf-8") as f:
            json.dump(self.usuarios, f, ensure_ascii=False, indent=2)

    def _cadeia_compativel(self):
        """A cadeia salva só é reaproveitada se o gênesis for desta versão (com emissores
        iniciais) e o administrador for a carteira atual; senão, é de uma versão antiga."""
        try:
            genesis = Blockchain.load(self.arq_cadeia).blocks[0].data
        except (OSError, ValueError, KeyError, IndexError):
            return False
        return "emissores_iniciais" in genesis and genesis.get("admin") == self.carteiras[0].endereco

    def _carregar_ou_criar_carteiras_demo(self):
        if os.path.exists(self.arq_carteiras):
            try:
                dados = carregar_carteiras_bruto(self.arq_carteiras)
                if dados and all(isinstance(d, dict) and "chave_privada_cifrada" in d for d in dados):
                    for d in dados:
                        Carteira.from_dict(d)
                    nomes = [d["nome"] for d in dados]
                    if nomes[:len(CONTAS_PADRAO)] == [n for n, _ in CONTAS_PADRAO]:
                        return dados
            except (TypeError, ValueError, KeyError):
                pass

        criadas = [Carteira.criar(nome, senha) for nome, senha in CONTAS_PADRAO]
        salvar_carteiras(criadas, self.arq_carteiras)
        return [c.to_dict() for c in criadas]

    def _resetar_demo(self):
        criadas = [Carteira.criar(nome, senha) for nome, senha in CONTAS_PADRAO]
        alunos = self._dados_carteiras[len(CONTAS_PADRAO):]  # preserva carteiras de alunos cadastrados
        self._dados_carteiras = [c.to_dict() for c in criadas] + alunos
        self.carteiras = [Carteira.from_dict(d) for d in self._dados_carteiras]
        salvar_carteiras(self.carteiras, self.arq_carteiras)

        # O gênesis define o administrador e os emissores iniciais (secretarias EST e ESA).
        # Assim a permissão delas está NA blockchain e sobrevive à reexecução da cadeia.
        admin = self.carteiras[0].endereco
        emissores_iniciais = [{"endereco": c.endereco, "nome": c.nome} for c in self.carteiras[1:3]]
        self.cadeia = Blockchain(self.dificuldade, genesis_data={
            "tipo": "GENESIS", "rede": "CertChain UEA", "admin": admin,
            "emissores_iniciais": emissores_iniciais,
            "descricao": "Registro de certificados acadêmicos"})
        self.contrato = ContratoCertificados(admin, emissores_iniciais)
        self.cadeia.save(self.arq_cadeia)

        if os.path.exists(self.arq_rejeitadas):
            with open(self.arq_rejeitadas, "w", encoding="utf-8") as f:
                json.dump([], f)
            self.rejeitadas = []

    # ------------------------------------------------------------ estado
    @staticmethod
    def reconstruir_estado(cadeia):
        """Reexecuta todas as transações desde o gênesis para obter o estado do contrato."""
        genesis = cadeia.blocks[0].data
        contrato = ContratoCertificados(genesis["admin"], genesis.get("emissores_iniciais", ()))
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
        """Carteira BLOQUEADA (só dados públicos), usada pela interface para
        mostrar nome/papel. Nunca use o retorno desta função para assinar."""
        return next((c for c in self.carteiras if c.endereco == endereco), None)

    def _carregar_usuarios(self):
        if not os.path.exists(self.arq_usuarios):
            usuarios = alunos_padrao()
            with open(self.arq_usuarios, "w", encoding="utf-8") as f:
                json.dump(usuarios, f, ensure_ascii=False, indent=2)
            return usuarios

        try:
            with open(self.arq_usuarios, encoding="utf-8") as f:
                usuarios = json.load(f)
            if not isinstance(usuarios, list):
                raise ValueError("arquivo de usuários inválido")
            if not usuarios:
                usuarios = alunos_padrao()
                with open(self.arq_usuarios, "w", encoding="utf-8") as f:
                    json.dump(usuarios, f, ensure_ascii=False, indent=2)
            return usuarios
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            usuarios = alunos_padrao()
            with open(self.arq_usuarios, "w", encoding="utf-8") as f:
                json.dump(usuarios, f, ensure_ascii=False, indent=2)
            return usuarios

    def registrar_usuario(self, nome, matricula, senha):
        nome = (nome or "").strip()
        matricula = (matricula or "").strip()
        senha = (senha or "").strip()
        if not nome or not matricula or not senha:
            return None

        for usuario in self.usuarios:
            if usuario.get("nome", "").strip().lower() == nome.lower() and str(usuario.get("matricula", "")).strip() == matricula:
                return None

        carteira = Carteira.criar(nome, senha)
        novo = {
            "nome": nome,
            "matricula": matricula,
            "senha": senha,
            "tipo": "ALUNO",
            "endereco": carteira.endereco,
        }
        self.usuarios.append(novo)
        self._dados_carteiras.append(carteira.to_dict())
        self.carteiras.append(carteira)
        with open(self.arq_usuarios, "w", encoding="utf-8") as f:
            json.dump(self.usuarios, f, ensure_ascii=False, indent=2)
        salvar_carteiras([Carteira.from_dict(d) for d in self._dados_carteiras], self.arq_carteiras)
        return novo

    def papel_exibicao(self, endereco):
        """Papel mostrado na interface: contas de aluno aparecem como ALUNO
        (no contrato elas continuam sem permissão para emitir ou revogar)."""
        papel = self.contrato.papel(endereco)
        eh_aluno = any(u.get("endereco") == endereco and str(u.get("tipo", "ALUNO")).upper() == "ALUNO"
                       for u in self.usuarios)
        return "ALUNO" if papel == "SEM PERMISSÃO" and eh_aluno else papel

    def listar_alunos(self):
        return [{
            "nome": u.get("nome"),
            "matricula": u.get("matricula"),
            "senha": u.get("senha"),
            "tipo": u.get("tipo", "ALUNO"),
        } for u in self.usuarios if str(u.get("tipo", "ALUNO")).upper() == "ALUNO"]

    def listar_usuarios(self):
        """Lista os usuários disponíveis para login da aplicação."""
        usuarios = []
        senha_por_nome = {nome: senha for nome, senha in CONTAS_PADRAO}
        for usuario in self.usuarios:
            nome = usuario.get("nome")
            if nome in senha_por_nome:
                continue  # contas padrão (ex.: Caio) são listadas abaixo
            if nome and str(usuario.get("tipo", "ALUNO")).upper() == "ALUNO":
                endereco = usuario.get("endereco")
                if endereco:
                    usuarios.append({
                        "nome": nome,
                        "endereco": endereco,
                        "papel": "ALUNO",
                        "senha": usuario.get("senha"),
                        "matricula": usuario.get("matricula"),
                    })
        vistos = {u["endereco"] for u in usuarios}
        for dados in self._dados_carteiras:
            carteira = Carteira.from_dict(dados)
            if carteira.endereco in vistos:
                continue
            papel = self.papel_exibicao(carteira.endereco) if hasattr(self, "contrato") else "SEM PERMISSÃO"
            usuarios.append({
                "nome": carteira.nome,
                "endereco": carteira.endereco,
                "papel": papel,
                "senha": senha_por_nome.get(carteira.nome) or next((u.get("senha") for u in self.usuarios if u.get("nome") == carteira.nome), None),
                "matricula": next((u.get("matricula") for u in self.usuarios if u.get("nome") == carteira.nome), None),
            })
        return usuarios

    def autenticar_aluno(self, nome, matricula, senha):
        for usuario in self.usuarios:
            if usuario.get("tipo", "ALUNO").upper() != "ALUNO":
                continue
            if usuario.get("nome", "").strip().lower() == str(nome).strip().lower() and str(usuario.get("matricula", "")).strip() == str(matricula).strip() and usuario.get("senha") == str(senha).strip():
                return {"nome": usuario["nome"], "matricula": usuario["matricula"], "tipo": usuario.get("tipo", "ALUNO")}
        return None

    # ------------------------------------------------------------ autenticação
    def autenticar(self, endereco, senha):
        """Tenta logar como `endereco`. Devolve uma carteira DESBLOQUEADA,
        isolada para quem chamou (não é a mesma instância guardada em
        `self.carteiras`, então não afeta outras sessões), ou None se a senha
        estiver errada ou o endereço não existir."""
        dados = next((d for d in self._dados_carteiras if d["endereco"] == endereco), None)
        if not dados:
            return None
        copia = Carteira.from_dict(dados)
        return copia if copia.desbloquear(senha) else None

    # ------------------------------------------------------------ operações
    def enviar(self, carteira_autenticada, tipo, payload):
        """Assina com uma carteira JÁ DESBLOQUEADA (resultado de `autenticar`,
        normalmente vindo de `st.session_state`) e submete a transação."""
        if carteira_autenticada is None or carteira_autenticada.bloqueada:
            return {"ok": False, "regra": "AUTH", "erro": "é preciso estar autenticado para enviar transações"}
        tx = criar_transacao(carteira_autenticada, tipo, payload,
                              self.contrato.proximo_nonce(carteira_autenticada.endereco))
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