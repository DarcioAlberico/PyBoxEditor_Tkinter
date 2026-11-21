"""A codificação declarada pelo capítulo é honrada (RG-10, R-26).

O capítulo que declarava ISO-8859-1 ou Windows-1252 e não passava pelo analisador (o
`expat` não conhece o Windows-1252; um XHTML malformado também cai aqui) era aberto em
modo código decodificado como UTF-8 com `replace`: cada letra acentuada virava U+FFFD, e
o salvamento gravava o estrago.
"""

import zipfile

from tests.test_ida_e_volta_do_pacote import _CAP, _NAV, _OPF

from core.editor import epub, modelo as m


def _epub(tmp_path, capitulo: bytes):
    caminho = str(tmp_path / "codificacao.epub")
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml",
                   '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:'
                   'container"><rootfiles><rootfile full-path="OEBPS/content.opf" '
                   'media-type="application/oebps-package+xml"/></rootfiles></container>')
        z.writestr("OEBPS/content.opf", _OPF)
        z.writestr("OEBPS/nav.xhtml", _NAV)
        z.writestr("OEBPS/Text/c1.xhtml", capitulo)
        z.writestr("OEBPS/Images/a.svg", '<svg xmlns="http://www.w3.org/2000/svg"/>')
        z.writestr("OEBPS/Images/a.png", b"\x89PNG\r\n\x1a\n")
    return caminho


def _capitulo(codificacao: str, texto: str, quebrado: bool = False) -> bytes:
    corpo = _CAP.replace('encoding="utf-8"', f'encoding="{codificacao}"').replace("Texto.", texto)
    if quebrado:
        corpo = corpo.replace("</p>", "")
    return corpo.encode(codificacao)


def test_windows_1252_abre_com_as_letras_e_as_aspas(tmp_path):
    livro, _ = epub.ler(_epub(tmp_path, _capitulo("windows-1252", "“Ação” — é só começar.")))
    cap = livro.capitulos[0]
    texto = cap.texto_cru if cap.texto_cru is not None else " ".join(m.texto_de(b) for b in cap.blocos)
    assert "“Ação” — é só começar." in texto and "�" not in texto


def test_iso_8859_1_malformado_abre_em_modo_codigo_sem_estrago_e_salva_em_utf8(tmp_path):
    livro, _ = epub.ler(_epub(tmp_path, _capitulo("iso-8859-1", "Ação e opção", quebrado=True)))
    cap = livro.capitulos[0]
    assert cap.texto_cru is not None and "Ação e opção" in cap.texto_cru
    assert "�" not in cap.texto_cru
    # O escritor recusa capítulo malformado: o usuário o conserta no modo código, e salva.
    cap.texto_cru = cap.texto_cru.replace("opção</body>", "opção</p></body>")
    saida = str(tmp_path / "volta.epub")
    epub.escrever(livro, saida)
    with zipfile.ZipFile(saida) as z:
        gravado = z.read("OEBPS/Text/c1.xhtml")
    texto = gravado.decode("utf-8")
    assert "Ação e opção" in texto and 'encoding="utf-8"' in texto.split("?>")[0], \
        "o arquivo gravado em UTF-8 continua declarando ISO-8859-1"


def test_iso_8859_1_bem_formado_continua_pelo_analisador(tmp_path):
    livro, _ = epub.ler(_epub(tmp_path, _capitulo("iso-8859-1", "Ação")))
    cap = livro.capitulos[0]
    assert cap.texto_cru is None and any("Ação" in m.texto_de(b) for b in cap.blocos)
