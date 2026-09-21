"""
O livro em texto puro, e o texto puro que vira livro (ED-10; SPEC_EDITOR §10.6 item 4,
§10.7, §10.8).

## O formato

Texto é o formato que não tem onde guardar formato — e por isso o que sai daqui é o
mínimo que ainda **volta**: um parágrafo por bloco separado por linha em branco; uma
quebra de linha suave como quebra de linha; um título como `#` × nível (a convenção
que todo mundo lê); citação com `> `; lista com `- ` ou `1. ` (recuada por nível);
tabela com ` | ` entre células e uma linha `--- | ---` sob o cabeçalho; separador `* * *`;
marca de página `[Página 12]`; quebra de página `[Quebra de página]`; figura `[Figura 3:
alt]`; e o diagrama como `[Diagrama 3: FEN]` — a posição não se perde nunca (AC-ED10-4;
DEC-06: o lado que o FEN carrega é o do próprio FEN, e o `Diagrama.lado` volta
desconhecido). A referência de nota é `[n]` no texto e a nota `[n] texto` no fim do
capítulo. A ilha sai como o seu texto, com aviso. Um capítulo por título de nível 1
na leitura (`titulos=True`, a opção da §10.6); sem a opção, um capítulo só.
"""

from __future__ import annotations

import os
import re
from typing import Sequence

from core.editor import epub, modelo, sumario
from core.editor.conversao import Cronometro, OpcoesDeConversao, RelatorioDeConversao
from core.editor.modelo import (Bloco, Capitulo, Celula, Citacao, Diagrama, Figura, IlhaBruta, ItemDeLista, Lista,
                                Livro, MarcaDePagina, Metadados, Nota, Paragrafo, QuebraDePagina, Separador, Tabela,
                                Titulo, Trecho)

_RE_TAG = re.compile(r"<[^>]*>")
_RE_TITULO = re.compile(r"^(#{1,6})\s+(.*)$")
_RE_DIAGRAMA = re.compile(r"^\[Diagrama(?:\s+(\d+))?:\s*(.+?)\]$")
_RE_FIGURA = re.compile(r"^\[Figura(?:\s+(\d+))?:\s*(.*?)\]$")
_RE_PAGINA = re.compile(r"^\[P[áa]gina\s+(\d+)\]$")
_RE_QUEBRA = re.compile(r"^\[Quebra de p[áa]gina\]$")
_RE_SEPARADOR = re.compile(r"^\*\s*\*\s*\*$")
_RE_ITEM = re.compile(r"^(\s*)(?:([-*•])|(\d+)[.)])\s+(.*)$")
_RE_NOTA = re.compile(r"^\[(\d+)\]\s+(.*)$", re.S)
_RE_REF_DE_NOTA = re.compile(r"\[(\d+)\]")
_RE_CITACAO = re.compile(r"^>\s?(.*)$")
_RE_LINHA_DE_TABELA = re.compile(r"^\s*-{3,}(\s*\|\s*-{3,})*\s*$")
QUEBRA_DE_PAGINA = "[Quebra de página]"
SEPARADOR = "* * *"


# ----------------------------------------------------------------------
# Escrever
# ----------------------------------------------------------------------

