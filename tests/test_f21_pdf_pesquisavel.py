"""
Testes da F2.1 — PDF pesquisável.

A saída antiga rasterizava o documento: convertia cada página em imagem,
desenhava por cima e salvava como PDF de imagens. Todo o texto selecionável
sumia — inclusive o que já estava perfeito no original.

Rodar sem pytest:      python tests/test_f21_pdf_pesquisavel.py
"""

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conftest import raiz_tk

import fitz
import tkinter as tk
from tkinter import filedialog, messagebox

from core.searchable_pdf import (MODOS, contar_paginas_com_texto,
                                 gerar_pdf_pesquisavel)


# ----------------------------------------------------------------------
# Apoio
# ----------------------------------------------------------------------

def _pdf_escaneado(caminho, texto="ABC def", paginas=1, dpi=150):
    """PDF sem texto nenhum: só a imagem da página, como um scan."""
    origem = fitz.open()
    for _ in range(paginas):
        p = origem.new_page()
        p.insert_text((60, 100), texto, fontsize=40)

    doc = fitz.open()
    for p in origem:
        pix = p.get_pixmap(dpi=dpi)
        nova = doc.new_page(width=p.rect.width, height=p.rect.height)
        nova.insert_image(nova.rect, pixmap=pix)
    doc.save(caminho)
    doc.close()
    origem.close()
    return caminho


def _pdf_digital(caminho, texto="Texto nativo que ja existe na pagina"):
    doc = fitz.open()
    doc.new_page().insert_text((60, 100), texto, fontsize=18)
    doc.save(caminho)
    doc.close()
    return caminho


def _reconhecedor(sequencia):
    """Devolve os caracteres de `sequencia` em ordem, ciclicamente."""
    estado = {"i": 0}

    def reconhecer(crop):
        ch = sequencia[estado["i"] % len(sequencia)]
        estado["i"] += 1
        return ch, 0.95
    return reconhecer


def _texto(pdf, pagina=0):
    d = fitz.open(pdf)
    try:
        return d[pagina].get_text().strip()
    finally:
        d.close()


# ----------------------------------------------------------------------
# O ponto central
# ----------------------------------------------------------------------

def test_saida_fica_pesquisavel():
    """Era: o PDF de saída não tinha texto nenhum."""
    with tempfile.TemporaryDirectory() as tmp:
        entrada = _pdf_escaneado(os.path.join(tmp, "in.pdf"))
        saida = os.path.join(tmp, "out.pdf")

        assert _texto(entrada) == "", "o PDF de entrada deveria ser um scan puro"

        resumo = gerar_pdf_pesquisavel(
            entrada, saida, reconhecer=_reconhecedor("XYZ"), dpi=150)

        assert resumo["reconhecidos"] > 0
        texto = _texto(saida)
        assert texto, "a saída continua sem texto extraível"
        assert set(texto) & set("XYZ"), f"texto inesperado: {texto!r}"


def test_pagina_original_nao_e_rasterizada():
    """A imagem original tem que continuar lá, intacta."""
    with tempfile.TemporaryDirectory() as tmp:
        entrada = _pdf_escaneado(os.path.join(tmp, "in.pdf"))
        saida = os.path.join(tmp, "out.pdf")

        gerar_pdf_pesquisavel(entrada, saida, reconhecer=_reconhecedor("A"), dpi=150)

        d = fitz.open(saida)
        try:
            assert d[0].get_images(), "a imagem original sumiu da página"
        finally:
            d.close()


def test_texto_nativo_e_preservado():
    """
    O modo antigo destruía até o texto que já estava perfeito no original.
    Numa página que já tem texto, o OCR nem deve rodar — escrever por cima
    duplicaria o conteúdo e a busca devolveria tudo duas vezes.
    """
    with tempfile.TemporaryDirectory() as tmp:
        entrada = _pdf_digital(os.path.join(tmp, "in.pdf"))
        saida = os.path.join(tmp, "out.pdf")
        original = _texto(entrada)

        resumo = gerar_pdf_pesquisavel(
            entrada, saida, reconhecer=_reconhecedor("ZZZ"), dpi=150)

        assert resumo["paginas_puladas"] == 1
        assert resumo["paginas_ocr"] == 0
        assert _texto(saida) == original, "o texto nativo foi alterado"
        assert "Z" not in _texto(saida), "escreveu OCR sobre página que já tinha texto"


