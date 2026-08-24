"""
Testes da F2.6 — o livro lido só do nosso OCR, e exportado.

Esta fase é a primeira que **ignora a camada de texto do PDF**. As outras
trabalham sobre ela; aqui a página é lida como imagem e o que sai é EPUB ou
DOCX. O que os testes fixam são as decisões que a medição forçou, cada uma
descoberta por um estrago concreto no Yusupov:

  - o retângulo do tabuleiro cresce antes de excluir, senão os rótulos `a`–`h`
    viram linhas de um caractere;
  - o respingo é cortado por **área**, e não por altura, senão o livro sai sem
    pontuação;
  - a página que é imagem sai inteira como figura, senão custa 160 s e devolve
    ruído.

Rodar sem pytest:      python tests/test_f26_livro.py
"""

import os
import sys
import tempfile
import time
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fitz
import numpy as np
from PIL import Image

from core import exportar, livro
from core.box_model import BoxEntry
from core.services.box_service import BoxService


# ----------------------------------------------------------------------
# Apoio
# ----------------------------------------------------------------------

def _classificador(char="a", confianca=0.99):
    """
    Responde sempre o mesmo. O modelo de verdade não entra na suíte.

    Serve porque o que estes testes medem é a **montagem** — onde quebra a
    linha, onde entra o espaço, o que é excluído —, e não o reconhecimento.
    """
    return lambda recorte: (char, confianca)


def _pagina(texto_linhas=("Uma linha de prosa comum.",), diagrama=False,
            largura=300, altura=400, rotulos=False, legenda=""):
    """
    Uma página PDF com texto e, se pedido, um quadrado do tamanho de um tabuleiro.

    `rotulos` põe as letras `a`–`h` e os números `8`–`1` em volta dele, como o
    livro impresso faz — é o que `coordenadas="auto"` da F95 vai buscar. E
    `legenda` põe uma linha logo abaixo da borda, que é onde o Nunn imprime o
    número do diagrama.
    """
    doc = fitz.open()
    p = doc.new_page(width=largura, height=altura)
    for i, linha in enumerate(texto_linhas):
        p.insert_text((30, 40 + i * 16), linha, fontsize=10)
    if diagrama:
        # Quase quadrado e grande, que é o que o `localizar` procura. Hachurado
        # por dentro para gerar contorno como um tabuleiro de verdade.
        p.draw_rect(fitz.Rect(40, 150, 200, 310), width=2)
        for j in range(8):
            for k in range(8):
                if (j + k) % 2:
                    p.draw_rect(fitz.Rect(40 + j * 20, 150 + k * 20,
                                          60 + j * 20, 170 + k * 20),
                                fill=(0.75, 0.75, 0.75))
        if rotulos:
            for j, ch in enumerate("abcdefgh"):
                p.insert_text((47 + j * 20, 320), ch, fontsize=8)
            for k, ch in enumerate("87654321"):
                p.insert_text((32, 165 + k * 20), ch, fontsize=8)
        if legenda:
            p.insert_text((45, 322), legenda, fontsize=8)
    return doc


def _cinza(page, dpi=150):
    return livro._pagina_cinza(page, dpi)


# ----------------------------------------------------------------------
# O ponto de entrada do BoxService
# ----------------------------------------------------------------------

def test_o_estagio_de_antes_do_descarte_ainda_tem_o_tabuleiro():
    """
    É a razão de o ponto de entrada existir: o descarte da F1.8 joga fora o
    contorno grande do tabuleiro, e é justamente ele que o `diagrama.localizar`
    procura.
    """
    doc = _pagina(diagrama=True)
    try:
        img = Image.fromarray(_cinza(doc[0]))
        antes, _th, escala, _cinza_arr = BoxService.boxes_antes_do_descarte(img)
        depois = BoxService.generate_boxes_opencv(img)
    finally:
        doc.close()

    def maior(boxes):
        return max((b.x2 - b.x1) * (b.y2 - b.y1) for b in boxes) if boxes else 0

    assert antes, "o estágio anterior ao descarte veio vazio"
    assert maior(antes) > maior(depois) * 4, (
        "o bloco grande do tabuleiro deveria estar antes do descarte e não depois")
    assert escala > 0


def test_o_ponto_de_entrada_e_o_mesmo_caminho_do_generate():
    """
    Se as duas rotas divergirem, o diagrama passa a ser procurado num estágio
    que não é o que o resto do pipeline produz — que foi o defeito que este
    ponto de entrada veio consertar.
    """
    doc = _pagina(texto_linhas=("Prosa numa linha.", "E outra linha aqui."))
    try:
        img = Image.fromarray(_cinza(doc[0]))
        antes, _th, escala, _c = BoxService.boxes_antes_do_descarte(img)
        completo = BoxService.generate_boxes_opencv(img)
    finally:
        doc.close()

    # tudo que sobreviveu ao descarte tem de estar no estágio anterior
    caixas_antes = {(b.x1, b.y1, b.x2, b.y2) for b in antes}
    faltando = [b for b in completo
                if (b.x1, b.y1, b.x2, b.y2) not in caixas_antes]
    assert len(faltando) <= len(completo) * 0.2, (
        "o estágio anterior não contém o que o caminho completo devolve")


def test_pagina_com_contorno_demais_devolve_vazio():
    """
    Era: 160 segundos numa página só.

    O `merge_vertical_boxes` é quadrático. Medido no Yusupov a 300 dpi, a
    página 11 dá 2.131 contornos e 0,4 s; a página 8, que é quase toda imagem,
    dá 78.558 e **160 s**.
    """
    ruido = np.random.default_rng(7).integers(0, 255, (300, 300), dtype=np.uint8)
    img = Image.fromarray(ruido)

    vazio, _th, _e, _c = BoxService.boxes_antes_do_descarte(img, max_contornos=50)
    assert vazio == []

    cheio, _th, _e, _c = BoxService.boxes_antes_do_descarte(img, max_contornos=None)
    assert cheio, "sem limite, a página deveria devolver as caixas"


