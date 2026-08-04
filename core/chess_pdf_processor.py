import fitz  # PyMuPDF
import os
from typing import Tuple

from core import perfis, relatorio_pdf


def _primeira_fonte_de_xadrez(block: dict) -> str:
    """Nome da primeira fonte de xadrez do bloco, ou '' se não houver."""
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            nome = span.get("font", "")
            if is_chess_font(nome):
                return nome
    return ""

# Keywords to detect chess fonts
CHESS_FONT_KEYWORDS = [
    "chess", "merida", "diagram", "figurine", "skak", "cburnett", "alpha", "leipzig"
]

# Os 12 símbolos Unicode de peças (U+2654..U+265F).
CHESS_UNICODE = "\u2654\u2655\u2656\u2657\u2658\u2659\u265A\u265B\u265C\u265D\u265E\u265F"

# Fontes candidatas, em ordem de preferência.
# ATENÇÃO: a maioria das fontes comuns NÃO tem estes glifos. Verificado neste
# sistema: Arial, Segoe UI, Times e Calibri falham nas 12 peças; apenas
# Segoe UI Symbol e MS Gothic cobrem. Por isso resolve_chess_font() valida a
# cobertura de verdade em vez de só checar se o arquivo existe.
CHESS_FONT_CANDIDATES = [
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "assets", "fonts", "DejaVuSans.ttf"),   # empacotada (preferencial)
    r"C:\Windows\Fonts\seguisym.ttf",                    # Segoe UI Symbol
    r"C:\Windows\Fonts\msgothic.ttc",                    # MS Gothic
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSerif.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
]


class ChessFontError(RuntimeError):
    """Nenhuma fonte disponível consegue desenhar as peças de xadrez."""


def missing_glyphs(font_path: str, chars: str = CHESS_UNICODE) -> list:
    """Retorna os caracteres que a fonte NÃO consegue desenhar."""
    font = fitz.Font(fontfile=font_path)
    # has_glyph devolve o id do glifo; 0 significa ausente.
    return [c for c in chars if not font.has_glyph(ord(c))]


def resolve_chess_font(chars: str = CHESS_UNICODE) -> str:
    """
    Primeira fonte candidata que cobre TODOS os caracteres pedidos.

    Levanta ChessFontError se nenhuma servir. Falhar alto aqui é proposital:
    a alternativa é o PyMuPDF trocar cada peça por '·' sem avisar, e o usuário
    só descobrir ao abrir o PDF já convertido.
    """
    tentativas = []
    for path in CHESS_FONT_CANDIDATES:
        if not os.path.exists(path):
            continue
        try:
            falta = missing_glyphs(path, chars)
        except Exception as e:
            tentativas.append(f"  {path}: erro ao ler ({e})")
            continue
        if not falta:
            return path
        tentativas.append(f"  {path}: não cobre {''.join(falta)}")

    detalhe = "\n".join(tentativas) if tentativas else "  (nenhuma candidata encontrada no disco)"
    raise ChessFontError(
        "Nenhuma fonte disponível desenha os símbolos de xadrez.\n"
        f"Fontes testadas:\n{detalhe}\n\n"
        "Solução: coloque DejaVuSans.ttf em assets/fonts/ "
        "(https://dejavu-fonts.github.io/)."
    )

# Default profile for mapping chess pseudo-ASCII to Unicode
# This is a generic fallback that attempts to cover the most common mappings.
DEFAULT_MAPPING_PROFILE = {
    # Merida / standard
    "K": "♔", "Q": "♕", "R": "♖", "B": "♗", "N": "♘", "P": "♙",
    "k": "♚", "q": "♛", "r": "♜", "b": "♝", "n": "♞", "p": "♟",
    " ": " ", ".": "·", "-": " ",
    # Sometimes they use A-F or other mappings, we can expand this profile if needed.
}


def is_chess_font(font_name: str) -> bool:
    """Check if the font name contains typical chess font keywords."""
    font_lower = font_name.lower()
    return any(kw in font_lower for kw in CHESS_FONT_KEYWORDS)


