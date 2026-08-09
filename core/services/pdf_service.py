"""
Carregamento e navegação de PDF, sobre PyMuPDF.

Antes usava `pdf2image`, que é um invólucro do binário externo **Poppler**: cada
página renderizada saía num subprocesso, e sem o Poppler no PATH o programa não
abria PDF nenhum. Era a fonte recorrente de erro no Windows, a ponto de a UI ter
uma mensagem só para esse caso. O PyMuPDF já era dependência do projeto — o
`chess_pdf_processor.py` e o `searchable_pdf.py` usam — e renderiza nativamente,
então a dependência nativa saiu sem nada em troca (F2.2).

**O documento é aberto a cada chamada, de propósito.** `load_page` roda dentro da
thread de trabalho da F4.1 (`main_window.py`, exportação de várias páginas) ao
mesmo tempo que a UI pode pedir outra página. Um `fitz.Document` guardado no
serviço seria estado compartilhado entre as duas, e documento do PyMuPDF não é
seguro para acesso concorrente. Abrir a partir dos bytes é barato: o PyMuPDF lê o
xref sob demanda e não decodifica página que ninguém pediu.
"""

import os
from typing import List, Optional, Tuple

import fitz  # PyMuPDF
from PIL import Image


# **Lido de uma tabela, e a tabela contradiz o comentário que estava aqui.**
#
# Este valor era 200 porque o `pdf2image.convert_from_bytes` usava 200 por
# omissão, e o comentário anterior avisava que mexer nele "mudaria
# silenciosamente todos os limiares relativos" da F1.5. Mudaria — para melhor.
# Medido nas 10 páginas rotuladas (~12.000 caracteres), F1 do pipeline inteiro:
#
#     dpi   recall   precisão     F1   espúrios
#     150    87,9%      89,1%   88,5        438
#     200    93,5%      93,2%   93,3        310
#     250    94,8%      94,3%   94,6        312
#     300    95,8%      94,8%   95,3        321
#
# São **+2,0 de F1** contra os 200 de antes, e o ganho aparece em todas as sete
# páginas do Kasparov (+2,0 a +4,1 cada, sem exceção) — o livro cuja
# digitalização tem 300 dpi de verdade. A 200 dpi o render jogava fora um terço
# da resolução que estava no arquivo.
#
# **Ampliar além do nativo não custa nada, e foi medido.** As três páginas do
# Aagaard vêm de uma imagem embutida de ~152 dpi: a 300 elas vão igual ou
# ligeiramente melhor que a 200 (+0,2 +0,3 +0,2), e a 150 — praticamente o
# nativo delas — perdem de 2,4 a 4,0. Por isso o valor é fixo e alto, e não
# "o nativo de cada documento": o nativo só diz onde há ganho a colher, não
# onde parar.
DPI_PADRAO = 300


def _para_pil(pagina: "fitz.Page", dpi: int, cinza: bool) -> Image.Image:
    """Renderiza uma página do PyMuPDF em PIL, sem passar por PNG."""
    if cinza:
        pix = pagina.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
        return Image.frombytes("L", (pix.width, pix.height), pix.samples)
    pix = pagina.get_pixmap(dpi=dpi)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


class PDFService:
    """
    Serviço puro para carregamento e navegação de PDFs.
    """

    def __init__(self):
        self.pdf_bytes: Optional[bytes] = None
        self.pdf_path: Optional[str] = None
        self.num_pages: int = 0

    def load_pdf(self, path: str) -> Tuple[int, str]:
        """
        Carrega um PDF do disco.
        Retorna (num_pages, error_message). Se error_message for vazio, sucesso.
        """
        if not os.path.exists(path):
            return 0, f"Arquivo não encontrado: {path}"

        try:
            with open(path, "rb") as f:
                dados = f.read()

            with fitz.open(stream=dados, filetype="pdf") as doc:
                # PDF protegido abre e devolve 0 páginas, o que viraria "PDF
                # vazio" mais adiante. Dizer o motivo aqui evita o diagnóstico
                # errado.
                if doc.needs_pass:
                    return 0, "PDF protegido por senha."
                paginas = doc.page_count
                if paginas <= 0:
                    return 0, "O PDF não tem páginas."

            self.pdf_bytes = dados
            self.pdf_path = path
            self.num_pages = paginas
            return self.num_pages, ""
        except Exception as e:
            self.close()
            return 0, f"Erro ao abrir PDF:\n{e}"

    def load_page(self, page_index: int) -> Optional[Image.Image]:
        """
        Carrega uma página específica do PDF previamente carregado.
        Retorna PIL.Image em grayscale (mode 'L') ou None.
        """
        if self.pdf_bytes is None:
            return None
        if not 0 <= page_index < self.num_pages:
            return None

        try:
            with fitz.open(stream=self.pdf_bytes, filetype="pdf") as doc:
                return _para_pil(doc[page_index], DPI_PADRAO, cinza=True)
        except Exception:
            return None

    def is_loaded(self) -> bool:
        return self.pdf_bytes is not None and self.num_pages > 0

    def close(self):
        self.pdf_bytes = None
        self.pdf_path = None
        self.num_pages = 0

    @staticmethod
    def convert_pdf_to_images(path: str, dpi: int = DPI_PADRAO) -> List[Image.Image]:
        """
        Converte todo um PDF em uma lista de imagens PIL.
        Útil para processamento em lote.

        Devolve RGB, como o `pdf2image` devolvia: quem chama converte para cinza
        quando precisa, e há caminho de UI que mostra a página colorida.
        """
        with open(path, "rb") as f:
            dados = f.read()

        with fitz.open(stream=dados, filetype="pdf") as doc:
            return [_para_pil(pagina, dpi, cinza=False) for pagina in doc]
