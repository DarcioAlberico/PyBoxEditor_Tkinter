"""
Testes de `core/editor/txt_io.py` (ED-10; SPEC_EDITOR §10.6 item 4): o TXT vai e volta
com `[Diagrama n: FEN]` (AC-ED10-4) — título por `#`, parágrafos por linha em branco,
quebra suave, citação, listas, tabela com legenda, marcas e quebra de página, notas —
e a leitura com e sem a opção dos títulos.

Rodar sem pytest:      python tests/test_editor_txt.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

import editor_livros as livros
from core.editor import epub, modelo as m, txt_io


def test_ac4_o_txt_vai_e_volta_com_diagrama_n_fen(tmp_path):
    livro = livros.livro_completo()
    caminho = str(tmp_path / "livro.txt")
    relatorio = txt_io.escrever(livro, caminho)
    assert relatorio.formato == "txt" and relatorio.capitulos == 2
    assert [a for a in relatorio.avisos if "ilha" in a]           # a ilha sai como texto, e avisa
    texto = open(caminho, encoding="utf-8").read()
    assert texto.startswith("# Capítulo um\n\nPrimeira linha sem recuo.\n\n")
    assert f"\n\n[Diagrama 1: {livros.FEN}]\nPosição\n\n[Diagrama 2: {livros.FEN}]\n\n" in texto
    assert "\n## Título 2\n\n### Título 3\n" in texto and "\n> Citação um.\n> Citação dois.\n" in texto
    assert "\n- item a\n- item b\n  continuação de b\n  - sub b1\n\n3. primeiro\n4. segundo\n" in texto
    assert "\nResultados\nJogador | Pontos\n--- | ---\nA | 1\nB | ½\n" in texto
    assert "\n[Página 11]\n\nTexto da página 11.\n" in texto and "\n[Quebra de página]\n\nDepois da quebra.\n" in texto
    assert "\n* * *\n" in texto and "[Figura 1: Uma foto]\nA foto\n" in texto
    assert ".[1] fim[2]\n" in texto and "\n[1] Nota de rodapé com link.\n\n[2] Nota de fim.\nSegundo parágrafo.\n" in texto
    assert "\n\n\n# Capítulo dois\n" in texto and chr(0xFEFF) not in texto and "\r" not in texto
    # volta
    relido, r2 = txt_io.ler(caminho, idioma="pt-BR")
    assert [c.arquivo for c in relido.capitulos] == ["Text/cap-0001.xhtml", "Text/cap-0002.xhtml"]
    assert relido.metadados.titulo == "Capítulo um"
    cap1, cap2 = relido.capitulos
    diagramas = [b for b in cap1.blocos if isinstance(b, m.Diagrama)]
    assert [d.fen for d in diagramas] == [livros.FEN] * 4 and [d.numero for d in diagramas] == [1, 2, 3, 4]
    assert all(d.lado == "" for d in diagramas) and diagramas[0].legenda[0].texto == "Posição"
    assert len(cap1.blocos) == len(livro.capitulos[0].blocos)
    tipos_antes = [type(b).__name__ for b in livro.capitulos[0].blocos]
    tipos_depois = [type(b).__name__ for b in cap1.blocos]
    # figuras e a ilha de bloco voltam como parágrafo (o texto não carrega imagem); todo o resto igual
    assert tipos_depois == [("Paragrafo" if t in ("Figura", "IlhaBruta") else t) for t in tipos_antes]
    for antes, depois in zip(livro.capitulos[0].blocos, cap1.blocos):
        if isinstance(antes, (m.Titulo,)) or (type(antes) is m.Paragrafo and not any(t.ilha for t in antes.trechos)):
            assert m.texto_de(antes) == m.texto_de(depois), m.texto_de(antes)
    titulos = [(b.nivel, m.texto_de(b)) for b in cap1.blocos if isinstance(b, m.Titulo)]
    assert titulos[:2] == [(1, "Capítulo um"), (2, "Título 2")] and (6, "Título 6") in titulos
    citacao = next(b for b in cap1.blocos if isinstance(b, m.Citacao))
    assert [m.texto_de(p) for p in citacao.blocos] == ["Citação um.", "Citação dois."]
    listas = [b for b in cap1.blocos if isinstance(b, m.Lista)]
    assert not listas[0].ordenada and listas[0].itens[1].filhos is not None
    assert m.texto_de(listas[0].itens[1].paragrafos[0]) == "item b\ncontinuação de b"
    assert listas[1].ordenada and listas[1].inicio == 3 and [m.texto_de(i.paragrafos[0]) for i in listas[1].itens] == [
        "primeiro", "segundo"]
    tabela = next(b for b in cap1.blocos if isinstance(b, m.Tabela))
    assert tabela.primeira_fila_cabecalho and tabela.legenda[0].texto == "Resultados"
    assert [[m.texto_de(c.blocos[0]) for c in f] for f in tabela.filas] == [["Jogador", "Pontos"], ["A", "1"], ["B", "½"]]
    assert [b.pagina for b in cap1.blocos if isinstance(b, m.MarcaDePagina)] == list(range(11, 23))
    assert any(isinstance(b, m.QuebraDePagina) for b in cap1.blocos) and any(isinstance(b, m.Separador)
                                                                            for b in cap1.blocos)
    assert [n.id for n in cap1.notas] == ["nota-1", "nota-2"] and len(cap1.notas[1].blocos) == 2
    assert [t.nota for t in m.trechos_do_capitulo(cap1) if t.nota] == ["nota-1", "nota-2"]
    assert any(t.quebra_antes and t.texto == "nova linha" for t in m.trechos_do_capitulo(cap1))
    assert [m.texto_de(b) for b in cap2.blocos] == ["Capítulo dois", "Alvo do link.", "Seção", "Subseção",
                                                    "Fora do sumário", "Fim."]
    assert relido.sumario and relido.sumario[0].rotulo == "Capítulo um"
    # e o livro relido grava um EPUB válido
    destino = str(tmp_path / "txt.epub")
    epub.escrever(relido, destino)
    assert epub.validar_estrutura(destino) == []


def test_ler_txt_sem_titulos_e_um_capitulo_so_e_o_fen_invalido_fica_texto(tmp_path):
    caminho = str(tmp_path / "solto.txt")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write("# Um\n\nParágrafo um.\n\n# Dois\n\n[Diagrama: 8/8/8/8/8/8/8/9 w - - 0 1]\n\n"
                "[Diagrama: rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1]\n\nFim.\n")
    livro, relatorio = txt_io.ler(caminho, titulos=False)
    assert len(livro.capitulos) == 1
    blocos = livro.capitulos[0].blocos
    assert [type(b).__name__ for b in blocos] == ["Paragrafo", "Paragrafo", "Paragrafo", "Paragrafo", "Diagrama",
                                                  "Paragrafo"]
    assert m.texto_de(blocos[0]) == "# Um" and blocos[4].numero is None
    assert any("FEN inválido" in a for a in relatorio.avisos)
    assert livro.metadados.titulo == "solto"
    com_titulos, _r = txt_io.ler(caminho, titulo="Meu livro", idioma="pt")
    assert len(com_titulos.capitulos) == 2 and com_titulos.metadados.titulo == "Meu livro"
    assert com_titulos.metadados.idioma == "pt" and isinstance(com_titulos.capitulos[0].blocos[0], m.Titulo)
    # windows-1252 e CRLF são aceitos
    with open(str(tmp_path / "cp.txt"), "wb") as f:
        f.write("# Título\r\n\r\nAção e coração.\r\n".encode("cp1252"))
    lido, r = txt_io.ler(str(tmp_path / "cp.txt"))
    assert m.texto_de(lido.capitulos[0].blocos[1]) == "Ação e coração." and any("Windows-1252" in a for a in r.avisos)
    with pytest.raises(ValueError):
        txt_io.ler(str(tmp_path / "nada.txt"))


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-o", "addopts="]))
