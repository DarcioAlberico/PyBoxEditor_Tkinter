"""
Capítulos aleatórios do dialeto, para os testes de propriedade do editor (ED-00).

Não é um teste: é o material dos testes de ida e volta (`tests/test_editor_xhtml.py`,
`tests/test_editor_texto_rico.py`). Gera só o que o dialeto representa **sem perda**
— é o que R2 promete —; o que sai do dialeto (ilhas, entidades, comentários) é
montado à mão nos testes de R3, porque ali o que se mede é outro contrato.

A semente é fixa por padrão: dois `pytest` seguidos veem os mesmos capítulos, e um
caso que falha se reproduz com `capitulo(semente)`.
"""

from __future__ import annotations

import random
from typing import Sequence

from core.editor import modelo as m

FENS = (
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
    "r1bqk2r/pp2bppp/2n1pn2/3p4/3P4/2N1PN2/PP2BPPP/R1BQK2R w - - 0 1",
    "8/8/4k3/8/8/4K3/8/8 w - - 0 1",
    "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 2 3",
)
PALAVRAS = ("xadrez", "peão", "torre", "Kasparov", "abertura", "final", "♕", "⩲", "±", "e4",
            "Nimzowitsch", "1.e4", "23…♖xe4", "—", "«aspas»", "ação", "gambito", "&", "<x>")
FAMILIAS = ("", "", "", "simbolos", "Georgia", "SkakNew-Diagram")
CORES = ("", "", "#c00000", "#004488")
CLASSES = ("", "", "", "x1", "destaque-y")
ESTILOS = ("corpo", "corpo", "corpo", "primeira", "notacao", "comentario", "legenda", "destaque",
           "epigrafe", "assinatura", "cabecalho-diagrama")


