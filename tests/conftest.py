import pytest

from contrato import hash_arquivo, hash_titular
from no import CONTAS_PADRAO, No


@pytest.fixture
def no(tmp_path):
    """Nó novo, com dados em pasta temporária e dificuldade baixa para os testes rodarem rápido.

    Atalho de teste: `no.enviar(endereco, tipo, payload)` autentica a conta com a senha
    de demonstração e assina — no app real, a carteira autenticada vem do login.
    """
    n = No(str(tmp_path / "dados"), dificuldade=2)
    senhas = {c.endereco: senha for c, (_, senha) in zip(n.carteiras, CONTAS_PADRAO)}
    enviar_original = n.enviar
    n.autenticada = lambda endereco: n.autenticar(endereco, senhas[endereco])
    n.enviar = lambda endereco, tipo, payload: enviar_original(n.autenticada(endereco), tipo, payload)
    return n


@pytest.fixture
def contas(no):
    """Reitoria (admin), secretarias EST e ESA (emissores no gênesis) e Carlos (sem permissão)."""
    admin, est, esa, aluno = (c.endereco for c in no.carteiras[:4])
    return {"admin": admin, "est": est, "esa": esa, "aluno": aluno}


@pytest.fixture
def cert():
    return {
        "codigo": "UEA-2026-0001",
        "documento_hash": hash_arquivo(b"PDF do diploma da Ana"),
        "titular_hash": hash_titular("Ana Souza", "2021001"),
        "curso": "Sistemas de Informação",
        "carga_horaria": 3200,
        "data_conclusao": "2026-07-15",
    }
