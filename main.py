# main.py
# Demonstração em terminal do núcleo da blockchain (equivalente ao main.py do professor).
from blockchain import Blockchain


def main():
    blockchain = Blockchain(4, genesis_data={"tipo": "GENESIS", "descricao": "Bloco gênesis"})
    for texto in ["Tout sur le Bitcoin", "Sylvain Saurel", "https://www.uea.edu.br"]:
        blockchain.add_block(blockchain.new_block({"tipo": "TEXTO", "conteudo": texto}))

    print(blockchain)
    print("\nBlockchain é válida?", "Sim" if blockchain.is_blockchain_valid() else "Não")

    # Adulteração: altera o conteúdo de um bloco já minerado
    blockchain.blocks[2].data["conteudo"] = "Texto adulterado"
    valida, indice, motivo = blockchain.validate()
    print(f"Após adulterar o bloco 2 -> válida? {valida} | bloco {indice}: {motivo}")


if __name__ == "__main__":
    main()