def is_diagram_span(span: dict) -> bool:
    """
    Check if a span is likely part of a diagram.
    For inline substitution, we want to IGNORE these spans.
    A diagram span usually has:
    - Only a few characters but it's part of a very dense block, OR
    - It's very wide/tall, OR
    - It contains repetitive structures (though this is harder to check on a single span level).
    
    A simpler heuristic contextually:
     diagrams usually consist of many lines of chess fonts in a single block.
    """
    # This function is a placeholder; diagram detection is better done at the block level.
    # We will implement diagram detection at the block level in the main function.
    return False


def is_block_a_diagram(block: dict, perfil=None) -> bool:
    """
    Detect if a text block is likely a chess diagram (8x8 grid).
    Heuristic: A diagram is usually a block with multiple lines (often ~8 or more)
    where almost all text uses a chess font.

    Os dois limiares vêm do perfil quando há um (F2.4). Eles precisam ser por
    livro: fonte com subset e nome aleatório (`ABCD+F1`) muda a proporção de
    spans que esta conta enxerga como de xadrez.
    """
    min_linhas = getattr(perfil, "min_linhas_diagrama", 4)
    razao_minima = getattr(perfil, "razao_span_xadrez", 0.7)

    if "lines" not in block:
        return False

    line_count = len(block["lines"])
    if line_count < min_linhas:  # Too few lines to be a full diagram
        return False

    chess_span_count = 0
    total_span_count = 0

    for line in block["lines"]:
        for span in line["spans"]:
            total_span_count += 1
            if is_chess_font(span["font"]):
                chess_span_count += 1

    # If a high percentage of spans in this large block are chess fonts, it's a diagram.
    return total_span_count > 0 and (chess_span_count / total_span_count) > razao_minima


# Caracteres que atravessam a substituição sem tradução e **assim mesmo estão
# certos**: coluna, fila, captura, xeque, promoção, roque, anotação. Sem esta
# lista a confiança de "Nf3" daria 0,33 — só o 'N' está no perfil — e o aviso
# dispararia em toda notação normal, que é o mesmo que não avisar.
NOTACAO_ESPERADA = set("abcdefgh12345678xX+#=O0o-–—!?()[]{}.,;:/ ")


def _confianca_do_mapeamento(texto: str, mapping_profile: dict) -> float:
    """
    Fração dos caracteres do span que a conversão soube o que fazer.

    Não há OCR neste caminho — o texto vem do próprio PDF —, então "confiança"
    aqui é sobre o **mapeamento**, não sobre leitura. Conta como conhecido tanto
    o que o perfil traduz quanto o que é notação legítima de passagem; o que
    sobra é caractere que a conversão copiou sem saber o que era, e um span
    cheio deles é sinal de perfil errado para este livro.
    """
    if not texto:
        return 1.0
    conhecidos = sum(1 for c in texto
                     if c in mapping_profile or c in NOTACAO_ESPERADA)
    return conhecidos / len(texto)


