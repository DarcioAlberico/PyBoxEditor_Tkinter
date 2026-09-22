"""
O menu Xadrez na janela: `Xadrez(janela)` liga os comandos da ED-05 (SPEC_EDITOR §7.3
"Xadrez", "Inserir → Referência…/Figurina ▸/NAG ▸", §11.1–§11.7).

## O que mora aqui

Inserir diagrama (a `DialogoDeDiagrama`, também no modo código — vira a `<figure>`),
editar posição (`Enter` sobre o diagrama, `Ctrl+Shift+P`), diagrama a partir dos
lances (`posicao_apos` no cursor, com o lado proposto **gravado** — a linha sabe quem
joga), girar, coordenadas, lado a jogar e indicador (submenu dinâmico), validar
notação (seleção, capítulo ou livro → Resultados, a tag `notacao-ilegal` e o `✗` na
calha), figurinas ao digitar (o gancho `ao_fechar_token` do `TextoRico`), figurinas ↔
letras, marcar lances/NAGs/jogador/abertura, numerar, cabeçalho em legenda, as paletas,
a fonte dos símbolos e a fonte de diagrama do livro, a referência cruzada e a inserção
de um símbolo com o seu código (`inserir_simbolo_de_xadrez`, que a barra e a paleta
chamam). O painel "Xadrez" e a barra de xadrez são preenchidos aqui
(`ui/editor/paleta.py`). Da ED-05b: "Marcas e setas…" (a `DialogoDeMarcasESetas`),
"Legenda sugerida" (a proposta numa caixa de texto; o lado proposto vai à barra de
status, não ao diagrama) e "Chave de símbolos" (o capítulo `glossary`, refeito no lugar
quando já existe).

## O alvo é o diagrama do cursor

Girar, coordenadas, lado e editar posição agem sobre o diagrama sob o cursor (ou
selecionado); sem um, é erro de entrada ("o cursor precisa estar sobre um diagrama").
Toda mudança passa por `substituir_objeto`, que redesenha e registra o ponto de desfazer.
"""

from __future__ import annotations

import copy
from typing import Any, Callable, Sequence

from core.editor import modelo, xadrez as xadrez_mod, xhtml
from core.editor.modelo import Diagrama, Paragrafo, Titulo, Trecho
from ui.editor.paleta import (FIGURINAS, PainelDeXadrez, codigo_do_simbolo, precisa_da_fonte_de_simbolos,
                              preencher_barra_de_xadrez)
from ui.editor.resultados import Resultado

LADOS = (("w", "Brancas jogam"), ("b", "Pretas jogam"), ("", "Lado desconhecido"))
INDICADORES = (("", "Indicador: nenhum"), ("marca", "Indicador: marca"), ("legenda", "Indicador: legenda"))
IDIOMAS_DE_LETRAS = (("en", "inglês (KQRBN)"), ("pt", "português (RDTBC)"), ("es", "espanhol (RDTAC)"),
                     ("fr", "francês (RDTFC)"), ("de", "alemão (KDTLS)"))


