"""
F7.5 — quem decide vazia/ocupada deixa de ser um limiar.

Era um Otsu sobre a força do resíduo, por diagrama e por cor de casa, e **era o
gargalo da leitura sem que houvesse número que o dissesse**: os 94,5% por casa
da F7.1 misturavam esta decisão com a identificação da peça, e a F7.4 melhorou
só a segunda. Um diagrama saía com FEN legal, sem casa arbitrada, e com um peão
que a leitura não viu e outro que ela inventou.

O que destravou foi o gabarito: as 1.600 casas dos 25 diagramas rotulados,
transcritas à mão em `tests/dados/ocupacao_diagramas.txt`. Com ele medido:

    decisão                                    omissões  falsos+   acerto
    Otsu (F7.1)                                    86       38      92,25%
    melhor limiar possível, com o gabarito         —        —       98,25%
    rede dedicada                                   6        5      99,31%

A linha do meio é a que mandou trocar de abordagem em vez de afinar a que havia.

Estes testes não repetem a medição — ela precisa dos scans, que não vão no git.
Eles travam o que a medição decidiu: o formato e a integridade do gabarito, o
funil montado na ordem certa, e o contrato das duas bases separadas.

Rodar sem pytest:      python tests/test_f75_ocupacao.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pytest

from conftest import mexeu_na_ocupacao
from core import diagrama, treino_diagrama


GABARITO = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "dados", "ocupacao_diagramas.txt")


def _gabarito():
    """{chave do diagrama: [8 fileiras de 8 caracteres]}."""
    saida = {}
    for linha in open(GABARITO, encoding="utf-8"):
        if "=" not in linha or linha.lstrip().startswith("#"):
            continue
        chave, mascara = linha.split("=", 1)
        saida[chave.strip()] = mascara.strip().split("/")
    return saida


# ----------------------------------------------------------------------
# O gabarito — é o ativo, e é o que não pode apodrecer
# ----------------------------------------------------------------------

def test_o_gabarito_existe_e_cobre_os_25_diagramas():
    assert len(_gabarito()) == 25


def test_toda_linha_tem_8_fileiras_de_8_casas():
    """
    Uma fileira com 7 casas desloca o resto do tabuleiro em silêncio.

    Aconteceu na transcrição: um `.` a menos numa fileira, e as casas seguintes
    passaram todas a apontar para a vizinha.
    """
    for chave, fileiras in _gabarito().items():
        assert len(fileiras) == 8, chave
        for i, f in enumerate(fileiras):
            assert len(f) == 8, f"{chave}, fileira {8 - i}: {f!r}"


def test_o_gabarito_so_usa_os_dois_simbolos():
    for chave, fileiras in _gabarito().items():
        assert set("".join(fileiras)) <= {"#", "."}, chave


def test_a_contagem_de_ocupadas_e_a_medida():
    """
    Trava o número que todas as tabelas da F7.5 citam.

    Se ele mudar sem que as tabelas mudem junto, elas passam a descrever outra
    população — que é a forma silenciosa de uma medição virar folclore.
    """
    ocupadas = sum(f.count("#") for fs in _gabarito().values() for f in fs)
    assert (ocupadas, 25 * 64) == (551, 1600)


def test_nenhum_diagrama_tem_mais_de_32_pecas():
    """Piso de sanidade: posição de xadrez não passa de 32 peças."""
    for chave, fileiras in _gabarito().items():
        assert sum(f.count("#") for f in fileiras) <= 32, chave


# ----------------------------------------------------------------------
# O funil: quem decide o quê
# ----------------------------------------------------------------------

def test_residuos_nao_decide_mais_ocupacao():
    """
    `_residuos` devolve só resíduo. O Otsu que sobrou lá dentro serve a uma
    pergunta interna e tolerante — quais casas usar para reestimar o fundo —,
    não à leitura.
    """
    quadros = {(r, c): np.full((48, 48), 200, np.float32)
               for r in range(8) for c in range(8)}
    saida = diagrama._residuos(quadros)
    assert isinstance(saida, dict)
    assert len(saida) == 64
    assert all(isinstance(v, np.ndarray) for v in saida.values())


def test_a_ocupacao_tem_modelo_proprio():
    """Dois arquivos, e não um: as duas perguntas têm bases de origem diferente."""
    assert diagrama.CAMINHO_OCUPACAO != diagrama.CAMINHO_MODELO
    assert diagrama.CAMINHO_OCUPACAO.endswith(".pth")


def test_os_dois_modelos_embarcados_cabem_no_repositorio():
    """
    O `.gitignore` manda `*.pth` para fora e estes dois têm exceção nominal.

    A exceção só se justifica enquanto forem pequenos: são eles que fazem um
    clone novo ler diagramas sem baixar nada.
    """
    total = 0
    for caminho in (diagrama.CAMINHO_MODELO, diagrama.CAMINHO_OCUPACAO):
        if not os.path.isfile(caminho):
            pytest.skip("modelo não construído (rode treinar_diagrama.py)")
        total += os.path.getsize(caminho)
    assert total < 500_000


def test_o_modelo_de_ocupacao_declara_as_duas_classes():
    """
    A coluna do "tem peça" sai do arquivo, e não é fixada em 1.

    Trocar a ordem das duas classes num treino futuro inverteria a leitura
    inteira sem erro nenhum aparecer — é a mesma disciplina do `simbolos` da
    rede das peças (F7.4).
    """
    if not os.path.isfile(diagrama.CAMINHO_OCUPACAO):
        pytest.skip("modelo não construído (rode treinar_diagrama.py)")
    import torch
    d = torch.load(diagrama.CAMINHO_OCUPACAO, map_location="cpu",
                   weights_only=True)
    assert set(d["simbolos"]) == {diagrama.VAZIA, diagrama.OCUPADA}


def test_a_rede_de_ocupacao_recusa_o_modelo_errado(tmp_path, monkeypatch):
    """
    Apontar o caminho da ocupação para o modelo das peças tem de levantar.

    Sem a conferência, as doze saídas seriam lidas como duas e o tabuleiro
    inteiro sairia errado sem sintoma — a família de defeito da F7.3.
    """
    if not os.path.isfile(diagrama.CAMINHO_MODELO):
        pytest.skip("modelo não construído (rode treinar_diagrama.py)")
    monkeypatch.setattr(diagrama, "CAMINHO_OCUPACAO", diagrama.CAMINHO_MODELO)
    diagrama.esquecer_modelo()
    with pytest.raises(diagrama.ModeloAusente, match="ocupação"):
        diagrama._carregar_ocupacao()
    diagrama.esquecer_modelo()


def test_esquecer_modelo_larga_os_dois():
    """Treinar sem fechar o programa tem de valer para as duas redes."""
    diagrama._modelo = ("peças",)
    diagrama._modelo_ocupacao = ("ocupação",)
    diagrama.esquecer_modelo()
    assert diagrama._modelo is None and diagrama._modelo_ocupacao is None


# ----------------------------------------------------------------------
# As duas bases
# ----------------------------------------------------------------------

def test_a_base_de_ocupacao_e_separada_da_de_pecas():
    assert treino_diagrama.PASTA_OCUPACAO != treino_diagrama.PASTA_PADRAO


def test_a_base_de_ocupacao_esta_intacta():
    """
    A suíte não escreve na base de verdade — conferido até este ponto da fila.

    **O que mudou, e por quê.** Isto era uma contagem fixa, `(400, 387)`, e a
    contagem estava errada como instrumento: a base **cresce de propósito**, a
    cada diagrama que o usuário confere (F8.3). Quando esta linha foi trocada
    eram 1.720 casas vazias e 1.116 ocupadas, todas de páginas de verdade —
    Aagaard, Kasparov — e amanhã são mais. Congelar o tamanho fazia a suíte
    reprovar por trabalho bem feito, e o conserto de rotina virava "atualizar o
    número", que é justamente o gesto que deixaria passar a gravação acidental
    contra a qual o teste existe.

    O que não pode mudar é a base **durante a sessão**: o que a suíte encontrou
    ao começar é o que ela tem de deixar no fim. A guarda que cobre a suíte
    inteira está no `conftest`, porque o `test_f83_treino_diagrama.py` roda
    depois deste arquivo; aqui fica o sinal cedo, com o nome que se procura.
    """
    if not os.path.isdir(treino_diagrama.PASTA_OCUPACAO):
        pytest.skip("base de ocupação não instalada")
    gravados, apagados = mexeu_na_ocupacao()
    assert not (gravados or apagados), (
        f"gravados: {gravados}\napagados: {apagados}")


def test_as_classes_da_ocupacao_nao_tem_cor(tmp_path):
    """Casa vazia não é branca nem preta, e a pasta reflete isso."""
    pasta = str(tmp_path / "o")
    r = np.zeros((diagrama.LADO, diagrama.LADO), np.float32)
    treino_diagrama.gravar(r, diagrama.VAZIA, "pag", "a1", pasta)
    treino_diagrama.gravar(r + 50, diagrama.OCUPADA, "pag", "b2", pasta)
    assert os.path.isdir(os.path.join(pasta, "vazia"))
    assert os.path.isdir(os.path.join(pasta, "ocupada"))
    assert not os.path.isdir(os.path.join(pasta, "branca"))


def test_treinar_com_base_propria_nao_toca_a_ocupacao_de_verdade(tmp_path):
    """
    Apontar `pasta` para outro lugar desliga a ocupação, e isso é proteção.

    Sem a regra, um teste com base própria treinaria — e **regravaria** — o
    modelo de ocupação de verdade, no meio da suíte.
    """
    pasta = str(tmp_path / "d")
    r = np.zeros((diagrama.LADO, diagrama.LADO), np.float32)
    for i, s in enumerate("PNBR"):
        for j in range(6):
            treino_diagrama.gravar(r + 20 * i, s, f"p{s}{j}", "a1", pasta)

    relatorio = treino_diagrama.treinar(pasta, str(tmp_path / "m.pth"),
                                        medir=False)
    assert relatorio.destino_ocupacao == ""
    assert relatorio.total_ocupacao == 0


def test_a_ocupacao_treina_quando_a_base_dela_vem_junto(tmp_path):
    pasta = str(tmp_path / "d")
    ocupacao = str(tmp_path / "o")
    r = np.zeros((diagrama.LADO, diagrama.LADO), np.float32)
    for i, s in enumerate("PNBR"):
        for j in range(6):
            treino_diagrama.gravar(r + 20 * i, s, f"p{s}{j}", "a1", pasta)
    for j in range(8):
        treino_diagrama.gravar(r, diagrama.VAZIA, f"v{j}", "a1", ocupacao)
        treino_diagrama.gravar(r + 80, diagrama.OCUPADA, f"v{j}", "b2", ocupacao)

    relatorio = treino_diagrama.treinar(
        pasta, str(tmp_path / "m.pth"), medir=False,
        pasta_ocupacao=ocupacao, destino_ocupacao=str(tmp_path / "o.pth"))
    assert relatorio.total_ocupacao == 16
    assert os.path.isfile(str(tmp_path / "o.pth"))


def test_a_contagem_nao_lista_classe_de_outra_base(tmp_path):
    """
    A impressão digital é a contagem por classe (F7.3).

    Listar em zero as classes da outra base mudaria a impressão de toda base de
    peças que já existe, e o programa passaria a acusar "modelo desatualizado"
    em quem não fez nada.
    """
    pasta = str(tmp_path / "d")
    r = np.zeros((diagrama.LADO, diagrama.LADO), np.float32)
    treino_diagrama.gravar(r, "P", "pag", "a1", pasta)
    conta = treino_diagrama.contagem(pasta)
    assert diagrama.VAZIA not in conta and diagrama.OCUPADA not in conta


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
        except TypeError:
            print(f"  PULA  {nome} (precisa de tmp_path)")
        except Exception as e:
            falhas.append(nome)
            print(f"  FALHA {nome}\n          {type(e).__name__}: {e}")
    print(f"\n{len(testes) - len(falhas)}/{len(testes)} testes passaram")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(_main())