def process_span(page: fitz.Page, span: dict, mapping_profile: dict,
                 fontname: str, font: fitz.Font,
                 pagina_num: int = 0, dry_run: bool = False):
    """
    Substitui os glifos de xadrez de um span por texto Unicode.

    'fontname' é o alias já registrado na página via page.insert_font(), e 'font'
    o objeto fitz.Font correspondente (usado para medir a largura do texto).

    Devolve a `Substituicao` correspondente, ou None se o span não era de fonte
    de xadrez. Com `dry_run=True` mede tudo e **não escreve nada** na página: é a
    mesma travessia, os mesmos avisos, o mesmo cálculo de encolhimento — o que
    permite conferir o relatório antes de deixar o conversor tocar no arquivo.
    """
    font_name = span.get("font", "")
    if not is_chess_font(font_name):
        return None  # Not a chess font, do nothing

    original_text = span.get("text", "")
    if not original_text:
        return None

    bbox = fitz.Rect(span["bbox"])

    # Map the text
    new_text = "".join(mapping_profile.get(char, char) for char in original_text)

    avisos = []
    # A fonte de saída foi validada em resolve_chess_font() para as 12 peças, mas
    # o span pode trazer caractere fora desse conjunto (dígito, sinal de xeque),
    # e aí o PyMuPDF desenha um vazio sem reclamar.
    if any(not font.has_glyph(ord(c)) for c in new_text):
        avisos.append("fonte_sem_glifo")

    confianca = _confianca_do_mapeamento(original_text, mapping_profile)
    if confianca < relatorio_pdf.LIMIAR_CONFIANCA:
        avisos.append("confianca_baixa")

    # Ajustar o corpo da fonte para caber na largura original.
    # Os símbolos Unicode costumam ser mais largos que os glifos da fonte de
    # xadrez, e estourar o bbox empurraria a notação por cima do texto vizinho.
    corpo_original = span["size"]
    size = corpo_original
    largura_alvo = bbox.width
    if largura_alvo > 0:
        limite = size * 0.6  # abaixo disso a leitura sofre; melhor deixar estourar
        while size > limite and font.text_length(new_text, fontsize=size) > largura_alvo:
            size -= 0.5

    if corpo_original > 0 and size / corpo_original < relatorio_pdf.LIMIAR_ENCOLHIMENTO:
        avisos.append("fonte_reduzida")

    sub = relatorio_pdf.Substituicao(
        pagina=pagina_num,
        bbox=(bbox.x0, bbox.y0, bbox.x1, bbox.y1),
        fonte_original=font_name,
        texto_original=original_text,
        texto_substituto=new_text,
        confianca=confianca,
        corpo_original=corpo_original,
        corpo_final=size,
        aplicada=not dry_run,
        avisos=avisos,
    )

    if dry_run:
        return sub

    # 1. Erase the original text by drawing a white rectangle over the bounding box
    # We use white assuming white background. Ideally, we should detect background color,
    # but for most PDFs white is safe.
    page.draw_rect(bbox, color=(1, 1, 1), fill=(1, 1, 1))

    # 2. Escrever na baseline do span original.
    #    insert_text (e não insert_textbox): o textbox reflui o conteúdo dentro do
    #    retângulo e desloca a notação inline; para um trecho curto como "♘f3" o
    #    que importa é manter o alinhamento com a linha de texto.
    origin = span.get("origin") or (bbox.x0, bbox.y1)

    page.insert_text(
        fitz.Point(origin),
        new_text,
        fontname=fontname,
        fontsize=size,
    )
    return sub


def _resolver_perfil(nome_da_fonte, perfil, perfis_disponiveis):
    """
    Perfil a usar num span: o forçado, o que casa com a fonte, ou nenhum.

    `perfil` explícito ganha de tudo — é o override manual que a SPEC pede na UI.
    """
    if perfil is not None:
        return perfil
    if not perfis_disponiveis:
        return None
    return perfis.escolher(nome_da_fonte, perfis_disponiveis)


