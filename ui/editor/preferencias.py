"""
Preferências e ajuda do editor (ED-13; SPEC_EDITOR §7.6 "Preferências", §7.3 "Ajuda", §13).

## Um dict plano em `Settings.get("editor")`

As preferências são as chaves da §7.6 — `estilo_de_tela` (família, corpo em pt,
família monoespaçada), `largura_de_leitura`, `zoom`, `tema_codigo`, `tabulacao`,
`idioma_ortografia`, `fonte_diagrama`, `modo_diagrama`, `figurinas_ao_digitar`, `ncx`,
`intervalo_rascunho`, `notas`, `indicador_de_lado` — editadas numa caixa de formulário
(`Caixas.formulario`, injetável nos testes) e gravadas por `janela._gravar_preferencia`,
que é o que toda fase já usa. O que se pode aplicar sem reabrir, aplica-se na hora: o
estilo de tela, o zoom e a largura de leitura redesenham os capítulos abertos; o tema e
a tabulação do código valem nas abas que abrirem depois (a barra de status avisa).

## Ajuda

"Ajuda…" é um texto percorrível (a mesma caixa dos atalhos) com o essencial: os dois
modos, os painéis e o `F6`, o menu Xadrez, a ponte com o pipeline e onde ficam os
roteiros. Não substitui a spec: aponta para ela.
"""

from __future__ import annotations

from typing import Any, Callable

from ui.editor.texto_rico import TextoRico

SIM_NAO = ("sim", "não")
TEMAS_DO_CODIGO = ("claro", "escuro")
MODOS_DE_DIAGRAMA = ("png", "fonte")
NOTAS = ("rodape", "fim")
INDICADORES = ("marca", "legenda", "nenhum")

TEXTO_DE_AJUDA = """\
Editor de livro do PyBoxEditor — ajuda rápida (SPEC_EDITOR.md tem tudo)

Dois modos sobre o mesmo livro
  • Texto (à maneira do WordPad e do Word): parágrafos, estilos, listas, tabelas, figuras,
    diagramas, notas. O que está fora do dialeto do livro aparece como ilha (Ajuda → O dialeto
    do livro) e se edita no modo código.
  • Código (à maneira do Sigil): o XHTML de cada capítulo, com realce, autocompletar e o
    "Consertar". F11 alterna; nada se perde na volta.

Abrir e salvar
  • Arquivo → Abrir… aceita EPUB, HTML/XHTML, TXT, DOCX e o JSON do documento editorial
    (o livro que o OCR produziu, com a proveniência de cada bloco).
  • Salvar grava EPUB 3. Exportar… escreve HTML (único ou pasta), TXT, DOCX, PDF paginado e
    PGN; Imprimir… gera o PDF e o abre.
  • O rascunho automático grava a cada minuto com o livro sujo; ao reabrir, ele é oferecido.
    Livro → Pontos de verificação guarda cópias datadas.

Painéis e teclado
  • F6 percorre os painéis (navegador, sumário, estilos, propriedades, xadrez, busca,
    resultados, mensagens). Alt+letra abre os menus pelo mnemônico; Ajuda → Atalhos de
    teclado… lista os acordes.
  • Enter sobre um objeto faz a ação principal (diagrama: editar posição; tabela: entrar);
    Alt+Enter abre as Propriedades; Esc volta ao texto.
  • O tabuleiro do editor de posição: setas movem a casa, a letra da peça (K Q R B N P, ou
    R D T B C P em português) põe a peça branca, Shift+letra a preta, Delete esvazia, F gira.

Xadrez
  • Inserir diagrama (Ctrl+Shift+D), Editar posição (Ctrl+Shift+P), Diagrama a partir dos
    lances (Ctrl+Shift+G), Validar notação, figurinas ao digitar, Marcar lances/NAGs/
    jogador, Numerar, Índices, Chave de símbolos, PGN do capítulo.
  • O lado a jogar só é gravado quando o livro o afirma (Lado a jogar ▸); "desconhecido"
    é um estado honesto, e o diagrama avisa.

A ponte com o OCR
  • Um livro aberto do documento editorial (ou de um EPUB que veio dele) guarda a origem
    de cada bloco. Ao salvar, o que mudou vira evento no diário da revisão; o bloco que o
    OCR pôs na fila vem marcado (fundo amarelo, ! na calha) e o painel Propriedades mostra
    os motivos e as leituras — "Marcar como revisto" tira a marca.

Roteiros e medição: docs/roteiros/ (teclado, DOCX), scripts/medir_editor.py.
"""


