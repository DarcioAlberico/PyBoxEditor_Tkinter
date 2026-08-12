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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fitz

from core.searchable_pdf import gerar_pdf_pesquisavel, MODOS


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