class Xadrez:
    def __init__(self, janela: Any):
        self.j = janela
        x = self
        self.comandos: dict[str, Callable[..., Any]] = {
            "inserir_diagrama": x.inserir_diagrama, "editar_posicao": x.editar_posicao,
            "diagrama_dos_lances": x.diagrama_dos_lances, "girar_diagrama": x.girar_diagrama,
            "coordenadas_do_diagrama": x.coordenadas_do_diagrama, "lado_a_jogar": x.lado_a_jogar,
            "indicador_de_lado": x.indicador_de_lado, "validar_notacao": x.validar_notacao,
            "figurinas_ao_digitar": x.figurinas_ao_digitar, "figurinas_para_letras": x.figurinas_para_letras,
            "letras_para_figurinas": x.letras_para_figurinas, "marcar_lances": x.marcar_lances,
            "marcar_nags": x.marcar_nags, "marcar_jogador": x.marcar_jogador, "numerar_objetos": x.numerar_objetos,
            "cabecalho_em_legenda": x.cabecalho_em_legenda, "paleta_de_figurinas": x.paleta_de_figurinas,
            "paleta_de_nags": x.paleta_de_nags, "fonte_dos_simbolos": x.fonte_dos_simbolos,
            "fonte_de_diagrama": x.fonte_de_diagrama, "inserir_referencia": x.inserir_referencia,
            "inserir_simbolo_de_xadrez": x.inserir_simbolo_de_xadrez,
            # ED-05b
            "marcas_e_setas": x.marcas_e_setas, "legenda_sugerida": x.legenda_sugerida,
            "chave_de_simbolos": x.chave_de_simbolos,
        }
        self.so_no_texto = ("editar_posicao", "diagrama_dos_lances", "girar_diagrama", "coordenadas_do_diagrama",
                            "lado_a_jogar", "indicador_de_lado", "figurinas_para_letras", "letras_para_figurinas",
                            "marcar_lances", "marcar_nags", "marcar_jogador", "cabecalho_em_legenda",
                            "inserir_referencia", "marcas_e_setas", "legenda_sugerida")
        self.painel: PainelDeXadrez | None = None
        self._instalar_painel()
        janela.itens_dinamicos["lado"] = self.itens_de_lado
        janela.itens_dinamicos["figurinas"] = self.itens_de_figurinas
        janela.itens_dinamicos["nags"] = self.itens_de_nags
        janela.itens_dinamicos["figurinas_letras"] = self.itens_de_letras
        janela.itens_dinamicos["numerar"] = self.itens_de_numerar
        janela.variaveis["figurinas_ao_digitar"].set(bool(janela._preferencia("figurinas_ao_digitar", True)))

    # -- painel e barra ------------------------------------------------------------

    def _instalar_painel(self) -> None:
        j = self.j
        try:
            j.xadrez.destroy()
        except Exception:      # noqa: BLE001 — o rótulo de espera pode não existir
            pass
        self.painel = PainelDeXadrez(j.quadro_xadrez, ao_inserir=self.inserir_simbolo_de_xadrez,
                                     ao_sair=j.foco_no_editor, status=j.status)
        self.painel.pack(fill="both", expand=True)
        j.xadrez = self.painel
        if "xadrez" in j.paineis:
            j.paineis["xadrez"].foco = self.painel.foco
        preencher_barra_de_xadrez(j.barra_de_xadrez, j)

    # -- utilidades ---------------------------------------------------------------

    def _texto(self) -> Any:
        return self.j._texto_ativo()

    def _idioma(self) -> str:
        livro = self.j.projeto.livro if self.j.projeto is not None else None
        idioma = (livro.metadados.idioma if livro else "") or self.j._preferencia("idioma_ortografia", "pt") or "pt"
        return idioma.split("-")[0].lower()

    def _diagrama_alvo(self) -> tuple[Any, Diagrama]:
        """`(texto rico, diagrama)` sob o cursor ou selecionado; `ValueError` sem diagrama."""
        texto = self._texto()
        objeto = texto.objeto_no_cursor()
        if not isinstance(objeto, Diagrama):
            raise ValueError("o cursor precisa estar sobre um diagrama (ou selecione um)")
        return texto, objeto

    def _trocar(self, texto: Any, d: Diagrama, **mudancas: Any) -> Diagrama:
        novo = modelo.de_dict(modelo.para_dict(d))
        for chave, valor in mudancas.items():
            setattr(novo, chave, valor)
        if novo.lado == "" and novo.lado_indicador:
            novo.lado_indicador = ""
        xadrez_mod.conferir_marcas(novo)
        texto.substituir_objeto(d.id, novo)
        return novo

    def _recorte_de(self, d: Diagrama) -> Any:
        """A imagem do recorte impresso (PIL), quando o diagrama a tem e ela está no livro."""
        if not d.recorte or self.j.projeto is None:
            return None
        dados = self.j._dados_do_recurso(d.recorte)
        if not dados:
            return None
        try:
            import io as _io

            from PIL import Image

            return Image.open(_io.BytesIO(dados))
        except Exception:      # noqa: BLE001 — recorte ilegível: a caixa abre sem ele
            return None

    # -- diagramas ---------------------------------------------------------------------

    def inserir_diagrama(self, diagrama: Diagrama | None = None) -> str | None:
        """Inserir diagrama… (`Ctrl+Shift+D`): a caixa; no texto entra como objeto, no código como `<figure>`."""
        j = self.j
        if j.editor_ativo() is None:
            raise ValueError("Nenhuma aba aberta.")
        if diagrama is None:
            base = Diagrama(fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                            fonte=j._preferencia("fonte_diagrama", modelo.FONTE_PADRAO) or modelo.FONTE_PADRAO,
                            modo=j._preferencia("modo_diagrama", "png") or "png")
            diagrama = j.caixas.diagrama(base, idioma=self._idioma(), titulo="Inserir diagrama")
            if diagrama is None:
                return None
        if j.modo_atual() == "texto":
            texto = self._texto()
            bloco_id = texto.inserir_objeto(diagrama)
            j.status("Diagrama inserido")
            return bloco_id
        editor = j._codigo()
        editor.inserir(xhtml.escrever_fragmento([diagrama]) + "\n")
        j.status("Diagrama inserido (como <figure class=\"diagrama\">)")
        return diagrama.id

    def editar_posicao(self, diagrama: Diagrama | None = None) -> Diagrama | None:
        """Editar posição… (`Ctrl+Shift+P`, `Enter` sobre o diagrama): a caixa sobre o diagrama do cursor."""
        texto, atual = self._diagrama_alvo()
        if diagrama is None:
            diagrama = self.j.caixas.diagrama(atual, recorte=self._recorte_de(atual), idioma=self._idioma(),
                                              titulo="Editar posição")
            if diagrama is None:
                return None
        diagrama.id = atual.id
        texto.substituir_objeto(atual.id, diagrama)
        self.j.status("Posição editada")
        return diagrama

    def diagrama_dos_lances(self) -> str:
        """Diagrama a partir dos lances (`Ctrl+Shift+G`): a posição da linha do cursor, com o lado que ela diz."""
        j = self.j
        texto = self._texto()
        bloco_id, desloc = texto.posicao()
        if bloco_id is None:
            raise ValueError("o cursor precisa estar numa linha de jogo (parágrafo de notação)")
        cap = texto.sincronizar()
        blocos = list(cap.blocos)
        indices = {b.id: i for i, b in enumerate(blocos)}
        if bloco_id not in indices:
            raise ValueError("o cursor precisa estar no corpo do capítulo")
        if not xadrez_mod.e_notacao(blocos[indices[bloco_id]]):
            raise ValueError("o cursor não está numa linha de jogo: só parágrafos de notação contam (§11.3)")
        d, posicao = xadrez_mod.diagrama_dos_lances(
            blocos, (indices[bloco_id], desloc), fonte=j._preferencia("fonte_diagrama", modelo.FONTE_PADRAO)
            or modelo.FONTE_PADRAO, modo=j._preferencia("modo_diagrama", "png") or "png",
            lado_indicador=j._preferencia("indicador_de_lado", "marca") or "")
        for aviso in posicao.avisos:
            j.log.warning("%s", aviso)
        if posicao.erro:
            raise ValueError(f"{posicao.erro} não é legal na linha — corrija antes de inserir o diagrama "
                             f"(a posição vai até o lance anterior)")
        if "o cursor não está numa linha de jogo" in posicao.avisos:
            raise ValueError("o cursor não está numa linha de jogo: só parágrafos de notação contam (§11.3)")
        novo_id = texto.inserir_bloco_no_cursor(d)
        j.status(f"Diagrama inserido: {xadrez_mod.legenda_de_lado(d, self._idioma())}")
        return novo_id

    def girar_diagrama(self) -> str:
        texto, d = self._diagrama_alvo()
        novo = self._trocar(texto, d, orientacao="preta" if d.orientacao == "branca" else "branca")
        return novo.orientacao

    def coordenadas_do_diagrama(self) -> bool:
        texto, d = self._diagrama_alvo()
        return self._trocar(texto, d, coordenadas=not d.coordenadas).coordenadas

    def lado_a_jogar(self, lado: str) -> str:
        if lado not in ("w", "b", ""):
            raise ValueError(f"lado inválido: {lado!r}")
        texto, d = self._diagrama_alvo()
        return self._trocar(texto, d, lado=lado).lado

    def indicador_de_lado(self, indicador: str) -> str:
        if indicador not in ("", "marca", "legenda"):
            raise ValueError(f"indicador inválido: {indicador!r}")
        texto, d = self._diagrama_alvo()
        if indicador and not d.lado:
            raise ValueError("o lado a jogar é desconhecido: escolha brancas ou pretas antes do indicador (DEC-06)")
        self.j._gravar_preferencia("indicador_de_lado", indicador)
        return self._trocar(texto, d, lado_indicador=indicador).lado_indicador

    # -- ED-05b: marcas e setas, legenda sugerida ----------------------------------------

    def marcas_e_setas(self, marcas: Sequence[str] | None = None,
                       setas: Sequence[Sequence[str]] | None = None) -> Diagrama | None:
        """Marcas e setas… (§11.1): a caixa sobre o diagrama do cursor; em modo `fonte` fica o aviso."""
        texto, d = self._diagrama_alvo()
        if marcas is None and setas is None:
            novo = self.j.caixas.marcas_e_setas(d, idioma=self._idioma())
            if novo is None:
                return None
            marcas, setas = list(novo.marcas), list(novo.setas)
        marcas = [m for m in (marcas or []) if xadrez_mod.casa_valida(m)]
        setas = [(a, b) for a, b in (tuple(s) for s in (setas or [])) if xadrez_mod.casa_valida(a)
                 and xadrez_mod.casa_valida(b) and a != b]
        novo = self._trocar(texto, d, marcas=marcas, setas=setas)
        self.j.status(f"Marcas: {len(marcas)} · setas: {len(setas)}" + (f" — {novo.aviso}" if novo.aviso else ""))
        return novo

    def legenda_sugerida(self, legenda: str | None = None) -> str | None:
        """Legenda sugerida (§11.7): "Diagrama 12: após 23…♖xe4 — Pretas jogam"; o lado é proposto, não gravado."""
        texto, d = self._diagrama_alvo()
        cap = texto.sincronizar()
        blocos = list(cap.blocos)
        ids = [b.id for b in blocos]
        if d.id not in ids:
            raise ValueError("o diagrama precisa estar no corpo do capítulo")
        sugestao, lado = xadrez_mod.legenda_sugerida(blocos, ids.index(d.id), self._idioma())
        if legenda is None:
            legenda = self.j.caixas.pedir_texto("Legenda sugerida", "Legenda:", sugestao)
            if legenda is None:
                return None
        legenda = legenda.strip()
        self._trocar(texto, d, legenda=[Trecho(texto=legenda)] if legenda else [])
        aviso = ""
        if lado and lado != d.lado:
            rotulo = {"w": "brancas", "b": "pretas"}[lado]
            aviso = f" — lado proposto: {rotulo} (não gravado; Lado a jogar ▸ grava)"
        self.j.status(f"Legenda: {legenda or '(vazia)'}{aviso}")
        return legenda

    def chave_de_simbolos(self) -> str:
        """Chave de símbolos (§11.10): o capítulo `glossary` com os NAGs usados, aberto no fim."""
        j = self.j
        projeto = j._exigir_projeto()
        j._sincronizar_tudo()
        cap = xadrez_mod.chave_de_simbolos(projeto.livro, idioma=self._idioma())
        usados = xadrez_mod.nags_usados(projeto.livro)
        j.operacoes._depois(cap.arquivo)
        j.abrir_capitulo(cap.arquivo)
        j.status(f"Chave de símbolos: {len(usados)} símbolo(s) em {cap.arquivo}")
        j.log.info("Chave de símbolos refeita: %s (%d símbolos).", cap.arquivo, len(usados))
        return cap.arquivo

    def itens_de_lado(self) -> list[tuple[str, Callable[[], Any] | None]]:
        try:
            _texto, d = self._diagrama_alvo()
        except ValueError:
            return [("(o cursor não está num diagrama)", None)]
        itens: list[tuple[str, Callable[[], Any] | None]] = []
        for valor, rotulo in LADOS:
            marca = "✓ " if d.lado == valor else "   "
            itens.append((marca + rotulo, lambda v=valor: self.j.executar("lado_a_jogar", v)))
        for valor, rotulo in INDICADORES:
            marca = "✓ " if d.lado_indicador == valor else "   "
            itens.append((marca + rotulo, lambda v=valor: self.j.executar("indicador_de_lado", v)))
        return itens

    # -- validação ------------------------------------------------------------------------

    def validar_notacao(self, escopo: str = "capitulo") -> list[Resultado]:
        """Validar notação (seleção, capítulo ou livro): Resultados, a tag `notacao-ilegal` e o `✗` na calha."""
        j = self.j
        projeto = j._exigir_projeto()
        if escopo not in ("selecao", "capitulo", "livro"):
            raise ValueError(f"escopo inválido: {escopo!r}")
        resultados: list[Resultado] = []
        problemas_do_capitulo: list[xadrez_mod.Problema] = []
        capitulos = projeto.livro.capitulos if escopo == "livro" else [None]
        aba = j.aba_ativa()
        texto = aba.widget if aba is not None and aba.modo == "texto" and aba.tipo == "capitulo" else None
        for cap in capitulos:
            if cap is None:
                if texto is None:
                    raise ValueError("abra um capítulo no modo texto para validar a notação")
                cap = texto.sincronizar()
            elif texto is not None and aba is not None and aba.arquivo == cap.arquivo:
                cap = texto.sincronizar()
            blocos = list(cap.blocos)
            if escopo == "selecao" and texto is not None:
                selecao = texto.selecao()
                if selecao:
                    a, _da = texto.posicao_de(selecao[0])
                    b, _db = texto.posicao_de(selecao[1])
                    ids = [x.id for x in blocos]
                    if a in ids and b in ids:
                        ia, ib = sorted((ids.index(a), ids.index(b)))
                        recorte = blocos[ia:ib + 1]
                        problemas = [p_ for p_ in xadrez_mod.validar(recorte)]
                        for p_ in problemas:
                            p_.i_bloco += ia
                    else:
                        problemas = xadrez_mod.validar(blocos)
                else:
                    problemas = xadrez_mod.validar(blocos)
            else:
                problemas = xadrez_mod.validar(blocos)
            if texto is not None and (escopo != "livro" or (aba is not None and aba.arquivo == cap.arquivo)):
                problemas_do_capitulo = problemas
            for p_ in problemas:
                resultados.append(Resultado(cap.arquivo, f"bloco {p_.i_bloco + 1}", p_.mensagem,
                                            {"bloco": p_.bloco_id, "deslocamento": p_.inicio,
                                             "comprimento": p_.fim - p_.inicio, "sugestao": p_.sugestao}))
        if texto is not None:
            self.marcar_no_widget(texto, problemas_do_capitulo)
        rotulo = {"selecao": "na seleção", "capitulo": "no capítulo", "livro": "no livro"}[escopo]
        j.resultados.definir(resultados, f"Notação {rotulo}: {len(resultados)} lance(s) ilegal(is)")
        if resultados:
            j._focar_inferior(j.resultados)
        j.status(f"Validação da notação {rotulo}: {len(resultados)} problema(s)")
        j.log.info("Validação da notação %s: %d problema(s).", rotulo, len(resultados))
        return resultados

    @staticmethod
    def marcar_no_widget(texto: Any, problemas: Sequence[xadrez_mod.Problema]) -> int:
        """A tag `notacao-ilegal` em cada lance ilegal do widget, e o `✗` na calha do bloco; devolve quantos."""
        t = texto.texto
        t.tag_remove("notacao-ilegal", "1.0", "end")
        for bloco_id in list(getattr(texto.calha, "_icones", {})):
            if texto.calha.icone_de(bloco_id) == "notacao-ilegal":
                texto.calha.marcar(bloco_id, None)
        marcados = 0
        for p_ in problemas:
            a = texto.indice_de(p_.bloco_id, p_.inicio)
            b = texto.indice_de(p_.bloco_id, p_.fim)
            if a is None or b is None:
                continue
            t.tag_add("notacao-ilegal", a, b)
            texto.calha.marcar(p_.bloco_id, "notacao-ilegal")
            marcados += 1
        return marcados

    # -- figurinas e letras --------------------------------------------------------------

    def figurinas_ao_digitar(self, ligar: bool | None = None) -> bool:
        """A caixa de marcar: o gancho fica ligado/desligado nos editores abertos e na preferência."""
        j = self.j
        if ligar is None:
            ligar = bool(j.variaveis["figurinas_ao_digitar"].get())
        else:
            j.variaveis["figurinas_ao_digitar"].set(bool(ligar))
        j._gravar_preferencia("figurinas_ao_digitar", bool(ligar))
        j.status("Figurinas ao digitar: " + ("ligadas" if ligar else "desligadas"))
        return bool(ligar)

    def ao_fechar_token(self, bloco_id: str, deslocamento: int) -> bool:
        """O gancho do `TextoRico`: o token fechado vira figurina quando a opção está ligada e o parágrafo é notação."""
        j = self.j
        if not j.variaveis["figurinas_ao_digitar"].get():
            return False
        aba = j.aba_ativa()
        if aba is None or aba.modo != "texto" or aba.tipo != "capitulo":
            return False
        texto = aba.widget
        par = texto.modelo_de(bloco_id)
        if not isinstance(par, Paragrafo) or isinstance(par, Titulo):
            return False
        copia = copy.deepcopy(par)
        if not xadrez_mod.figurina_ao_digitar(copia, deslocamento, self._idioma()):
            return False
        posicao = texto.posicao()
        texto._reescrever_bloco(bloco_id, copia)
        if posicao[0] == bloco_id:
            texto.ir_para(bloco_id, posicao[1])
        return True

    def _converter_notacao(self, funcao: Callable[[str], str], rotulo: str) -> int:
        texto = self._texto()
        cap = texto.sincronizar()
        mudados = 0
        texto._abrir_composto(rotulo)
        try:
            for bloco in list(cap.blocos):
                if not isinstance(bloco, Paragrafo) or isinstance(bloco, Titulo):
                    continue
                if bloco.estilo not in xadrez_mod.ESTILOS_DE_NOTACAO and not any(t.papel == "lance"
                                                                                 for t in bloco.trechos):
                    continue
                copia = copy.deepcopy(bloco)
                mudou = False
                for t in copia.trechos:
                    if t.texto:
                        novo = funcao(t.texto)
                        if novo != t.texto:
                            t.texto, mudou = novo, True
                if mudou:
                    texto._reescrever_bloco(bloco.id, copia)
                    mudados += 1
        finally:
            texto._fechar_composto()
        self.j.status(f"{rotulo}: {mudados} parágrafo(s)")
        return mudados

    def figurinas_para_letras(self, idioma: str = "en") -> int:
        return self._converter_notacao(lambda t: xadrez_mod.para_letras(t, "figurinas", idioma),
                                       f"Figurinas → letras ({idioma})")

    def letras_para_figurinas(self, idioma: str | None = None) -> int:
        idioma = idioma or self._idioma()
        return self._converter_notacao(lambda t: xadrez_mod.para_figurinas(t, idioma),
                                       f"Letras ({idioma}) → figurinas")

    def itens_de_letras(self) -> list[tuple[str, Callable[[], Any] | None]]:
        itens: list[tuple[str, Callable[[], Any] | None]] = []
        for codigo, rotulo in IDIOMAS_DE_LETRAS:
            itens.append((f"Figurinas → letras em {rotulo}",
                          lambda c=codigo: self.j.executar("figurinas_para_letras", c)))
        for codigo, rotulo in IDIOMAS_DE_LETRAS:
            itens.append((f"Letras em {rotulo} → figurinas",
                          lambda c=codigo: self.j.executar("letras_para_figurinas", c)))
        return itens

    # -- marcar --------------------------------------------------------------------------

    def _aplicar_nos_blocos(self, funcao: Callable[[list], Any], rotulo: str) -> Any:
        """`funcao(blocos)` sobre cópias dos blocos do capítulo; os que mudaram são reescritos no widget."""
        texto = self._texto()
        cap = texto.sincronizar()
        copias = copy.deepcopy(list(cap.blocos))
        resultado = funcao(copias)
        texto._abrir_composto(rotulo)
        try:
            for antes, depois in zip(cap.blocos, copias):
                if not modelo.igual(antes, depois):
                    texto._reescrever_bloco(antes.id, depois)
        finally:
            texto._fechar_composto()
        return resultado

    def marcar_lances(self) -> int:
        n = self._aplicar_nos_blocos(xadrez_mod.marcar_lances, "Marcar lances")
        self.j.status(f"Lances marcados: {n}")
        return n

    def marcar_nags(self) -> tuple[int, list[str]]:
        n, ambiguos = self._aplicar_nos_blocos(xadrez_mod.marcar_nags, "Marcar NAGs")
        texto = ", ".join(ambiguos)
        self.j.status(f"NAGs marcados: {n}" + (f" — ambíguos, deixados como estão: {texto}" if ambiguos else ""))
        if ambiguos:
            self.j.log.info("NAGs ambíguos (não marcados): %s", texto)
        return n, ambiguos

    def marcar_jogador(self, escolhidas: Sequence[int] | None = None) -> int:
        """Marcar jogador/abertura…: as sugestões dos cabeçalhos, com a lista para marcar."""
        texto = self._texto()
        cap = texto.sincronizar()
        sugestoes = xadrez_mod.sugerir_jogadores_e_aberturas(list(cap.blocos))
        if not sugestoes:
            raise ValueError("nenhum cabeçalho \"Nome – Nome\" nem código ECO encontrado no capítulo")
        if escolhidas is None:
            opcoes = [f"{s.texto}  →  {s.chave}  ({s.papel})" for s in sugestoes]
            escolhidas = self.j.caixas.marcar_varios("Marcar jogador/abertura", "Marcar como índice:", opcoes,
                                                    marcadas=list(range(len(opcoes))), ok="Marcar")
            if escolhidas is None:
                return 0
        selecao = [sugestoes[i] for i in escolhidas if 0 <= i < len(sugestoes)]
        n = self._aplicar_nos_blocos(lambda blocos: xadrez_mod.marcar_jogador_abertura(blocos, selecao),
                                     "Marcar jogador/abertura")
        self.j.status(f"Marcados: {n}")
        return n

    # -- numerar, cabeçalho, referências -------------------------------------------------

    def numerar_objetos(self, tipo: str = "diagrama", por_capitulo: bool = False) -> dict[str, int]:
        """Numerar ▸: diagramas, figuras ou tabelas, por livro ou por capítulo; as referências são refeitas."""
        j = self.j
        projeto = j._exigir_projeto()
        if tipo not in modelo.ROTULOS_DE_OBJETO:
            raise ValueError(f"tipo inválido: {tipo!r}")
        j._sincronizar_tudo()
        numeros = modelo.numerar_objetos(projeto.livro, tipo, por_capitulo)
        projeto.marcar_sujo()
        for aba in list(j.abas.abas):
            if aba.tipo == "capitulo":
                j._recarregar_aba(aba)
        j.status(f"{modelo.ROTULOS_DE_OBJETO[tipo]}s numerados: {len(numeros)}"
                 + (" (por capítulo)" if por_capitulo else ""))
        j.atualizar()
        return numeros

    def itens_de_numerar(self) -> list[tuple[str, Callable[[], Any] | None]]:
        itens: list[tuple[str, Callable[[], Any] | None]] = []
        for tipo, rotulo in modelo.ROTULOS_DE_OBJETO.items():
            itens.append((f"{rotulo}s por livro", lambda t=tipo: self.j.executar("numerar_objetos", t, False)))
            itens.append((f"{rotulo}s por capítulo", lambda t=tipo: self.j.executar("numerar_objetos", t, True)))
        return itens

    def cabecalho_em_legenda(self) -> Diagrama | None:
        """Cabeçalho em legenda: o título/cabeçalho do cursor vira legenda do diagrama seguinte."""
        texto = self._texto()
        bloco_id, _desloc = texto.posicao()
        cap = texto.sincronizar()
        ids = [b.id for b in cap.blocos]
        if bloco_id not in ids:
            raise ValueError("o cursor precisa estar num título ou cabeçalho de diagrama")
        i = ids.index(bloco_id)
        copia = copy.deepcopy(cap)
        d = xadrez_mod.cabecalho_em_legenda(copia, i)
        if d is None:
            raise ValueError("o bloco do cursor não é um cabeçalho seguido de um diagrama")
        texto._abrir_composto("Cabeçalho em legenda")
        try:
            texto.substituir_objeto(d.id, d)
            texto.apagar_bloco(bloco_id)
        finally:
            texto._fechar_composto()
        self.j.status("Cabeçalho virou legenda do diagrama")
        return d

    def inserir_referencia(self, alvo: str | None = None) -> str | None:
        """Inserir → Referência…: "Diagrama 12", "Figura 3", "Tabela 1" ou um título, com o texto regenerável."""
        j = self.j
        projeto = j._exigir_projeto()
        texto = self._texto()
        j._sincronizar_tudo()
        alvos = xadrez_mod.alvos_de_referencia(projeto.livro)
        if not alvos:
            raise ValueError("o livro não tem diagrama, figura, tabela nem título para referenciar")
        aba = j.aba_ativa()
        if alvo is None:
            rotulos = [f"{rot}  —  {arq}" for arq, _id, _tipo, rot in alvos]
            indice = j.caixas.escolher("Inserir referência", "Alvo:", rotulos, "Inserir")
            if indice is None:
                return None
            arquivo, bloco_id, tipo, rotulo = alvos[indice]
        else:
            arquivo, _, bloco_id = alvo.partition("#")
            achado = next((a for a in alvos if a[0] == arquivo and a[1] == bloco_id), None)
            if achado is None:
                raise ValueError(f"alvo desconhecido: {alvo}")
            arquivo, bloco_id, tipo, rotulo = achado
        link = f"#{bloco_id}" if aba is not None and aba.arquivo == arquivo else f"{arquivo}#{bloco_id}"
        texto.inserir_formatado(rotulo, ref=tipo, link=link)
        j.status(f"Referência inserida: {rotulo}")
        return rotulo

    # -- paletas, símbolos, fontes ------------------------------------------------------

    def paleta_de_figurinas(self) -> None:
        j = self.j
        if not j.paineis["xadrez"].visivel:
            j.mostrar_painel("xadrez", True)
        if self.painel is not None:
            self.painel.grades[0].foco()

    def paleta_de_nags(self) -> None:
        j = self.j
        if not j.paineis["xadrez"].visivel:
            j.mostrar_painel("xadrez", True)
        if self.painel is not None and len(self.painel.grades) > 1:
            self.painel.grades[1].foco()

    def inserir_simbolo_de_xadrez(self, simbolo: str) -> str:
        """O símbolo da paleta/barra no editor ativo, com o código (`papel`/`nag`) e a família quando precisa."""
        j = self.j
        if j.editor_ativo() is None:
            raise ValueError("Nenhuma aba aberta.")
        if j.modo_atual() != "texto":
            j.inserir_texto(simbolo)
            return simbolo
        texto = self._texto()
        atributos: dict[str, Any] = {}
        if simbolo in dict(FIGURINAS):
            atributos["papel"] = "figurina"
        else:
            codigo = codigo_do_simbolo(simbolo)
            if codigo is not None:
                atributos.update(papel="nag", nag=codigo)
        if precisa_da_fonte_de_simbolos(simbolo):
            atributos["familia"] = "simbolos"
        texto.inserir_formatado(simbolo, **atributos)
        return simbolo

    def itens_de_figurinas(self) -> list[tuple[str, Callable[[], Any] | None]]:
        return [(f"{simbolo}  {nome}", lambda s=simbolo: self.j.executar("inserir_simbolo_de_xadrez", s))
                for simbolo, nome in FIGURINAS]

    def itens_de_nags(self) -> list[tuple[str, Callable[[], Any] | None]]:
        from core import nags

        itens: list[tuple[str, Callable[[], Any] | None]] = []
        for _familia, pares in nags.NAGS_POR_FAMILIA:
            for simbolo, descricao in pares:
                codigo = codigo_do_simbolo(simbolo)
                rotulo = f"{simbolo}  {descricao}" + (f"  (${codigo})" if codigo is not None else "")
                itens.append((rotulo, lambda s=simbolo: self.j.executar("inserir_simbolo_de_xadrez", s)))
        return itens

    def fonte_dos_simbolos(self, familia: str | None = None) -> int:
        """Fonte dos símbolos…: os símbolos do livro na fonte de recurso (`simbolos`) ou na do texto."""
        j = self.j
        projeto = j._exigir_projeto()
        if familia is None:
            indice = j.caixas.escolher("Fonte dos símbolos", "Os símbolos de xadrez do livro saem em:",
                                       ["fonte de símbolos embutida (recomendado)", "fonte do texto"], "Aplicar")
            if indice is None:
                return 0
            familia = "simbolos" if indice == 0 else ""
        j._sincronizar_tudo()
        n = xadrez_mod.fonte_dos_simbolos_do_livro(projeto.livro, familia)
        if n:
            projeto.marcar_sujo()
            for aba in list(j.abas.abas):
                if aba.tipo == "capitulo":
                    j._recarregar_aba(aba)
        j.status(f"Trechos com símbolos {'na fonte de símbolos' if familia else 'na fonte do texto'}: {n}")
        return n

    def fonte_de_diagrama(self, fonte: str | None = None) -> int:
        """Fonte de diagrama do livro…: a fonte de todos os diagramas (e a preferência para os novos)."""
        j = self.j
        projeto = j._exigir_projeto()
        from ui.editor.diagrama import fontes_de_diagrama

        fontes = fontes_de_diagrama()
        if fonte is None:
            atual = j._preferencia("fonte_diagrama", modelo.FONTE_PADRAO)
            indice = j.caixas.escolher("Fonte de diagrama do livro", "Fonte:", fontes, "Aplicar")
            if indice is None:
                return 0
            fonte = fontes[indice] if indice < len(fontes) else atual
        if fonte not in fontes:
            raise ValueError(f"fonte de diagrama desconhecida: {fonte!r} (há: {', '.join(fontes)})")
        j._gravar_preferencia("fonte_diagrama", fonte)
        j._sincronizar_tudo()
        n = xadrez_mod.fonte_do_livro(projeto.livro, fonte)
        if n:
            projeto.marcar_sujo()
            for aba in list(j.abas.abas):
                if aba.tipo == "capitulo":
                    j._recarregar_aba(aba)
        j.status(f"Fonte de diagrama do livro: {fonte} ({n} diagrama(s) mudaram)")
        return n


__all__ = ["Xadrez", "LADOS", "INDICADORES", "IDIOMAS_DE_LETRAS"]