class _Escritor:
    def __init__(self, cap: Capitulo, relatorio: RelatorioDeConversao):
        self.cap = cap
        self.relatorio = relatorio
        cap.normalizar_notas()
        self.numero_da_nota = {n.id: i for i, n in enumerate(cap.notas, start=1)}
        self.contadores = {"diagrama": 0, "figura": 0}

    def trechos(self, trechos: Sequence[Trecho]) -> str:
        partes: list[str] = []
        for t in trechos:
            if t.quebra_antes:
                partes.append("\n")
            if t.ilha:
                partes.append(_RE_TAG.sub("", t.ilha))
                self.relatorio.aviso(f"{self.cap.arquivo}: ilha inline saiu como texto")
                continue
            if t.nota:
                partes.append(f"[{self.numero_da_nota.get(t.nota, 0)}]")
                continue
            partes.append(t.texto)
        return "".join(partes)

    def paragrafo(self, p: Paragrafo, prefixo: str = "") -> str:
        texto = self.trechos(p.trechos)
        if isinstance(p, Titulo):
            return "#" * p.nivel + " " + texto.replace("\n", " ")
        return prefixo + texto.replace("\n", "\n" + prefixo)

    def bloco(self, bloco: Bloco) -> str:
        if isinstance(bloco, Paragrafo):
            return self.paragrafo(bloco)
        if isinstance(bloco, Citacao):
            return "\n".join(self.paragrafo(p, "> ") for p in bloco.blocos)
        if isinstance(bloco, Lista):
            return self.lista(bloco, 0)
        if isinstance(bloco, Tabela):
            return self.tabela(bloco)
        if isinstance(bloco, Diagrama):
            self.contadores["diagrama"] += 1
            n = bloco.numero if bloco.numero is not None else self.contadores["diagrama"]
            legenda = ("\n" + self.trechos(bloco.legenda)) if bloco.legenda else ""
            return f"[Diagrama {n}: {bloco.fen}]{legenda}"
        if isinstance(bloco, Figura):
            self.contadores["figura"] += 1
            n = bloco.numero if bloco.numero is not None else self.contadores["figura"]
            legenda = ("\n" + self.trechos(bloco.legenda)) if bloco.legenda else ""
            return f"[Figura {n}: {bloco.alt}]{legenda}"
        if isinstance(bloco, MarcaDePagina):
            return f"[Página {bloco.pagina}]"
        if isinstance(bloco, QuebraDePagina):
            return QUEBRA_DE_PAGINA
        if isinstance(bloco, Separador):
            return SEPARADOR
        if isinstance(bloco, IlhaBruta):
            self.relatorio.aviso(f"{self.cap.arquivo}: ilha <{bloco.elemento}> saiu como texto")
            return re.sub(r"\s+", " ", _RE_TAG.sub(" ", bloco.xhtml)).strip()
        return modelo.texto_de(bloco)

    def lista(self, lista: Lista, nivel: int) -> str:
        linhas: list[str] = []
        recuo = "  " * nivel
        for k, item in enumerate(lista.itens):
            marcador = f"{lista.inicio + k}. " if lista.ordenada else "- "
            for j, p in enumerate(item.paragrafos):
                texto = self.trechos(p.trechos).replace("\n", "\n" + recuo + " " * len(marcador))
                linhas.append(recuo + (marcador if j == 0 else " " * len(marcador)) + texto)
            if item.filhos is not None:
                linhas.append(self.lista(item.filhos, nivel + 1))
        return "\n".join(linhas)

    def tabela(self, tabela: Tabela) -> str:
        linhas: list[str] = []
        if tabela.legenda:
            linhas.append(self.trechos(tabela.legenda))
        for i, fila in enumerate(tabela.filas):
            celulas = [" ".join(self.trechos(p.trechos).replace("\n", " ") for p in c.blocos).replace("|", "¦")
                       for c in fila]
            linhas.append(" | ".join(celulas))
            if i == 0 and tabela.primeira_fila_cabecalho:
                linhas.append(" | ".join("---" for _ in fila))
        return "\n".join(linhas)

    def notas(self) -> list[str]:
        saida = []
        for i, nota in enumerate(self.cap.notas, start=1):
            texto = "\n".join(self.trechos(p.trechos) for p in nota.blocos)
            saida.append(f"[{i}] {texto}")
        return saida

    def capitulo(self) -> str:
        partes = [self.bloco(b) for b in self.cap.blocos]
        partes.extend(self.notas())
        return "\n\n".join(p for p in partes if p.strip())


