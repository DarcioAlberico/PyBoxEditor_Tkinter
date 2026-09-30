"""
Testes da ED-17 (Arquivo → Abrir PDF…): `core/editor/abrir_pdf.py` (faixa, comando, a
`Tarefa` com processos de verdade que imitam o canal), `scripts/pdf_para_editor.py` (o canal
e o erro de argumento), o `DialogoAbrirPdf` com um PDF gerado, e o fluxo na janela — o
processo de leitura trocado por um que devolve um documento editorial sintético, que vira
livro novo. O teste `slow` roda o leitor de produção de verdade num PDF de duas páginas.

Rodar sem pytest:      python tests/test_editor_abrir_pdf.py
"""

import json
import os
import sys
import textwrap
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from core.editor import abrir_pdf as ap


def _pdf(caminho, paginas=5, texto="Página {n}: 1.e4 e5 2.Cf3 Cc6 3.Bb5 a6, a abertura espanhola. " * 6):
    import fitz

    doc = fitz.open()
    for n in range(1, paginas + 1):
        pagina = doc.new_page(width=300, height=420)
        pagina.insert_textbox(fitz.Rect(20, 20, 280, 400), texto.format(n=n), fontsize=9)
    doc.save(str(caminho))
    doc.close()
    return str(caminho)


# ----------------------------------------------------------------------
# O núcleo
# ----------------------------------------------------------------------

def test_faixa_de_paginas_nos_dois_sentidos():
    assert ap.faixa_de("30-32, 60 31", 100) == [30, 31, 32, 60]
    assert ap.faixa_de("5–7;9", None) == [5, 6, 7, 9]
    assert ap.faixa_de("", 3) == [1, 2, 3]
    for ruim in ("0", "5-3", "a", "3-"):
        with pytest.raises(ValueError):
            ap.faixa_de(ruim, 100)
    with pytest.raises(ValueError, match="passa do fim"):
        ap.faixa_de("99-101", 100)
    assert ap.texto_da_faixa([60, 30, 31, 32, 31]) == "30-32, 60"
    assert ap.texto_da_faixa([]) == ""


def test_saida_ao_lado_do_pdf_e_o_comando():
    pdf = os.path.join("C:\\livros", "Livro X.pdf") if os.name == "nt" else "/livros/Livro X.pdf"
    assert ap.saida_padrao(pdf, [30, 31, 60]).endswith("Livro X_p30-31_60.json")
    pedido = ap.Pedido(pdf=pdf, paginas=[3, 4], idioma="pt", camada="nunca", reparar=True)
    assert pedido.saida == ap.saida_padrao(pdf, [3, 4])
    argv = ap.comando(pedido, python="py")
    assert argv[:3] == ["py", ap.SCRIPT, os.path.abspath(pdf)]
    assert argv[argv.index("--paginas") + 1:argv.index("--paginas") + 3] == ["3", "4"]
    assert "--reparar" in argv and argv[argv.index("--camada") + 1] == "nunca"
    assert argv[argv.index("--idioma") + 1] == "pt"


def test_informacoes_conta_as_paginas_com_texto(tmp_path):
    pdf = _pdf(tmp_path / "a.pdf", paginas=3)
    info = ap.informacoes(pdf)
    assert info["paginas"] == 3 and info["com_texto"] == info["amostradas"] == 3


def _esperar(tarefa, segundos=20):
    fim = time.time() + segundos
    eventos = []
    while time.time() < fim:
        eventos += tarefa.eventos()
        if tarefa.terminou:
            return eventos + tarefa.eventos()
        time.sleep(0.05)
    raise AssertionError("a tarefa não terminou")


def test_tarefa_le_o_canal_e_separa_o_texto_solto():
    codigo = ("import json,sys\n"
              "print(json.dumps({'evento':'progresso','atual':1,'total':2}), flush=True)\n"
              "print('isto nao e json', flush=True)\n"
              "print('ruido no stderr', file=sys.stderr, flush=True)\n"
              "print(json.dumps({'evento':'fim','arquivo':'x.json','paginas':2,'avisos':[]}), flush=True)\n")
    tarefa = ap.Tarefa([sys.executable, "-c", codigo]).iniciar()
    eventos = _esperar(tarefa)
    assert [e["evento"] for e in eventos] == ["progresso", "texto", "fim"]
    assert tarefa.codigo == 0 and "ruido no stderr" in tarefa.stderr()


def test_tarefa_cancelada_mata_o_processo():
    tarefa = ap.Tarefa([sys.executable, "-c", "import time; time.sleep(60)"]).iniciar()
    time.sleep(0.2)
    tarefa.cancelar()
    _esperar(tarefa)
    assert tarefa.cancelada and tarefa.codigo != 0


