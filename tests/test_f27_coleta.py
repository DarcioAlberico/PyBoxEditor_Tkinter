"""
Testes da F2.7 — os recortes que o modelo não soube ler viram material de treino.

A propriedade central é de **segurança**, e é o que estes testes cobram antes de
qualquer conveniência: o recorte de baixa confiança é, por definição, aquele em
que o modelo errou ou hesitou, e gravá-lo direto em `training_data/<palpite>/`
seria treinar o modelo no próprio erro. Vai para quarentena, e só entra na base
depois que alguém olhar.

É a mesma lição que o `folder_to_char` documenta — devolver "?" em silêncio
"permitiu 127 amostras treinarem a classe errada sem ninguém notar" — e a mesma
que a guarda de sessão do `conftest` protege na base de ocupação.

Rodar sem pytest:      python tests/test_f27_coleta.py
"""

import csv
import itertools
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fitz
import numpy as np

from core import coleta, livro
from core.learner import CharacterLearner, char_to_folder


_serie = itertools.count()


def _recorte(valor=120, lado=20, igual=None):
    """
    Um recorte **diferente a cada chamada**, porque a coleta deduplica (F93).

    `igual=n` devolve sempre o mesmo recorte para o mesmo `n`: é como se
    escreve, aqui, "o mesmo glifo apareceu outra vez na página" — que é o caso
    para o qual a dedução existe.

    A marca fica em blocos de 4x4 e não em pixels soltos: a impressão da dedução
    é o hash do redimensionamento para 32x32, e um pixel isolado pode ser comido
    pela interpolação. São **dois** blocos porque um só dá 61 recortes distintos
    e há teste que pede 250 — o primeiro corte deste ajudante repetiu-se em
    silêncio e derrubou justamente o teste do "sem teto não descarta nada".

    E os valores ficam bem abaixo do fundo (0..60 contra 120) para o recorte
    nunca sair uniforme por acaso: um `Coletor(filtrar=True)` o recusaria por
    falta de contraste, que é um motivo que nenhum destes testes está pedindo.
    """
    marca = next(_serie) if igual is None else igual
    img = np.full((lado, lado), valor, dtype=np.uint8)
    img[:4, :4] = marca % 61
    img[:4, 4:8] = (marca // 61) % 61
    return img


# ----------------------------------------------------------------------
# A quarentena
# ----------------------------------------------------------------------

def test_o_recorte_vai_para_a_quarentena_e_nao_para_a_base():
    """
    **A propriedade que dá sentido à fase.** Gravar o palpite do modelo como
    rótulo em `training_data` é treiná-lo no próprio erro.
    """
    with tempfile.TemporaryDirectory() as tmp:
        base = os.path.join(tmp, "training_data")
        os.makedirs(base)
        c = coleta.Coletor(pasta=os.path.join(tmp, "revisao"))

        c(_recorte(), "o", 0.31, pagina=4)

        assert c.total == 1
        assert os.listdir(base) == [], "escreveu na base de treino sem revisão"
        assert os.path.isdir(os.path.join(tmp, "revisao", char_to_folder("o")))


def test_a_quarentena_e_o_padrao_e_fica_fora_da_base():
    """
    O destino padrão **é** a propriedade de segurança, e por isso é fixado aqui.

    Um coletor construído sem argumento nenhum — que é como a UI o constrói —
    não pode acabar escrevendo em `training_data`: uma pasta que o treino varre
    não pode conter amostra por conferir.
    """
    assert coleta.PASTA_PADRAO != "training_data"
    assert "training_data" not in coleta.PASTA_PADRAO
    assert coleta.Coletor().pasta == coleta.PASTA_PADRAO

    from inspect import signature
    assert signature(coleta.promover).parameters["pasta"].default == coleta.PASTA_PADRAO


def test_o_limiar_decide_o_que_e_guardado():
    """
    Quem filtra é o coletor, não a extração. É o que faz a mesma chamada servir
    para "só os duvidosos" e para "todos, para bater o olho".
    """
    with tempfile.TemporaryDirectory() as tmp:
        duvidosos = coleta.Coletor(pasta=os.path.join(tmp, "a"), limiar=0.5)
        duvidosos(_recorte(), "o", 0.31, 0)
        duvidosos(_recorte(), "o", 0.99, 0)
        assert duvidosos.total == 1, "guardou o que o modelo leu com folga"

        tudo = coleta.Coletor(pasta=os.path.join(tmp, "b"), limiar=None)
        tudo(_recorte(), "o", 0.31, 0)
        tudo(_recorte(), "o", 0.99, 0)
        assert tudo.total == 2, "com limiar None tem de guardar todos"


def test_com_limiar_none_a_extracao_entrega_tudo():
    doc = fitz.open()
    doc.new_page(width=300, height=200).insert_text((30, 40), "abc", fontsize=12)
    with tempfile.TemporaryDirectory() as tmp:
        tudo = coleta.Coletor(pasta=os.path.join(tmp, "tudo"), limiar=None)
        so_maus = coleta.Coletor(pasta=os.path.join(tmp, "maus"), limiar=0.5)
        try:
            p = livro.extrair_pagina(doc[0], lambda r: ("z", 0.99), dpi=150,
                                     conf_minima=0.5, coletor=tudo)
            livro.extrair_pagina(doc[0], lambda r: ("z", 0.99), dpi=150,
                                 conf_minima=0.5, coletor=so_maus)
        finally:
            doc.close()

        assert tudo.total > 0
        assert so_maus.total == 0
        assert p.caracteres > 0, "coletar tudo não pode mexer no texto extraído"


def test_a_pasta_da_quarentena_usa_o_nome_que_a_base_usa():
    """Promover é mover: se os nomes divergissem, não seria."""
    with tempfile.TemporaryDirectory() as tmp:
        c = coleta.Coletor(pasta=os.path.join(tmp, "revisao"))
        for palpite in ("o", "A", "5", ".", "♘", "fi"):
            c(_recorte(), palpite, 0.4, pagina=0)

        for palpite in ("o", "A", "5", ".", "♘", "fi"):
            assert os.path.isdir(os.path.join(tmp, "revisao",
                                              char_to_folder(palpite))), palpite


def test_o_nome_do_arquivo_carrega_confianca_e_pagina():
    """Para ordenar por 'mais duvidoso primeiro' sem abrir o índice."""
    with tempfile.TemporaryDirectory() as tmp:
        c = coleta.Coletor(pasta=os.path.join(tmp, "revisao"))
        caminho = c(_recorte(), "o", 0.37, pagina=41)

        nome = os.path.basename(caminho)
        assert nome.startswith("c037_p0042_"), nome
        assert nome.endswith(".png")


def test_ordenar_por_nome_da_a_fila_do_mais_duvidoso():
    """
    **A ordem prometida tem de ser a que sai** (F93).

    O nome sempre carregou os dois números, e a promessa sempre foi "ordenar
    por mais duvidoso primeiro sem abrir o índice". Com a página na frente,
    porém, clicar em Nome no Explorer dava a ordem do **livro**: o recorte mais
    duvidoso da classe podia estar na página 240, no fim da lista. Este teste é
    a promessa, e não o formato — por isso ordena de verdade em vez de conferir
    prefixo.
    """
    with tempfile.TemporaryDirectory() as tmp:
        c = coleta.Coletor(pasta=os.path.join(tmp, "revisao"))
        # O mais duvidoso está na última página, que é o caso que o formato
        # antigo mandava para o fim da lista.
        c(_recorte(), "o", 0.90, pagina=0)
        c(_recorte(), "o", 0.60, pagina=5)
        c(_recorte(), "o", 0.10, pagina=240)

        pasta = os.path.join(tmp, "revisao", char_to_folder("o"))
        confiancas = [int(n[1:4]) for n in sorted(os.listdir(pasta))]
        assert confiancas == sorted(confiancas), (
            f"a ordem por nome não é a do mais duvidoso: {confiancas}")


def test_o_teto_por_classe_impede_uma_classe_de_inundar():
    with tempfile.TemporaryDirectory() as tmp:
        c = coleta.Coletor(pasta=os.path.join(tmp, "revisao"), max_por_classe=3)
        for _ in range(10):
            c(_recorte(), "o", 0.3, pagina=0)
        c(_recorte(), "s", 0.3, pagina=0)

        assert c.gravados[char_to_folder("o")] == 3
        # Sete candidatos não couberam. Desde a F93 o teto sorteia, então
        # alguns deles entraram no lugar de um anterior em vez de serem
        # ignorados — o que a conta cobra é que os sete estão explicados.
        assert c.ignorados_por_teto + c.trocados_pelo_teto == 7
        assert c.total == 4, "o teto de uma classe não pode calar as outras"
        # E o disco tem de bater com a contagem: o sorteio apaga o que trocou.
        pasta = os.path.join(tmp, "revisao", char_to_folder("o"))
        assert len(os.listdir(pasta)) == 3, os.listdir(pasta)


def test_sem_teto_e_o_padrao_e_ele_nao_descarta_nada():
    """
    **O padrão não pode jogar recorte fora em silêncio.** O teto era 200 fixo no
    código, e quem coleta o livro inteiro para engordar a base quer os ~260 mil:
    o que passou do 200 sumia sem aviso, e recuperá-lo custa rodar a extração de
    novo. Quanto é demais é decisão de quem coleta, não do módulo.
    """
    assert coleta.MAX_POR_CLASSE is None
    assert coleta.Coletor().max_por_classe is None

    with tempfile.TemporaryDirectory() as tmp:
        c = coleta.Coletor(pasta=os.path.join(tmp, "revisao"))
        for _ in range(250):                      # de propósito acima do antigo 200
            c(_recorte(), "o", 0.3, pagina=0)

        assert c.gravados[char_to_folder("o")] == 250
        assert c.ignorados_por_teto == 0


def test_teto_zero_ou_negativo_e_o_mesmo_que_sem_teto():
    """
    Um teto que não deixa passar nada não é teto, é desligar a coleta — e quem
    quer desligá-la não passa coletor nenhum. Sem teto tem **uma** forma de se
    dizer, `None`, senão um `0` vindo de campo em branco grava zero recorte e
    chama isso de limite.
    """
    with tempfile.TemporaryDirectory() as tmp:
        for valor in (0, -1):
            c = coleta.Coletor(pasta=os.path.join(tmp, str(valor)),
                               max_por_classe=valor)
            c(_recorte(), "o", 0.3, pagina=0)

            assert c.max_por_classe is None
            assert c.total == 1, f"teto {valor} calou a coleta"


def test_teto_de_texto_le_o_que_foi_digitado():
    """Em branco é sem teto — é a resposta que o `askinteger` não sabe dar."""
    assert coleta.teto_de_texto("") is None
    assert coleta.teto_de_texto("   ") is None
    assert coleta.teto_de_texto(None) is None
    assert coleta.teto_de_texto("ilimitado") is None
    assert coleta.teto_de_texto(" Sem Limite ") is None
    assert coleta.teto_de_texto("0") is None
    assert coleta.teto_de_texto("150") == 150
    assert coleta.teto_de_texto(" 5.000 ") == 5000, "separador de milhar"


def test_teto_de_texto_recusa_o_que_nao_e_numero():
    """
    Adivinhar aqui é o defeito histórico do `folder_to_char`: um `l` no lugar do
    `1` viraria ilimitado calado, e o disco só contaria a história no fim do
    livro.
    """
    # '²' e '٣' passam no `isdigit` e quebram o `int`: têm de ser recusados aqui.
    for lixo in ("l00", "abc", "-5", "1,5x", "200 recortes", "²", "٣"):
        try:
            coleta.teto_de_texto(lixo)
        except ValueError:
            continue
        raise AssertionError(f"aceitou {lixo!r} como teto")


def test_recorte_vazio_nao_grava_nada():
    with tempfile.TemporaryDirectory() as tmp:
        c = coleta.Coletor(pasta=os.path.join(tmp, "revisao"))
        assert c(np.empty((0, 0), dtype=np.uint8), "o", 0.3, 0) is None
        assert c(None, "o", 0.3, 0) is None
        assert c.total == 0


def test_o_indice_soma_em_vez_de_apagar():
    """A coleta de um segundo livro não pode apagar a do primeiro."""
    with tempfile.TemporaryDirectory() as tmp:
        pasta = os.path.join(tmp, "revisao")
        primeiro = coleta.Coletor(pasta=pasta, origem="livro A")
        primeiro(_recorte(), "o", 0.3, pagina=0)
        primeiro.gravar_indice()

        segundo = coleta.Coletor(pasta=pasta, origem="livro B")
        segundo(_recorte(), "s", 0.4, pagina=1)
        caminho = segundo.gravar_indice()

        with open(caminho, encoding="utf-8-sig", newline="") as f:
            linhas = list(csv.DictReader(f))
        assert len(linhas) == 2
        assert {l["origem"] for l in linhas} == {"livro A", "livro B"}
        assert linhas[0]["palpite"] == "o" and linhas[0]["pagina"] == "1"


def test_sem_recorte_nao_ha_indice():
    with tempfile.TemporaryDirectory() as tmp:
        c = coleta.Coletor(pasta=os.path.join(tmp, "revisao"))
        assert c.gravar_indice() is None
        assert "nenhum" in c.resumo()


# ----------------------------------------------------------------------
# A F93 — a pasta de revisão a serviço de quem revisa
# ----------------------------------------------------------------------

def test_a_mesma_imagem_entra_uma_vez_so():
    """
    **É igualdade, não semelhança.** Dois recortes com a mesma impressão são o
    mesmo tensor 32x32 que a rede recebe: treinar nos dois ensina exatamente o
    que treinar num deles ensina, e na grade de miniaturas a segunda cópia é
    uma chance a menos de o intruso aparecer. Medido num PDF digital, 82,5% da
    pilha era cópia.
    """
    with tempfile.TemporaryDirectory() as tmp:
        c = coleta.Coletor(pasta=os.path.join(tmp, "revisao"))
        for _ in range(50):
            c(_recorte(igual=1), "o", 0.3, pagina=0)

        assert c.total == 1
        assert c.ignorados_por_repeticao == 49
        assert "repetido" in c.resumo(), c.resumo()


def test_a_dedução_nao_encosta_em_recorte_diferente():
    """
    A contrapartida do teste acima, e a que impede a dedução de virar perda: o
    que a rede sabe distinguir tem de chegar inteiro à pasta.
    """
    with tempfile.TemporaryDirectory() as tmp:
        c = coleta.Coletor(pasta=os.path.join(tmp, "revisao"))
        for i in range(20):
            c(_recorte(igual=i), "o", 0.3, pagina=0)

        assert c.total == 20
        assert c.ignorados_por_repeticao == 0


def test_a_dedução_e_por_classe():
    """
    O mesmo desenho em duas classes é duas amostras: a pasta de `o` e a de `c`
    guardam coisas diferentes mesmo quando o recorte é o mesmo — é justamente
    o par que o revisor precisa ver lado a lado.
    """
    with tempfile.TemporaryDirectory() as tmp:
        c = coleta.Coletor(pasta=os.path.join(tmp, "revisao"))
        c(_recorte(igual=7), "o", 0.3, pagina=0)
        c(_recorte(igual=7), "c", 0.3, pagina=0)

        assert c.total == 2
        assert c.ignorados_por_repeticao == 0


def test_o_teto_sorteia_sobre_o_livro_e_nao_pega_as_primeiras_paginas():
    """
    **O defeito que esta troca fecha, medido:** com teto de 30 e
    primeiro-a-chegar, a mediana das classes que encheram era **1 página** —
    a classe inteira saía da primeira página em que apareceu. Sorteando, sobem
    para 8 das 10. O itálico da página 200, o borrado e o quebrado são
    exatamente o que a revisão quer ver, e eram os descartados.
    """
    with tempfile.TemporaryDirectory() as tmp:
        c = coleta.Coletor(pasta=os.path.join(tmp, "revisao"),
                           max_por_classe=10)
        for pagina in range(200):
            c(_recorte(), "o", 0.3, pagina=pagina)

        assert c.total == 10
        pasta = os.path.join(tmp, "revisao", char_to_folder("o"))
        assert len(os.listdir(pasta)) == 10, "sobrou arquivo trocado no disco"

        paginas = sorted(l["pagina"] for l in c.linhas)
        assert max(paginas) > 100, (
            f"o teto ficou com o começo do livro: {paginas}")
        assert len(set(paginas)) == 10, f"páginas repetidas: {paginas}"


def test_o_sorteio_do_teto_e_reproduzivel():
    """
    Amostra aleatória e resultado reproduzível não se opõem: o que o sorteio
    precisa é não depender da ordem das páginas, e não é sortear diferente a
    cada rodada. Sem isto, duas coletas do mesmo livro não se comparam.
    """
    def paginas_coletadas(pasta):
        c = coleta.Coletor(pasta=pasta, max_por_classe=5)
        for pagina in range(60):
            c(_recorte(igual=pagina), "o", 0.3, pagina=pagina)
        return sorted(l["pagina"] for l in c.linhas)

    with tempfile.TemporaryDirectory() as tmp:
        assert (paginas_coletadas(os.path.join(tmp, "a"))
                == paginas_coletadas(os.path.join(tmp, "b")))


def test_o_indice_so_lista_o_que_esta_no_disco():
    """
    O sorteio apaga o arquivo que trocou; o índice tem de esquecê-lo junto.
    Um CSV que aponta para PNG que não existe é pior que um CSV incompleto:
    quem revisa ordena por ele e clica em nada.
    """
    with tempfile.TemporaryDirectory() as tmp:
        pasta = os.path.join(tmp, "revisao")
        c = coleta.Coletor(pasta=pasta, max_por_classe=4)
        for pagina in range(40):
            c(_recorte(), "o", 0.3, pagina=pagina)
        caminho = c.gravar_indice()

        with open(caminho, encoding="utf-8-sig", newline="") as f:
            linhas = list(csv.DictReader(f))
        assert len(linhas) == 4
        for l in linhas:
            assert os.path.exists(os.path.join(pasta, l["arquivo"])), l


def test_o_indice_traz_a_segunda_candidata():
    """
    Quem revisa e acha um recorte na pasta errada quer saber **para onde ele
    ia**. É dado no CSV e não régua: a F47 mediu que a margem não ganha da
    confiança no ponto de operação, e nada aqui a promove a critério.
    """
    with tempfile.TemporaryDirectory() as tmp:
        pasta = os.path.join(tmp, "revisao")
        c = coleta.Coletor(pasta=pasta,
                           detalhar=lambda img: [("o", 0.40), ("c", 0.30),
                                                 ("e", 0.05)])
        c(_recorte(), "o", 0.40, pagina=0)
        caminho = c.gravar_indice()

        with open(caminho, encoding="utf-8-sig", newline="") as f:
            linha = next(iter(csv.DictReader(f)))
        assert linha["segunda"] == "c"
        assert float(linha["p2"]) == 0.30
        assert abs(float(linha["margem"]) - 0.25) < 1e-6


def test_sem_detalhar_o_indice_sai_igual_e_a_coleta_nao_quebra():
    """
    O `detalhar` é opcional e custa uma inferência: quem não o passa — a suíte,
    e qualquer chamada de biblioteca — não pode pagar por ele nem quebrar.
    E se a rede levantar no meio de um livro de 264 páginas, a coleta continua:
    perder a segunda candidata de um recorte não vale perder a coleta inteira.
    """
    def explode(img):
        raise RuntimeError("a rede caiu")

    with tempfile.TemporaryDirectory() as tmp:
        for nome, detalhar in (("sem", None), ("quebrado", explode)):
            c = coleta.Coletor(pasta=os.path.join(tmp, nome), detalhar=detalhar)
            assert c(_recorte(), "o", 0.3, pagina=0) is not None
            caminho = c.gravar_indice()
            with open(caminho, encoding="utf-8-sig", newline="") as f:
                linha = next(iter(csv.DictReader(f)))
            assert linha["segunda"] == ""
            assert linha["palpite"] == "o"


def test_a_porta_esta_desligada_e_o_instrumento_continua_medindo():
    """
    **A hipótese era boa e a medição a derrubou** — e o padrão desta suíte é
    fixar a conclusão, não só o código. Nas 10 páginas rotuladas o melhor corte
    de geometria pega 11 recortes sem caractere e leva **49 caracteres de
    verdade** junto: as medianas de lado, área, tinta e proporção coincidem nos
    dois lados, porque depois da exclusão de diagrama o que sobra sem rótulo é
    texto que o rotulador não rotulou.

    É a mesma decisão da F47 com a margem: o instrumento fica, a conclusão é
    não. Reproduzir: `python medir_coleta.py --varrer`.
    """
    assert coleta.Coletor().filtrar is False, (
        "a porta voltou a ligada sem medição nova — ver F93")

    # E ela continua sabendo dizer o que recusaria, para a próxima medição.
    branco = np.full((20, 20), 200, dtype=np.uint8)
    assert coleta.motivo_de_recusa(branco) == "sem contraste"
    assert coleta.motivo_de_recusa(np.zeros((2, 30), dtype=np.uint8)) == "minúsculo"
    assert coleta.motivo_de_recusa(_recorte()) == ""

    with tempfile.TemporaryDirectory() as tmp:
        c = coleta.Coletor(pasta=os.path.join(tmp, "revisao"), filtrar=True)
        assert c(branco, "o", 0.3, pagina=0) is None
        assert c.recusados == {"sem contraste": 1}
        assert "não eram caractere" in c.resumo(), c.resumo()


def test_o_resumo_explica_todo_recorte_que_nao_ficou():
    """
    **Nada some em silêncio.** É o padrão do módulo desde o teto: um número
    escondido é o que deixaria uma régua mal calibrada varrer um livro inteiro
    sem ninguém notar.
    """
    with tempfile.TemporaryDirectory() as tmp:
        c = coleta.Coletor(pasta=os.path.join(tmp, "revisao"),
                           max_por_classe=2, filtrar=True)
        chegaram = 0
        for _ in range(9):                                   # entram e sobram
            c(_recorte(), "o", 0.3, pagina=0)
            chegaram += 1
        for _ in range(4):                                   # repetidos
            c(_recorte(igual=99), "s", 0.3, pagina=0)
            chegaram += 1
        for _ in range(3):                                   # recusados
            c(np.full((20, 20), 200, dtype=np.uint8), "e", 0.3, pagina=0)
            chegaram += 1

        assert c.total + c.descartados == chegaram, c.resumo()
        for esperado in ("repetido", "não eram caractere", "além do teto"):
            assert esperado in c.resumo(), (esperado, c.resumo())


# ----------------------------------------------------------------------
# A promoção
# ----------------------------------------------------------------------

def test_promover_le_o_rotulo_do_nome_da_pasta():
    """
    É o que faz a revisão ser trabalho de mouse: confirmar é deixar onde está,
    corrigir é arrastar para outra pasta, descartar é apagar.
    """
    with tempfile.TemporaryDirectory() as tmp:
        pasta, base = os.path.join(tmp, "revisao"), os.path.join(tmp, "training_data")
        c = coleta.Coletor(pasta=pasta)
        c(_recorte(90), "o", 0.3, pagina=0)
        c(_recorte(90), "o", 0.3, pagina=1)
        # o usuário corrigiu um: moveu de 'o' para 's'
        origem = os.path.join(pasta, char_to_folder("o"))
        destino = os.path.join(pasta, char_to_folder("s"))
        os.makedirs(destino)
        arquivo = sorted(os.listdir(origem))[0]
        os.rename(os.path.join(origem, arquivo), os.path.join(destino, arquivo))

        r = coleta.promover(pasta, data_dir=base)

        assert r.aprendidos == 2 and r.classes == 2
        assert os.listdir(os.path.join(base, char_to_folder("o")))
        assert os.listdir(os.path.join(base, char_to_folder("s")))


def test_promover_recusa_pasta_com_nome_que_nao_e_rotulo():
    """
    Adivinhar aqui é o defeito histórico: um "?" em silêncio já treinou 127
    amostras na classe errada.
    """
    with tempfile.TemporaryDirectory() as tmp:
        pasta, base = os.path.join(tmp, "revisao"), os.path.join(tmp, "training_data")
        intrusa = os.path.join(pasta, "amostras soltas")
        os.makedirs(intrusa)
        import cv2
        cv2.imwrite(os.path.join(intrusa, "x.png"), _recorte())

        r = coleta.promover(pasta, data_dir=base)

        assert r.aprendidos == 0
        assert "amostras soltas" in r.recusados
        # Nenhuma classe criada. O `.learner_cache.npz` é do próprio learner e
        # não é amostra, então o que se cobra é a ausência de **pasta**.
        classes = [n for n in os.listdir(base)
                   if os.path.isdir(os.path.join(base, n))]
        assert classes == [], f"criou classe a partir de nome inválido: {classes}"


def test_promover_sem_pasta_nao_quebra():
    with tempfile.TemporaryDirectory() as tmp:
        r = coleta.promover(os.path.join(tmp, "nao_existe"),
                            data_dir=os.path.join(tmp, "base"))
        assert r.aprendidos == 0


def test_promover_pode_esvaziar_a_quarentena():
    with tempfile.TemporaryDirectory() as tmp:
        pasta, base = os.path.join(tmp, "revisao"), os.path.join(tmp, "training_data")
        c = coleta.Coletor(pasta=pasta)
        c(_recorte(), "o", 0.3, pagina=0)

        coleta.promover(pasta, data_dir=base, apagar=True)

        assert os.listdir(os.path.join(pasta, char_to_folder("o"))) == []
        assert os.listdir(os.path.join(base, char_to_folder("o")))


# ----------------------------------------------------------------------
# Ligado na extração
# ----------------------------------------------------------------------

def test_a_extracao_entrega_ao_coletor_o_que_reprovou():
    """
    O piso de confiança já derrubava esses caracteres — 3.943 no Chess
    Evolution 1. A fase só para de jogá-los fora.

    **Sem dedução aqui de propósito.** O que se cobra é a ligação entre a
    extração e o coletor — "chegou exatamente o que foi reprovado" —, e com a
    dedução ligada a igualdade viraria `<=`: as letras repetidas da página são,
    para a rede, o mesmo recorte. Isso é o assunto de outro teste.
    """
    doc = fitz.open()
    doc.new_page(width=300, height=200).insert_text((30, 40), "abc def", fontsize=12)
    with tempfile.TemporaryDirectory() as tmp:
        c = coleta.Coletor(pasta=os.path.join(tmp, "revisao"), origem="teste",
                           deduplicar=False)
        try:
            # tudo abaixo do piso: todo caractere é reprovado
            p = livro.extrair_pagina(doc[0], lambda r: ("z", 0.10), dpi=150,
                                     conf_minima=0.5, coletor=c)
        finally:
            doc.close()

        assert p.descartados_por_confianca > 0
        assert c.total == p.descartados_por_confianca, (
            "o coletor não recebeu exatamente os reprovados")
        assert p.caracteres == 0, "caractere reprovado não pode entrar no texto"


def test_sem_coletor_a_extracao_segue_igual():
    doc = fitz.open()
    doc.new_page(width=300, height=200).insert_text((30, 40), "abc", fontsize=12)
    try:
        com = livro.extrair_pagina(doc[0], lambda r: ("z", 0.10), dpi=150,
                                   conf_minima=0.5, coletor=None)
        sem = livro.extrair_pagina(doc[0], lambda r: ("z", 0.10), dpi=150,
                                   conf_minima=0.5)
    finally:
        doc.close()
    assert com.descartados_por_confianca == sem.descartados_por_confianca


def test_o_que_passa_no_piso_nao_e_coletado():
    doc = fitz.open()
    doc.new_page(width=300, height=200).insert_text((30, 40), "abc", fontsize=12)
    with tempfile.TemporaryDirectory() as tmp:
        c = coleta.Coletor(pasta=os.path.join(tmp, "revisao"))
        try:
            livro.extrair_pagina(doc[0], lambda r: ("z", 0.99), dpi=150,
                                 conf_minima=0.5, coletor=c)
        finally:
            doc.close()
        assert c.total == 0, "coletou caractere que o modelo leu com folga"


# ----------------------------------------------------------------------
# O teto na tela
# ----------------------------------------------------------------------

def _janela():
    """MainWindow com o aviso neutralizado, ou (None, None, None) sem display."""
    from tkinter import messagebox, simpledialog
    from conftest import raiz_tk

    raiz = raiz_tk()
    if raiz is None:
        return None, None, None
    originais = (simpledialog.askstring, messagebox.showwarning)
    messagebox.showwarning = lambda t, m, **k: None

    from ui.main_window import MainWindow
    return MainWindow(raiz), raiz, originais


def _fechar(raiz, originais):
    import tkinter as tk
    from tkinter import messagebox, simpledialog

    simpledialog.askstring, messagebox.showwarning = originais
    try:
        raiz.destroy()
    except tk.TclError:
        pass


def test_o_dialogo_do_teto_nao_confunde_em_branco_com_cancelar():
    """
    **São as duas respostas mais opostas que o diálogo aceita**: em branco manda
    gravar tudo, Cancelar manda não rodar. Um `askinteger` devolve o mesmo
    `None` para as duas, e é por isso que o campo é de texto.
    """
    from tkinter import simpledialog

    win, raiz, originais = _janela()
    if win is None:
        return                      # sem display; o resto do arquivo não usa Tk
    try:
        from ui.main_window import MainWindow

        simpledialog.askstring = lambda *a, **k: ""
        assert win._perguntar_teto() is None, "em branco tem de ser sem teto"

        simpledialog.askstring = lambda *a, **k: "ilimitado"
        assert win._perguntar_teto() is None

        simpledialog.askstring = lambda *a, **k: "300"
        assert win._perguntar_teto() == 300

        simpledialog.askstring = lambda *a, **k: None
        assert win._perguntar_teto() is MainWindow.CANCELADO
    finally:
        _fechar(raiz, originais)


def test_teto_invalido_pergunta_de_novo_em_vez_de_derrubar_a_acao():
    """
    O erro aqui é de dedo, e recusar a ação inteira custa reabrir o PDF e a
    pasta. O campo volta com o que foi digitado, para corrigir em vez de redigitar.
    """
    from tkinter import simpledialog

    win, raiz, originais = _janela()
    if win is None:
        return
    try:
        respostas, vistos = iter(["l00", "250"]), []

        def perguntar(titulo, mensagem, **kw):
            vistos.append(kw.get("initialvalue"))
            return next(respostas)

        simpledialog.askstring = perguntar

        assert win._perguntar_teto() == 250
        assert vistos == ["", "l00"], "não devolveu o que foi digitado ao campo"
    finally:
        _fechar(raiz, originais)


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
