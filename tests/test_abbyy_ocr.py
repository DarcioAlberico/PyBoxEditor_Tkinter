import os

import fitz

from core import abbyy_ocr


def _pdf_de_tres_paginas(caminho):
    doc = fitz.open()
    for numero in range(3):
        pagina = doc.new_page()
        pagina.insert_text((40, 60), f"Pagina {numero + 1}")
    doc.save(caminho)
    doc.close()


def test_intervalo_abbyy_preserva_ordem_e_selecao(tmp_path):
    origem = tmp_path / "livro.pdf"
    _pdf_de_tres_paginas(str(origem))

    paginas = abbyy_ocr._pdf_do_intervalo(str(origem), [2, 0], str(tmp_path))
    with fitz.open(paginas) as recorte:
        assert len(recorte) == 2
        assert recorte[0].get_text().strip() == "Pagina 3"
        assert recorte[1].get_text().strip() == "Pagina 1"


def test_exportacao_abbyy_move_saida_com_espacos(monkeypatch, tmp_path):
    origem = tmp_path / "livro.pdf"
    _pdf_de_tres_paginas(str(origem))
    saida = tmp_path / "resultado com espacos.docx"

    monkeypatch.setattr(abbyy_ocr, "caminho_executavel",
                        lambda: "C:/ABBYY/FineReaderOCR.exe")

    def falso_run(comando, **_kwargs):
        with open(comando[comando.index("/out") + 1], "wb") as arquivo:
            arquivo.write(b"DOCX")

        class Resultado:
            returncode = 0
            stderr = ""

        return Resultado()

    monkeypatch.setattr(abbyy_ocr.subprocess, "run", falso_run)
    assert abbyy_ocr.exportar_docx(str(origem), str(saida), paginas=[1]) == str(saida)
    assert saida.read_bytes() == b"DOCX"
    assert os.path.isfile(saida)