def test_o_script_recusa_pagina_zero_pelo_canal(tmp_path, monkeypatch):
    import io

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
    import pdf_para_editor

    canal = io.StringIO()
    monkeypatch.setattr(pdf_para_editor, "_CANAL", canal)
    assert pdf_para_editor.main([str(tmp_path / "a.pdf"), "-o", str(tmp_path / "a.json"), "--paginas", "0"]) == 1
    eventos = [json.loads(linha) for linha in canal.getvalue().splitlines()]
    assert eventos == [{"evento": "erro", "mensagem": "--paginas usa números 1-based positivos"}]


# ----------------------------------------------------------------------
# O diálogo
# ----------------------------------------------------------------------

def test_dialogo_marca_nos_dois_sentidos_e_devolve_o_pedido(tmp_path):
    from conftest import raiz_tk
    from ui.editor.dialogo_pdf import DialogoAbrirPdf

    raiz = raiz_tk()
    if raiz is None:
        pytest.skip("sem display")
    try:
        pdf = _pdf(tmp_path / "livro.pdf", paginas=6)
        caixa = DialogoAbrirPdf(raiz, pdf, {"idioma": "pt", "camada": "nunca"})
        caixa.construir()
        raiz.update()
        assert caixa.total == 6
        caixa.var_paginas.set("2-3")
        assert caixa.marcadas == {2, 3}
        caixa.alternar(5)
        assert caixa.var_paginas.get() == "2-3, 5"
        caixa.alternar(3)                                     # desmarca
        caixa.alternar(6, faixa=True)                         # Shift: de 3 a 6
        assert caixa.var_paginas.get() == "2-6"
        assert caixa.var_saida.get().endswith("livro_p2-6.json")
        # o clique numa miniatura acha a página pela posição
        x, y = caixa._posicao(4)
        assert caixa.pagina_em(x + 5, y + 5) == 4
        # a miniatura das páginas visíveis foi desenhada
        caixa._desenhar_visiveis()
        assert caixa._imagens
        # faixa ruim: aviso, e a caixa não fecha
        caixa.var_paginas.set("9")
        assert "passa do fim" in caixa.aviso.cget("text")
        assert caixa.confirmar() is None and caixa.top is not None
        caixa.var_paginas.set("1, 4")
        pedido = caixa.confirmar()
        assert pedido.paginas == [1, 4] and pedido.camada == "nunca" and pedido.idioma == "pt"
        assert pedido.dividir == "pagina" and pedido.saida.endswith("livro_p1_4.json") and caixa.top is None
    finally:
        raiz.destroy()


# ----------------------------------------------------------------------
# Na janela
# ----------------------------------------------------------------------

def _leitor_de_mentira(tmp_path, documento_json, falhar=False):
    """Um `pdf_para_editor.py` que emite o canal e copia um documento pronto para o `-o`."""
    script = tmp_path / "leitor.py"
    script.write_text(textwrap.dedent(f"""
        import json, shutil, sys
        saida = sys.argv[sys.argv.index("-o") + 1]
        def emitir(**d): print(json.dumps(d), flush=True)
        emitir(evento="inicio", paginas=[1, 2])
        emitir(evento="etapa", texto="Carregando o modelo…")
        emitir(evento="progresso", atual=0, total=2)
        emitir(evento="progresso", atual=1, total=2)
        if {falhar!r}:
            emitir(evento="erro", mensagem="RuntimeError: o Tesseract não está instalado")
            sys.exit(1)
        shutil.copy({str(documento_json)!r}, saida)
        emitir(evento="progresso", atual=2, total=2)
        emitir(evento="fim", arquivo=saida, paginas=2, avisos=["um aviso do pipeline"])
        import time; time.sleep(0.6)      # o de verdade demora a sair depois do fim
    """), encoding="utf-8")
    return str(script)


def _rodar(t, pedido, segundos=30):
    j = t.j
    resultados = []
    j.leitura_de_pdf.ao_terminar = resultados.append
    j.leitura_de_pdf.mostrar_progresso = False
    j.leitura_de_pdf.abrir_pdf(pedido=pedido)
    fim = time.time() + segundos
    while not resultados and time.time() < fim:
        j.update()
        time.sleep(0.03)
    assert resultados, "a leitura não terminou"
    return resultados[0]