def analisar_substituicao(input_pdf: str, output_pdf: str,
                          mapping_profile: dict = None, progress_callback=None,
                          dry_run: bool = False,
                          gravar_relatorio: bool = True,
                          perfil=None, usar_perfis: bool = True):
    """
    Percorre o PDF, substitui os glifos de xadrez e devolve o relatório (F2.3).

    Com `dry_run=True` faz exatamente a mesma travessia — mesma detecção de
    diagrama, mesmos avisos, mesmo cálculo de encolhimento de corpo — e **não
    grava o PDF**. É a única forma de conferir antes: o conversor apaga o texto
    original com um retângulo branco e desenha outro por cima, e depois de
    gravado não há como comparar com o que havia.

    O relatório vai em JSON e CSV ao lado do arquivo de saída. Em dry-run os
    nomes levam `_simulacao` em vez de `_relatorio`, para os dois poderem
    conviver e serem comparados.
    """
    if not os.path.exists(input_pdf):
        raise FileNotFoundError(f"Arquivo não encontrado: {input_pdf}")

    # `mapping_profile` explícito desliga a seleção por perfil: quem passou um
    # dicionário quer aquele mapeamento, e não que o arquivo escolha outro.
    mapeamento_forcado = mapping_profile is not None
    if mapping_profile is None:
        mapping_profile = DEFAULT_MAPPING_PROFILE

    perfis_disponiveis = []
    if usar_perfis and not mapeamento_forcado and perfil is None:
        perfis_disponiveis = perfis.carregar_todos()

    try:
        doc = fitz.open(input_pdf)
    except Exception as e:
        raise Exception(f"Erro ao abrir PDF: {e}")

    # Resolver a fonte ANTES de tocar no documento: se nenhuma fonte do sistema
    # desenhar as peças, é melhor abortar do que gerar um PDF com '·' no lugar
    # de cada símbolo. resolve_chess_font() levanta ChessFontError nesse caso.
    font_path = resolve_chess_font()
    font_obj = fitz.Font(fontfile=font_path)
    FONT_ALIAS = "chessuni"

    rel = relatorio_pdf.RelatorioSubstituicao(
        arquivo_entrada=input_pdf,
        arquivo_saida="" if dry_run else output_pdf,
        dry_run=dry_run,
        total_paginas=len(doc),
        fonte_saida=font_path,
    )

    for page_num, page in enumerate(doc):
        # Em dry-run nem o alias é registrado: insert_font já altera o documento,
        # e o combinado é não encostar nele.
        if not dry_run:
            page.insert_font(fontname=FONT_ALIAS, fontfile=font_path)

        # Notify progress
        if progress_callback:
            progress_callback(page_num, rel.total_paginas)

        # Extract text blocks with detailed layout info
        text_page = page.get_text("dict")
        if "blocks" not in text_page:
            continue

        for block in text_page["blocks"]:
            # Skip image blocks
            if block.get("type", 0) != 0:
                continue

            # O perfil do bloco sai da primeira fonte de xadrez que ele contém —
            # os limiares de diagrama são por livro, e um bloco não mistura
            # livros.
            perfil_do_bloco = _resolver_perfil(
                _primeira_fonte_de_xadrez(block), perfil, perfis_disponiveis)

            # Nível 1: Filter out diagrams
            if is_block_a_diagram(block, perfil_do_bloco):
                # Registrado, não descartado em silêncio: é a heurística com
                # mais chance de errar, e sem isto um diagrama tratado como
                # texto (ou o contrário) não deixa rastro nenhum.
                spans = sum(len(l.get("spans", [])) for l in block.get("lines", []))
                rel.diagramas_ignorados.append((page_num, spans))
                continue

            # Nível 2: Process inline text
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    if not is_chess_font(span["font"]):
                        continue
                    escolhido = _resolver_perfil(span["font"], perfil,
                                                 perfis_disponiveis)
                    sub = process_span(
                        page, span,
                        escolhido.mapeamento if escolhido else mapping_profile,
                        FONT_ALIAS, font_obj,
                        pagina_num=page_num, dry_run=dry_run)
                    if sub is not None:
                        sub.perfil = escolhido.nome if escolhido else ""
                        rel.substituicoes.append(sub)

    if not dry_run:
        try:
            doc.save(output_pdf)
        except Exception as e:
            doc.close()
            raise Exception(f"Erro ao salvar PDF: {e}")
    doc.close()

    if gravar_relatorio and output_pdf:
        relatorio_pdf.gravar(output_pdf, rel)

    return rel


def substitute_chess_glyphs(input_pdf: str, output_pdf: str, mapping_profile: dict = None,
                            progress_callback=None) -> Tuple[int, int]:
    """
    Reads a PDF, finds inline chess glyphs, replaces them with Unicode, and saves the new PDF.
    Ignores 8x8 chess diagrams.

    Mantida com a assinatura antiga — devolve (total_pages, replaced_spans_count).
    Quem precisa do detalhe usa `analisar_substituicao`, que devolve o relatório.

    Returns:
        tuple: (total_pages, replaced_spans_count)
    """
    rel = analisar_substituicao(input_pdf, output_pdf, mapping_profile,
                                progress_callback)
    return rel.total_paginas, rel.total_substituicoes