class Gerador:
    def __init__(self, semente: int = 7):
        self.r = random.Random(semente)
        self.ids_de_nota: list[str] = []
        self.paginas_usadas: set[int] = set()

    # -- trechos ----------------------------------------------------------

    def texto(self, minimo: int = 1, maximo: int = 5) -> str:
        return " ".join(self.r.choice(PALAVRAS) for _ in range(self.r.randint(minimo, maximo)))

    def trecho(self, *, primeiro: bool = False) -> m.Trecho:
        r = self.r
        t = m.Trecho(texto=self.texto())
        for atributo in ("negrito", "italico", "sublinhado", "tachado", "versalete", "codigo"):
            if r.random() < 0.15:
                setattr(t, atributo, True)
        if r.random() < 0.1:
            t.posicao = r.choice(("sobre", "sub"))
        t.familia = r.choice(FAMILIAS)
        if r.random() < 0.1:
            t.corpo_pt = r.choice((9.0, 10.5, 12.0, 14.0))
        t.cor = r.choice(CORES)
        if r.random() < 0.08:
            t.fundo = "#ffff00"
        t.classe = r.choice(CLASSES)
        if r.random() < 0.08:
            t.lang = r.choice(("ru", "de"))
        if r.random() < 0.08:
            t.titulo = "dica"
        if r.random() < 0.15:
            t.link = r.choice(("https://exemplo.org/x?a=1&b=2", "Text/cap-0002.xhtml#sec-3", "#sec-3"))
            if t.link.startswith(("Text/", "#")) and r.random() < 0.5:
                t.ref = r.choice(("diagrama", "figura", "tabela", "titulo"))
                t.texto = "Diagrama 3"
        papel = r.choice(("", "", "", "lance", "nag", "figurina", "comentario", "jogador", "abertura"))
        t.papel = papel
        if papel == "nag":
            t.nag = r.choice((1, 14, 140))
        if papel in ("jogador", "abertura"):
            t.chave = "Wely, Loek van" if papel == "jogador" else "C42"
        if not primeiro and r.random() < 0.1:
            t.quebra_antes = True
        return t

    def trechos(self, minimo: int = 1, maximo: int = 5) -> list[m.Trecho]:
        saida = [self.trecho(primeiro=i == 0) for i in range(self.r.randint(minimo, maximo))]
        if self.ids_de_nota and self.r.random() < 0.25:
            saida.append(m.Trecho(nota=self.r.choice(self.ids_de_nota)))
            saida.append(m.Trecho(texto="."))
        if self.r.random() < 0.08:
            pagina = self._pagina_nova()
            if pagina is not None:
                saida.append(m.Trecho(texto=self.texto(), pagina=pagina))
        return m.trechos_normalizados(saida)

    def _pagina_nova(self) -> int | None:
        for _ in range(5):
            pagina = self.r.randint(1, 400)
            if pagina not in self.paginas_usadas:
                self.paginas_usadas.add(pagina)
                return pagina
        return None

    # -- blocos -----------------------------------------------------------

    def paragrafo(self, estilo: str | None = None) -> m.Paragrafo:
        r = self.r
        p = m.Paragrafo(trechos=self.trechos(), estilo=estilo or r.choice(ESTILOS))
        if r.random() < 0.2:
            p.alinhamento = r.choice(("esquerda", "centro", "direita", "justificado"))
        for campo in ("recuo_primeira_em", "recuo_esquerda_em", "recuo_direita_em", "antes_em", "depois_em"):
            if r.random() < 0.08:
                setattr(p, campo, r.choice((0.0, 0.5, 1.2, 2.0)))
        if r.random() < 0.08:
            p.entrelinha = r.choice((1.0, 1.15, 1.5, 2.0))
        if r.random() < 0.05:
            p.manter_com_proximo = True
        if r.random() < 0.05:
            p.manter_linhas = True
        p.classe = r.choice(CLASSES)
        self._extras(p)
        if r.random() < 0.1:
            p.id = f"par-{r.randint(1, 999)}"
            p.id_persistente = True
        return p

    def _extras(self, bloco: m.Bloco) -> None:
        r = self.r
        if r.random() < 0.06:
            bloco.extras["epub:type"] = r.choice(("chapter", "bridgehead", "epigraph"))
        if r.random() < 0.04:
            bloco.extras["role"] = "doc-epigraph"
        if r.random() < 0.04:
            bloco.extras["lang"] = "de"
        if r.random() < 0.04:
            bloco.extras["title"] = "dica"
        if r.random() < 0.02:
            bloco.extras["dir"] = "rtl"

    def titulo(self) -> m.Titulo:
        t = m.Titulo(trechos=self.trechos(1, 3), nivel=self.r.randint(1, 6))
        if self.r.random() < 0.5:
            t.id = f"sec-{self.r.randint(1, 999)}"
        self._extras(t)
        return t

    def lista(self, profundidade: int = 0) -> m.Lista:
        r = self.r
        itens = []
        for _ in range(r.randint(1, 4)):
            paragrafos = [m.Paragrafo(trechos=self.trechos(1, 3))]
            if r.random() < 0.2:
                paragrafos.append(self.paragrafo("corpo"))
            filhos = self.lista(profundidade + 1) if profundidade < 1 and r.random() < 0.3 else None
            itens.append(m.ItemDeLista(paragrafos=paragrafos, filhos=filhos))
        lista = m.Lista(ordenada=r.random() < 0.5, itens=itens)
        if lista.ordenada and r.random() < 0.3:
            lista.inicio = r.randint(2, 9)
        if r.random() < 0.3:
            lista.marcador = r.choice(("disco", "circulo", "quadrado", "decimal", "alfa", "romano"))
        return lista

    def tabela(self) -> m.Tabela:
        r = self.r
        colunas = r.randint(1, 4)
        filas = []
        for _ in range(r.randint(1, 4)):
            fila = []
            for _ in range(colunas):
                blocos = [m.Paragrafo(trechos=self.trechos(1, 2))]
                if r.random() < 0.1:
                    blocos.append(self.paragrafo("corpo"))
                if r.random() < 0.05:
                    blocos = []
                fila.append(m.Celula(blocos=blocos, alinhamento=r.choice(("", "", "direita", "centro"))))
            filas.append(fila)
        tabela = m.Tabela(filas=filas, primeira_fila_cabecalho=r.random() < 0.4)
        if r.random() < 0.4:
            tabela.legenda = self.trechos(1, 3)
        if r.random() < 0.3:
            tabela.numero = r.randint(1, 30)
        if r.random() < 0.3:
            tabela.largura_pct = r.choice((50, 80, 100))
        return tabela

    def figura(self) -> m.Figura:
        r = self.r
        f = m.Figura(recurso=f"Images/fig-{r.randint(1, 99):04d}.png", alt=self.texto(1, 3))
        if r.random() < 0.5:
            f.legenda = self.trechos(1, 3)
        if r.random() < 0.3:
            f.numero = r.randint(1, 30)
        if r.random() < 0.4:
            f.largura_pt = r.choice((120.0, 200.5, 300.0))
        f.alinhamento = r.choice(("centro", "centro", "esq", "dir"))
        return f

    def diagrama(self) -> m.Diagrama:
        r = self.r
        d = m.Diagrama(fen=r.choice(FENS), lado=r.choice(("", "w", "b")),
                       orientacao=r.choice(("branca", "preta")), coordenadas=r.random() < 0.5,
                       lado_indicador=r.choice(("", "marca", "legenda")),
                       fonte=r.choice(("SkakNew-Diagram", "ChessMerida-Diagram")),
                       moldura=r.choice(("sem", "simples", "dupla")), cantos=r.choice(("reto", "arredondado")),
                       corpo_pt=r.choice((12.0, 16.0, 18.5)), modo=r.choice(("png", "fonte")))
        if r.random() < 0.3:
            d.marcas = r.sample(["e4", "d5", "f7", "g1"], r.randint(1, 2))
        if r.random() < 0.3:
            d.setas = [("e2", "e4")]
        if r.random() < 0.4:
            d.numero = r.randint(1, 50)
        if r.random() < 0.5:
            d.legenda = self.trechos(1, 3)
        if r.random() < 0.3:
            d.alt = "Posição após 23…♖xe4"
        if r.random() < 0.2:
            d.recorte = "Images/recorte-0003.png"
        if r.random() < 0.2:
            d.estado, d.aviso = "revisar", "orientação não registrada"
        return d

    def citacao(self) -> m.Citacao:
        return m.Citacao(blocos=[m.Paragrafo(trechos=self.trechos(1, 3), estilo="citacao")
                                 for _ in range(self.r.randint(1, 3))])

    def nota(self) -> m.Nota:
        nota = m.Nota(tipo=self.r.choice(("rodape", "fim")),
                      blocos=[m.Paragrafo(trechos=self.trechos(1, 3), estilo="nota")
                              for _ in range(self.r.randint(1, 2))])
        self.ids_de_nota.append(nota.id)
        return nota

    def bloco(self) -> m.Bloco:
        r = self.r
        sorteio = r.random()
        if sorteio < 0.45:
            return self.paragrafo()
        if sorteio < 0.6:
            return self.titulo()
        if sorteio < 0.68:
            return self.lista()
        if sorteio < 0.75:
            return self.tabela()
        if sorteio < 0.8:
            return self.figura()
        if sorteio < 0.9:
            return self.diagrama()
        if sorteio < 0.94:
            return self.citacao()
        if sorteio < 0.97:
            pagina = self._pagina_nova()
            return m.MarcaDePagina(pagina=pagina) if pagina is not None else m.Separador()
        if sorteio < 0.985:
            return m.QuebraDePagina()
        return m.Separador()

    # -- capítulo ---------------------------------------------------------

    def capitulo(self, n_blocos: int | None = None, arquivo: str = "Text/cap-0001.xhtml") -> m.Capitulo:
        r = self.r
        self.ids_de_nota = []
        self.paginas_usadas = set()
        cap = m.Capitulo(arquivo=arquivo, titulo=self.texto(1, 3) if r.random() < 0.7 else "")
        # As notas nascem antes dos blocos, para os trechos poderem apontá-las.
        for _ in range(r.randint(0, 2)):
            cap.notas.append(self.nota())
        cap.blocos = [self.bloco() for _ in range(n_blocos or r.randint(1, 12))]
        cap.folhas = ["Styles/estilo.css"] if r.random() < 0.8 else []
        cap.idioma = r.choice(("", "en", "pt"))
        cap.semantica = r.choice(("", "bodymatter", "chapter"))
        if r.random() < 0.3:
            cap.cabeca_extra = '<meta name="viewport" content="width=device-width"/>'
        cap.notas = [n for n in cap.notas if self._referenciada(cap, n.id)] + \
                    [n for n in cap.notas if not self._referenciada(cap, n.id)]
        cap.normalizar_notas()
        return cap

    @staticmethod
    def _referenciada(cap: m.Capitulo, nota_id: str) -> bool:
        return any(t.nota == nota_id for t in m.trechos_do_capitulo(cap))


def capitulo(semente: int, n_blocos: int | None = None) -> m.Capitulo:
    return Gerador(semente).capitulo(n_blocos)


def capitulos(quantos: int, semente_inicial: int = 1) -> Sequence[m.Capitulo]:
    return [capitulo(semente_inicial + i) for i in range(quantos)]
