"""
Mede o editor de livros: `carregar`, `sincronizar` (só o que mudou), `dump` (o
capítulo inteiro relido do widget para o modelo) e a latência de uma tecla simulada
num capítulo de ~20 páginas (ED-03; SPEC_EDITOR §13.1) — e, desde a ED-04, uma tabela
de 20×20 (o limite de 400 células, §8.6): quanto custa carregá-la como grade de células
e quanto custa uma tecla numa célula (AC-ED04-2).

Desde a ED-13 mede também o **livro do AC-005** (`medir_livro`): 300 capítulos-página,
300 mil caracteres e 500 diagramas — abrir, abrir um capítulo, alternar o modo, buscar no
livro inteiro, salvar, e o RSS do processo (orçamentos: 3 s, 0,5 s, 1 s, 2 s, 5 s, 600 MB;
os `assert` estão em `tests/test_editor_ac_globais.py::test_ac005…`, `slow`).

Os números saem no console; os `assert` moram em `tests/test_editor_desempenho.py` e no
AC-005 (`slow`, fora do gate padrão). Rodar:

    .venv/Scripts/python.exe scripts/medir_editor.py [--paginas 20] [--repeticoes 3] [--livro]

O capítulo é gerado por `tests/editor_gerador.py` (prosa, títulos, listas, citações,
quebras suaves; sem objetos, que a ED-05 mede), com cerca de dez blocos por página. A
janela é `withdraw`n: o que se mede é o widget e o modelo, não a pintura.
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
import time
import tkinter as tk
from typing import Any

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "tests"))

BLOCOS_POR_PAGINA = 10


def capitulo_de(paginas: int):
    """Um capítulo com ~`paginas` páginas, só de blocos que a ED-03 desenha por texto."""
    import editor_gerador as gerador
    from core.editor import modelo as m

    objetos = (m.Diagrama, m.Figura, m.Tabela, m.IlhaBruta, m.MarcaDePagina, m.QuebraDePagina, m.Separador)
    blocos = []
    semente = 1
    while len(blocos) < paginas * BLOCOS_POR_PAGINA:
        cap = gerador.capitulo(semente)
        for b in cap.blocos:
            if isinstance(b, objetos):
                continue
            for interno in m.blocos_do_capitulo(m.Capitulo(arquivo="x", blocos=[b])):
                if isinstance(interno, m.Paragrafo):
                    interno.trechos = [t for t in interno.trechos if not t.ilha]
            blocos.append(b)
        semente += 1
    return m.Capitulo(arquivo="Text/medida.xhtml", blocos=blocos[: paginas * BLOCOS_POR_PAGINA])


def medir(paginas: int = 20, repeticoes: int = 3) -> dict[str, float]:
    from core.editor import modelo as m
    from ui.editor.texto_rico import TextoRico

    raiz = tk.Tk()
    raiz.withdraw()
    widget = TextoRico(raiz)
    widget.pack(fill="both", expand=True)
    cap = capitulo_de(paginas)
    caracteres = sum(len(m.texto_de(b)) for b in cap.blocos)
    tempos: dict[str, list[float]] = {"carregar": [], "sincronizar": [], "dump": [], "tecla": []}
    for _ in range(repeticoes):
        t0 = time.perf_counter()
        widget.carregar(cap)
        tempos["carregar"].append(time.perf_counter() - t0)
        t0 = time.perf_counter()
        copia = widget.sincronizar()
        tempos["sincronizar"].append(time.perf_counter() - t0)
        t0 = time.perf_counter()
        copia = widget.sincronizar(reler=True)
        tempos["dump"].append(time.perf_counter() - t0)
        assert m.igual(copia, cap), "o capítulo medido não fecha a ida e volta"
        # Uma tecla no meio do capítulo: inserir um caractere e reconciliar o bloco.
        meio = widget.ordem[len(widget.ordem) // 2]
        widget.ir_para(meio, 3)
        t0 = time.perf_counter()
        widget.inserir("x")
        tempos["tecla"].append(time.perf_counter() - t0)
    raiz.destroy()
    saida = {chave: statistics.median(v) for chave, v in tempos.items()}
    saida["blocos"] = len(cap.blocos)
    saida["caracteres"] = caracteres
    return saida


def medir_tabela(filas: int = 20, colunas: int = 20, repeticoes: int = 3) -> dict[str, float]:
    """A tabela no limite (§8.6): carregar a grade, reler o capítulo, uma tecla numa célula e o ponto dela."""
    from core.editor import modelo as m
    from ui.editor.texto_rico import TextoRico

    raiz = tk.Tk()
    raiz.withdraw()
    widget = TextoRico(raiz)
    widget.pack(fill="both", expand=True)
    tabela = m.Tabela(filas=[[m.Celula(blocos=[m.Paragrafo(trechos=[m.Trecho(texto=f"c{f},{c}")])])
                              for c in range(colunas)] for f in range(filas)])
    cap = m.Capitulo(arquivo="Text/tabela.xhtml",
                     blocos=[m.Paragrafo(trechos=[m.Trecho(texto="antes")]), tabela,
                             m.Paragrafo(trechos=[m.Trecho(texto="depois")])])
    tempos: dict[str, list[float]] = {"carregar_tabela": [], "dump_tabela": [], "tecla_na_celula": [],
                                      "ponto_da_tabela": []}
    for _ in range(repeticoes):
        t0 = time.perf_counter()
        widget.carregar(cap)
        tempos["carregar_tabela"].append(time.perf_counter() - t0)
        t0 = time.perf_counter()
        copia = widget.sincronizar(reler=True)
        tempos["dump_tabela"].append(time.perf_counter() - t0)
        assert m.igual(copia, cap), "a tabela medida não fecha a ida e volta"
        grade = widget.widget_do_objeto(tabela.id)
        celula = grade.entrar(filas // 2, colunas // 2)
        t0 = time.perf_counter()
        celula.inserir("x")
        tempos["tecla_na_celula"].append(time.perf_counter() - t0)
        # O ponto de desfazer da tabela inteira é adiado (ATRASO_DA_CELULA_MS); `sincronizar` o cobra agora.
        t0 = time.perf_counter()
        widget.sincronizar()
        tempos["ponto_da_tabela"].append(time.perf_counter() - t0)
    raiz.destroy()
    saida = {chave: statistics.median(v) for chave, v in tempos.items()}
    saida["celulas"] = filas * colunas
    return saida


def livro_grande(capitulos: int = 300, caracteres: int = 300_000, diagramas: int = 500):
    """O livro do AC-005: `capitulos` capítulos-página, ~`caracteres` de texto e `diagramas` diagramas."""
    from core.editor import epub, modelo as m

    frase = "A partida seguiu com as brancas pressionando o flanco da dama enquanto as pretas buscavam contrajogo. "
    por_capitulo = max(1, caracteres // capitulos)
    posicoes = ["rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 1",
                "r1bqkbnr/1ppp1ppp/p1n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 0 4",
                "6k1/5ppp/8/8/4R3/8/5PPP/6K1 b - - 0 23", "8/8/8/8/8/8/8/K6k w - - 0 1"]
    livro = epub.novo_livro("Livro grande", "Medição", "pt")
    padrao = livro.folhas[0]
    livro.capitulos = []
    restantes = diagramas
    for k in range(1, capitulos + 1):
        blocos = [m.Titulo(trechos=[m.Trecho(texto=f"Capítulo {k}")], nivel=1)]
        escrito = 0
        while escrito < por_capitulo:
            texto = (frase * 3).strip()
            blocos.append(m.Paragrafo(trechos=[m.Trecho(texto=texto)]))
            escrito += len(texto)
        blocos.append(m.Paragrafo(trechos=[m.Trecho(texto="1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6 5.O-O")],
                                  estilo="notacao"))
        quota = -(-restantes // (capitulos - k + 1))            # os diagramas repartidos entre os capítulos que faltam
        for i in range(quota):
            blocos.append(m.Diagrama(fen=posicoes[(k + i) % len(posicoes)], modo="png"))
        restantes -= quota
        livro.capitulos.append(m.Capitulo(arquivo=f"Text/cap-{k:04d}.xhtml", blocos=blocos, folhas=[padrao],
                                          idioma="pt"))
    from core.editor import sumario

    livro.sumario = sumario.gerar_dos_titulos(livro)
    livro.marcos = [("bodymatter", livro.capitulos[0].arquivo)]
    return livro


def _rss_mb() -> float:
    """
    O RSS **atual** do processo em MB: `psutil` quando há; senão o `GetProcessMemoryInfo` do
    Windows; senão o `/proc/self/statm` do Linux; senão o `ru_maxrss`; senão 0.

    O `ru_maxrss` fica por último porque é outra medida: é o pico, e no Linux o pico atravessa
    o `execve` — o processo que o pytest lança nasce com o RSS do pai, e o AC-005 medido num
    processo próprio dava os 645 MB do pytest (com Torch e cv2) em vez dos ~90 do editor.
    """
    try:
        import psutil

        return psutil.Process().memory_info().rss / (1024 * 1024)
    except ImportError:
        pass
    if sys.platform.startswith("win"):
        import ctypes
        from ctypes import wintypes

        class Contadores(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

        contadores = Contadores()
        contadores.cb = ctypes.sizeof(Contadores)
        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        funcao = ctypes.windll.psapi.GetProcessMemoryInfo
        funcao.argtypes = [wintypes.HANDLE, ctypes.POINTER(Contadores), wintypes.DWORD]
        funcao.restype = wintypes.BOOL
        if funcao(kernel32.GetCurrentProcess(), ctypes.byref(contadores), contadores.cb):
            return contadores.WorkingSetSize / (1024 * 1024)
    try:
        with open("/proc/self/statm") as f:
            paginas_residentes = int(f.read().split()[1])
        return paginas_residentes * os.sysconf("SC_PAGE_SIZE") / (1024 * 1024)
    except (OSError, ValueError, IndexError, AttributeError):
        pass
    try:
        import resource

        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    except (ImportError, AttributeError):
        return 0.0


def medir_livro(capitulos: int = 300, caracteres: int = 300_000, diagramas: int = 500,
                pasta: str | None = None, raiz: Any = None) -> dict[str, float]:
    """
    O AC-005 numa `JanelaDoEditor` `withdraw`n: `abrir_s` (Arquivo → Abrir), `capitulo_s` (abrir um
    capítulo pelo navegador), `modo_s` (texto → código), `busca_s` (contar no livro inteiro),
    `salvar_s` (Salvar como) e `rss_mb` no fim. Escreve o EPUB do livro grande em `pasta`
    (temporária por omissão) e devolve as medidas.
    """
    import shutil
    import tempfile

    from config.settings import Settings
    from core.editor import epub
    from ui.editor.janela import JanelaDoEditor

    pasta = pasta or tempfile.mkdtemp(prefix="pbe-livro-grande-")
    caminho = os.path.join(pasta, "grande.epub")
    livro = livro_grande(capitulos, caracteres, diagramas)
    inicio = time.perf_counter()
    epub.escrever(livro, caminho)
    escrever_s = time.perf_counter() - inicio
    propria = raiz is None                      # o teste passa a raiz da sessão; o script cria a sua
    if propria:
        raiz = tk.Tk()
        raiz.withdraw()
    medidas: dict[str, float] = {"capitulos": capitulos, "caracteres": caracteres, "diagramas": diagramas,
                                 "escrever_epub_s": escrever_s, "tamanho_kb": os.path.getsize(caminho) / 1024}
    try:
        j = JanelaDoEditor(raiz, settings=Settings(os.path.join(pasta, "settings.json")))
        j.withdraw()
        j.caixas.pergunta = lambda *a, **k: False
        j.caixas.informar = lambda *a, **k: None                   # "Contar" termina numa caixa: aqui, não
        j.caixas.conclusao = lambda *a, **k: None

        def falhou(mensagem, detalhe="", *a, **k):                # nenhuma caixa modal numa medição
            raise RuntimeError(f"{mensagem}\n{detalhe}")

        j.caixas.falha = falhou
        j.caixas.entrada = falhou
        inicio = time.perf_counter()
        j.executar("abrir", caminho)
        j.update_idletasks()
        medidas["abrir_s"] = time.perf_counter() - inicio
        inicio = time.perf_counter()
        j.abrir_capitulo(j.projeto.livro.capitulos[capitulos // 2].arquivo)
        j.update_idletasks()
        medidas["capitulo_s"] = time.perf_counter() - inicio
        inicio = time.perf_counter()
        j.executar("alternar_modo")
        j.update_idletasks()
        medidas["modo_s"] = time.perf_counter() - inicio
        j.executar("alternar_modo")
        painel = j.busca
        painel.var_texto.set("contrajogo")
        painel.var_escopo.set(_rotulo_do_escopo("livro"))
        inicio = time.perf_counter()
        contagem = j.executar("contar_ocorrencias")
        medidas["busca_s"] = time.perf_counter() - inicio
        medidas["ocorrencias"] = float(sum(contagem.values())) if isinstance(contagem, dict) else 0.0
        destino = os.path.join(pasta, "salvo.epub")
        inicio = time.perf_counter()
        j.executar("salvar_como", destino)
        medidas["salvar_s"] = time.perf_counter() - inicio
        medidas["rss_mb"] = _rss_mb()
        j.destroy()
    finally:
        if propria:
            raiz.destroy()
        shutil.rmtree(pasta, ignore_errors=True)
    return medidas


def _rotulo_do_escopo(escopo: str) -> str:
    from core.editor import busca as busca_mod

    return busca_mod.ROTULOS_DOS_ESCOPOS[escopo]


ORCAMENTOS_DO_LIVRO = {"abrir_s": 3.0, "capitulo_s": 0.5, "modo_s": 1.0, "busca_s": 2.0, "salvar_s": 5.0,
                       "rss_mb": 600.0}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mede carregar/sincronizar/dump/tecla do modo texto e a tabela.")
    parser.add_argument("--paginas", type=int, default=20)
    parser.add_argument("--repeticoes", type=int, default=3)
    parser.add_argument("--sem-tabela", action="store_true", help="pula a medição da tabela de 20×20")
    parser.add_argument("--livro", action="store_true", help="mede também o livro do AC-005 (300 capítulos)")
    parser.add_argument("--capitulos", type=int, default=300)
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    resultado = medir(args.paginas, args.repeticoes)
    print(f"capítulo de {args.paginas} páginas: {resultado['blocos']} blocos, {resultado['caracteres']} caracteres")
    for chave in ("carregar", "sincronizar", "dump", "tecla"):
        print(f"  {chave:16s} {resultado[chave] * 1000:8.1f} ms (mediana de {args.repeticoes})")
    if not args.sem_tabela:
        tabela = medir_tabela(repeticoes=args.repeticoes)
        print(f"tabela de 20×20: {tabela['celulas']} células")
        for chave in ("carregar_tabela", "dump_tabela", "tecla_na_celula", "ponto_da_tabela"):
            print(f"  {chave:16s} {tabela[chave] * 1000:8.1f} ms (mediana de {args.repeticoes})")
    if args.livro:
        livro = medir_livro(capitulos=args.capitulos)
        print(f"livro do AC-005: {int(livro['capitulos'])} capítulos, {int(livro['caracteres'])} caracteres, "
              f"{int(livro['diagramas'])} diagramas ({livro['tamanho_kb']:.0f} KB, escrito em "
              f"{livro['escrever_epub_s']:.1f} s)")
        print("| Medida | Valor | Orçamento | |")
        print("|---|---|---|---|")
        for chave, teto in ORCAMENTOS_DO_LIVRO.items():
            valor = livro[chave]
            unidade = "MB" if chave.endswith("_mb") else "s"
            ok = "✅" if valor <= teto else "❌"
            print(f"| {chave} | {valor:.2f} {unidade} | ≤ {teto:g} {unidade} | {ok} |")
        print(f"  ocorrências da busca: {int(livro.get('ocorrencias', 0))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