def test_forcar_ocr_em_pagina_com_texto():
    with tempfile.TemporaryDirectory() as tmp:
        entrada = _pdf_digital(os.path.join(tmp, "in.pdf"))
        saida = os.path.join(tmp, "out.pdf")

        resumo = gerar_pdf_pesquisavel(
            entrada, saida, reconhecer=_reconhecedor("Z"), dpi=150,
            pular_paginas_com_texto=False)

        assert resumo["paginas_ocr"] == 1


# ----------------------------------------------------------------------
# Modos
# ----------------------------------------------------------------------

def test_modo_searchable_nao_altera_o_visual():
    """render_mode=3 é invisível: nada some nem aparece na página."""
    with tempfile.TemporaryDirectory() as tmp:
        entrada = _pdf_escaneado(os.path.join(tmp, "in.pdf"))
        saida = os.path.join(tmp, "out.pdf")

        gerar_pdf_pesquisavel(entrada, saida, reconhecer=_reconhecedor("A"),
                              dpi=150, modo="searchable")

        a = fitz.open(entrada)[0].get_pixmap(dpi=72)
        b = fitz.open(saida)[0].get_pixmap(dpi=72)
        assert a.samples == b.samples, "o modo searchable alterou a imagem da página"


def test_modo_replace_desenha_pecas():
    with tempfile.TemporaryDirectory() as tmp:
        entrada = _pdf_escaneado(os.path.join(tmp, "in.pdf"))
        saida = os.path.join(tmp, "out.pdf")

        resumo = gerar_pdf_pesquisavel(
            entrada, saida, reconhecer=_reconhecedor("♔"),  # ♔
            dpi=150, modo="replace")

        assert resumo["pecas_substituidas"] > 0

        a = fitz.open(entrada)[0].get_pixmap(dpi=72)
        b = fitz.open(saida)[0].get_pixmap(dpi=72)
        assert a.samples != b.samples, "o modo replace não mexeu na página"


def test_modo_replace_alcanca_a_ligadura_com_figurina():
    """
    `♗x` tem de ser substituída como qualquer peça.

    Antes de `tem_peca`, o filtro era `char in PECAS` e a captura de bispo — que
    o modelo lê numa classe só desde as ligaduras da SPEC §5.2 item 6 — passava
    batida, deixando o glifo original na página sem contar em `sem_glifo` nem em
    lugar nenhum do resumo.
    """
    with tempfile.TemporaryDirectory() as tmp:
        entrada = _pdf_escaneado(os.path.join(tmp, "in.pdf"))
        saida = os.path.join(tmp, "out.pdf")

        resumo = gerar_pdf_pesquisavel(
            entrada, saida, reconhecer=_reconhecedor("♗x"),
            dpi=150, modo="both")

        assert resumo["pecas_substituidas"] > 0
        assert "♗x" in _texto(saida)


def test_modo_both_faz_as_duas_coisas():
    with tempfile.TemporaryDirectory() as tmp:
        entrada = _pdf_escaneado(os.path.join(tmp, "in.pdf"))
        saida = os.path.join(tmp, "out.pdf")

        resumo = gerar_pdf_pesquisavel(
            entrada, saida, reconhecer=_reconhecedor("♕"),  # ♕
            dpi=150, modo="both")

        assert resumo["pecas_substituidas"] > 0
        assert "♕" in _texto(saida), "faltou a camada pesquisável"


def test_modo_invalido():
    with tempfile.TemporaryDirectory() as tmp:
        entrada = _pdf_escaneado(os.path.join(tmp, "in.pdf"))
        try:
            gerar_pdf_pesquisavel(entrada, os.path.join(tmp, "o.pdf"),
                                  reconhecer=_reconhecedor("A"), modo="xpto")
        except ValueError as e:
            assert "modo" in str(e)
        else:
            raise AssertionError("aceitou um modo inválido")


def test_modos_declarados():
    assert MODOS == ("searchable", "replace", "both")


# ----------------------------------------------------------------------
# Peças de xadrez sobrevivem à ida e volta
# ----------------------------------------------------------------------

def test_pecas_unicode_sobrevivem():
    """
    Mesmo risco da F0.2: fonte sem os glifos escreveria outra coisa. Aqui o
    texto é invisível, então o erro só apareceria na hora de buscar.
    """
    with tempfile.TemporaryDirectory() as tmp:
        entrada = _pdf_escaneado(os.path.join(tmp, "in.pdf"), texto="XXXXXX")
        saida = os.path.join(tmp, "out.pdf")

        pecas = "♔♕♖♗♘♙"
        gerar_pdf_pesquisavel(entrada, saida, reconhecer=_reconhecedor(pecas),
                              dpi=150, modo="searchable")

        texto = _texto(saida)
        achados = [p for p in pecas if p in texto]
        assert achados, f"nenhuma peça sobreviveu: {texto!r}"
        assert "·" not in texto, "voltou a escrever '·' no lugar das peças"


