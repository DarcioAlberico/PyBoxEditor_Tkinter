"""
`scripts/processar_editorial.py` lê como a janela (item 8 da revisão de 2026-09-18).

O script se anunciava como "OCR editorial de produção" e montava a fachada sem
leitor — a biblioteca das Fases 3 e 4, que numa página digitalizada devolve um
bloco vazio. O padrão passou a ser o leitor medido
(`core.editorial_legacy.pipeline_de_producao`), e a biblioteca só com
`--biblioteca`. Os serviços do leitor entram por injeção: o PDF de prova é
nascido digital, lido da camada (F110), e nem o modelo nem o Tesseract são
chamados.
"""

import json
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import processar_editorial  # noqa: E402
from core.editorial_legacy import ExtratorDeLivro  # noqa: E402
from core.biblioteca.ocr_phase4 import Phase4Processor  # noqa: E402
from tests.test_f110_camada import _livro_digital  # noqa: E402


class _Aprendizado:
    def load_predictor(self):
        return True

    def motivo_do_modelo(self):
        return ""

    def leitor_de_texto(self, _idioma):
        def classificar(_recorte, _referencia=None):
            raise AssertionError("a página nascida digital não passa pelo classificador")
        return classificar

    def candidatas(self, _recorte, _k=3):
        raise AssertionError("a página nascida digital não passa pela poda da F112")


class _Motor:
    def tesseract_pagina_detalhada_conf(self, *_a, **_k):
        raise AssertionError("a página nascida digital não passa pelo Tesseract")

    tesseract_faixa_detalhada_conf = tesseract_pagina_detalhada_conf


def _args(*argv):
    return processar_editorial.construir_parser().parse_args(list(argv))


def test_a_cli_expone_limites_de_poda_do_cache():
    args = _args("livro.pdf", "-o", "x.json",
                 "--cache-max-idade-horas", "2", "--cache-max-mb", "64")
    assert args.cache_max_idade_horas == 2
    assert args.cache_max_mb == 64


def test_o_padrao_e_o_leitor_de_producao():
    pipeline, extrator = processar_editorial.montar_pipeline(
        _args("livro.pdf", "-o", "x.json", "--idioma", "pt"),
        servicos=(_Aprendizado(), _Motor()))
    assert isinstance(extrator, ExtratorDeLivro)
    assert pipeline.legacy_extractor is extrator
    # como a janela: a camada do PDF nascido digital é lida como texto (F110)
    assert (extrator.opcoes.idioma, extrator.opcoes.camada) == ("pt", "auto")


def test_ensemble_de_producao_so_e_ligado_por_flag():
    _pipeline, extrator = processar_editorial.montar_pipeline(
        _args("livro.pdf", "-o", "x.json", "--usar-ensemble"),
        servicos=(_Aprendizado(), _Motor()))

    assert extrator.opcoes.usar_ensemble is True


def test_a_biblioteca_so_por_extenso():
    pipeline, extrator = processar_editorial.montar_pipeline(
        _args("livro.pdf", "-o", "x.json", "--biblioteca"))
    assert extrator is None
    assert (pipeline.legacy_extractor, pipeline.recognizer) == (None, None)


def test_usar_engines_e_a_biblioteca_com_os_motores():
    pipeline, extrator = processar_editorial.montar_pipeline(
        _args("livro.pdf", "-o", "x.json", "--usar-engines"))
    assert extrator is None and pipeline.legacy_extractor is None
    assert isinstance(pipeline.recognizer, Phase4Processor)


def test_o_documento_sai_do_leitor_de_producao(tmp_path, capsys):
    pdf = _livro_digital(tmp_path / "d.pdf")
    saida = tmp_path / "d.json"
    assert processar_editorial.main([pdf, "-o", str(saida)],
                                    servicos=(_Aprendizado(), _Motor())) == 0
    resumo = json.loads(capsys.readouterr().out)
    assert (resumo["reader"], resumo["pages"]) == ("livro.extrair", 1)
    documento = json.loads(saida.read_text(encoding="utf-8"))
    assert documento["metadata"]["adapter"] == "legacy_extractor"
    [pagina] = documento["pages"]
    tipos = [bloco["kind"] for bloco in pagina["blocks"]]
    assert "diagram" in tipos and "paragraph" in tipos
    texto = " ".join(str(bloco["decision"]["value"]) for bloco in pagina["blocks"])
    assert "horizontal opposition" in texto


