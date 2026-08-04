"""
Testes da F2.2 — leitura de PDF sem o binário externo Poppler.

O `pdf_service.py` usava `pdf2image`, invólucro do Poppler: sem o binário no
PATH, nenhum PDF abria, e a UI tinha uma mensagem de erro só para esse caso. O
PyMuPDF já era dependência (`chess_pdf_processor.py`, `searchable_pdf.py`) e
renderiza nativamente.

Dois pontos que os testes fixam porque quebrariam em silêncio:

1. **200 dpi.** Era o padrão do `pdf2image.convert_from_bytes`, e a segmentação
   da F1.5 foi calibrada em cima disso — os limiares são relativos à largura
   mediana de caractere. Renderizar noutra escala mudaria todos eles sem erro
   nenhum aparecer.
2. **`load_page` devolve 'L' e `convert_pdf_to_images` devolve RGB.** Era assim
   com o `pdf2image` e há chamador de cada tipo.

Rodar sem pytest:      python tests/test_f22_pdf_nativo.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fitz
from PIL import Image

from core.services.pdf_service import DPI_PADRAO, PDFService


def _pdf_de_teste(paginas=3, largura=300, altura=400, senha=None):
    """PDF pequeno, com um texto diferente por página."""
    doc = fitz.open()
    for i in range(paginas):
        pagina = doc.new_page(width=largura, height=altura)
        pagina.insert_text((40, 80), f"pagina {i + 1}", fontsize=28)
    caminho = os.path.join(tempfile.mkdtemp(), "teste.pdf")
    if senha:
        doc.save(caminho, encryption=fitz.PDF_ENCRYPT_AES_256,
                 owner_pw=senha, user_pw=senha)
    else:
        doc.save(caminho)
    doc.close()
    return caminho


# ----------------------------------------------------------------------
# Sem Poppler
# ----------------------------------------------------------------------

def _modulos_importados(caminho):
    """Nomes importados por um arquivo, incluindo import dentro de função."""
    import ast

    with open(caminho, encoding="utf-8") as f:
        arvore = ast.parse(f.read())

    nomes = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            nomes.update(a.name.split(".")[0] for a in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module:
            nomes.add(no.module.split(".")[0])
    return nomes


def test_nenhum_modulo_de_producao_importa_pdf2image():
    """
    O ponto da fase: nada em produção pode voltar a puxar o Poppler.

    Olha o `import` pela árvore sintática, não o texto do arquivo — o
    `pdf_service.py` cita o `pdf2image` na docstring para explicar por que ele
    saiu, e uma busca por substring reprovaria a própria documentação. O
    `pdf2image` também era importado dentro das funções, então varrer só o topo
    do arquivo não bastaria.
    """
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    culpados = []
    for pasta in ("core", "ui"):
        for atual, _, arquivos in os.walk(os.path.join(raiz, pasta)):
            if "__pycache__" in atual:
                continue
            for nome in arquivos:
                if not nome.endswith(".py"):
                    continue
                caminho = os.path.join(atual, nome)
                if "pdf2image" in _modulos_importados(caminho):
                    culpados.append(os.path.relpath(caminho, raiz))

    assert not culpados, f"voltaram a depender do Poppler: {culpados}"


def test_pdf_service_importa_pymupdf():
    import core.services.pdf_service as mod

    assert "fitz" in _modulos_importados(mod.__file__)


def test_pdf2image_nao_esta_nos_requisitos():
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    req = open(os.path.join(raiz, "requirements.txt"), encoding="utf-8").read()
    linhas = [l.strip() for l in req.splitlines()
              if l.strip() and not l.strip().startswith("#")]
    assert not any("pdf2image" in l for l in linhas), \
        "pdf2image voltou a ser dependência declarada"


# ----------------------------------------------------------------------
# Carregamento
# ----------------------------------------------------------------------

def test_load_pdf_conta_paginas():
    svc = PDFService()
    n, erro = svc.load_pdf(_pdf_de_teste(paginas=5))
    assert erro == "" and n == 5
    assert svc.is_loaded()


def test_load_pdf_arquivo_inexistente():
    svc = PDFService()
    n, erro = svc.load_pdf(os.path.join(tempfile.gettempdir(), "nao_existe_1234.pdf"))
    assert n == 0 and "não encontrado" in erro
    assert not svc.is_loaded()


def test_load_pdf_arquivo_invalido():
    caminho = os.path.join(tempfile.mkdtemp(), "falso.pdf")
    with open(caminho, "wb") as f:
        f.write(b"isto nao e um PDF")

    svc = PDFService()
    n, erro = svc.load_pdf(caminho)
    assert n == 0 and erro
    assert not svc.is_loaded()
    assert "poppler" not in erro.lower(), "mensagem ainda fala do Poppler"


def test_pdf_com_senha_diz_o_motivo():
    """
    PDF protegido abre e devolve 0 páginas — sem esta checagem viraria
    "o PDF não tem páginas", que manda o usuário para o lado errado.
    """
    svc = PDFService()
    n, erro = svc.load_pdf(_pdf_de_teste(senha="segredo"))
    assert n == 0 and "senha" in erro.lower()


def test_close_limpa_o_estado():
    svc = PDFService()
    svc.load_pdf(_pdf_de_teste())
    svc.close()
    assert not svc.is_loaded()
    assert svc.pdf_bytes is None and svc.pdf_path is None and svc.num_pages == 0
    assert svc.load_page(0) is None


# ----------------------------------------------------------------------
# Renderização
# ----------------------------------------------------------------------

def test_load_page_devolve_grayscale():
    svc = PDFService()
    svc.load_pdf(_pdf_de_teste())
    img = svc.load_page(0)
    assert isinstance(img, Image.Image)
    assert img.mode == "L", f"esperava grayscale, veio {img.mode}"


def test_load_page_usa_200_dpi():
    """
    72 pt = 1 polegada. Uma página de 300x400 pt a 200 dpi dá ~833x1111 px.

    Não é preciosismo: os limiares da F1.5 são relativos à largura mediana de
    caractere, medida nesta escala.
    """
    svc = PDFService()
    svc.load_pdf(_pdf_de_teste(largura=300, altura=400))
    img = svc.load_page(0)

    assert DPI_PADRAO == 200
    esperado = (round(300 * 200 / 72), round(400 * 200 / 72))
    assert abs(img.size[0] - esperado[0]) <= 2, f"{img.size} != ~{esperado}"
    assert abs(img.size[1] - esperado[1]) <= 2, f"{img.size} != ~{esperado}"


def test_load_page_indice_fora_da_faixa():
    svc = PDFService()
    svc.load_pdf(_pdf_de_teste(paginas=3))
    assert svc.load_page(-1) is None
    assert svc.load_page(3) is None
    assert svc.load_page(2) is not None


def test_paginas_diferentes_saem_diferentes():
    """Guarda contra devolver sempre a primeira página."""
    svc = PDFService()
    svc.load_pdf(_pdf_de_teste(paginas=3))
    a, b = svc.load_page(0), svc.load_page(2)
    assert a.tobytes() != b.tobytes()


def test_load_page_tem_tinta():
    """Página em branco significaria render silenciosamente vazio."""
    svc = PDFService()
    svc.load_pdf(_pdf_de_teste())
    img = svc.load_page(0)
    extremos = img.getextrema()
    assert extremos[0] < 128, "a página saiu toda clara — nada foi renderizado"


def test_convert_pdf_to_images_devolve_rgb():
    caminho = _pdf_de_teste(paginas=4)
    imagens = PDFService.convert_pdf_to_images(caminho)
    assert len(imagens) == 4
    assert all(i.mode == "RGB" for i in imagens), \
        "quem chama espera RGB, como o pdf2image devolvia"


def test_convert_pdf_to_images_respeita_o_dpi():
    caminho = _pdf_de_teste(paginas=1, largura=300, altura=400)
    baixo = PDFService.convert_pdf_to_images(caminho, dpi=100)[0]
    alto = PDFService.convert_pdf_to_images(caminho, dpi=200)[0]
    assert alto.size[0] > baixo.size[0] * 1.8


# ----------------------------------------------------------------------
# Concorrência — load_page roda na thread de trabalho da F4.1
# ----------------------------------------------------------------------

def test_load_page_e_seguro_entre_threads():
    """
    `main_window.py` chama `load_page` de dentro da thread de trabalho enquanto
    a UI pode pedir outra página. Por isso o documento é aberto por chamada, e
    não guardado no serviço: `fitz.Document` não é seguro para acesso
    concorrente.
    """
    import threading

    svc = PDFService()
    svc.load_pdf(_pdf_de_teste(paginas=4))

    resultados, erros = {}, []

    def trabalho(i):
        try:
            img = svc.load_page(i % 4)
            resultados[i] = None if img is None else img.size
        except Exception as e:
            erros.append(e)

    fios = [threading.Thread(target=trabalho, args=(i,)) for i in range(12)]
    for f in fios:
        f.start()
    for f in fios:
        f.join()

    assert not erros, f"acesso concorrente falhou: {erros[:3]}"
    assert len(resultados) == 12
    assert all(v is not None for v in resultados.values())


def test_servico_nao_guarda_documento_aberto():
    """Se voltar a guardar um fitz.Document, o teste acima vira intermitente."""
    svc = PDFService()
    svc.load_pdf(_pdf_de_teste())
    svc.load_page(0)
    guardados = [v for v in vars(svc).values() if isinstance(v, fitz.Document)]
    assert not guardados, "o serviço passou a guardar um fitz.Document"


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
