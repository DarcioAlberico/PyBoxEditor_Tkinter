"""
As operações de livro na janela (ED-08; SPEC_EDITOR §9 tabela, §9.5–§9.8, §10.1): o menu
Livro inteiro (capa, sumário, semântica, marcos, folhas, arquivos, renomear, excluir,
mover, ordenar, abrir com…), os relatórios, a validação com o `epubcheck`, as duas
limpezas, a prévia (`F12`), "Sumário como página", "Folhas de estilo do livro…" e os
metadados completos.

Cada comando descobre o **alvo** pelo navegador (o arquivo focado) ou, sem ele, pela aba
ativa; muda o modelo por `core/editor/livro_ops.py`; e recarrega o que está na tela —
navegador, sumário, as abas do que mudou. O que precisa perguntar passa por
`janela.caixas`, que o teste troca. "Abrir com…" exporta o arquivo para uma pasta
temporária, lança o programa (`lancador`, injetável) e vigia o arquivo: quando ele muda
no disco, volta para o livro.
"""

from __future__ import annotations

import os
import posixpath
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Sequence

from core.editor import epub, livro_ops, relatorios, sumario as core_sumario, validacao
from core.editor.modelo import Recurso
from ui.editor import metadados as metadados_ui
from ui.editor.resultados import Resultado

RELATORIOS = relatorios.RELATORIOS
INTERVALO_DA_VIGIA_MS = 1500


def _lancar_padrao(caminho: str, programa: str = "") -> None:
    """Abre `caminho` no programa dado, ou no associado pelo sistema."""
    if programa:
        subprocess.Popen([programa, caminho])
    elif sys.platform.startswith("win"):
        os.startfile(caminho)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", caminho])
    else:
        subprocess.Popen(["xdg-open", caminho])