def test_o_fluxo_de_producao_pode_bloquear_antes_da_exportacao(tmp_path, capsys):
    pdf = _livro_digital(tmp_path / "d.pdf")
    saida = tmp_path / "d.json"
    assert processar_editorial.main(
        [pdf, "-o", str(saida), "--validar-qualidade"],
        servicos=(_Aprendizado(), _Motor()),
    ) == 0
    resumo = json.loads(capsys.readouterr().out)
    assert resumo["quality_gate"]["valid"] is True


def test_o_epub_sai_do_escritor_historico(tmp_path, capsys):
    pdf = _livro_digital(tmp_path / "d.pdf")
    saida = tmp_path / "d.epub"
    assert processar_editorial.main([pdf, "-o", str(saida)],
                                    servicos=(_Aprendizado(), _Motor())) == 0
    assert json.loads(capsys.readouterr().out)["files"] == [str(saida)]
    with zipfile.ZipFile(saida) as epub:
        xhtml = " ".join(epub.read(nome).decode("utf-8") for nome in epub.namelist()
                         if nome.endswith(".xhtml"))
    assert "horizontal opposition" in xhtml
    # o escritor histórico redesenha o diagrama: o PNG vai dentro do livro
    assert any(nome.endswith(".png") for nome in zipfile.ZipFile(saida).namelist())


def test_a_exportacao_de_producao_tambem_passa_pela_fachada(tmp_path):
    pdf = _livro_digital(tmp_path / "d.pdf")
    pipeline, _extrator = processar_editorial.montar_pipeline(
        _args("livro.pdf", "-o", "x.epub"),
        servicos=(_Aprendizado(), _Motor()),
    )
    documento = pipeline.process(
        processar_editorial.DocumentSource.from_path(pdf),
        processar_editorial.ProcessOptions(use_cache=False),
    )
    saida = tmp_path / "fachada.epub"

    relatorio = pipeline.export(
        documento, saida, processar_editorial.ExportOptions(format="epub")
    )

    assert relatorio.metadata["escritor"] == "exportar"
    assert relatorio.metadata["paginas"] == "leitor", "as páginas lidas é que foram escritas"
    assert relatorio.files == (str(saida),)
    with zipfile.ZipFile(saida) as epub:
        xhtml = " ".join(
            epub.read(nome).decode("utf-8")
            for nome in epub.namelist() if nome.endswith(".xhtml")
        )
        assert "horizontal opposition" in xhtml


def test_a_exportacao_de_producao_aplica_a_decisao_do_ir(tmp_path):
    from core.editorial_review import ReviewSession

    pdf = _livro_digital(tmp_path / "d.pdf")
    pipeline, _extrator = processar_editorial.montar_pipeline(
        _args("livro.pdf", "-o", "x.epub"),
        servicos=(_Aprendizado(), _Motor()),
    )
    documento = pipeline.process(
        processar_editorial.DocumentSource.from_path(pdf),
        processar_editorial.ProcessOptions(use_cache=False),
    )
    bloco = next(item for item in documento.pages[0].blocks
                 if item.kind == "paragraph")
    documento = ReviewSession(documento).edit(bloco.id, "Texto revisado pelo editor")
    saida = tmp_path / "revisado.epub"

    pipeline.export(
        documento, saida, processar_editorial.ExportOptions(format="epub")
    )

    with zipfile.ZipFile(saida) as epub:
        xhtml = " ".join(
            epub.read(nome).decode("utf-8")
            for nome in epub.namelist() if nome.endswith(".xhtml")
        )
    assert "Texto revisado pelo editor" in xhtml
