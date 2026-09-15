from core.ocr_result import RegionResult
from core.ocr_routing import OCRRouter, registrar_roteamento


def _region(tipo, ident="r1", metadata=None):
    return RegionResult(ident, tipo, 0, 0.9, (0, 0, 100, 40), metadata=metadata or {})


def test_prosa_vai_para_linha_e_tem_glifo_como_fallback():
    decisao = OCRRouter().decide(_region("body"))
    assert (decisao.domain, decisao.primary, decisao.fallback) == ("prose", "line", "glyph")


def test_cabecalho_e_rodape_usam_ocr_de_linha():
    for tipo in ("header", "footer"):
        decisao = OCRRouter().decide(_region(tipo))
        assert decisao.domain == "prose"
        assert decisao.primary == "line"
        assert decisao.fallback == "glyph"


def test_notacao_e_simbolo_preservam_caminho_de_glifo():
    for tipo in ("notation", "symbol"):
        decisao = OCRRouter().decide(_region(tipo))
        assert decisao.primary == "glyph"
        assert decisao.fallback == "line"


def test_especiais_nao_sao_tratados_como_prosa():
    decisao = OCRRouter().decide(_region("diagram"))
    assert decisao.domain == "diagram"
    assert decisao.primary == "special"


def test_metadata_pode_forcar_dominio_e_registro_e_serializavel():
    registro = registrar_roteamento([_region("unknown", metadata={"domain": "prose"})])
    assert registro[0]["primary"] == "line"
    assert registro[0]["reason"] == "metadata.domain"
