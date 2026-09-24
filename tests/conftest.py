import pytest

from contrato import hash_arquivo, hash_titular
from no import No


@pytest.fixture
def no(tmp_path):
    """Nó novo, com dados em pasta temporária e dificuldade baixa para os testes rodarem rápido."""
    return No(str(tmp_path / "dados"), dificuldade=2)


@pytest.fixture
def contas(no):
    admin, est, esa, aluno = (c.endereco for c in no.carteiras)
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


@pytest.fixture
def no_com_emissor(no, contas):
    r = no.enviar(contas["admin"], "AUTORIZAR_EMISSOR", {"endereco": contas["est"], "nome": "UEA — EST"})
    assert r["ok"]
    return no