# ----------------------------------------------------------------------
# Limiares, progresso e cancelamento
# ----------------------------------------------------------------------

def test_confianca_minima_descarta():
    with tempfile.TemporaryDirectory() as tmp:
        entrada = _pdf_escaneado(os.path.join(tmp, "in.pdf"))
        saida = os.path.join(tmp, "out.pdf")

        resumo = gerar_pdf_pesquisavel(
            entrada, saida, reconhecer=lambda c: ("A", 0.20),
            dpi=150, conf_minima=0.5)

        assert resumo["boxes"] > 0
        assert resumo["reconhecidos"] == 0, "aceitou reconhecimento abaixo do limiar"
        assert _texto(saida) == ""


def test_progresso_por_pagina():
    with tempfile.TemporaryDirectory() as tmp:
        entrada = _pdf_escaneado(os.path.join(tmp, "in.pdf"), paginas=3)
        saida = os.path.join(tmp, "out.pdf")

        vistos = []
        gerar_pdf_pesquisavel(
            entrada, saida, reconhecer=_reconhecedor("A"), dpi=150,
            progress_callback=lambda p, t: vistos.append((p, t)))

        assert vistos[0] == (0, 3)
        assert vistos[-1] == (3, 3), "faltou o aviso de conclusão"


def test_cancelamento_nao_deixa_arquivo():
    """O PDF só é gravado no fim: abortar não pode deixar saída pela metade."""
    class _Parou(Exception):
        pass

    with tempfile.TemporaryDirectory() as tmp:
        entrada = _pdf_escaneado(os.path.join(tmp, "in.pdf"), paginas=3)
        saida = os.path.join(tmp, "out.pdf")

        def progresso(p, t):
            if p >= 1:
                raise _Parou()

        try:
            gerar_pdf_pesquisavel(entrada, saida, reconhecer=_reconhecedor("A"),
                                  dpi=150, progress_callback=progresso)
        except _Parou:
            pass
        else:
            raise AssertionError("o cancelamento não propagou")

        assert not os.path.exists(saida), "deixou um PDF incompleto no disco"


def test_arquivo_inexistente():
    try:
        gerar_pdf_pesquisavel("nao_existe_xyz.pdf", "saida.pdf",
                              reconhecer=_reconhecedor("A"))
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("deveria reclamar de arquivo inexistente")


# ----------------------------------------------------------------------
# Pular página que já tem texto é a decisão que muda tudo
# ----------------------------------------------------------------------

def test_contar_paginas_com_texto():
    """A conta que deixa a UI perguntar só quando há o que perguntar."""
    with tempfile.TemporaryDirectory() as tmp:
        scan = _pdf_escaneado(os.path.join(tmp, "scan.pdf"), paginas=3)
        assert contar_paginas_com_texto(scan) == (0, 3)

        digital = _pdf_digital(os.path.join(tmp, "digital.pdf"))
        assert contar_paginas_com_texto(digital) == (1, 1)


def test_contar_paginas_com_texto_num_documento_misto():
    """
    O caso dos livros deste projeto: digitalização que já veio com OCR. A conta
    tem de separar as duas metades, senão a pergunta da UI sai errada.
    """
    with tempfile.TemporaryDirectory() as tmp:
        scan = fitz.open(_pdf_escaneado(os.path.join(tmp, "s.pdf"), paginas=2))
        misto = fitz.open()
        misto.insert_pdf(scan)
        misto.new_page().insert_text((60, 100), "pagina com texto nativo", fontsize=18)
        caminho = os.path.join(tmp, "misto.pdf")
        misto.save(caminho)
        misto.close()
        scan.close()

        assert contar_paginas_com_texto(caminho) == (1, 3)


def test_contar_paginas_reclama_de_arquivo_inexistente():
    try:
        contar_paginas_com_texto("nao_existe_xyz.pdf")
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("deveria reclamar de arquivo inexistente")


# ----------------------------------------------------------------------
# A pergunta na UI
# ----------------------------------------------------------------------

