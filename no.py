# no.py
# NÓ LOCAL da rede: junta a blockchain (blocos + mineração) ao contrato inteligente.
#
# Fluxo de uma operação:
#   login (autenticar) -> transação assinada -> contrato valida regras
#     -> rejeitada: registrada no log de rejeições, NÃO entra na cadeia
#     -> aceita: vira um bloco, é minerado (PoW), estado atualizado, salvo em disco
#
# IMPORTANTE sobre concorrência: em app.py, este `No` é criado com
# @st.cache_resource — ou seja, é UM ÚNICO objeto compartilhado por TODAS as
# sessões/usuários que acessarem o servidor Streamlit ao mesmo tempo. Por isso:
#   - `self.carteiras` guarda só carteiras BLOQUEADAS (nome/endereço/chave
#     pública — informação pública, segura de expor);
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
    ("Secretaria Acadêmica EST/UEA", "est-2026"),
    ("Secretaria Acadêmica ESA/UEA", "esa-2026"),
    ("Carlos — aluno (sem permissão)", "carlos123"),
]


def _escrever_credenciais_referencia():
    """Escreve secrets/usuarios_demo.json como REFERÊNCIA a partir de CONTAS_PADRAO.
    Este arquivo nunca é lido para obter senha — a fonte da verdade é CONTAS_PADRAO."""
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

        for usuario in self.usuarios:
            if str(usuario.get("tipo", "ALUNO")).upper() != "ALUNO":
                continue
            nome = (usuario.get("nome") or "").strip()
            if not nome:
                continue
            if any(d.get("nome") == nome for d in self._dados_carteiras):
                continue
            carteira = Carteira.criar(nome, str(usuario.get("senha") or ""))
            self._dados_carteiras.append(carteira.to_dict())
            self.carteiras.append(carteira)
            usuario["endereco"] = carteira.endereco
        salvar_carteiras([Carteira.from_dict(d) for d in self._dados_carteiras], self.arq_carteiras)

        self.rejeitadas = []
        if os.path.exists(self.arq_rejeitadas):
            with open(self.arq_rejeitadas, encoding="utf-8") as f:
                self.rejeitadas = json.load(f)

        if os.path.exists(self.arq_cadeia):
            self.restaurar_do_disco()
            if getattr(self, "contrato", None) is not None and self.contrato.admin != self.carteiras[0].endereco:
                self._resetar_demo()
        else:
            self._resetar_demo()

        self._garantir_usuarios_demo()

    def _carregar_ou_criar_carteiras_demo(self):
        if os.path.exists(self.arq_carteiras):
            try:
                dados = carregar_carteiras_bruto(self.arq_carteiras)
                if dados and all(isinstance(d, dict) for d in dados):
                    for d in dados:
                        Carteira.from_dict(d)
                    nomes = [d["nome"] for d in dados]
                    if nomes == [n for n, _ in CONTAS_PADRAO]:
                        return dados
            except (TypeError, ValueError, KeyError):
                pass

        criadas = [Carteira.criar(nome, senha) for nome, senha in CONTAS_PADRAO]
        salvar_carteiras(criadas, self.arq_carteiras)
        return [c.to_dict() for c in criadas]

    def _resetar_demo(self):
        criadas = [Carteira.criar(nome, senha) for nome, senha in CONTAS_PADRAO]
        salvar_carteiras(criadas, self.arq_carteiras)
        self._dados_carteiras = [c.to_dict() for c in criadas]
        self.carteiras = [Carteira.from_dict(d) for d in self._dados_carteiras]

        admin = self.carteiras[0].endereco
        self.cadeia = Blockchain(self.dificuldade, genesis_data={
            "tipo": "GENESIS", "rede": "CertChain UEA", "admin": admin,
            "descricao": "Registro de certificados acadêmicos"})
        self.contrato = ContratoCertificados(admin)
        self.cadeia.save(self.arq_cadeia)

        if os.path.exists(self.arq_rejeitadas):
            with open(self.arq_rejeitadas, "w", encoding="utf-8") as f:
                json.dump([], f)
            self.rejeitadas = []

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
        """Carteira BLOQUEADA (só dados públicos) — usada pela interface para
        mostrar nome/papel. Nunca use o retorno desta função para assinar."""
        return next((c for c in self.carteiras if c.endereco == endereco), None)

    def _garantir_usuarios_demo(self):
        """Cria as permissões iniciais do cenário demo do projeto.

        Em vez de depender de uma transação de autorização no momento do bootstrap,
        o contrato usa o estado inicial do ambiente de demonstração diretamente. Isso
        mantém a lógica real da blockchain intacta e garante que os usuários demo
        recebam os papéis corretos ao iniciar a aplicação.
        """
        if self.contrato.emissores:
            return

        for nome, _ in CONTAS_PADRAO[1:3]:
            carteira = next((c for c in self.carteiras if c.nome == nome), None)
            if carteira is None:
                continue
            self.contrato.emissores[carteira.endereco] = {
                "endereco": carteira.endereco,
                "nome": carteira.nome,
                "ativo": True,
                "autorizado_no_bloco": 0,
                "removido_no_bloco": None,
            }

    def _carregar_usuarios(self):
        if not os.path.exists(self.arq_usuarios):
            usuarios = [{
                "nome": "Carlos — aluno (sem permissão)",
                "matricula": "2026001",
                "senha": "carlos123",
                "tipo": "ALUNO",
            }]
            with open(self.arq_usuarios, "w", encoding="utf-8") as f:
                json.dump(usuarios, f, ensure_ascii=False, indent=2)
            return usuarios

        try:
            with open(self.arq_usuarios, encoding="utf-8") as f:
                usuarios = json.load(f)
            if not isinstance(usuarios, list):
                raise ValueError("arquivo de usuários inválido")
            if not usuarios:
                usuarios = [{
                    "nome": "Carlos — aluno (sem permissão)",
                    "matricula": "2026001",
                    "senha": "carlos123",
                    "tipo": "ALUNO",
                }]
                with open(self.arq_usuarios, "w", encoding="utf-8") as f:
                    json.dump(usuarios, f, ensure_ascii=False, indent=2)
            return usuarios
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            usuarios = [{
                "nome": "Carlos — aluno (sem permissão)",
                "matricula": "2026001",
                "senha": "carlos123",
                "tipo": "ALUNO",
            }]
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
        for dados in self._dados_carteiras:
            carteira = Carteira.from_dict(dados)
            papel = self.contrato.papel(carteira.endereco) if hasattr(self, "contrato") else "SEM PERMISSÃO"
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