def escrever(livro: Livro, caminho: str, opcoes: OpcoesDeConversao | None = None) -> RelatorioDeConversao:
    """O livro em texto puro (UTF-8, sem BOM). Devolve o relatório."""
    caminho = os.fspath(caminho)
    relatorio = RelatorioDeConversao(formato="txt", arquivos=[caminho])
    with Cronometro(relatorio):
        partes: list[str] = []
        for cap in livro.capitulos:
            if cap.texto_cru is not None:
                from core.editor import xhtml

                try:
                    cap = xhtml.ler(cap.texto_cru, cap.arquivo)
                except xhtml.ErroDeXhtml as erro:
                    relatorio.aviso(f"{cap.arquivo}: XHTML mal-formado, capítulo não exportado ({erro})")
                    continue
            partes.append(_Escritor(cap, relatorio).capitulo())
        texto = "\n\n\n".join(p for p in partes if p)
        pasta = os.path.dirname(os.path.abspath(caminho))
        os.makedirs(pasta, exist_ok=True)
        with open(caminho, "w", encoding="utf-8", newline="\n") as f:
            f.write(texto + ("\n" if texto else ""))
    relatorio.contar(livro)
    return relatorio


# ----------------------------------------------------------------------
# Ler
# ----------------------------------------------------------------------

def _trechos_de(texto: str, notas: dict[int, str]) -> list[Trecho]:
    """O texto de um parágrafo → trechos: `[n]` vira referência de nota; `\\n` vira quebra suave."""
    saida: list[Trecho] = []
    quebra = False
    for linha_i, linha in enumerate(texto.split("\n")):
        quebra = linha_i > 0
        pos = 0
        for m in _RE_REF_DE_NOTA.finditer(linha):
            n = int(m.group(1))
            if n not in notas:
                continue
            if m.start() > pos:
                saida.append(Trecho(texto=linha[pos:m.start()], quebra_antes=quebra))
                quebra = False
            saida.append(Trecho(nota=notas[n], quebra_antes=quebra))
            quebra = False
            pos = m.end()
        if pos < len(linha) or (quebra and not saida):
            saida.append(Trecho(texto=linha[pos:], quebra_antes=quebra))
            quebra = False
        elif quebra:
            saida.append(Trecho(texto="", quebra_antes=True))
    return saida or [Trecho(texto="")]


def _bloco_de(paragrafo: str, notas: dict[int, str], relatorio: RelatorioDeConversao, titulos: bool) -> Bloco | None:
    linhas = paragrafo.split("\n")
    primeira = linhas[0]
    if titulos:
        m = _RE_TITULO.match(primeira) if len(linhas) == 1 else None
        if m:
            return Titulo(trechos=[Trecho(texto=m.group(2).strip())], nivel=len(m.group(1)))
    if len(linhas) == 1:
        m = _RE_DIAGRAMA.match(primeira.strip())
        if m and modelo.fen_valido(m.group(2).strip()):
            return Diagrama(fen=m.group(2).strip(), lado="", numero=int(m.group(1)) if m.group(1) else None)
        if m:
            relatorio.aviso(f"FEN inválido, ficou como texto: {m.group(2)[:40]}")
        m = _RE_PAGINA.match(primeira.strip())
        if m:
            return MarcaDePagina(pagina=int(m.group(1)))
        if _RE_QUEBRA.match(primeira.strip()):
            return QuebraDePagina()
        if _RE_SEPARADOR.match(primeira.strip()):
            return Separador()
    m = _RE_DIAGRAMA.match(primeira.strip())
    if m and modelo.fen_valido(m.group(2).strip()):
        legenda = _trechos_de("\n".join(linhas[1:]), notas) if len(linhas) > 1 else []
        return Diagrama(fen=m.group(2).strip(), lado="", numero=int(m.group(1)) if m.group(1) else None,
                        legenda=legenda)
    m = _RE_FIGURA.match(primeira.strip())
    if m:
        relatorio.aviso(f"figura sem imagem (o texto não a carrega): {m.group(2)[:40]}")
        legenda = _trechos_de("\n".join(linhas[1:]), notas) if len(linhas) > 1 else []
        return Paragrafo(trechos=[Trecho(texto=f"[Figura: {m.group(2)}]")] + ([Trecho(texto="", quebra_antes=True)]
                                                                            + legenda if legenda else []),
                         estilo="legenda")
    if all(_RE_CITACAO.match(li) for li in linhas):
        texto = "\n".join(_RE_CITACAO.match(li).group(1) for li in linhas)
        return Citacao(blocos=[Paragrafo(trechos=_trechos_de(t, notas), estilo="citacao") for t in texto.split("\n")])
    if all(_RE_ITEM.match(li) or li.startswith("  ") for li in linhas) and _RE_ITEM.match(primeira):
        return _lista_de(linhas, notas)
    if len(linhas) >= 2 and _e_tabela(linhas):
        return _tabela_de(linhas, notas)
    return Paragrafo(trechos=_trechos_de(paragrafo, notas))