class _AppOCR:
    """
    MainWindow com os diálogos e a conversão de verdade neutralizados.

    `gerar_pdf_pesquisavel` é trocado **no espaço de nomes de `ui.main_window`**,
    que é onde o nome está ligado. Assim o teste lê os argumentos sem carregar o
    modelo neural nem as 127 mil imagens do k-NN, que é o que `trabalho` faria
    antes de chamá-lo.
    """

    def __init__(self, entrada, resposta):
        import ui.main_window as mw
        from ui.main_window import MainWindow

        self.mw = mw
        self.entrada = entrada
        self.saida = os.path.join(os.path.dirname(entrada), "saida.pdf")
        self.resposta = resposta
        self.perguntas = []
        self.avisos = []
        self.chamadas = []

        self._original = (messagebox.showinfo, messagebox.showerror,
                          messagebox.askyesnocancel, filedialog.askopenfilename,
                          filedialog.asksaveasfilename, mw.gerar_pdf_pesquisavel)
        messagebox.showinfo = lambda t, m, **k: self.avisos.append((t, m))
        messagebox.showerror = lambda t, m, **k: self.avisos.append((t, m))
        messagebox.askyesnocancel = self._perguntar
        filedialog.askopenfilename = lambda **k: self.entrada
        filedialog.asksaveasfilename = lambda **k: self.saida
        mw.gerar_pdf_pesquisavel = self._gerar

        self.root = raiz_tk()
        self.win = MainWindow(self.root)
        # Modelo neural e base de referência não entram num teste de diálogo.
        self.win.learning_service.load_predictor = lambda *a, **k: None
        self.win.learning_service._get_learner = lambda *a, **k: None
        self.win.learning_service._predictor = None

    def _perguntar(self, titulo, mensagem, **k):
        self.perguntas.append((titulo, mensagem))
        return self.resposta

    def _gerar(self, entrada, saida, **kw):
        self.chamadas.append(kw)
        return {"paginas": 1, "paginas_ocr": 1, "paginas_puladas": 0, "boxes": 3,
                "reconhecidos": 3, "baixa_confianca": 0, "pecas_substituidas": 0,
                "sem_glifo": 0}

    def aguardar(self, limite=30.0):
        fim = time.time() + limite
        self.root.update()
        while self.win.task.is_running() and time.time() < fim:
            self.root.update()
            time.sleep(0.01)
        self.root.update()
        assert not self.win.task.is_running(), "a tarefa não terminou no tempo"

    def __enter__(self):
        return self

    def __exit__(self, *a):
        (messagebox.showinfo, messagebox.showerror, messagebox.askyesnocancel,
         filedialog.askopenfilename, filedialog.asksaveasfilename,
         self.mw.gerar_pdf_pesquisavel) = self._original
        try:
            self.win.task.shutdown()
            self.win.status.end_task()
            self.root.update()
        except Exception:
            pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass


def test_responder_nao_reprocessa_as_paginas_que_ja_tem_texto():
    """
    Era: a UI nunca passava `pular_paginas_com_texto`, e o padrão pula.

    Nos três livros de `PDF/` — digitalizações que já vêm com OCR de fábrica —
    isso é 58/60, 57/60 e 53/60 páginas puladas, e "Substituir Glifos em PDF
    **Escaneado**" respondia "OCR em 0" diante de um livro escaneado. A opção
    existia em `gerar_pdf_pesquisavel` desde o início e não chegava aqui.
    """
    with tempfile.TemporaryDirectory() as tmp:
        entrada = _pdf_digital(os.path.join(tmp, "in.pdf"))
        with _AppOCR(entrada, resposta=False) as app:   # 'Não' = reprocessar
            app.win.gerar_pdf_pesquisavel_action()
            app.aguardar()

            assert app.perguntas, "não perguntou nada sobre as páginas com texto"
            assert "1 de 1" in app.perguntas[0][1], app.perguntas[0][1]
            assert len(app.chamadas) == 1
            assert app.chamadas[0]["pular_paginas_com_texto"] is False


def test_responder_sim_mantem_o_padrao_de_pular():
    with tempfile.TemporaryDirectory() as tmp:
        entrada = _pdf_digital(os.path.join(tmp, "in.pdf"))
        with _AppOCR(entrada, resposta=True) as app:
            app.win.gerar_pdf_pesquisavel_action()
            app.aguardar()

            assert app.perguntas
            assert app.chamadas[0]["pular_paginas_com_texto"] is True


def test_desistir_da_pergunta_nao_converte():
    """Cancelar na pergunta não pode seguir para o diálogo de salvar."""
    with tempfile.TemporaryDirectory() as tmp:
        entrada = _pdf_digital(os.path.join(tmp, "in.pdf"))
        with _AppOCR(entrada, resposta=None) as app:
            app.win.gerar_pdf_pesquisavel_action()
            app.root.update()

            assert app.perguntas
            assert not app.chamadas, "converteu depois de o usuário desistir"