# ----------------------------------------------------------------------
# Extração
# ----------------------------------------------------------------------

def test_o_texto_da_pagina_vira_paragrafo():
    doc = _pagina(texto_linhas=("Primeira linha da prosa.",
                                "Segunda linha da mesma prosa."))
    try:
        p = livro.extrair_pagina(doc[0], _classificador("x"), dpi=150)
    finally:
        doc.close()

    paragrafos = [b for b in p.blocos if isinstance(b, livro.Paragrafo)]
    assert paragrafos, "nenhum parágrafo saiu da página"
    assert p.caracteres > 0
    assert not p.pagina_de_imagem


def test_o_vao_entre_caracteres_vira_espaco():
    """Sem isto o livro sai com as palavras coladas: 'Thiscounter-attack'."""
    doc = _pagina(texto_linhas=("aaa bbb ccc ddd",))
    try:
        p = livro.extrair_pagina(doc[0], _classificador("x"), dpi=150)
    finally:
        doc.close()

    junto = " ".join(b.texto for b in p.blocos if isinstance(b, livro.Paragrafo))
    assert " " in junto, f"não separou palavra nenhuma: {junto!r}"
    assert junto.count("x") >= 12, junto


def test_a_pagina_de_imagem_sai_inteira_como_figura():
    """
    O limiar é baixado no teste em vez de se forjar uma página com 78 mil
    contornos: o que importa fixar é **o que a extração faz** quando a página
    passa do limite, e não quanto ruído é preciso para chegar lá — isso já está
    em `test_pagina_com_contorno_demais_devolve_vazio`.
    """
    doc = _pagina(texto_linhas=("Isto seria texto numa página normal.",))
    original = BoxService.MAX_CONTORNOS_DE_TEXTO
    BoxService.MAX_CONTORNOS_DE_TEXTO = 3
    try:
        extraida = livro.extrair_pagina(doc[0], _classificador("x"), dpi=150)
    finally:
        BoxService.MAX_CONTORNOS_DE_TEXTO = original
        doc.close()

    assert extraida.pagina_de_imagem
    assert len(extraida.blocos) == 1
    assert isinstance(extraida.blocos[0], livro.Figura)
    assert extraida.caracteres == 0
    assert extraida.blocos[0].largura > 100, "a figura não é a página inteira"


def test_o_diagrama_sai_como_figura_e_o_miolo_dele_nao_vira_texto():
    doc = _pagina(texto_linhas=("Texto antes do diagrama.",), diagrama=True)
    try:
        p = livro.extrair_pagina(doc[0], _classificador("x"), dpi=150)
    finally:
        doc.close()

    figuras = [b for b in p.blocos if isinstance(b, livro.Figura)]
    assert figuras, "o tabuleiro não virou figura"
    assert p.diagramas >= 1
    assert figuras[0].largura > 50 and figuras[0].altura > 50


def test_a_margem_do_diagrama_alcanca_os_rotulos_das_casas():
    """
    Era: oito linhas contendo só "8", "7", "6"... na página 10 do Yusupov.

    O `diagrama.localizar` devolve a borda do **tabuleiro**, e as letras `a`–`h`
    embaixo e os números `8`–`1` ao lado moram fora dela. Sem margem eles não
    são excluídos e entram no texto como linhas de um caractere.
    """
    escala = 30
    tabuleiro = (100, 100, 400, 400)
    forma = (600, 600)
    com_margem = livro._com_margem(tabuleiro, escala * livro.MARGEM_DIAGRAMA, forma)

    # um "8" rente à borda esquerda do tabuleiro, como o livro imprime
    rotulo = BoxEntry("", 100 - int(escala * 0.9), 200,
                      100 - int(escala * 0.2), 200 + escala)

    assert not livro._dentro(rotulo, tabuleiro), "o teste não está fora da borda"
    assert livro._dentro(rotulo, com_margem), (
        "a margem não alcança o rótulo da casa — ver MARGEM_DIAGRAMA")

    # ...e a margem não é tão larga que engula o texto da coluna ao lado
    prosa = BoxEntry("", 480, 200, 520, 230)
    assert not livro._dentro(prosa, com_margem), "a margem engoliu o texto vizinho"


def test_o_recorte_por_area_preserva_a_pontuacao():
    """
    Era: cortando por **altura**, o livro saía sem pontuação nenhuma —
    `5.♔xf2` virava `5♔d2` e `G.Levenfish` virava `G Levenfish`. Um ponto final
    é baixo, mas não é respingo.
    """
    # Os tamanhos são os medidos na página 10 do Yusupov, cuja escala é 44.
    escala = 44
    minima = livro.MIN_AREA_GLIFO * escala * escala

    def area(b):
        return (b.x2 - b.x1) * (b.y2 - b.y1)

    ponto = BoxEntry("", 0, 0, 8, 8)         # 0,033 · escala²
    hifen = BoxEntry("", 0, 0, 14, 3)        # 0,022 · escala²
    respingo = BoxEntry("", 0, 0, 2, 2)      # 0,0021 · escala², a faixa da régua

    assert area(ponto) >= minima, "o limiar de área derruba o ponto final"
    assert area(hifen) >= minima, "o limiar de área derruba o hífen"
    assert area(respingo) < minima, "o limiar deixa passar o respingo da régua"


def test_onde_ha_respingo_demais_o_texto_e_ornamento():
    """
    A régua de meio-tom do cabeçalho passa pelo limiar de área em fragmentos, e
    nem confiança a tira. O que a denuncia é a companhia.
    """
    escala = 20
    juntos = [BoxEntry("", 100 + i, 100, 102 + i, 102)
              for i in range(livro.RESPINGOS_DE_ORNAMENTO)]
    celulas = livro._celulas_de_ornamento(juntos, escala)
    assert celulas, "não marcou a célula cheia de respingo"
    assert livro._celula(BoxEntry("", 100, 100, 110, 110), escala) in celulas
    assert livro._celula(BoxEntry("", 900, 900, 910, 910), escala) not in celulas

    poucos = juntos[:livro.RESPINGOS_DE_ORNAMENTO - 1]
    assert not livro._celulas_de_ornamento(poucos, escala), (
        "marcou ornamento com respingo de menos")


