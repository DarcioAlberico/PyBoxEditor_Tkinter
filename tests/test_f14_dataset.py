"""
Testes da F1.4 — saneamento da base de treino.

A pasta `training_data/sym_f7` guardava 127 imagens da casa de xadrez "f7".
Como `chr(int("f7"))` levanta ValueError, o código devolvia "?" em silêncio:
127 amostras treinando a classe errada, colidindo com `sym_63`, que é o "?" de
verdade. O treino rodava, reportava acurácia alta e ninguém via nada.

Rodar sem pytest:      python tests/test_f14_dataset.py
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np

from core.learner import (NomeDePastaInvalido, char_to_folder, folder_to_char)
from core.dataset_check import (aplicar_migracao, nome_canonico,
                                planejar_migracao, validar_dataset)


def _base(tmp, conteudo):
    """
    Cria uma base de treino de mentira: {pasta: qtd de PNGs}.

    Grava com PIL, não com cv2.imwrite: no Windows o OpenCV não escreve em
    caminho não-ASCII e devolve False sem levantar erro — e alguns destes
    testes precisam justamente de pastas como 'lower_ä'.
    """
    from PIL import Image
    for k, (pasta, n) in enumerate(conteudo.items()):
        d = os.path.join(tmp, pasta)
        os.makedirs(d, exist_ok=True)
        img = np.full((32, 32), 255, dtype=np.uint8)
        # Um desenho por classe, e não o mesmo quadrado para todas: uma base em
        # que classes diferentes têm a MESMA imagem é contraditória, e a
        # verificação de rótulo contraditório (F7.2) a denuncia com razão.
        img[8:24, 8:24] = 0
        img[2:6, 2 + (k % 6) * 4:6 + (k % 6) * 4] = 0
        for i in range(n):
            Image.fromarray(img).save(os.path.join(d, f"{i:03d}.png"))
    return tmp


# ----------------------------------------------------------------------
# Ida e volta nome <-> caractere
# ----------------------------------------------------------------------

def test_ida_e_volta_dos_casos_normais():
    for ch in ["A", "z", "7", ".", "?", "♔", "ä", "÷"]:
        pasta = char_to_folder(ch)
        assert folder_to_char(pasta) == ch, f"{ch!r} -> {pasta} -> quebrou"


def test_ligadura_alfanumerica():
    """Era o bug: 'f7' caía no ramo hexadecimal porque isalpha() é falso."""
    assert char_to_folder("f7") == "ligature_f7"
    assert folder_to_char("ligature_f7") == "f7"

    assert char_to_folder("fi") == "ligature_fi"
    assert folder_to_char("ligature_fi") == "fi"


def test_ligadura_hexadecimal_ida_e_volta():
    """O TODO antigo devolvia '?' e a largura variável era ambígua."""
    for texto in ["a♔", "♔♕", "é!", "x±y"]:
        pasta = char_to_folder(texto)
        assert pasta.startswith("ligature_hex_")
        assert folder_to_char(pasta) == texto, f"{texto!r} nao voltou"


def test_hex_de_largura_fixa_evita_ambiguidade():
    """Com largura variável, 'ab'+'c' e 'a'+'bc' gerariam o mesmo nome."""
    a = char_to_folder("áé")     # dois caracteres de 2 dígitos hex
    b = char_to_folder("ด")           # um caractere de 3 dígitos hex
    assert a != b
    assert folder_to_char(a) == "áé"
    assert folder_to_char(b) == "ด"


def test_legado_sym_f7():
    """Confirmado olhando as amostras: são a casa de xadrez 'f7'."""
    assert folder_to_char("sym_f7") == "f7"


def test_modo_estrito_denuncia_nome_invalido():
    """Devolver '?' em silêncio foi o que deixou o defeito passar."""
    assert folder_to_char("sym_zzz") == "?"
    try:
        folder_to_char("sym_zzz", strict=True)
    except NomeDePastaInvalido:
        pass
    else:
        raise AssertionError("modo estrito não denunciou o nome inválido")


def test_nome_canonico():
    assert nome_canonico("upper_A") == "upper_A"
    assert nome_canonico("sym_f7") == "ligature_f7", "nome legado devia ser corrigido"
    assert nome_canonico("lower_ä") == "sym_228", "acentuado não é ASCII puro"
    assert nome_canonico("sym_zzz") is None


# ----------------------------------------------------------------------
# Validação
# ----------------------------------------------------------------------

def test_base_saudavel_nao_acusa_nada():
    with tempfile.TemporaryDirectory() as tmp:
        _base(tmp, {"upper_A": 12, "lower_b": 15, "digit_3": 11})
        assert validar_dataset(tmp) == []


def test_detecta_nome_invalido():
    with tempfile.TemporaryDirectory() as tmp:
        _base(tmp, {"sym_zzz": 20, "upper_A": 12})
        problemas = validar_dataset(tmp)
        assert any(p.tipo == "nome_invalido" and p.pasta == "sym_zzz"
                   for p in problemas)
        assert all(p.grave for p in problemas if p.tipo == "nome_invalido")


def test_detecta_colisao_de_caractere():
    """Duas pastas para o mesmo caractere partem a classe em duas."""
    with tempfile.TemporaryDirectory() as tmp:
        _base(tmp, {"lower_ä": 12, "sym_228": 12})
        problemas = validar_dataset(tmp)
        assert any(p.tipo == "colisao" for p in problemas)


def test_detecta_pasta_vazia():
    with tempfile.TemporaryDirectory() as tmp:
        _base(tmp, {"upper_A": 12})
        os.makedirs(os.path.join(tmp, "upper_B"))
        problemas = validar_dataset(tmp)
        assert any(p.tipo == "pasta_vazia" and p.pasta == "upper_B"
                   for p in problemas)


def test_detecta_png_ilegivel():
    with tempfile.TemporaryDirectory() as tmp:
        _base(tmp, {"upper_A": 12})
        with open(os.path.join(tmp, "upper_A", "quebrado.png"), "wb") as f:
            f.write(b"isto nao e um png")
        problemas = validar_dataset(tmp)
        assert any(p.tipo == "png_ilegivel" for p in problemas)


def test_poucas_amostras_e_aviso_nao_erro():
    """Classe rara atrapalha o treino, mas não invalida a base."""
    with tempfile.TemporaryDirectory() as tmp:
        _base(tmp, {"upper_A": 12, "upper_Z": 1})
        problemas = validar_dataset(tmp)
        poucas = [p for p in problemas if p.tipo == "poucas_amostras"]
        assert poucas and not poucas[0].grave


# ----------------------------------------------------------------------
# Migração
# ----------------------------------------------------------------------

def test_migracao_renomeia_nome_legado():
    with tempfile.TemporaryDirectory() as tmp:
        _base(tmp, {"sym_f7": 20, "upper_A": 12})
        aplicar_migracao(tmp, planejar_migracao(tmp))

        assert os.path.isdir(os.path.join(tmp, "ligature_f7"))
        assert not os.path.exists(os.path.join(tmp, "sym_f7"))
        assert len(os.listdir(os.path.join(tmp, "ligature_f7"))) == 20


def test_migracao_mescla_classes_irmas():
    """Nenhuma amostra pode se perder na mesclagem."""
    with tempfile.TemporaryDirectory() as tmp:
        _base(tmp, {"lower_ä": 7, "sym_228": 5})
        aplicar_migracao(tmp, planejar_migracao(tmp))

        assert not os.path.exists(os.path.join(tmp, "lower_ä"))
        assert len(os.listdir(os.path.join(tmp, "sym_228"))) == 12


def test_png_legivel_nao_confunde_caminho_com_corrupcao():
    """
    O bug mais caro desta fase: a primeira versão usava cv2.imread, que falha
    em caminho não-ASCII no Windows. Sete PNGs válidos numa pasta 'lower_ä'
    foram marcados como corrompidos — e apagados.
    """
    from core.dataset_check import png_legivel
    from PIL import Image
    with tempfile.TemporaryDirectory() as tmp:
        d = os.path.join(tmp, "lower_ä")
        os.makedirs(d)
        valido = os.path.join(d, "ok.png")
        Image.fromarray(np.full((32, 32), 255, np.uint8)).save(valido)
        corrompido = os.path.join(d, "ruim.png")
        with open(corrompido, "wb") as f:
            f.write(b"isto nao e um png")

        assert png_legivel(valido) is True,             "PNG válido em pasta não-ASCII marcado como ilegível"
        assert png_legivel(corrompido) is False
        assert cv2.imread(valido, cv2.IMREAD_GRAYSCALE) is None,             "se o OpenCV passou a ler caminho não-ASCII, revisar png_legivel"


def test_ilegivel_vai_para_quarentena_nao_para_o_lixo():
    """Migração que apaga arquivo do usuário tem que errar para o lado seguro."""
    from core.dataset_check import PASTA_QUARENTENA
    with tempfile.TemporaryDirectory() as tmp:
        _base(tmp, {"upper_A": 12})
        with open(os.path.join(tmp, "upper_A", "quebrado.png"), "wb") as f:
            f.write(b"lixo")

        aplicar_migracao(tmp, planejar_migracao(tmp))

        quarentena = os.path.join(tmp, PASTA_QUARENTENA)
        assert os.path.isdir(quarentena)
        assert len(os.listdir(quarentena)) == 1, "o arquivo suspeito foi perdido"


def test_quarentena_nao_conta_como_classe():
    from core.dataset_check import PASTA_QUARENTENA
    with tempfile.TemporaryDirectory() as tmp:
        _base(tmp, {"upper_A": 12})
        os.makedirs(os.path.join(tmp, PASTA_QUARENTENA))
        assert validar_dataset(tmp) == []


def test_migracao_remove_vazias_e_ilegiveis():
    with tempfile.TemporaryDirectory() as tmp:
        _base(tmp, {"upper_A": 12})
        os.makedirs(os.path.join(tmp, "upper_B"))
        with open(os.path.join(tmp, "upper_A", "quebrado.png"), "wb") as f:
            f.write(b"lixo")

        aplicar_migracao(tmp, planejar_migracao(tmp))

        assert not os.path.exists(os.path.join(tmp, "upper_B"))
        assert not os.path.exists(os.path.join(tmp, "upper_A", "quebrado.png"))
        assert len(os.listdir(os.path.join(tmp, "upper_A"))) == 12


def test_migracao_converge():
    """
    Remover o único arquivo de uma pasta a deixa vazia — efeito em cascata que
    a primeira passada não vê. Rodar de novo tem que limpar o resto.
    """
    with tempfile.TemporaryDirectory() as tmp:
        _base(tmp, {"upper_A": 12, "lower_ü": 0})
        os.makedirs(os.path.join(tmp, "lower_ü"), exist_ok=True)
        with open(os.path.join(tmp, "lower_ü", "so_esse.png"), "wb") as f:
            f.write(b"lixo")

        for _ in range(3):
            acoes = planejar_migracao(tmp)
            if not acoes:
                break
            aplicar_migracao(tmp, acoes)

        assert planejar_migracao(tmp) == [], "a migração não convergiu"
        assert validar_dataset(tmp) == []


def test_migracao_e_idempotente():
    with tempfile.TemporaryDirectory() as tmp:
        _base(tmp, {"sym_f7": 20, "upper_A": 12})
        aplicar_migracao(tmp, planejar_migracao(tmp))
        assert planejar_migracao(tmp) == []


# ----------------------------------------------------------------------
# A base real e o modelo já treinado
# ----------------------------------------------------------------------

def test_base_real_esta_sanada():
    real = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "training_data")
    if not os.path.isdir(real):
        return          # base não distribuída com o código
    graves = [p for p in validar_dataset(real, checar_pngs=False) if p.grave]
    assert not graves, f"a base real voltou a ter problemas: {graves[:3]}"


def test_metadado_do_modelo_corrigido():
    """
    "f7" e "?" são classes distintas no modelo em uso.

    O defeito era `sym_f7` treinar 127 imagens da casa "f7" com o rótulo "?",
    colidindo com `sym_63`, que é o "?" de verdade.

    A primeira versão deste teste fixava os índices 79 e 63, que eram os do
    modelo de março. O retreino da F1.3 os moveu — as duas pastas vazias
    deixaram de ocupar índice — e o teste quebrou sem que nada estivesse errado.
    O invariante é a separação das duas classes, não onde elas caem.
    """
    meta_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "model_meta.json")
    if not os.path.isfile(meta_path):
        return
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)

    idx_to_char = meta["idx_to_char"]
    de_f7 = [k for k, v in idx_to_char.items() if v == "f7"]
    de_interrogacao = [k for k, v in idx_to_char.items() if v == "?"]

    assert len(de_f7) == 1, f"'f7' em {len(de_f7)} índices"
    assert len(de_interrogacao) == 1, f"'?' em {len(de_interrogacao)} índices"
    assert de_f7 != de_interrogacao

    assert "sym_f7" not in meta["label_map"]
    assert meta["label_map"]["ligature_f7"] == int(de_f7[0])


def test_metadado_e_lido_como_utf8():
    """
    Era aberto sem encoding, caindo no cp1252 do Windows. Funcionava por acaso
    porque o json.dump padrão escapa tudo em ASCII; bastou gravar o arquivo em
    UTF-8 de verdade para o carregamento do modelo quebrar.
    """
    from core.neural_trainer import NeuralPredictor
    import inspect
    fonte = inspect.getsource(NeuralPredictor.load)
    assert 'encoding="utf-8"' in fonte, "load() voltou a abrir sem encoding"


# ----------------------------------------------------------------------
# F1.1 — o alfabeto de figurinas do domínio
# ----------------------------------------------------------------------

def test_alfabeto_de_figurinas_tem_cinco():
    """
    Trava um achado que custou investigação: a base NÃO está faltando 7 peças.

    Peão não tem letra em notação algébrica ("e4", nunca uma figurina), e o
    livro usa um único conjunto de figurinas para os dois lados — em
    "17...(cavalo)e5 18.(dama)c2 (cavalo)a6 19.(cavalo)c4" o lance 17... é das
    pretas e o 19. das brancas, com o mesmo glifo. Sobram K Q R B N.

    Se alguém "consertar" isto de volta para 12, o filtro de substituição
    volta a ter 7 entradas que nunca casam.
    """
    from core.searchable_pdf import PECAS
    assert PECAS == set("♔♕♖♗♘")
    assert len(PECAS) == 5

    for inalcancavel in "♙♟":          # peões
        assert inalcancavel not in PECAS
    for inalcancavel in "♚♛♜♝♞":   # conjunto "preto"
        assert inalcancavel not in PECAS


def test_modelo_emite_exatamente_essas_figurinas():
    """
    O filtro tem que bater com o que o modelo treinado realmente produz.

    **A conta é por caractere, não por classe**, e a diferença custou uma
    falha: com as ligaduras da SPEC §5.2 item 6 o modelo passou a emitir a
    classe `♗x`, que não é figurina nenhuma como string — mas contém uma. Ler
    classe a classe fazia o teste acusar um filtro incompleto que estava certo,
    e escondia o defeito verdadeiro, que era `searchable_pdf` pular a captura de
    bispo no modo "replace" (ver `tem_peca`).
    """
    from core.searchable_pdf import PECAS
    meta_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "model_meta.json")
    if not os.path.isfile(meta_path):
        return
    with open(meta_path, encoding="utf-8") as f:
        emitiveis = set(json.load(f)["idx_to_char"].values())

    figurinas = {c for classe in emitiveis for c in classe if "♔" <= c <= "♟"}
    assert figurinas == PECAS, (
        f"o modelo emite {sorted(figurinas)} mas o filtro espera {sorted(PECAS)}")


def test_ligadura_com_figurina_conta_como_peca():
    """
    `♗x` é peça para o modo "replace", e é o caso comum: numa captura de bispo o
    glifo encosta no `x` e os dois saem num box só.
    """
    from core.searchable_pdf import PECAS, tem_peca

    assert tem_peca("♗x") and tem_peca("♘")
    assert not tem_peca("fi") and not tem_peca("e4") and not tem_peca("")
    assert all(tem_peca(p) for p in PECAS)


# ----------------------------------------------------------------------
# Execução direta
# ----------------------------------------------------------------------

def _main():
    testes = [(n, o) for n, o in sorted(globals().items())
              if n.startswith("test_") and callable(o)]
    falhas = []
    for nome, fn in testes:
        try:
            fn()
            print(f"  PASS  {nome}")
        except Exception as e:
            falhas.append(nome)
            print(f"  FALHA {nome}\n          {type(e).__name__}: {e}")
    print(f"\n{len(testes) - len(falhas)}/{len(testes)} testes passaram")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(_main())