def test_scan_puro_nao_gera_pergunta():
    """Sem página com texto não há decisão a tomar — perguntar seria ruído."""
    with tempfile.TemporaryDirectory() as tmp:
        entrada = _pdf_escaneado(os.path.join(tmp, "in.pdf"), paginas=2)
        with _AppOCR(entrada, resposta=None) as app:
            app.win.substitute_glyphs_neural_action()
            app.aguardar()

            assert not app.perguntas, "perguntou sobre páginas com texto num scan puro"
            assert app.chamadas[0]["pular_paginas_com_texto"] is True
            assert app.chamadas[0]["modo"] == "both"


def test_conversao_que_pulou_tudo_diz_o_que_fazer():
    """
    "OCR em 0, 264 já tinham texto" não é informação suficiente para quem
    escolheu a ferramenta certa e não recebeu nada.
    """
    with tempfile.TemporaryDirectory() as tmp:
        entrada = _pdf_digital(os.path.join(tmp, "in.pdf"))
        with _AppOCR(entrada, resposta=True) as app:
            app._gerar = lambda e, s, **kw: (
                app.chamadas.append(kw) or
                {"paginas": 9, "paginas_ocr": 0, "paginas_puladas": 9, "boxes": 0,
                 "reconhecidos": 0, "baixa_confianca": 0, "pecas_substituidas": 0,
                 "sem_glifo": 0})
            app.mw.gerar_pdf_pesquisavel = app._gerar

            app.win.gerar_pdf_pesquisavel_action()
            app.aguardar()

            texto = app.avisos[-1][1]
            assert "Nenhuma página foi processada" in texto, texto
            assert "«Não»" in texto or "Não»" in texto, texto


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


# ----------------------------------------------------------------------
# F18 — a leitura por linha entra, mas só onde a cadeia está fraca
# ----------------------------------------------------------------------

def _pdf_de_uma_pagina(caminho, texto="Foreword"):
    import fitz
    doc = fitz.open()
    pagina = doc.new_page(width=300, height=120)
    pagina.insert_text(fitz.Point(20, 60), texto, fontsize=28)
    doc.save(caminho)
    doc.close()


def _rodar(tmp, reconhecer, **kw):
    import os
    from core.searchable_pdf import gerar_pdf_pesquisavel
    entrada = os.path.join(tmp, "e.pdf")
    saida = os.path.join(tmp, "s.pdf")
    _pdf_de_uma_pagina(entrada)
    return gerar_pdf_pesquisavel(entrada, saida, reconhecer=reconhecer,
                                 pular_paginas_com_texto=False, **kw)


def test_sem_ler_linha_o_caminho_e_o_de_antes(tmp_path):
    """A F18 é opcional: quem não passa `ler_linha` não paga nada por ela."""
    vistos = []

    def reconhecer(crop):
        vistos.append(crop)
        return ("x", 0.99)

    resumo = _rodar(str(tmp_path), reconhecer)
    assert resumo["corrigidos_pela_linha"] == 0
    assert vistos, "o reconhecedor não foi chamado"


def test_a_linha_nao_mexe_onde_a_cadeia_esta_confiante(tmp_path):
    """
    O ponto da fase. A rede responde 98,9% dos boxes com 97,6% de acerto;
    deixar a linha sobrescrever isso custa 7,3 pontos.
    """
    chamadas = []

    def ler_linha(faixa):
        chamadas.append(faixa)
        return ("ZZZZZZZZ", 0.99)

    resumo = _rodar(str(tmp_path), lambda crop: ("x", 0.99),
                    ler_linha=ler_linha)
    assert chamadas, "a linha nem chegou a ser lida"
    assert resumo["corrigidos_pela_linha"] == 0, \
        "a linha sobrescreveu box em que a cadeia estava confiante"


def test_a_linha_manda_onde_a_cadeia_esta_fraca(tmp_path):
    def ler_linha(faixa):
        return ("ZZZZZZZZ", 0.99)

    resumo = _rodar(str(tmp_path), lambda crop: ("x", 0.10),
                    ler_linha=ler_linha)
    assert resumo["corrigidos_pela_linha"] > 0, \
        "a cadeia estava fraca e a linha não corrigiu nada"


def test_o_corte_e_configuravel(tmp_path):
    def ler_linha(faixa):
        return ("ZZZZZZZZ", 0.99)

    frouxo = _rodar(str(tmp_path), lambda crop: ("x", 0.80),
                    ler_linha=ler_linha, conf_linha_maxima=0.95)
    assert frouxo["corrigidos_pela_linha"] > 0

    apertado = _rodar(str(tmp_path), lambda crop: ("x", 0.80),
                      ler_linha=ler_linha, conf_linha_maxima=0.70)
    assert apertado["corrigidos_pela_linha"] == 0