def test_extrair_reclama_de_arquivo_inexistente():
    try:
        livro.extrair("nao_existe_xyz.pdf", _classificador())
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("deveria reclamar de arquivo inexistente")


# ----------------------------------------------------------------------
# Exportação
# ----------------------------------------------------------------------

def _paginas_de_teste():
    return [
        livro.PaginaExtraida(
            numero=0,
            blocos=[livro.Paragrafo("Primeiro parágrafo com ♖xf3 e ♕d5."),
                    livro.Figura(_png_pequeno(), 40, 40),
                    livro.Paragrafo("Depois da figura.")],
            caracteres=50, diagramas=1),
        livro.PaginaExtraida(numero=1,
                             blocos=[livro.Paragrafo("Só texto na segunda.")],
                             caracteres=20),
    ]


def _png_pequeno():
    import io as _io
    buffer = _io.BytesIO()
    Image.fromarray(np.full((40, 40), 200, dtype=np.uint8)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_o_epub_tem_a_forma_que_o_formato_exige():
    """
    O `mimetype` vai primeiro e **sem compressão** — é a única exigência
    posicional do EPUB, e um zip que comprima essa entrada é recusado por
    leitor que valide.
    """
    with tempfile.TemporaryDirectory() as tmp:
        caminho = exportar.para_epub(_paginas_de_teste(),
                                     os.path.join(tmp, "livro.epub"),
                                     titulo="Teste", autor="Autor")
        with zipfile.ZipFile(caminho) as z:
            nomes = z.namelist()
            assert nomes[0] == "mimetype"
            assert z.getinfo("mimetype").compress_type == zipfile.ZIP_STORED
            assert z.read("mimetype") == b"application/epub+zip"
            assert "META-INF/container.xml" in nomes
            assert "OEBPS/content.opf" in nomes
            assert "OEBPS/nav.xhtml" in nomes
            assert sum(1 for n in nomes if n.endswith(".xhtml")) == 3  # 2 + nav
            assert sum(1 for n in nomes if n.endswith(".png")) == 1

            opf = z.read("OEBPS/content.opf").decode("utf-8")
            assert "<dc:title>Teste</dc:title>" in opf
            assert "<dc:creator>Autor</dc:creator>" in opf
            pagina = z.read("OEBPS/pagina-0001.xhtml").decode("utf-8")
            # A figurina vai embrulhada na fonte de recurso (F62), a letra não.
            assert '<span class="sim">♖</span>xf3' in pagina
            assert "<img" in pagina


def test_o_epub_escapa_o_que_e_marcacao():
    paginas = [livro.PaginaExtraida(
        numero=0, blocos=[livro.Paragrafo("1<2 & 3>2 <script>x</script>")])]
    with tempfile.TemporaryDirectory() as tmp:
        caminho = exportar.para_epub(paginas, os.path.join(tmp, "x.epub"))
        with zipfile.ZipFile(caminho) as z:
            xhtml = z.read("OEBPS/pagina-0001.xhtml").decode("utf-8")
    assert "<script>" not in xhtml
    assert "&lt;script&gt;" in xhtml


def test_o_docx_abre_de_volta_com_texto_e_imagem():
    from docx import Document

    with tempfile.TemporaryDirectory() as tmp:
        caminho = exportar.para_docx(_paginas_de_teste(),
                                     os.path.join(tmp, "livro.docx"),
                                     titulo="Teste")
        doc = Document(caminho)

    texto = "\n".join(p.text for p in doc.paragraphs)
    assert "♖xf3" in texto
    assert "Só texto na segunda." in texto
    assert len(doc.inline_shapes) == 1, "a figura não entrou no DOCX"
    assert doc.core_properties.title == "Teste"


def test_o_formato_sai_da_extensao():
    with tempfile.TemporaryDirectory() as tmp:
        epub = exportar.exportar(_paginas_de_teste(), os.path.join(tmp, "a.epub"))
        docx = exportar.exportar(_paginas_de_teste(), os.path.join(tmp, "a.docx"))
        assert zipfile.is_zipfile(epub) and zipfile.is_zipfile(docx)


def test_formato_invalido():
    with tempfile.TemporaryDirectory() as tmp:
        try:
            exportar.exportar(_paginas_de_teste(), os.path.join(tmp, "a.txt"))
        except ValueError as e:
            assert "formato" in str(e)
        else:
            raise AssertionError("aceitou um formato inválido")


# ----------------------------------------------------------------------
# Execução direta
# ----------------------------------------------------------------------

def _main():
    """
    Roda o que está **acima** desta função, que é onde moram os testes de
    módulo. Os da UI e os da F58 vêm depois do `if __name__`, fora do alcance
    dela — e ali é o lugar deles: pedem `monkeypatch`, que é do pytest.
    """
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


# ----------------------------------------------------------------------
# A ação da UI, que é a cola que nenhum teste de módulo alcança
# ----------------------------------------------------------------------

def _pdf_de_uma_pagina(caminho, texto="Foreword"):
    doc = fitz.open()
    pagina = doc.new_page(width=300, height=140)
    pagina.insert_text(fitz.Point(20, 60), texto, fontsize=28)
    doc.save(caminho)
    doc.close()


class _MolduraFixa:
    """
    Dublê do `ui.dialogo_moldura.DialogoMoldura` (F97).

    **Sem ele a suíte trava, e trava calada.** Aquele diálogo não é um
    `messagebox` — é um `Toplevel` com `grab_set` e `wait_window`, e um `Tk`
    sem ninguém para clicar espera para sempre. Foi assim que ele entrou aqui:
    o teste não falhou, ficou pendurado.
    """

    #: O que o dublê responde. `None` imita o Cancelar, que desiste da ação.
    resposta = ("simples", 16.0)

    def __init__(self, _parent, **_kw):
        pass

    def mostrar(self):
        return self.resposta


class _App:
    """
    MainWindow com os diálogos capturados e o modelo neural fora do caminho.

    Os diálogos são a metade da ação que não dá para exercitar de outro jeito —
    é neles que estão a escolha do formato pela extensão, as perguntas de sim ou
    não, e a caixa da moldura e do corpo (F97), que sai pelo `_MolduraFixa`.

    **As respostas vão por título, e não uma para todas.** Enquanto havia uma
    pergunta só, um booleano bastava; com três (desenhar, coordenadas, coletar)
    um booleano faria o teste da coleta ligar o desenho de carona, e o teste
    passaria a medir outra coisa sem avisar.
    """

    #: título da pergunta → resposta. O que não casar responde "não".
    #:
    #: `Seguir` é a primeira das duas perguntas de coordenada (F95): "como no
    #: livro?". Só quem responde não é perguntado em seguida se quer ou não
    #: quer para o livro inteiro, e é essa segunda que `Coordenadas` responde.
    PADRAO = {"Redesenhar": True, "Seguir": False, "Coordenadas": False,
              "Guardar": False}

    def __init__(self, entrada, saida, coletar=False, respostas=None,
                 moldura=("simples", 16.0)):
        from tkinter import filedialog, messagebox

        self.moldura = moldura

        self.originais = (filedialog.askopenfilename,
                          filedialog.asksaveasfilename,
                          messagebox.askyesno, messagebox.showinfo,
                          messagebox.showerror)
        self.avisos = []
        self.erros = []
        self.respostas = dict(self.PADRAO, Guardar=coletar, **(respostas or {}))
        filedialog.askopenfilename = lambda *a, **k: entrada
        filedialog.asksaveasfilename = lambda *a, **k: saida
        messagebox.askyesno = self._responder
        messagebox.showinfo = lambda t, m="", *a, **k: self.avisos.append(m)
        messagebox.showerror = lambda t, m="", *a, **k: self.erros.append(m)

    def _responder(self, titulo="", _mensagem="", *a, **k):
        for chave, valor in self.respostas.items():
            if chave.lower() in titulo.lower():
                return valor
        return False

    def __enter__(self):
        from conftest import raiz_tk
        from ui.main_window import MainWindow

        self.root = raiz_tk()
        self.win = MainWindow(self.root)
        # A rede não é o assunto aqui: qualquer leitura serve para o caminho
        # inteiro rodar. Carregá-la de verdade levaria minutos e faria o teste
        # depender de um `.pth` que o `.gitignore` mantém fora.
        self.win.learning_service.load_predictor = lambda: True
        self.win.learning_service.predict_neural = lambda crop: ("a", 0.99)
        duble = type("_Duble", (_MolduraFixa,), {"resposta": self.moldura})
        self.win.DIALOGO_MOLDURA = duble
        return self

    def rodar(self, segundos=60.0):
        """
        Roda a ação e espera o desfecho, **por prazo e não por contagem**.

        A primeira versão dava 300 voltas de `update()`. Passava sozinha e
        falhava na suíte inteira, porque ali a thread de trabalho divide a
        máquina com tudo o mais e 300 voltas acabam antes do EPUB — um teste
        que só falha acompanhado é pior que um que nunca passa.
        """
        self.win.exportar_livro_action()
        limite = time.time() + segundos
        while time.time() < limite:
            self.root.update()
            if self.avisos or self.erros:
                break
            time.sleep(0.01)
        return self

    def rodar_sem_esperar(self):
        """Para os caminhos que voltam na hora, sem thread nenhuma."""
        self.win.exportar_livro_action()
        self.root.update()
        return self

    def __exit__(self, *a):
        from tkinter import filedialog, messagebox
        (filedialog.askopenfilename, filedialog.asksaveasfilename,
         messagebox.askyesno, messagebox.showinfo,
         messagebox.showerror) = self.originais
        try:
            self.win.task.shutdown()
            self.root.destroy()
        except Exception:
            pass


def test_a_acao_escreve_o_epub():
    tmp = tempfile.mkdtemp()
    entrada = os.path.join(tmp, "livro.pdf")
    saida = os.path.join(tmp, "saida.epub")
    _pdf_de_uma_pagina(entrada)

    with _App(entrada, saida) as app:
        app.rodar()
        assert not app.erros, app.erros
        assert os.path.exists(saida), "o EPUB não foi escrito"
        assert zipfile.is_zipfile(saida), "o EPUB não é um zip"
        assert app.avisos, "a conclusão não foi anunciada"


def test_extensao_desconhecida_recusa_antes_de_ler_o_pdf():
    """
    O formato sai da extensão do arquivo escolhido. Sem esta guarda, o caminho
    inteiro rodaria — minutos de OCR — para falhar na hora de escrever.
    """
    tmp = tempfile.mkdtemp()
    entrada = os.path.join(tmp, "livro.pdf")
    _pdf_de_uma_pagina(entrada)

    with _App(entrada, os.path.join(tmp, "saida.txt")) as app:
        app.rodar_sem_esperar()
        assert app.erros, "aceitou uma extensão que não sabe escrever"
        assert not app.avisos


def test_cancelar_a_escolha_do_arquivo_nao_faz_nada():
    with _App("", "") as app:
        app.rodar_sem_esperar()
        assert not app.avisos and not app.erros


def test_as_duas_perguntas_da_f58_chegam_a_extracao(monkeypatch):
    """
    As opções não valem nada se pararem no diálogo. Aqui a extração é trocada
    por uma que só anota o que recebeu — é o único jeito de provar que a
    resposta do usuário atravessa a thread de trabalho.
    """
    recebido = {}

    def falsa(input_pdf, classificar, **kw):
        recebido.clear()
        recebido.update(kw)
        return []

    monkeypatch.setattr(livro, "extrair", falsa)

    tmp = tempfile.mkdtemp()
    entrada = os.path.join(tmp, "livro.pdf")
    _pdf_de_uma_pagina(entrada)

    with _App(entrada, os.path.join(tmp, "a.epub")) as app:
        app.rodar()
        assert not app.erros, app.erros
        assert recebido["diagramas"] == "render", "o desenho é o padrão da F58"
        assert recebido["coordenadas"] is False, "coordenada só quando se pede"

    with _App(entrada, os.path.join(tmp, "b.epub"),
              respostas={"Redesenhar": False, "Coordenadas": True}) as app:
        app.rodar()
        assert not app.erros, app.erros
        assert recebido["diagramas"] == "recorte"
        assert recebido["coordenadas"] is True

    # A terceira resposta da F95: nem sim nem não para o livro inteiro — cada
    # diagrama como o livro o imprimiu.
    with _App(entrada, os.path.join(tmp, "c.epub"),
              respostas={"Seguir": True, "Coordenadas": False}) as app:
        app.rodar()
        assert not app.erros, app.erros
        assert recebido["coordenadas"] == livro.COMO_NO_LIVRO, (
            "'como no livro' parou no diálogo")


def test_a_moldura_e_o_corpo_chegam_aos_dois_lados(monkeypatch):
    """
    A escolha da F97 tem **dois destinos**, e é o que a torna fácil de perder
    pela metade: a moldura vai para a extração, porque quem desenha o filete no
    PNG é o renderizador; a moldura *e* o corpo vão para a escrita, porque no
    modo de fonte quem os desenha é o formato. Um caminho ligado e o outro não
    dá um livro em que o diagrama tem moldura e o tamanho continua o de antes.
    """
    extraiu, escreveu = {}, {}

    def falsa_extrair(input_pdf, classificar, **kw):
        extraiu.clear()
        extraiu.update(kw)
        return []

    def falso_exportar(paginas, caminho, **kw):
        escreveu.clear()
        escreveu.update(kw)
        with open(caminho, "wb") as f:
            f.write(b"")
        return caminho

    monkeypatch.setattr(livro, "extrair", falsa_extrair)
    monkeypatch.setattr(exportar, "exportar", falso_exportar)

    tmp = tempfile.mkdtemp()
    entrada = os.path.join(tmp, "livro.pdf")
    _pdf_de_uma_pagina(entrada)

    with _App(entrada, os.path.join(tmp, "a.epub"),
              moldura=("dupla", 20.0)) as app:
        app.rodar()
        assert not app.erros, app.erros
        assert extraiu["moldura"] == "dupla", "a moldura parou no diálogo"
        assert escreveu["moldura"] == "dupla"
        assert escreveu["corpo_pt"] == 20.0, "o corpo parou no diálogo"


def test_cancelar_a_moldura_desiste_da_exportacao(monkeypatch):
    """
    Fechar aquela caixa não é "faça como sempre": quem a abriu veio decidir
    alguma coisa, e um livro de 264 páginas escrito com o padrão porque alguém
    apertou Escape é o pior desfecho possível.
    """
    def nao_devia_rodar(*_a, **_kw):
        raise AssertionError("a extração rodou depois do Cancelar")

    monkeypatch.setattr(livro, "extrair", nao_devia_rodar)

    tmp = tempfile.mkdtemp()
    entrada = os.path.join(tmp, "livro.pdf")
    saida = os.path.join(tmp, "a.epub")
    _pdf_de_uma_pagina(entrada)

    with _App(entrada, saida, moldura=None) as app:
        app.rodar_sem_esperar()
        assert not app.avisos and not app.erros
        assert not os.path.exists(saida)


# ----------------------------------------------------------------------
# O diagrama redesenhado (F58)
# ----------------------------------------------------------------------

def _leitura_firme(fen="8/8/8/4k3/8/8/8/4K3 w - - 0 1"):
    """Uma leitura que passa no porteiro, montada à mão — sem carregar modelo."""
    from core import diagrama as diag

    leitura = diag.Leitura(caixa=(0, 0, 64, 64))
    tabuleiro = {}
    for i, fila in enumerate(fen.split()[0].split("/")):
        coluna = 0
        for ch in fila:
            if ch.isdigit():
                coluna += int(ch)
            else:
                tabuleiro[(i, coluna)] = ch
                coluna += 1
    for r in range(8):
        for c in range(8):
            leitura.casas.append(diag.Casa(r, c, tabuleiro.get((r, c)), 1.0,
                                           confianca_ocupacao=1.0))
    return leitura


def _pagina_com_diagrama(**kw):
    """Extrai a página de teste com a leitura de diagrama controlada."""
    doc = _pagina(texto_linhas=("Texto antes do diagrama.",), diagrama=True)
    try:
        return livro.extrair_pagina(doc[0], _classificador("x"), dpi=150, **kw)
    finally:
        doc.close()


def test_o_diagrama_confiavel_sai_desenhado_e_com_o_fen(monkeypatch):
    """
    O caminho inteiro da F58 num teste: a leitura passa no porteiro, o diagrama
    vira desenho, e o FEN viaja junto para virar texto alternativo lá na frente.
    """
    monkeypatch.setattr(livro.diagrama, "ler",
                        lambda img, caixa=None, **k: _leitura_firme())
    p = _pagina_com_diagrama(diagramas="render")

    figuras = [b for b in p.blocos if isinstance(b, livro.Figura)]
    assert figuras, "o tabuleiro não virou figura"
    assert figuras[0].origem == "render"
    assert figuras[0].fen == "8/8/8/4k3/8/8/8/4K3 w - - 0 1"
    assert figuras[0].aviso is None
    assert p.diagramas_desenhados == 1
    assert figuras[0].largura == figuras[0].altura, "o desenho não é quadrado"


def test_a_leitura_que_nao_convence_cai_para_o_recorte(monkeypatch):
    """
    O porteiro barrando é o caso comum — 9% dos tabuleiros na medição da F58 —
    e o livro não pode ficar sem diagrama por causa disso: ele sai recortado, e
    o motivo fica na figura para o relatório do fim.
    """
    fraca = _leitura_firme()
    fraca.casas[60].confianca = 0.10          # a casa mais fraca do tabuleiro
    monkeypatch.setattr(livro.diagrama, "ler", lambda img, caixa=None, **k: fraca)

    p = _pagina_com_diagrama(diagramas="render")
    figuras = [b for b in p.blocos if isinstance(b, livro.Figura)]
    assert figuras[0].origem == "recorte"
    assert figuras[0].fen is None
    assert "10%" in (figuras[0].aviso or "")
    assert p.diagramas_desenhados == 0


def test_sem_modelo_de_diagrama_a_exportacao_nao_cai(monkeypatch):
    """
    Um livro de 264 páginas não pode morrer na página 3 porque o `.pth` do
    diagrama não foi treinado. Cai para o recorte e diz o que faltou.
    """
    def sem_modelo(img, caixa=None, **k):
        raise livro.diagrama.ModeloAusente("modelo de teste ausente")

    monkeypatch.setattr(livro.diagrama, "ler", sem_modelo)
    p = _pagina_com_diagrama(diagramas="render")

    figuras = [b for b in p.blocos if isinstance(b, livro.Figura)]
    assert figuras[0].origem == "recorte"
    assert "não deu para desenhar" in (figuras[0].aviso or "")


def test_o_modo_recorte_nao_lê_diagrama_nenhum(monkeypatch):
    """Quem pediu o livro como antes não paga duas redes por tabuleiro."""
    def nao_deveria(img, caixa=None, **k):
        raise AssertionError("o modo recorte leu o diagrama")

    monkeypatch.setattr(livro.diagrama, "ler", nao_deveria)
    p = _pagina_com_diagrama(diagramas="recorte")

    figuras = [b for b in p.blocos if isinstance(b, livro.Figura)]
    assert figuras and figuras[0].origem == "recorte"
    assert figuras[0].aviso is None, "recortar por opção não é queixa"


def test_modo_de_diagrama_invalido_reclama():
    doc = _pagina(diagrama=True)
    try:
        livro.extrair_pagina(doc[0], _classificador(), diagramas="svg")
    except ValueError as erro:
        assert "svg" in str(erro)
    else:
        raise AssertionError("aceitou um modo que não existe")
    finally:
        doc.close()


def test_o_recorte_de_queda_segue_a_opcao_de_coordenadas(monkeypatch):
    """
    Desenho e recorte convivem no mesmo livro. Se o recorte trouxesse os rótulos
    quando o desenho não traz, a única diferença visível entre as duas páginas
    seria a que o leitor não deveria notar.
    """
    monkeypatch.setattr(livro.diagrama, "ler", lambda img, caixa=None, **k: _leitura_firme())
    monkeypatch.setattr(livro.diagrama, "confiavel",
                        lambda leitura, **kw: (False, "de propósito"))

    justo = _pagina_com_diagrama(diagramas="render",
                                 coordenadas=False)
    largo = _pagina_com_diagrama(diagramas="render",
                                 coordenadas=True)

    def figura(p):
        return [b for b in p.blocos if isinstance(b, livro.Figura)][0]

    assert figura(justo).largura < figura(largo).largura, (
        "o recorte com coordenadas deveria alcançar os rótulos das casas")


def test_a_pagina_de_imagem_se_declara():
    """
    Ela não é diagrama nem recorte de tabuleiro — é a página inteira —, e a
    `origem` precisa dizer isso para o relatório não contá-la como queda.
    """
    doc = fitz.open()
    doc.new_page(width=200, height=200)      # em branco: nenhum contorno
    try:
        p = livro.extrair_pagina(doc[0], _classificador(), dpi=72)
    finally:
        doc.close()
    assert p.pagina_de_imagem
    assert p.blocos[0].origem == "pagina"
    assert p.diagramas_desenhados == 0


# ----------------------------------------------------------------------
# A faixa do cabeçalho (F60)
# ----------------------------------------------------------------------

def _pagina_com_cabecalho():
    """
    Um diagrama com uma linha impressa logo acima dele, como o livro faz.

    A distância importa: o cabeçalho tem de cair **dentro** da margem de
    exclusão, que é o que o torna invisível para o texto — e era o que o fazia
    sumir do livro antes desta fase.
    """
    doc = _pagina(texto_linhas=("Prosa bem no alto da pagina.",), diagrama=True)
    doc[0].insert_text((44, 145), "Diagram 1-5", fontsize=7)
    return doc


def _figuras(p):
    return [b for b in p.blocos if isinstance(b, livro.Figura)]


def test_o_cabecalho_legivel_vira_titulo(monkeypatch):
    """
    Era: a página 220 do Yusupov saía com seis diagramas e nenhum `Ex. 22-1`.
    A margem de exclusão come 27 caixas por diagrama, 11 delas acima da borda —
    e, com o tabuleiro redesenhado, elas não viravam texto nem figura.

    A F60 as trouxe de volta como imagem; a F67 as lê. Título, e não parágrafo
    comum: é o que dá `<h2>` no EPUB e `Heading 2` no DOCX, por onde o sumário
    do leitor navega.
    """
    monkeypatch.setattr(livro.diagrama, "ler", lambda img, caixa=None, **k: _leitura_firme())
    doc = _pagina_com_cabecalho()
    try:
        p = livro.extrair_pagina(doc[0], _classificador("x"), dpi=150,
                                 diagramas="render")
    finally:
        doc.close()

    assert [f.origem for f in _figuras(p)] == ["render"], "a faixa saiu como imagem"
    titulos = [b for b in p.blocos if isinstance(b, livro.Paragrafo) and b.titulo]
    assert len(titulos) == 1, [b.texto for b in p.blocos
                               if isinstance(b, livro.Paragrafo)]
    assert titulos[0].texto, "o título veio vazio"
    assert p.blocos.index(titulos[0]) < p.blocos.index(_figuras(p)[0]), (
        "o cabeçalho tem de vir antes do diagrama que ele encabeça")


def test_o_cabecalho_ilegivel_continua_saindo_como_imagem(monkeypatch):
    """
    Uma letra fraca já manda a faixa de volta para a imagem, e é mais severo
    que o resto do livro de propósito: a faixa tem quatro ou cinco caracteres, e
    o buraco nela é o número do exercício. Medido na página 220, o hífen de
    `Ex. 22-4` sai com 0,108 de confiança — o `★` e o `▼` saem com 1,000.
    """
    monkeypatch.setattr(livro.diagrama, "ler", lambda img, caixa=None, **k: _leitura_firme())
    doc = _pagina_com_cabecalho()
    try:
        p = livro.extrair_pagina(doc[0], _classificador("x", 0.20), dpi=150,
                                 diagramas="render", conf_minima=0.5)
    finally:
        doc.close()

    figuras = _figuras(p)
    assert [f.origem for f in figuras] == ["faixa", "render"]
    assert figuras[0].altura < figuras[1].altura / 3, (
        "isso não é uma faixa, é meia página")
    assert not [b for b in p.blocos
                if isinstance(b, livro.Paragrafo) and b.titulo]


def test_a_faixa_sai_na_largura_do_diagrama():
    """
    As duas figuras são escaladas para a mesma largura no arquivo. Se a faixa
    saísse na escala do scan, um cabeçalho recortado a 150 dpi apareceria com
    metade da largura de um tabuleiro desenhado a 528 px.
    """
    doc = _pagina_com_cabecalho()
    try:
        p = livro.extrair_pagina(doc[0], _classificador("x", 0.20), dpi=150,
                                 diagramas="recorte", conf_minima=0.5)
    finally:
        doc.close()

    faixa, tabuleiro = _figuras(p)
    assert abs(faixa.largura - tabuleiro.largura) <= tabuleiro.largura * 0.15


def test_o_recorte_com_coordenadas_nao_duplica_o_cabecalho():
    """
    Ali a figura sai pelo retângulo de exclusão e já traz o cabeçalho dentro —
    uma faixa a mais seria a mesma tinta duas vezes, uma em cima da outra.
    """
    doc = _pagina_com_cabecalho()
    try:
        p = livro.extrair_pagina(doc[0], _classificador("x"), dpi=150,
                                 diagramas="recorte", coordenadas=True)
    finally:
        doc.close()

    figuras = _figuras(p)
    assert len(figuras) == 1 and figuras[0].origem == "recorte"


# ----------------------------------------------------------------------
# As coordenadas como o livro as imprimiu (F95)
# ----------------------------------------------------------------------

def _extrair(doc, **kw):
    try:
        return livro.extrair_pagina(doc[0], _classificador("x"), dpi=150, **kw)
    finally:
        doc.close()


def test_como_no_livro_nao_poe_coordenada_onde_o_livro_nao_pos():
    """
    A terceira resposta da F95, no caso mais comum: o livro que não rotula
    continua saindo sem rótulo, sem ninguém ter de escolher isso.
    """
    p = _extrair(_pagina(diagrama=True), diagramas="recorte",
                 coordenadas=livro.COMO_NO_LIVRO)

    figuras = _figuras(p)
    assert figuras and not figuras[0].coordenadas


def test_como_no_livro_poe_coordenada_onde_o_livro_pos():
    p = _extrair(_pagina(diagrama=True, rotulos=True), diagramas="recorte",
                 coordenadas=livro.COMO_NO_LIVRO)

    figuras = _figuras(p)
    assert figuras and figuras[0].coordenadas, (
        "o tabuleiro rotulado saiu sem os rótulos")


def test_coordenada_que_nao_existe_reclama():
    """
    `coordenadas` aceita string desde a F95, e a partir daí `"Auto"` com
    maiúscula seria **verdadeiro** — o livro inteiro sairia rotulado em
    silêncio, por um erro de digitação.
    """
    doc = _pagina(diagrama=True)
    try:
        livro.extrair_pagina(doc[0], _classificador(), coordenadas="Auto")
    except ValueError as erro:
        assert "Auto" in str(erro)
    else:
        raise AssertionError("aceitou uma escolha que não existe")
    finally:
        doc.close()


def test_o_booleano_continua_mandando_no_livro_inteiro():
    """
    `True` e `False` não consultam a página: quem pediu um livro inteiro de um
    jeito só continua tendo isso, e é por isso que o padrão não mudou.
    """
    com = _extrair(_pagina(diagrama=True, rotulos=True), diagramas="recorte",
                   coordenadas=False)
    sem = _extrair(_pagina(diagrama=True), diagramas="recorte",
                   coordenadas=True)

    assert not _figuras(com)[0].coordenadas
    assert _figuras(sem)[0].coordenadas


def test_a_legenda_de_baixo_e_reconhecida_como_do_diagrama():
    """
    O lado que a F60 nunca olhou. O `437` do Nunn fica embaixo do tabuleiro, e
    o `_faixa_acima` só procurava acima — a legenda saía como parágrafo solto,
    sem nada dizendo de que diagrama ela era.
    """
    doc = _pagina(diagrama=True, legenda="437")
    try:
        _boxes, diagramas, _e, _r, _c = livro.caixas_e_diagramas(
            _cinza(doc[0]), _classificador("x"))
    finally:
        doc.close()

    assert diagramas, "o tabuleiro não foi achado"
    assert diagramas[0].legenda.lado == "abaixo"
    assert diagramas[0].legenda.texto


def test_a_legenda_de_baixo_vira_paragrafo_e_nao_sai_duas_vezes():
    """
    O `437` do Nunn começa dentro da margem de exclusão e acaba fora dela, então
    ele chega ao texto da página. Vira legenda **e** sai de lá — senão sairia
    uma vez colado na figura e outra solto no meio da prosa.
    """
    p = _extrair(_pagina(texto_linhas=("Texto antes do diagrama.",),
                         diagrama=True, legenda="437"),
                 diagramas="recorte")

    blocos = p.blocos
    figuras = [i for i, b in enumerate(blocos) if isinstance(b, livro.Figura)]
    assert figuras, "o tabuleiro não virou figura"
    depois = blocos[figuras[0] + 1:]
    assert depois and isinstance(depois[0], livro.Paragrafo), (
        "a legenda não entrou depois da figura")
    assert not depois[0].titulo, "legenda embaixo da figura não é título"
    assert sum(1 for b in blocos
               if isinstance(b, livro.Paragrafo)
               and b.texto == depois[0].texto) == 1, "a legenda saiu em dobro"


def test_diagrama_sem_nada_em_cima_vem_sozinho():
    """A faixa é do livro de exercícios; o diagrama no meio da prosa não tem."""
    doc = _pagina(texto_linhas=("Texto bem longe do diagrama.",), diagrama=True)
    try:
        p = livro.extrair_pagina(doc[0], _classificador("x"), dpi=150,
                                 diagramas="recorte")
    finally:
        doc.close()

    assert [f.origem for f in _figuras(p)] == ["recorte"]


def test_a_faixa_se_declara_no_texto_alternativo():
    """FEN ela não tem, e "Diagrama" ela não é."""
    faixa = livro.Figura(_png_pequeno(), 40, 10, origem="faixa")
    assert exportar._alternativo(faixa) == "Cabeçalho do diagrama"


def test_do_pdf_ao_desenho_sem_nenhum_dublê():
    """
    A costura inteira, com os modelos de verdade: uma página com um diagrama
    impresso vira uma figura redesenhada com **o mesmo FEN** que entrou.

    Os outros testes desta seção trocam a `diagrama.ler` por uma leitura montada
    à mão, porque o que eles medem é a decisão do `livro`. Este não troca nada —
    é o que pega o erro que nenhum deles pegaria: retângulo de exclusão no lugar
    do retângulo do tabuleiro, que desloca as 64 casas e devolve um FEN errado
    sem quebrar nada.
    """
    from core import diagrama as diag
    from core import render_diagrama as rd

    fen = "r1bqk2r/pp2bppp/2n1pn2/3p4/3P4/2N1PN2/PP2BPPP/R1BQK2R w - - 0 1"
    # Impresso com coordenadas, que é como o livro imprime — e é justamente o
    # que sobra fora da borda para atrapalhar quem recorta pelo retângulo errado.
    png, _l, _a = rd.desenhar(fen, lado_px=700, coordenadas=True, tons=0)

    doc = fitz.open()
    pagina = doc.new_page(width=300, height=420)
    pagina.insert_text((30, 40), "Texto antes do diagrama.", fontsize=10)
    pagina.insert_image(fitz.Rect(40, 60, 260, 280), stream=png)
    pagina.insert_text((30, 300), "Texto depois do diagrama.", fontsize=10)

    try:
        p = livro.extrair_pagina(pagina, _classificador("x"), dpi=300,
                                 diagramas="render")
    except diag.ModeloAusente:
        import pytest
        pytest.skip("modelo não construído (rode treinar_diagrama.py)")
    finally:
        doc.close()

    figuras = [b for b in p.blocos if isinstance(b, livro.Figura)]
    desenhados = [f for f in figuras if f.origem == "render"]
    assert len(desenhados) == 1, [f.origem for f in figuras]
    assert desenhados[0].fen == fen
    assert p.diagramas_desenhados == 1
    # A linha impressa logo acima cai dentro da margem de exclusão e volta como
    # cabeçalho (F60, lida na F67) — antes disso, sumia do livro.
    assert [f.origem for f in figuras] == ["render"]
    titulos = [b for b in p.blocos if isinstance(b, livro.Paragrafo) and b.titulo]
    assert len(titulos) == 1 and p.blocos.index(titulos[0]) == 0


def test_o_livro_sai_com_o_mais_do_xeque_e_nao_com_a_cruz():
    """
    Era: `♘e4✝` no EPUB, e uma busca por `Nxe4+` não achava a página. A classe
    do modelo é a cruz que o livro desenha; o texto exportado é o `+` que a
    pessoa digita. Medido na página 11 do Yusupov, 16 ocorrências numa página.
    """
    doc = _pagina(texto_linhas=("xxx",))
    try:
        p = livro.extrair_pagina(doc[0], _classificador("✝"), dpi=150)
    finally:
        doc.close()

    assert p.texto, "a página saiu sem texto"
    assert "✝" not in p.texto
    assert "+" in p.texto


def test_o_texto_alternativo_da_figura_e_o_fen():
    """
    Acessibilidade e busca no mesmo campo: o leitor de tela diz a posição, e uma
    busca por FEN encontra o diagrama. O recorte não sabe de nada e fica com o
    rótulo genérico.
    """
    fen = "8/8/8/4k3/8/8/8/4K3 w - - 0 1"
    paginas = [livro.PaginaExtraida(
        numero=0,
        blocos=[livro.Figura(_png_pequeno(), 40, 40, fen=fen, origem="render"),
                livro.Figura(_png_pequeno(), 40, 40)])]

    with tempfile.TemporaryDirectory() as tmp:
        caminho = exportar.para_epub(paginas, os.path.join(tmp, "x.epub"))
        with zipfile.ZipFile(caminho) as z:
            xhtml = z.read("OEBPS/pagina-0001.xhtml").decode("utf-8")
    assert f'alt="{fen}"' in xhtml
    assert 'alt="Diagrama"' in xhtml, "o recorte perdeu o rótulo genérico"


def test_o_docx_leva_o_fen_no_texto_alternativo():
    fen = "8/8/8/4k3/8/8/8/4K3 w - - 0 1"
    paginas = [livro.PaginaExtraida(
        numero=0,
        blocos=[livro.Figura(_png_pequeno(), 40, 40, fen=fen, origem="render")])]

    with tempfile.TemporaryDirectory() as tmp:
        caminho = exportar.para_docx(paginas, os.path.join(tmp, "x.docx"))
        with zipfile.ZipFile(caminho) as z:
            documento = z.read("word/document.xml").decode("utf-8")
    assert fen in documento, "o FEN não chegou ao `descr` da figura"
