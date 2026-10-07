"""Integração opcional com o ABBYY FineReader PDF instalado no Windows.

O exportador próprio reconhece caracteres isolados para poder reconstruir os
diagramas. Isso é uma estratégia ruim para prosa corrida: palavras deixam de
ser contexto e erros como ``O/0`` e ``l/1`` se acumulam. Quando o FineReader
está instalado, ele faz o OCR de página inteira e entrega ao Word o texto
reconhecido pelo seu próprio analisador de layout.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Sequence


CAMINHOS_CONHECIDOS = (
    Path(r"C:\Program Files\ABBYY FineReader 16\FineReaderOCR.exe"),
    Path(r"C:\Program Files (x86)\ABBYY FineReader 16\FineReaderOCR.exe"),
)


def caminho_executavel() -> Optional[str]:
    """Retorna o executável do FineReader 16, se estiver instalado."""
    candidatos = list(CAMINHOS_CONHECIDOS)
    for variavel in ("ProgramFiles", "ProgramFiles(x86)"):
        pasta = os.environ.get(variavel)
        if pasta:
            candidatos.append(Path(pasta) / "ABBYY FineReader 16"
                              / "FineReaderOCR.exe")
    for candidato in candidatos:
        if candidato.is_file():
            return str(candidato)
    return None


def disponivel() -> bool:
    return caminho_executavel() is not None


def _pdf_do_intervalo(caminho_pdf: str, paginas: Sequence[int], pasta: str) -> str:
    """Cria um PDF temporário com os índices zero-based pedidos."""
    import fitz

    origem = fitz.open(caminho_pdf)
    try:
        total = len(origem)
        numeros = list(paginas)
        if not numeros or any(not 0 <= n < total for n in numeros):
            raise ValueError("intervalo de páginas fora dos limites do PDF")
        destino = fitz.open()
        try:
            for numero in numeros:
                destino.insert_pdf(origem, from_page=numero, to_page=numero)
            caminho = os.path.join(pasta, "paginas_selecionadas.pdf")
            destino.save(caminho)
            return caminho
        finally:
            destino.close()
    finally:
        origem.close()


def exportar_docx(caminho_pdf: str, caminho_docx: str, *,
                  paginas: Optional[Sequence[int]] = None,
                  idioma: str = "English", timeout: int = 1800) -> str:
    """Reconhece ``caminho_pdf`` com ABBYY e grava o DOCX pedido.

    ``paginas`` usa índices zero-based, como ``livro.extrair``. A lista pode
    ser não contígua; isso permite reaproveitar a mesma seleção da UI.
    """
    executavel = caminho_executavel()
    if executavel is None:
        raise FileNotFoundError("ABBYY FineReader 16 não foi encontrado")

    with tempfile.TemporaryDirectory(prefix="pyboxeditor_abbyy_") as pasta:
        origem = (caminho_pdf if paginas is None else
                  _pdf_do_intervalo(caminho_pdf, paginas, pasta))
        relatorio = os.path.join(pasta, "relatorio.xml")
        # O FineReader 16 registra corretamente a origem com espaços, mas em
        # algumas instalações rejeita o destino com espaços e ainda devolve
        # código 0. Um nome temporário simples evita esse falso sucesso.
        saida_temporaria = os.path.join(pasta, "resultado.docx")
        comando = [executavel, origem, "/lang", idioma, "/out",
                   saida_temporaria,
                   "/report", relatorio]
        try:
            processo = subprocess.run(
                comando, check=False, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=timeout)
        except subprocess.TimeoutExpired as erro:
            raise TimeoutError(
                f"O ABBYY não terminou em {timeout // 60} minuto(s).") from erro

        if processo.returncode != 0 or not os.path.isfile(saida_temporaria):
            detalhe = ""
            if os.path.isfile(relatorio):
                detalhe = Path(relatorio).read_text(
                    encoding="utf-8", errors="replace")[-3000:]
            elif processo.stderr:
                detalhe = processo.stderr[-3000:]
            raise RuntimeError(
                f"O ABBYY não conseguiu exportar o DOCX (código "
                f"{processo.returncode}).\n{detalhe}")
        os.makedirs(os.path.dirname(os.path.abspath(caminho_docx)),
                    exist_ok=True)
        shutil.move(saida_temporaria, caminho_docx)
    return caminho_docx