def _lista_de(linhas: Sequence[str], notas: dict[int, str]) -> Lista:
    """Itens por recuo (dois espaços por nível); `1.` ordena, `-` não."""
    itens: list[tuple[int, bool, int | None, str]] = []      # (nível, ordenada, número, texto)
    for linha in linhas:
        m = _RE_ITEM.match(linha)
        if m:
            nivel = len(m.group(1)) // 2
            itens.append((nivel, m.group(3) is not None, int(m.group(3)) if m.group(3) else None, m.group(4)))
        elif itens:
            nivel, ordenada, numero, texto = itens[-1]
            itens[-1] = (nivel, ordenada, numero, texto + "\n" + linha.strip())

    def montar(inicio: int, nivel: int) -> tuple[Lista, int]:
        lista = Lista(ordenada=itens[inicio][1], itens=[])
        if lista.ordenada and itens[inicio][2] is not None and itens[inicio][2] != 1:
            lista.inicio = itens[inicio][2]
        i = inicio
        while i < len(itens):
            n, _ordenada, _numero, texto = itens[i]
            if n < nivel:
                break
            if n > nivel:
                filhos, i = montar(i, n)
                if lista.itens:
                    lista.itens[-1].filhos = filhos
                else:
                    lista.itens.append(ItemDeLista(paragrafos=[Paragrafo(trechos=[Trecho(texto="")])], filhos=filhos))
                continue
            lista.itens.append(ItemDeLista(paragrafos=[Paragrafo(trechos=_trechos_de(texto, notas))]))
            i += 1
        return lista, i

    lista, _ = montar(0, itens[0][0])
    return lista


def _e_tabela(linhas: Sequence[str]) -> bool:
    """Toda linha com ` | ` (ou a linha de `---`), a menos da primeira, que pode ser a legenda."""
    corpo = linhas if " | " in linhas[0] else linhas[1:]
    return (len(corpo) >= 1 and all(" | " in li or _RE_LINHA_DE_TABELA.match(li) for li in corpo)
            and any(" | " in li for li in corpo))


def _tabela_de(linhas: Sequence[str], notas: dict[int, str]) -> Tabela:
    filas: list[list[Celula]] = []
    cabecalho = False
    legenda: list[Trecho] = []
    if " | " not in linhas[0]:
        legenda = _trechos_de(linhas[0], notas)
        linhas = linhas[1:]
    for i, linha in enumerate(linhas):
        if _RE_LINHA_DE_TABELA.match(linha):
            if i == 1:
                cabecalho = True
            continue
        celulas = [Celula(blocos=[Paragrafo(trechos=_trechos_de(c.strip().replace("¦", "|"), notas))])
                   for c in linha.split(" | ")]
        filas.append(celulas)
    largura = max(len(f) for f in filas)
    for fila in filas:
        while len(fila) < largura:
            fila.append(Celula(blocos=[Paragrafo(trechos=[Trecho(texto="")])]))
    if cabecalho and filas:
        for celula in filas[0]:
            celula.cabecalho = True
    return Tabela(filas=filas, primeira_fila_cabecalho=cabecalho, legenda=legenda)