def test_abrir_pdf_vira_livro_novo_com_as_paginas(tmp_path, monkeypatch):
    from editor_ambiente import Janela
    from test_editor_importar_ir import documento_sintetico

    documento = tmp_path / "pronto.json"
    documento_sintetico("khenkin").save_json(documento)
    monkeypatch.setattr(ap, "SCRIPT", _leitor_de_mentira(tmp_path, documento))
    pdf = _pdf(tmp_path / "Khenkin.pdf", paginas=3)
    with Janela() as t:
        j = t.j
        assert j.menus.estado("abrir_pdf") == "normal"
        pedido = ap.Pedido(pdf=pdf, paginas=[1, 2], idioma="en", camada="nunca")
        projeto = _rodar(t, pedido)
        assert projeto is not None and j.projeto is projeto
        assert os.path.isfile(pedido.saida)                                   # o JSON ao lado do PDF
        livro = projeto.livro
        assert len(livro.capitulos) >= 3                                      # um capítulo por página
        assert projeto.caminho is None and projeto.sujo                       # livro novo: Salvar como…
        assert projeto.diario and projeto.diario.startswith(os.path.splitext(pedido.saida)[0])
        assert j._preferencia("abrir_pdf", {}).get("camada") == "nunca"      # a escolha fica para a próxima
        assert "PDF aberto como livro novo" in j.campos["aviso"].cget("text")
        assert j.leitura_de_pdf.tarefa is None


def test_abrir_pdf_que_falha_avisa_e_nao_troca_o_livro(tmp_path, monkeypatch):
    from editor_ambiente import Janela
    from test_editor_importar_ir import documento_sintetico

    documento = tmp_path / "pronto.json"
    documento_sintetico().save_json(documento)
    monkeypatch.setattr(ap, "SCRIPT", _leitor_de_mentira(tmp_path, documento, falhar=True))
    pdf = _pdf(tmp_path / "a.pdf", paginas=2)
    with Janela() as t:
        j = t.j
        antes = j.projeto
        assert _rodar(t, ap.Pedido(pdf=pdf, paginas=[1, 2])) is None
        assert j.projeto is antes
        assert "Tesseract" in j.leitura_de_pdf.ultimo_erro
        assert any("Tesseract" in m for m in t.caixas.entradas())


def test_abrir_pdf_cancelado_e_segunda_leitura_recusada(tmp_path, monkeypatch):
    from editor_ambiente import Janela

    lento = tmp_path / "lento.py"
    lento.write_text("import time, json\nprint(json.dumps({'evento':'inicio'}), flush=True)\ntime.sleep(60)\n",
                     encoding="utf-8")
    monkeypatch.setattr(ap, "SCRIPT", str(lento))
    pdf = _pdf(tmp_path / "a.pdf", paginas=2)
    with Janela() as t:
        j = t.j
        leitura = j.leitura_de_pdf
        resultados = []
        leitura.ao_terminar = resultados.append
        leitura.mostrar_progresso = False
        leitura.abrir_pdf(pedido=ap.Pedido(pdf=pdf, paginas=[1]))
        with pytest.raises(ValueError, match="já há um PDF"):
            leitura.abrir_pdf(pedido=ap.Pedido(pdf=pdf, paginas=[2]))
        assert j.executar("cancelar_pdf") is True
        fim = time.time() + 20
        while not resultados and time.time() < fim:
            j.update()
            time.sleep(0.03)
        assert resultados == [None] and "cancelada" in j.campos["aviso"].cget("text")


def test_o_seletor_de_pdf_e_a_caixa_sao_pedidos(tmp_path, monkeypatch):
    from editor_ambiente import Janela

    pdf = _pdf(tmp_path / "a.pdf", paginas=2)
    with Janela() as t:
        j = t.j
        pedidos = []
        j.leitura_de_pdf.pedir_pedido = lambda caminho: (pedidos.append(caminho), None)[1]
        j.caixas.abrir = lambda *a, **k: pdf
        assert j.executar("abrir_pdf") is None and pedidos == [os.path.abspath(pdf)]
        assert j.leitura_de_pdf.tarefa is None                                  # cancelou na caixa


@pytest.mark.slow
def test_o_leitor_de_verdade_le_duas_paginas(tmp_path):
    """O script de verdade (modelo, Tesseract, camada do PDF) em duas páginas geradas."""
    from config.paths import caminhos_modelo_glifos

    if not os.path.isfile(str(caminhos_modelo_glifos()[0])):
        # O modelo é treinado na máquina de quem usa (`*.pth` no .gitignore): a CI não o tem.
        pytest.skip("custom_model.pth fica fora do git; sem ele o leitor de produção não monta")
    pdf = _pdf(tmp_path / "real.pdf", paginas=2)
    pedido = ap.Pedido(pdf=pdf, paginas=[1, 2], camada="sempre")
    tarefa = ap.Tarefa(ap.comando(pedido)).iniciar()
    eventos = _esperar(tarefa, segundos=300)
    fim = [e for e in eventos if e["evento"] == "fim"]
    assert fim and tarefa.codigo == 0, tarefa.stderr()[-2000:]
    from core.editor import importar_ir
    from core.editorial_model import EditorialDocument

    livro, _rel = importar_ir.de_documento(EditorialDocument.load_json(fim[0]["arquivo"]), dividir="pagina")
    texto = " ".join(importar_ir.modelo.texto_de(b) for c in livro.capitulos for b in c.blocos
                     if hasattr(b, "trechos"))
    assert "abertura espanhola" in texto


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-o", "addopts="]))