class Preferencias:
    def __init__(self, janela: Any):
        self.j = janela
        self.comandos: dict[str, Callable[..., Any]] = {"preferencias": self.preferencias, "ajuda": self.ajuda}

    # -- o formulário -------------------------------------------------------------

    def _campos(self) -> tuple[list[tuple[str, str, str]], dict[str, tuple[str, ...]]]:
        j = self.j
        tela = j._preferencia("estilo_de_tela", {}) or {}
        from core.editor import modelo
        from ui.editor.diagrama import fontes_de_diagrama

        fontes = tuple(fontes_de_diagrama()) or (modelo.FONTE_PADRAO,)
        campos = [
            ("familia", "Fonte do texto na tela:", str(tela.get("familia", "Georgia"))),
            ("corpo_pt", "Corpo do texto na tela (pt):", f"{float(tela.get('corpo_pt', 12.0)):g}"),
            ("familia_mono", "Fonte monoespaçada:", str(tela.get("familia_mono", "Consolas"))),
            ("zoom", "Zoom da superfície:", f"{float(j._preferencia('zoom', 1.0) or 1.0):g}"),
            ("largura_de_leitura", "Largura de leitura (caracteres; 0 = toda a janela):",
             str(int(j._preferencia("largura_de_leitura", 0) or 0))),
            ("tema_codigo", "Tema do modo código:", str(j._preferencia("tema_codigo", "claro") or "claro")),
            ("tabulacao", "Tabulação do código (espaços):", str(int(j._preferencia("tabulacao", 2) or 2))),
            ("idioma_ortografia", "Idioma da ortografia:", str(j._preferencia("idioma_ortografia", "pt") or "pt")),
            ("fonte_diagrama", "Fonte de diagrama dos novos diagramas:",
             str(j._preferencia("fonte_diagrama", modelo.FONTE_PADRAO) or modelo.FONTE_PADRAO)),
            ("modo_diagrama", "Modo dos novos diagramas:", str(j._preferencia("modo_diagrama", "png") or "png")),
            ("indicador_de_lado", "Indicador de lado dos novos diagramas:",
             str(j._preferencia("indicador_de_lado", "marca") or "nenhum")),
            ("figurinas_ao_digitar", "Figurinas ao digitar:",
             "sim" if j._preferencia("figurinas_ao_digitar", True) else "não"),
            ("ncx", "Escrever toc.ncx no EPUB:", "sim" if j._preferencia("ncx", True) in (True, None) else "não"),
            ("notas", "Notas no DOCX/PDF:", str(j._preferencia("notas", "rodape") or "rodape")),
            ("intervalo_rascunho", "Intervalo do rascunho (s):",
             f"{float(j._preferencia('intervalo_rascunho', 60)):g}"),
        ]
        opcoes = {"tema_codigo": TEMAS_DO_CODIGO, "modo_diagrama": MODOS_DE_DIAGRAMA, "notas": NOTAS,
                  "indicador_de_lado": INDICADORES, "figurinas_ao_digitar": SIM_NAO, "ncx": SIM_NAO,
                  "fonte_diagrama": fontes}
        return campos, opcoes

    def preferencias(self, valores: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """Editar → Preferências…: a caixa; grava em `Settings.get("editor")` e aplica o que dá na hora."""
        j = self.j
        campos, opcoes = self._campos()
        if valores is None:
            valores = j.caixas.formulario("Preferências", campos, opcoes)
            if valores is None:
                return None
        valores = {k: v for k, v in valores.items()}

        def numero(chave: str, padrao: float, minimo: float, maximo: float) -> float:
            bruto = valores.get(chave, padrao)
            try:
                valor = float(str(bruto).replace(",", "."))
            except ValueError:
                raise ValueError(f"{chave}: {bruto!r} não é um número") from None
            if not minimo <= valor <= maximo:
                raise ValueError(f"{chave}: o valor precisa estar entre {minimo:g} e {maximo:g}")
            return valor

        def sim(chave: str, padrao: bool) -> bool:
            valor = valores.get(chave, padrao)
            return valor if isinstance(valor, bool) else str(valor).strip().lower() in ("sim", "s", "true", "1")

        def escolha(chave: str, padrao: str, permitidas: tuple[str, ...]) -> str:
            valor = str(valores.get(chave, padrao) or padrao).strip()
            if valor not in permitidas:
                raise ValueError(f"{chave}: {valor!r} não é uma das opções ({', '.join(permitidas)})")
            return valor

        tela_antes = dict(j._preferencia("estilo_de_tela", {}) or {})
        tela = dict(tela_antes)
        tela["familia"] = str(valores.get("familia", tela.get("familia", "Georgia"))).strip() or "Georgia"
        tela["corpo_pt"] = numero("corpo_pt", float(tela.get("corpo_pt", 12.0)), 6, 40)
        tela["familia_mono"] = str(valores.get("familia_mono", tela.get("familia_mono", "Consolas"))).strip() \
            or "Consolas"
        zoom = numero("zoom", float(j._preferencia("zoom", 1.0) or 1.0), 0.5, 4.0)
        largura = int(numero("largura_de_leitura", int(j._preferencia("largura_de_leitura", 0) or 0), 0, 400))
        tabulacao = int(numero("tabulacao", int(j._preferencia("tabulacao", 2) or 2), 1, 8))
        intervalo = numero("intervalo_rascunho", float(j._preferencia("intervalo_rascunho", 60) or 60), 5, 3600)
        fontes = tuple(opcoes["fonte_diagrama"])
        gravar = {
            "estilo_de_tela": tela, "zoom": zoom, "largura_de_leitura": largura,
            "tema_codigo": escolha("tema_codigo", "claro", TEMAS_DO_CODIGO), "tabulacao": tabulacao,
            "idioma_ortografia": str(valores.get("idioma_ortografia", j._preferencia("idioma_ortografia", "pt"))
                                     or "pt").strip().lower(),
            "fonte_diagrama": escolha("fonte_diagrama", fontes[0], fontes),
            "modo_diagrama": escolha("modo_diagrama", "png", MODOS_DE_DIAGRAMA),
            "indicador_de_lado": {"nenhum": ""}.get(escolha("indicador_de_lado", "marca", INDICADORES),
                                                   escolha("indicador_de_lado", "marca", INDICADORES)),
            "figurinas_ao_digitar": sim("figurinas_ao_digitar", True), "ncx": sim("ncx", True),
            "notas": escolha("notas", "rodape", NOTAS), "intervalo_rascunho": intervalo,
        }
        for chave, valor in gravar.items():
            j._gravar_preferencia(chave, valor)
        self._aplicar(gravar, tela_antes)
        j.status("Preferências gravadas" + (" — o tema e a tabulação do código valem nas abas que abrirem"
                                             if self._codigo_aberto() else ""))
        j.log.info("Preferências gravadas: %s.", ", ".join(f"{k}={v}" for k, v in gravar.items()
                                                            if k != "estilo_de_tela"))
        return gravar

    def _codigo_aberto(self) -> bool:
        return any(aba.modo == "codigo" for aba in self.j.abas.abas)

    def _aplicar(self, prefs: dict[str, Any], tela_antes: dict[str, Any]) -> None:
        """O estilo de tela, o zoom e a largura de leitura nos capítulos abertos; o resto onde se lê a preferência."""
        j = self.j
        if "figurinas_ao_digitar" in j.variaveis:
            j.variaveis["figurinas_ao_digitar"].set(bool(prefs["figurinas_ao_digitar"]))
        if hasattr(j, "rascunho") and j.rascunho is not None:
            j.rascunho.intervalo_s = float(prefs["intervalo_rascunho"])
        novo = j._estilo_de_tela()
        for aba in list(j.abas.abas):
            widget = aba.widget
            if not isinstance(widget, TextoRico):
                continue
            tela = widget.tela
            mudou = (tela.familia, tela.corpo_pt, tela.familia_mono, tela.largura_de_leitura) != (
                novo.familia, novo.corpo_pt, novo.familia_mono, novo.largura_de_leitura) or tela.zoom != novo.zoom
            if not mudou:
                continue
            tela.familia, tela.corpo_pt, tela.familia_mono = novo.familia, novo.corpo_pt, novo.familia_mono
            tela.largura_de_leitura = novo.largura_de_leitura
            widget.zoom(novo.zoom)                         # redesenha com o estilo novo
        j.atualizar()

    # -- ajuda ------------------------------------------------------------------------

    def ajuda(self) -> str:
        """Ajuda → Ajuda…: o texto percorrível com o essencial."""
        self.j.caixas.texto("Ajuda", TEXTO_DE_AJUDA, monoespaco=False)
        return TEXTO_DE_AJUDA


__all__ = ["Preferencias", "TEXTO_DE_AJUDA", "SIM_NAO", "TEMAS_DO_CODIGO", "MODOS_DE_DIAGRAMA", "NOTAS"]