def _capitulo_de(paragrafos: Sequence[str], arquivo: str, relatorio: RelatorioDeConversao, titulos: bool) -> Capitulo:
    """Os parágrafos de um capítulo (já separados por linha em branco) → `Capitulo`, com as notas do fim."""
    corpo: list[str] = []
    notas_texto: dict[int, str] = {}
    for p in paragrafos:
        m = _RE_NOTA.match(p)
        if m and int(m.group(1)) not in notas_texto:
            notas_texto[int(m.group(1))] = m.group(2)
        else:
            corpo.append(p)
    ids = {n: f"nota-{n}" for n in sorted(notas_texto)}
    cap = Capitulo(arquivo=arquivo)
    for p in corpo:
        bloco = _bloco_de(p, ids, relatorio, titulos)
        if bloco is not None:
            cap.blocos.append(bloco)
    for n in sorted(notas_texto):
        cap.notas.append(Nota(id=ids[n], tipo="rodape",
                              blocos=[Paragrafo(trechos=_trechos_de(t, {}), estilo="nota")
                                      for t in notas_texto[n].split("\n")]))
    # uma nota nunca referenciada continua no capítulo (INV-02: aviso, nunca perda)
    referenciadas = {t.nota for t in modelo.trechos_do_capitulo(cap) if t.nota}
    for n in sorted(notas_texto):
        if ids[n] not in referenciadas:
            relatorio.aviso(f"{arquivo}: a nota [{n}] não é referenciada no texto")
    return cap


def ler(caminho: str, titulos: bool = True, dividir_por_titulo: bool = True,
        titulo: str = "", idioma: str = "") -> tuple[Livro, RelatorioDeConversao]:
    """
    Texto puro → `Livro`: parágrafos por linha em branco, `#` título (opção `titulos`),
    `[Diagrama n: FEN]` e as outras marcas do cabeçalho do módulo; um capítulo por
    título de nível 1 quando `dividir_por_titulo`.
    """
    caminho = os.fspath(caminho)
    relatorio = RelatorioDeConversao(formato="txt", arquivos=[caminho])
    with Cronometro(relatorio):
        try:
            with open(caminho, "rb") as f:
                dados = f.read()
        except OSError as erro:
            raise ValueError(f"não deu para ler {caminho}: {erro}") from None
        if dados.startswith(b"\xef\xbb\xbf"):
            dados = dados[3:]
        try:
            texto = dados.decode("utf-8")
        except UnicodeDecodeError:
            relatorio.aviso("o arquivo não é UTF-8; lido como Windows-1252")
            texto = dados.decode("cp1252", errors="replace")
        texto = texto.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n\n" + QUEBRA_DE_PAGINA + "\n\n")
        paragrafos = [p.strip("\n") for p in re.split(r"\n\s*\n", texto) if p.strip()]
        grupos: list[list[str]] = [[]]
        for p in paragrafos:
            if titulos and dividir_por_titulo and _RE_TITULO.match(p) and len(_RE_TITULO.match(p).group(1)) == 1 \
                    and "\n" not in p and grupos[-1]:
                grupos.append([])
            grupos[-1].append(p)
        capitulos = [_capitulo_de(g, f"Text/cap-{k:04d}.xhtml", relatorio, titulos) for k, g in enumerate(grupos, 1)]
        nome = titulo or os.path.splitext(os.path.basename(caminho))[0]
        primeiro_titulo = next((modelo.texto_de(b) for c in capitulos for b in c.blocos
                                if isinstance(b, Titulo) and b.nivel == 1), "")
        livro = epub.novo_livro(titulo or primeiro_titulo or nome, "", idioma or "und", ncx=True)
        padrao = livro.folhas[0]
        for cap in capitulos:
            cap.folhas = [padrao]
        livro.capitulos = capitulos
        livro.metadados = Metadados(titulo=titulo or primeiro_titulo or nome, idioma=idioma or "und",
                                    identificador=livro.metadados.identificador)
        livro.sumario = sumario.gerar_dos_titulos(livro)
        livro.marcos = [("bodymatter", capitulos[0].arquivo)]
    relatorio.contar(livro)
    return livro, relatorio


__all__ = ["escrever", "ler", "QUEBRA_DE_PAGINA", "SEPARADOR"]
