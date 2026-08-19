# -*- coding: utf-8 -*-
"""Gera um PDF com a lista completa das classes do modelo (classe, caractere,
codepoints e nome Unicode do caractere).

Uso: python gerar_pdf_classes.py
Lê model_meta.json e escreve classes_do_modelo.pdf, ambos na raiz do projeto.
"""
import json
import unicodedata
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import Align

RAIZ = Path(__file__).resolve().parent
META = RAIZ / "model_meta.json"
SAIDA = RAIZ / "classes_do_modelo.pdf"

WIN_FONTS = Path(r"C:\Windows\Fonts")
F_TEXTO = WIN_FONTS / "segoeui.ttf"
F_TEXTO_B = WIN_FONTS / "segoeuib.ttf"
# fonte de recurso: desenha os glifos que a Segoe UI não tem (peças de xadrez, setas)
F_SIMBOLO = WIN_FONTS / "seguisym.ttf"

GRUPOS = [
    ("digit", "Dígitos", "algarismos 0-9"),
    ("lower", "Letras minúsculas", "a-z"),
    ("upper", "Letras maiúsculas", "A-Z"),
    ("sym", "Símbolos", "pontuação, acentuadas, setas e peças de xadrez"),
    ("ligature", "Ligaduras", "grupos de glifos colados que a fonte desenha como um só"),
]

# classificadores auxiliares, fora do modelo de glifos
AUXILIARES = [
    (
        "Diagramas — peça por casa",
        [
            ("branca/K", "\u2654"),
            ("branca/Q", "\u2655"),
            ("branca/R", "\u2656"),
            ("branca/B", "\u2657"),
            ("branca/N", "\u2658"),
            ("branca/P", "\u2659"),
            ("preta/K", "\u265A"),
            ("preta/Q", "\u265B"),
            ("preta/R", "\u265C"),
            ("preta/B", "\u265D"),
            ("preta/N", "\u265E"),
            ("preta/P", "\u265F"),
        ],
    ),
    ("Ocupação — casa cheia ou vazia", [("ocupada", "\u25A0"), ("vazia", "\u25A1")]),
]

LARGURAS = (14, 46, 16, 40, 145)
CABECALHO = ("Índice", "Classe", "Caractere", "Codepoints", "Nome do caractere (Unicode)")


def nome_unicode(texto):
    return " + ".join(unicodedata.name(c, "(sem nome Unicode)") for c in texto)


def carregar():
    meta = json.loads(META.read_text(encoding="utf-8"))
    inv = {v: k for k, v in meta["label_map"].items()}
    linhas = []
    for i in range(meta["num_classes"]):
        classe = inv[i]
        char = meta["idx_to_char"][str(i)]
        linhas.append(
            {
                "idx": i,
                "classe": classe,
                "char": char,
                "cps": " ".join("U+%04X" % ord(c) for c in char),
                "nome": nome_unicode(char),
                "grupo": classe.split("_")[0],
            }
        )
    return meta, linhas


class PDF(FPDF):
    def header(self):
        if self.page_no() == 1:
            return
        self.set_font("Segoe", "B", 8)
        self.set_text_color(120)
        self.cell(0, 5, "Classes do modelo — PyBoxEditor", align=Align.R)
        self.ln(7)
        self.set_text_color(0)

    def footer(self):
        self.set_y(-12)
        self.set_font("Segoe", "", 8)
        self.set_text_color(120)
        self.cell(0, 5, f"pág. {self.page_no()}/{{nb}}", align=Align.C)
        self.set_text_color(0)


def linha_tabela(pdf, valores, larguras, zebra, col_caractere):
    """Desenha uma linha; a coluna do caractere sai em corpo maior."""
    if zebra:
        pdf.set_fill_color(245, 246, 249)
    y = pdf.get_y()
    x = pdf.l_margin
    for j, (valor, larg) in enumerate(zip(valores, larguras)):
        pdf.set_xy(x, y)
        pdf.set_font("Segoe", "", 11 if j == col_caractere else 8.5)
        pdf.cell(larg, 5.5, valor, border=0, align=Align.L, fill=zebra)
        x += larg
    pdf.set_xy(pdf.l_margin, y + 5.5)


