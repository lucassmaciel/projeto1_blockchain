"""Integridade da blockchain (núcleo baseado no exemplo do professor)."""
from blockchain import Blockchain


def cadeia(n=3):
    c = Blockchain(2, genesis_data={"tipo": "GENESIS"})
    for i in range(n):
        c.add_block(c.new_block({"i": i}))
    return c


def test_cadeia_nova_e_valida():
    assert cadeia().validate() == (True, None, None)


def test_blocos_encadeados_pelo_hash_anterior():
    c = cadeia()
    for anterior, atual in zip(c.blocks, c.blocks[1:]):
        assert atual.previous_hash == anterior.hash


def test_prova_de_trabalho_gera_hash_com_zeros():
    assert all(b.hash.startswith("00") for b in cadeia().blocks)


def test_adulterar_dados_invalida_a_cadeia():
    c = cadeia()
    c.blocks[2].data["i"] = 999
    assert c.validate() == (False, 2, "hash não confere com o conteúdo (dados adulterados)")


def test_recalcular_hash_de_bloco_adulterado_quebra_o_elo_seguinte():
    c = cadeia()
    c.blocks[1].data["i"] = 999
    c.blocks[1].proof_of_work(2)          # atacante "remina" o bloco adulterado
    valida, indice, motivo = c.validate()
    assert not valida and indice == 2 and "elo quebrado" in motivo


def test_bloco_sem_prova_de_trabalho_e_rejeitado():
    c = cadeia(0)
    b = c.new_block({"x": 1})             # adicionado sem minerar
    c.blocks.append(b)
    valida, indice, motivo = c.validate()
    assert not valida and indice == 1


def test_salvar_e_carregar_preserva_a_cadeia(tmp_path):
    c = cadeia()
    arq = str(tmp_path / "chain.json")
    c.save(arq)
    d = Blockchain.load(arq)
    assert d.validate()[0] and [b.hash for b in d.blocks] == [b.hash for b in c.blocks]