class OperacoesDoLivro:
    def __init__(self, janela: Any):
        self.j = janela
        self.lancador: Callable[[str, str], Any] = _lancar_padrao
        self.correr_epubcheck: Any = subprocess.run          # injetável: o teste não precisa do Java
        self.vigiados: dict[str, tuple[str, float]] = {}      # caminho temporário → (href, mtime)
        self._vigia_id: str | None = None
        self._pasta_temporaria: str | None = None
        j = self
        self.comandos: dict[str, Callable[..., Any]] = {
            "abrir_do_navegador": j.abrir_do_navegador, "reordenar_capitulos": j.reordenar_capitulos,
            "capa": j.capa, "sumario_gerar": j.sumario_gerar, "sumario_editar": j.sumario_editar,
            "sumario_gravar": j.sumario_gravar, "sumario_como_pagina": j.sumario_como_pagina,
            "semantica": j.semantica, "marcos": j.marcos, "vincular_folhas": j.vincular_folhas,
            "adicionar_arquivo": j.adicionar_arquivo, "adicionar_copia": j.adicionar_copia,
            "novo_capitulo": j.novo_capitulo, "nova_folha": j.nova_folha, "renomear": j.renomear,
            "renomear_varios": j.renomear_varios, "excluir": j.excluir,
            "mover_para_cima": lambda: j.mover(-1), "mover_para_baixo": lambda: j.mover(1),
            "ordenar_por_nome": j.ordenar_por_nome, "abrir_com": j.abrir_com, "metadados": j.metadados,
            "folhas_de_estilo": j.folhas_de_estilo, "validar_epub": j.validar_epub,
            "apagar_recursos": j.apagar_recursos, "apagar_classes": j.apagar_classes, "previa": j.previa,
        }
        for nome in RELATORIOS:
            self.comandos[f"relatorio_{nome}"] = (lambda n=nome: j.relatorio(n))

    # -- o alvo -----------------------------------------------------------------

    def alvo(self, so_capitulo: bool = False) -> str:
        """O href do navegador (focado), senão o da aba ativa; `ValueError` sem nenhum."""
        j = self.j
        projeto = j._exigir_projeto()
        href = j.painel_navegador.selecionado() if hasattr(j, "painel_navegador") else None
        if href is None:
            aba = j.aba_ativa()
            href = aba.arquivo if aba is not None else None
        if not href:
            raise ValueError("escolha um arquivo no navegador (ou abra uma aba)")
        if so_capitulo and projeto.livro.capitulo(href) is None:
            raise ValueError(f"{href} não é um capítulo")
        return href

    def _depois(self, *arquivos: str, sumario: bool = True) -> None:
        """O que toda operação faz no fim: sujo, navegador, sumário, as abas do que mudou, a barra."""
        j = self.j
        projeto = j._exigir_projeto()
        projeto.marcar_sujo()
        j.atualizar_navegador()
        if sumario:
            j.atualizar_sumario()
        for arquivo in arquivos:
            aba = j.abas.por_arquivo(arquivo)
            if aba is not None:
                if projeto.livro.capitulo(arquivo) is None and projeto.livro.recurso(arquivo) is None:
                    j.abas.fechar(aba)
                else:
                    j._recarregar_aba(aba)
        j.atualizar()

    def abrir_do_navegador(self, href: str | None = None) -> Any:
        j = self.j
        href = href or self.alvo()
        livro = j._exigir_projeto().livro
        if href == livro.opf:
            return j.abrir_leitura(href)
        return j.abrir_arquivo(href)

    # -- capa, sumário, semântica, marcos, folhas ----------------------------------

    def capa(self, href_da_imagem: str | None = None) -> str | None:
        """Livro → Capa…: uma imagem do livro (ou do disco) vira a capa, com o invólucro SVG (AC-ED08-4)."""
        j = self.j
        projeto = j._exigir_projeto()
        livro = projeto.livro
        imagens = [c for c, r in livro.recursos.items() if r.tipo_mime.startswith("image/")]
        if href_da_imagem is None:
            escolhido = j.painel_navegador.selecionado()
            if escolhido in imagens:
                href_da_imagem = escolhido
            else:
                opcoes = imagens + ["(uma imagem do disco…)"]
                indice = j.caixas.escolher("Capa", "Imagem da capa:", opcoes, "Definir")
                if indice is None:
                    return None
                if indice == len(imagens):
                    caminho = j.caixas.abrir_imagem(j._preferencia("diretorios", {}).get("imagens", ""))
                    if not caminho:
                        return None
                    href_da_imagem = self._importar_arquivo(caminho)
                else:
                    href_da_imagem = imagens[indice]
        elif href_da_imagem not in livro.recursos and os.path.isfile(href_da_imagem):
            href_da_imagem = self._importar_arquivo(href_da_imagem)
        arquivo = livro_ops.definir_capa(livro, href_da_imagem, titulo="Capa")
        self._depois(arquivo)
        j.log.info("Capa: %s (%s).", href_da_imagem, arquivo)
        j.status(f"Capa: {href_da_imagem}")
        return arquivo

    def sumario_gerar(self, niveis: Sequence[int] | None = None) -> list:
        j = self.j
        projeto = j._exigir_projeto()
        if niveis is None:
            indice = j.caixas.escolher("Gerar sumário", "Dos títulos de nível:", ["1 e 2", "1, 2 e 3", "só 1"], "Gerar")
            if indice is None:
                return projeto.livro.sumario
            niveis = ((1, 2), (1, 2, 3), (1,))[indice]
        j._sincronizar_tudo()
        projeto.livro.sumario = core_sumario.gerar_dos_titulos(projeto.livro, niveis)
        self._depois()
        j.log.info("Sumário gerado dos títulos %s: %d entrada(s).", list(niveis), len(projeto.livro.sumario))
        return projeto.livro.sumario

    def sumario_editar(self) -> list | None:
        """`Ctrl+T`: o editor de sumário; a lista devolvida vira o `Livro.sumario`."""
        j = self.j
        projeto = j._exigir_projeto()
        j._sincronizar_tudo()
        aba = j.aba_ativa()
        destino = ""
        if aba is not None and aba.tipo == "capitulo":
            destino = aba.arquivo
            if aba.modo == "texto" and aba.widget is not None:
                bloco_id = aba.widget.bloco_atual()
                if bloco_id and bloco_id in aba.widget.ordem_do_capitulo:
                    destino = f"{aba.arquivo}#{bloco_id}"
        novo = j.caixas.sumario(projeto.livro.sumario, projeto.livro, destino)
        if novo is None:
            return None
        projeto.livro.sumario = list(novo)
        self._depois()
        j.log.info("Sumário editado: %d entrada(s).", len(projeto.livro.sumario))
        return projeto.livro.sumario

    def sumario_gravar(self) -> str:
        """Livro → Sumário → Gravar: confere os destinos, refaz o `nav.xhtml` (a aba de leitura) e marca sujo."""
        j = self.j
        projeto = j._exigir_projeto()
        j._sincronizar_tudo()
        quebrados = core_sumario.destinos_quebrados(projeto.livro)
        for destino in quebrados:
            j.log.warning("sumário: destino inexistente: %s", destino)
        texto = core_sumario.escrever_nav(projeto.livro)
        aba = j.abas.por_arquivo(projeto.livro.nav)
        if aba is not None and aba.widget is not None:
            aba.widget.texto.configure(state="normal")
            aba.widget.carregar(texto)
            aba.widget.texto.configure(state="disabled")
        self._depois()
        j.status("Sumário gravado no nav.xhtml" + (f" ({len(quebrados)} destino(s) inexistente(s))" if quebrados
                                                  else "") + ".")
        return texto

    def sumario_como_pagina(self, arquivo: str | None = None) -> str:
        """Inserir → Sumário como página do livro: `Text/sumario.xhtml` com `epub:type="toc"` (AC-ED08-2)."""
        j = self.j
        projeto = j._exigir_projeto()
        livro = projeto.livro
        j._sincronizar_tudo()
        if not livro.sumario:
            livro.sumario = core_sumario.gerar_dos_titulos(livro)
        existente = next((c for c in livro.capitulos if c.semantica == "toc"), None)
        if arquivo is None:
            arquivo = existente.arquivo if existente is not None else livro_ops.nome_livre(
                livro, posixpath.join(livro_ops._pasta_de_texto(livro), "sumario.xhtml")
                if livro_ops._pasta_de_texto(livro) else "sumario.xhtml")
        cap = core_sumario.pagina_de_sumario(livro, arquivo)
        if existente is not None and existente.arquivo == arquivo:
            livro.capitulos[livro.capitulos.index(existente)] = cap
        else:
            posicao = 1 if livro.capitulos and livro.capitulos[0].semantica == "cover" else 0
            livro.capitulos.insert(posicao, cap)
        livro_ops.definir_semantica(livro, arquivo, "toc")
        self._depois(arquivo)
        j.abrir_capitulo(arquivo)
        j.log.info("Sumário como página: %s.", arquivo)
        return arquivo

    def semantica(self, tipo: str, href: str | None = None, ligar: bool | None = None) -> str:
        """Livro → Semântica do capítulo ▸: liga (ou desliga, se já era) o `epub:type` e o marco."""
        j = self.j
        projeto = j._exigir_projeto()
        href = href or self.alvo(so_capitulo=True)
        cap = projeto.livro.capitulo(href)
        assert cap is not None
        if ligar is None:
            ligar = cap.semantica != tipo
        j._sincronizar_tudo()
        resultado = livro_ops.definir_semantica(projeto.livro, href, tipo, ligar)
        aba = j.abas.por_arquivo(href)
        if aba is not None and aba.modo == "texto" and aba.widget is not None and aba.widget._capitulo is not None:
            aba.widget._capitulo.semantica = resultado
        self._depois(*([href] if aba is not None and aba.modo == "codigo" else []))
        j.status(f"{href}: semântica {resultado or 'nenhuma'}")
        return resultado

    def itens_de_semantica(self) -> list[tuple[str, Callable[[], Any] | None]]:
        """O submenu Livro → Semântica do capítulo ▸, com ✓ no que o capítulo alvo tem."""
        try:
            href = self.alvo(so_capitulo=True)
        except ValueError:
            return []
        cap = self.j.projeto.livro.capitulo(href)
        atual = cap.semantica if cap is not None else ""
        return [(("✓ " if tipo == atual else "") + rotulo, (lambda t=tipo: self.j.executar("semantica", t)))
                for tipo, rotulo in livro_ops.SEMANTICAS]

    def marcos(self, novos: Sequence[tuple[str, str]] | None = None) -> list[tuple[str, str]]:
        j = self.j
        projeto = j._exigir_projeto()
        livro = projeto.livro
        if novos is None:
            novos = j.caixas.marcos(livro.marcos, livro_ops.SEMANTICAS, [c.arquivo for c in livro.capitulos])
            if novos is None:
                return livro.marcos
        arquivos = {c.arquivo for c in livro.capitulos}
        for tipo, destino in novos:
            if destino.split("#")[0] not in arquivos:
                raise ValueError(f"o marco {tipo} aponta para um capítulo que não existe: {destino}")
        livro.marcos = [(str(t), str(d)) for t, d in novos]
        self._depois(sumario=False)
        j.log.info("Marcos: %s.", ", ".join(t for t, _d in livro.marcos) or "nenhum")
        return livro.marcos

    def vincular_folhas(self, folhas: Sequence[str] | None = None,
                        capitulos: Sequence[str] | str | None = None) -> int:
        """
        Livro → Vincular folhas de estilo…: as folhas marcadas passam a ser as do capítulo alvo
        (`capitulos=None`: o do navegador, ou todos se não há alvo; `"todos"`: todos).
        """
        j = self.j
        projeto = j._exigir_projeto()
        livro = projeto.livro
        css = [c for c, r in livro.recursos.items() if r.tipo_mime == epub.MIME_CSS]
        if not css:
            raise ValueError("o livro não tem folha de estilo (Livro → Nova folha de estilo)")
        if capitulos == "todos":
            capitulos = None
        elif capitulos is None:
            try:
                capitulos = [self.alvo(so_capitulo=True)]
            except ValueError:
                capitulos = None
        if folhas is None:
            cap = livro.capitulo(capitulos[0]) if capitulos else None
            marcadas = [k for k, c in enumerate(css) if cap is not None and c in cap.folhas]
            rotulo = (f"Folhas de {capitulos[0]}:" if capitulos else "Folhas de todos os capítulos:")
            indices = j.caixas.marcar_varios("Vincular folhas de estilo", rotulo, css, marcadas, "Vincular")
            if indices is None:
                return 0
            folhas = [css[k] for k in indices]
        j._sincronizar_tudo()
        mudados = livro_ops.vincular_folhas(livro, capitulos, list(folhas))
        self._depois(*(capitulos or [c.arquivo for c in livro.capitulos]), sumario=False)
        j.status(f"Folhas vinculadas em {mudados} capítulo(s).")
        return mudados

    def folhas_de_estilo(self, folhas: Sequence[str] | None = None) -> list[str]:
        """Formatar → Folhas de estilo do livro…: quais (e em que ordem) são as do livro; a primeira é a padrão."""
        j = self.j
        projeto = j._exigir_projeto()
        livro = projeto.livro
        css = [c for c, r in livro.recursos.items() if r.tipo_mime == epub.MIME_CSS]
        if not css:
            raise ValueError("o livro não tem folha de estilo (Livro → Nova folha de estilo)")
        if folhas is None:
            marcadas = [k for k, c in enumerate(css) if c in livro.folhas]
            indices = j.caixas.marcar_varios("Folhas de estilo do livro", "A primeira marcada é a folha padrão "
                                             "(a que o painel Estilos edita):", css, marcadas, "Definir")
            if indices is None:
                return livro.folhas
            folhas = [css[k] for k in indices]
        for folha in folhas:
            if folha not in livro.recursos:
                raise ValueError(f"folha de estilo inexistente: {folha}")
        livro.folhas = list(folhas)
        j._atualizar_painel_de_estilos()
        self._depois(sumario=False)
        return livro.folhas

    # -- arquivos -------------------------------------------------------------------

    def _importar_arquivo(self, caminho: str, pasta: str | None = None) -> str:
        j = self.j
        projeto = j._exigir_projeto()
        caminho = os.path.abspath(os.fspath(caminho))
        if not os.path.isfile(caminho):
            raise ValueError(f"o arquivo não existe: {caminho}")
        with open(caminho, "rb") as f:
            dados = f.read()
        href = livro_ops.adicionar_arquivo(projeto.livro, os.path.basename(caminho), dados, pasta=pasta)
        j._gravar_preferencia("diretorios", {**j._preferencia("diretorios", {}), "imagens": os.path.dirname(caminho)})
        j.log.info("Arquivo adicionado ao livro: %s (%d bytes).", href, len(dados))
        return href

    def adicionar_arquivo(self, caminho: str | None = None) -> str | None:
        """Livro → Adicionar arquivo…: XHTML vira capítulo, CSS vira folha, o resto vira recurso."""
        j = self.j
        j._exigir_projeto()
        if caminho is None:
            caminho = j.caixas.abrir_qualquer("Adicionar arquivo", j._preferencia("diretorios", {}).get("imagens", ""))
            if not caminho:
                return None
        href = self._importar_arquivo(caminho)
        self._depois()
        j.painel_navegador.selecionar(href)
        j.status(f"Adicionado: {href}")
        return href

    def adicionar_copia(self, href: str | None = None) -> str:
        j = self.j
        projeto = j._exigir_projeto()
        href = href or self.alvo()
        j._sincronizar_tudo()
        novo = livro_ops.adicionar_copia(projeto.livro, href)
        self._depois()
        j.painel_navegador.selecionar(novo)
        j.log.info("Cópia: %s → %s.", href, novo)
        return novo

    def novo_capitulo(self, titulo: str | None = None) -> str | None:
        j = self.j
        projeto = j._exigir_projeto()
        if titulo is None:
            titulo = j.caixas.pedir_texto("Novo capítulo", "Título:", "Capítulo novo")
            if titulo is None:
                return None
        depois_de = None
        try:
            depois_de = self.alvo(so_capitulo=True)
        except ValueError:
            pass
        j._sincronizar_tudo()
        arquivo = livro_ops.novo_capitulo(projeto.livro, depois_de, titulo.strip() or "Capítulo novo")
        self._depois()
        j.abrir_capitulo(arquivo)
        j.log.info("Capítulo novo: %s.", arquivo)
        return arquivo

    def nova_folha(self, nome: str | None = None) -> str | None:
        j = self.j
        projeto = j._exigir_projeto()
        if nome is None:
            nome = j.caixas.pedir_texto("Nova folha de estilo", "Nome do arquivo:", "estilo.css")
            if nome is None:
                return None
        nome = nome.strip()
        if not nome.lower().endswith(".css"):
            nome += ".css"
        livro = projeto.livro
        pasta = posixpath.dirname(livro.folhas[0]) if livro.folhas else ("Styles" if posixpath.dirname(livro.opf)
                                                                         else "")
        arquivo = posixpath.join(pasta, nome) if pasta and "/" not in nome else nome
        from core.editor import dialeto

        texto = dialeto.css_padrao() if not livro.folhas else ""
        href = livro_ops.nova_folha(livro, livro_ops.nome_livre(livro, arquivo), texto, padrao=not livro.folhas)
        j._atualizar_painel_de_estilos()
        self._depois(sumario=False)
        j.abrir_recurso(href)
        j.log.info("Folha nova: %s.", href)
        return href

    def renomear(self, novo: str | None = None, href: str | None = None) -> str | None:
        """Livro → Renomear…: o arquivo e tudo que apontava para ele (AC-ED08-1)."""
        j = self.j
        projeto = j._exigir_projeto()
        href = href or self.alvo()
        livro = projeto.livro
        if href in (livro.nav, livro.ncx, livro.opf):
            raise ValueError(f"{href} é regenerado ao salvar e não se renomeia")
        if novo is None:
            novo = j.caixas.pedir_texto("Renomear", "Nome novo (com a pasta):", href)
            if novo is None:
                return None
        novo = novo.strip().replace("\\", "/")
        if not novo:
            raise ValueError("o nome não pode ficar vazio")
        if "/" not in novo and "/" in href:
            novo = posixpath.join(posixpath.dirname(href), novo)
        j._sincronizar_tudo()
        aba = j.abas.por_arquivo(href)
        arquivo_ativo = j.aba_ativa().arquivo if j.aba_ativa() is not None else None
        try:
            n = livro_ops.renomear(livro, href, novo)
        except KeyError as erro:
            raise ValueError(str(erro)) from None
        if aba is not None:
            aba.arquivo = novo
            j.abas.rotular(aba)
        self._depois(*[a.arquivo for a in j.abas.abas if a.arquivo != novo])
        if aba is not None:
            j._recarregar_aba(aba)
        j.painel_navegador.selecionar(novo)
        if arquivo_ativo == href:
            j.abas.selecionar(aba) if aba is not None else None
        j.log.info("Renomeado: %s → %s (%d referência(s) reescrita(s)).", href, novo, n)
        j.status(f"Renomeado: {novo} ({n} referência(s) reescrita(s))")
        return novo

    def renomear_varios(self, padrao: str | None = None, capitulos: Sequence[str] | None = None) -> dict[str, str]:
        j = self.j
        projeto = j._exigir_projeto()
        if padrao is None:
            padrao = j.caixas.pedir_texto("Renomear vários", "Padrão com %d (ex.: cap-%03d):", "cap-%03d")
            if padrao is None:
                return {}
        j._sincronizar_tudo()
        abertas = {a.arquivo: a for a in j.abas.abas}
        mapa = livro_ops.renomear_varios(projeto.livro, padrao.strip(), capitulos)
        for antigo, novo in mapa.items():
            if antigo in abertas:
                abertas[antigo].arquivo = novo
                j.abas.rotular(abertas[antigo])
        self._depois(*[a.arquivo for a in j.abas.abas])
        j.log.info("Renomeados %d capítulo(s) com %r.", len(mapa), padrao)
        return mapa

    def excluir(self, href: str | None = None, confirmar: bool = True) -> list[str]:
        """Livro → Excluir: tira o arquivo e lista em Resultados quem apontava para ele."""
        j = self.j
        projeto = j._exigir_projeto()
        href = href or self.alvo()
        livro = projeto.livro
        if href in (livro.nav, livro.ncx, livro.opf):
            raise ValueError(f"{href} é regenerado ao salvar e não se exclui")
        if livro.capitulo(href) is not None and len(livro.capitulos) == 1:
            raise ValueError("o livro precisa de pelo menos um capítulo")
        if confirmar and not j.caixas.pergunta(f"Excluir {href} do livro?\n(Nada é gravado até você salvar.)",
                                                 cancelar=False):
            return []
        j._sincronizar_tudo()
        aba = j.abas.por_arquivo(href)
        if aba is not None:
            j.abas.fechar(aba)
        try:
            apontavam = livro_ops.excluir(livro, href)
        except KeyError as erro:
            raise ValueError(str(erro)) from None
        j.arquivos_marcados.discard(href)
        self._depois(*[a.arquivo for a in j.abas.abas])
        if apontavam:
            itens = []
            for quem in apontavam:
                arquivo, _, bloco = quem.partition("#")
                itens.append(Resultado(arquivo, f"bloco {bloco}" if bloco else "", f"apontava para {href}",
                                       {"bloco": bloco} if bloco else {}))
            j.resultados.definir(itens, f"Quem apontava para {href}: {len(apontavam)}")
            j.log.warning("%s excluído; %d referência(s) ficaram apontando para ele.", href, len(apontavam))
        else:
            j.log.info("%s excluído.", href)
        if not j.abas.abas and livro.capitulos:
            j.abrir_capitulo(livro.capitulos[0].arquivo)
        j.status(f"Excluído: {href}")
        return apontavam

    def mover(self, passo: int, href: str | None = None) -> int:
        j = self.j
        projeto = j._exigir_projeto()
        href = href or self.alvo(so_capitulo=True)
        capitulos = [c.arquivo for c in projeto.livro.capitulos]
        i = capitulos.index(href)
        alvo = i + passo
        if not 0 <= alvo < len(capitulos):
            j.status("Já é o " + ("último" if passo > 0 else "primeiro") + " capítulo.")
            return i
        livro_ops.mover(projeto.livro, href, alvo)
        self._depois()
        j.painel_navegador.selecionar(href)
        return alvo

    def reordenar_capitulos(self, ordem: Sequence[str]) -> list[str]:
        """O arrastar do navegador: a espinha na ordem nova."""
        j = self.j
        projeto = j._exigir_projeto()
        livro_ops.ordenar(projeto.livro, list(ordem))
        self._depois()
        return [c.arquivo for c in projeto.livro.capitulos]

    def ordenar_por_nome(self) -> list[str]:
        j = self.j
        projeto = j._exigir_projeto()
        ordem = sorted((c.arquivo for c in projeto.livro.capitulos), key=lambda h: posixpath.basename(h).lower())
        livro_ops.ordenar(projeto.livro, ordem)
        self._depois()
        j.status("Capítulos ordenados por nome.")
        return ordem

    # -- abrir com… ------------------------------------------------------------------

    def pasta_temporaria(self) -> str:
        if self._pasta_temporaria is None or not os.path.isdir(self._pasta_temporaria):
            self._pasta_temporaria = tempfile.mkdtemp(prefix="pbe-editor-")
        return self._pasta_temporaria

    def abrir_com(self, programa: str | None = None, href: str | None = None) -> str:
        """Livro → Abrir com…: exporta o arquivo, lança o programa e vigia o arquivo para trazê-lo de volta."""
        j = self.j
        projeto = j._exigir_projeto()
        href = href or self.alvo()
        livro = projeto.livro
        j._sincronizar_tudo()
        cap = livro.capitulo(href)
        if cap is not None:
            from core.editor import xhtml

            dados = (cap.texto_cru if cap.texto_cru is not None else xhtml.escrever(cap)).encode("utf-8")
        else:
            recurso = livro.recurso(href)
            if recurso is None:
                raise ValueError(f"{href} não está no livro")
            dados = (recurso.texto_cru.encode("utf-8") if recurso.texto_cru is not None
                     else epub.dados_de(livro, recurso))
        if programa is None:
            programa = j.caixas.pedir_texto("Abrir com", "Programa (vazio = o do sistema):",
                                            j._preferencia("abrir_com", "")) or ""
        if programa:
            j._gravar_preferencia("abrir_com", programa)
        pasta = os.path.join(self.pasta_temporaria(), posixpath.dirname(href).replace("/", os.sep))
        os.makedirs(pasta, exist_ok=True)
        caminho = os.path.join(pasta, posixpath.basename(href))
        with open(caminho, "wb") as f:
            f.write(dados)
        self.lancador(caminho, programa)
        self.vigiados[caminho] = (href, os.path.getmtime(caminho))
        self._agendar_vigia()
        j.log.info("Aberto com %s: %s → %s.", programa or "o programa do sistema", href, caminho)
        j.status(f"{href} aberto fora; ao salvar lá, volta para o livro.")
        return caminho

    def _agendar_vigia(self) -> None:
        if self._vigia_id is not None or not self.vigiados:
            return
        try:
            self._vigia_id = self.j.after(INTERVALO_DA_VIGIA_MS, self._vigiar)
        except Exception:      # noqa: BLE001 — janela fechada
            self._vigia_id = None

    def _vigiar(self) -> None:
        self._vigia_id = None
        self.verificar_vigiados()
        if self.vigiados and self.j.winfo_exists():
            self._agendar_vigia()

    def verificar_vigiados(self) -> list[str]:
        """Os arquivos abertos fora que mudaram no disco voltam para o livro; devolve os hrefs que voltaram."""
        j = self.j
        voltaram: list[str] = []
        if j.projeto is None:
            self.vigiados.clear()
            return voltaram
        for caminho, (href, mtime) in list(self.vigiados.items()):
            try:
                atual = os.path.getmtime(caminho)
            except OSError:
                del self.vigiados[caminho]
                continue
            if atual == mtime:
                continue
            with open(caminho, "rb") as f:
                dados = f.read()
            self.vigiados[caminho] = (href, atual)
            livro = j.projeto.livro
            cap = livro.capitulo(href)
            if cap is not None:
                cap.texto_cru = dados.decode("utf-8", errors="replace")
                cap.blocos, cap.notas = [], []
            else:
                recurso = livro.recurso(href)
                if recurso is None:
                    continue
                if recurso.texto_cru is not None or recurso.tipo_mime.startswith("text/"):
                    recurso.texto_cru = dados.decode("utf-8", errors="replace")
                else:
                    recurso.dados = dados
            voltaram.append(href)
            self._depois(href)
            j.log.info("%s voltou do programa externo (%d bytes).", href, len(dados))
        return voltaram

    # -- metadados ----------------------------------------------------------------------

    def metadados(self, valores: dict[str, str] | str | None = None, autor: str | None = None,
                  idioma: str | None = None) -> Any:
        """
        Livro → Metadados… (`F8`), completa: `refines`, `ids` e extras ficam como estão
        (AC-ED08-3). A forma curta da ED-02 (`título, autor, idioma`) continua valendo.
        """
        j = self.j
        projeto = j._exigir_projeto()
        livro = projeto.livro
        imagens = [c for c, r in livro.recursos.items() if r.tipo_mime.startswith("image/")]
        if isinstance(valores, str):
            atuais = metadados_ui.valores_de(livro.metadados)
            atuais["titulo"] = valores
            if autor is not None:
                atuais["autores"] = autor
            if idioma:
                atuais["idioma"] = idioma
            valores = atuais
        if valores is None:
            valores = j.caixas.metadados_completos(livro.metadados, imagens)
            if valores is None:
                return None
        metadados_ui.aplicar(livro.metadados, valores)
        if livro.metadados.capa and livro.metadados.capa not in livro.recursos:
            raise ValueError(f"a capa aponta para uma imagem que não está no livro: {livro.metadados.capa}")
        projeto.marcar_sujo()
        j._gravar_preferencia("idioma_ortografia", livro.metadados.idioma)
        j.log.info("Metadados: %s — %s (%s).", livro.metadados.titulo,
                   livro.metadados.autores[0].nome if livro.metadados.autores else "sem autor", livro.metadados.idioma)
        j.atualizar_navegador()
        j.atualizar()
        return livro.metadados

    # -- relatórios, validação, limpezas ------------------------------------------------

    def _ler_recurso(self, recurso: Recurso) -> bytes:
        return epub.dados_de(self.j.projeto.livro, recurso)

    def relatorio(self, nome: str) -> list:
        """Ferramentas → Relatórios ▸: as linhas vão a Resultados (ativar leva ao bloco ou ao arquivo)."""
        j = self.j
        projeto = j._exigir_projeto()
        j._sincronizar_tudo()
        linhas = relatorios.relatorio(nome, projeto.livro, self._ler_recurso, self.pasta_temporaria())
        itens = []
        for li in linhas:
            dados = dict(li.dados)
            dados["gravidade"] = li.gravidade
            prefixo = {"erro": "✖ ", "aviso": "⚠ "}.get(li.gravidade, "")
            itens.append(Resultado(li.arquivo, li.onde, prefixo + li.mensagem, dados))
        rotulo = relatorios.ROTULOS_DOS_RELATORIOS.get(nome, nome)
        erros = sum(1 for li in linhas if li.gravidade == "erro")
        avisos = sum(1 for li in linhas if li.gravidade == "aviso")
        j.resultados.definir(itens, f"Relatório — {rotulo}: {len(linhas)} linha(s), {erros} erro(s), {avisos} aviso(s)")
        j._focar_inferior(j.resultados, j.resultados.foco)
        j.status(f"{rotulo}: {len(linhas)} linha(s), {erros} erro(s), {avisos} aviso(s)")
        return linhas

    def validar_epub(self) -> Any:
        """`Alt+F9`: o livro como está agora, gravado numa cópia temporária, passa pelo `epubcheck`."""
        j = self.j
        projeto = j._exigir_projeto()
        j._validar_abas_de_codigo()
        j._sincronizar_tudo()
        caminho = os.path.join(self.pasta_temporaria(), "validar.epub")
        zip_antes = projeto.livro.zip_de_origem
        j.status("Validando com o epubcheck…")
        j.configure(cursor="watch")
        try:
            j.update_idletasks()
        except Exception:      # noqa: BLE001
            pass
        try:
            epub.escrever(projeto.livro, caminho, ncx=j._preferencia("ncx", None))
        finally:
            projeto.livro.zip_de_origem = zip_antes
        try:
            resultado = validacao.validar(caminho, projeto.livro.opf, comando=self.comando_do_epubcheck() or [],
                                          correr=self.correr_epubcheck)
        finally:
            j.configure(cursor="")
        itens = [Resultado("", "estrutura", f"✖ {p}", {}) for p in resultado.estrutura]
        for m in resultado.mensagens:
            if m.gravidade in ("USAGE", "INFO", "SUPPRESSED"):
                continue
            dados: dict[str, Any] = {"codigo": m.codigo, "gravidade": m.gravidade}
            if m.linha:
                dados.update(linha=m.linha, coluna=m.coluna or 1)
            prefixo = "✖ " if m.gravidade in ("FATAL", "ERROR") else "⚠ "
            itens.append(Resultado(m.arquivo, m.onde, f"{prefixo}{m.codigo}: {m.texto}", dados))
        if resultado.sem_java:
            itens.append(Resultado("", "epubcheck", resultado.saida, {}))
            j.log.warning("%s", resultado.saida)
        j.validacao.definir(itens, resultado.resumo() + (" — válido" if resultado.valido else ""))
        j._focar_inferior(j.validacao, j.validacao.foco)
        j.status(resultado.resumo() + (" — válido" if resultado.valido else ""))
        j.log.info("Validação: %s (%d mensagem(ns)).", resultado.resumo(), len(resultado.mensagens))
        return resultado

    def comando_do_epubcheck(self) -> list[str] | None:
        return validacao.comando_do_epubcheck()

    def apagar_recursos(self, hrefs: Sequence[str] | None = None) -> list[str]:
        """Ferramentas → Apagar recursos não usados…: só o que nada referencia, escolhido na lista (AC-ED08-6)."""
        j = self.j
        projeto = j._exigir_projeto()
        j._sincronizar_tudo()
        nao_usados = relatorios.recursos_nao_usados(projeto.livro, self._ler_recurso)
        if not nao_usados:
            j.status("Nenhum recurso sem uso.")
            j.caixas.informar("Todos os recursos do livro são usados por alguma coisa.", "Apagar recursos não usados")
            return []
        if hrefs is None:
            indices = j.caixas.marcar_varios("Apagar recursos não usados", "Nada aponta para estes arquivos. "
                                             "Apagar os marcados:", nao_usados, range(len(nao_usados)), "Apagar")
            if indices is None:
                return []
            hrefs = [nao_usados[k] for k in indices]
        apagados = []
        for href in hrefs:
            if href not in nao_usados:
                raise ValueError(f"{href} é usado (ou não existe): não se apaga por aqui")
            aba = j.abas.por_arquivo(href)
            if aba is not None:
                j.abas.fechar(aba)
            livro_ops.excluir(projeto.livro, href)
            apagados.append(href)
        self._depois(sumario=False)
        j.log.info("Recursos apagados: %s.", ", ".join(apagados) or "nenhum")
        j.status(f"{len(apagados)} recurso(s) apagado(s).")
        return apagados

    def apagar_classes(self, confirmar: bool = True) -> dict[str, list[str]]:
        """Ferramentas → Apagar classes CSS não usadas…: por folha, só as regras de classes sem uso (AC-ED08-6)."""
        j = self.j
        projeto = j._exigir_projeto()
        livro = projeto.livro
        j._sincronizar_tudo()
        usadas = set(relatorios.classes_usadas(livro))
        propostas: dict[str, tuple[str, list[str]]] = {}
        for href, recurso in livro.recursos.items():
            if recurso.tipo_mime != epub.MIME_CSS:
                continue
            texto = j._texto_do_recurso(recurso)
            novo, apagadas = relatorios.apagar_classes_nao_usadas(texto, usadas)
            if apagadas:
                propostas[href] = (novo, apagadas)
        if not propostas:
            j.status("Nenhuma classe sem uso nas folhas.")
            j.caixas.informar("Toda classe definida nas folhas é usada em algum capítulo.",
                              "Apagar classes CSS não usadas")
            return {}
        if confirmar:
            linhas = [f"{href}: {', '.join(apagadas)}" for href, (_n, apagadas) in propostas.items()]
            if not j.caixas.pergunta("Apagar as regras destas classes, que nenhum capítulo usa?\n\n"
                                     + "\n".join(linhas), cancelar=False):
                return {}
        resultado: dict[str, list[str]] = {}
        for href, (novo, apagadas) in propostas.items():
            recurso = livro.recursos[href]
            recurso.texto_cru = novo
            if livro.folhas and href == livro.folhas[0]:
                j._gravar_folha_padrao(novo)
            resultado[href] = apagadas
        self._depois(*propostas, sumario=False)
        j.log.info("Classes apagadas: %s.", "; ".join(f"{h}: {', '.join(c)}" for h, c in resultado.items()))
        j.status(f"{sum(len(c) for c in resultado.values())} classe(s) apagada(s) em {len(resultado)} folha(s).")
        return resultado

    # -- prévia -------------------------------------------------------------------------

    def previa(self, ligar: bool | None = None) -> Any:
        """`F12`: a prévia ao lado do código da aba ativa (liga/desliga)."""
        from ui.editor.previa import Previa

        j = self.j
        aba = j.aba_ativa()
        editor = j._codigo() if aba is not None and aba.modo == "codigo" else None
        if aba is None or editor is None:
            raise ValueError("a prévia é do modo código (F11)")
        atual = aba.dados.get("previa")
        if ligar is None:
            ligar = atual is None
        if not ligar:
            if atual is not None:
                atual.destroy()
                aba.dados.pop("previa", None)
                editor.pack_forget()
                editor.pack(fill="both", expand=True)
            j.status("Prévia fechada.")
            return None
        if atual is not None:
            atual.atualizar(editor.texto_todo(), aba.arquivo)
            return atual
        projeto = j._exigir_projeto()
        cap = projeto.livro.capitulo(aba.arquivo)
        folhas = j._folhas_de(cap) if cap is not None else ()
        previa = Previa(aba.frame, atraso_ms=int(j._preferencia("previa_ms", 300)),
                        ao_clicar=lambda linha: (editor.ir_para(int(linha)), editor.foco()),
                        estilo_de_tela=j._estilo_de_tela(), folhas=folhas, recursos=j._dados_do_recurso)
        # Os dois lado a lado, com a largura dividida: dois `side="left"` expansíveis repartem o extra.
        editor.pack_forget()
        editor.pack(side="left", fill="both", expand=True)
        previa.pack(side="left", fill="both", expand=True)
        aba.dados["previa"] = previa
        editor.texto.bind("<<Mudou>>", lambda e: self._previa_mudou(aba), add="+")
        editor.texto.bind("<<CursorMoveu>>", lambda e: self._previa_cursor(aba), add="+")
        previa.atualizar(editor.texto_todo(), aba.arquivo)
        j.status("Prévia aberta (F12 fecha).")
        return previa

    def _previa_mudou(self, aba: Any) -> None:
        previa = aba.dados.get("previa")
        if previa is not None and aba.widget is not None:
            previa.atualizar(aba.widget.texto_todo(), aba.arquivo)

    def _previa_cursor(self, aba: Any) -> None:
        previa = aba.dados.get("previa")
        if previa is not None and aba.widget is not None and previa.capitulo is not None:
            previa.ir_ao_bloco(aba.widget.posicao[0])

    def fechar(self) -> None:
        if self._vigia_id is not None:
            try:
                self.j.after_cancel(self._vigia_id)
            except Exception:      # noqa: BLE001
                pass
            self._vigia_id = None
        self.vigiados.clear()


def agora() -> float:
    return time.time()


__all__ = ["OperacoesDoLivro", "RELATORIOS", "INTERVALO_DA_VIGIA_MS"]