def main():
    meta, linhas = carregar()

    pdf = PDF(orientation="L", unit="mm", format="A4")
    pdf.add_font("Segoe", "", F_TEXTO)
    pdf.add_font("Segoe", "B", F_TEXTO_B)
    pdf.add_font("Simbolo", "", F_SIMBOLO)
    pdf.set_fallback_fonts(["Simbolo"])
    pdf.set_auto_page_break(True, margin=16)
    pdf.set_margins(12, 12, 12)
    pdf.add_page()

    pdf.set_font("Segoe", "B", 20)
    pdf.cell(0, 10, "Classes do modelo de reconhecimento", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Segoe", "", 10)
    pdf.set_text_color(90)
    pdf.cell(
        0,
        6,
        f"{meta['num_classes']} classes  ·  treinado em {meta['treinado_em'].replace('T', ' ')}"
        f"  ·  temperatura {meta['temperatura']:.4f}",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.cell(
        0,
        5,
        f"modelo sha256 {meta['modelo_sha256'][:16]}…  ·  classes sha256 {meta['classes_sha256'][:16]}…",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.set_text_color(0)
    pdf.ln(3)

    def desenhar_cabecalho(colunas=CABECALHO, larguras=LARGURAS):
        pdf.set_font("Segoe", "B", 8.5)
        pdf.set_fill_color(228, 232, 238)
        for texto, larg in zip(colunas, larguras):
            pdf.cell(larg, 6, texto, border=0, align=Align.L, fill=True)
        pdf.ln(6)

    def espaco(altura):
        if pdf.will_page_break(altura):
            pdf.add_page()
            desenhar_cabecalho()

    for prefixo, titulo, subtitulo in GRUPOS:
        grupo = [l for l in linhas if l["grupo"] == prefixo]
        if not grupo:
            continue
        espaco(20)
        pdf.ln(3)
        pdf.set_font("Segoe", "B", 12)
        pdf.cell(0, 7, f"{titulo}  ({len(grupo)})", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Segoe", "", 8.5)
        pdf.set_text_color(110)
        pdf.cell(0, 4.5, subtitulo, new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0)
        pdf.ln(1.5)
        desenhar_cabecalho()

        for n, linha in enumerate(grupo):
            espaco(6)
            valores = (str(linha["idx"]), linha["classe"], linha["char"], linha["cps"], linha["nome"])
            linha_tabela(pdf, valores, LARGURAS, n % 2 == 1, col_caractere=2)

    pdf.add_page()
    pdf.set_font("Segoe", "B", 14)
    pdf.cell(0, 9, "Apêndice — modelos auxiliares", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Segoe", "", 9)
    pdf.set_text_color(110)
    pdf.cell(
        0,
        5,
        "Classificadores separados do modelo de glifos acima; não fazem parte das "
        f"{meta['num_classes']} classes.",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.set_text_color(0)

    larguras_aux = (46, 16, 145)
    for titulo, itens in AUXILIARES:
        pdf.ln(4)
        pdf.set_font("Segoe", "B", 11)
        pdf.cell(0, 6.5, f"{titulo}  ({len(itens)})", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
        desenhar_cabecalho(("Classe", "Caractere", "Nome do caractere (Unicode)"), larguras_aux)
        for n, (classe, char) in enumerate(itens):
            linha_tabela(
                pdf, (classe, char, nome_unicode(char)), larguras_aux, n % 2 == 1, col_caractere=1
            )

    pdf.output(str(SAIDA))
    print(f"OK -> {SAIDA}  ({SAIDA.stat().st_size // 1024} KB, {pdf.pages_count} páginas)")


if __name__ == "__main__":
    main()
