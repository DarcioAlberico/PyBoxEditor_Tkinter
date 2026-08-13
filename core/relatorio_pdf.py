"""
Relatório das substituições de glifo num PDF (F2.3, SPEC §4.4 / RF-06 e RNF-04).

Existe porque `substitute_chess_glyphs` reescreve o documento: apaga o texto
original com um retângulo branco e desenha outro por cima. Não há como desfazer
olhando o resultado, e até aqui o usuário só recebia dois números no fim
("páginas processadas, substituições realizadas"). Se o mapeamento estivesse
errado, ou se a fonte tivesse encolhido a ponto de ficar ilegível, ele
descobriria abrindo o PDF já convertido.

Daí as duas peças desta fase serem uma só na prática: o **dry-run** produz
exatamente o mesmo relatório da execução de verdade, sem tocar no arquivo. É a
mesma travessia do documento, os mesmos avisos, a mesma medição de encolhimento —
só não escreve. Conferir antes é comparar dois relatórios, não adivinhar.

Os avisos que a SPEC exige estão em `AVISOS`. Todos são condições em que a
substituição *acontece* mas o resultado merece um olho — nenhum deles interrompe
a conversão, porque interromper um livro inteiro por causa de um span seria pior.
"""

import csv
import json
import os
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple


# Abaixo disto a "confiança" do mapeamento é baixa: sobrou caractere sem entrada
# no perfil, e ele foi copiado como veio.
LIMIAR_CONFIANCA = 0.80

# Encolher a fonte para caber na largura original é normal — os símbolos Unicode
# são mais largos que os glifos da fonte de xadrez. Abaixo de 80% do corpo
# original já é perda de legibilidade, e a SPEC pede aviso.
LIMIAR_ENCOLHIMENTO = 0.80

AVISOS = {
    "fonte_sem_glifo": "a fonte de saída não desenha um dos símbolos",
    "fonte_reduzida": f"corpo reduzido além de {int(LIMIAR_ENCOLHIMENTO * 100)}%",
    "confianca_baixa": f"confiança abaixo de {LIMIAR_CONFIANCA:.2f}",
    "diagrama_ignorado": "span ignorado pela heurística de diagrama",
}


@dataclass
class Substituicao:
    """Uma substituição — feita, ou que seria feita em dry-run."""
    pagina: int
    bbox: Tuple[float, float, float, float]
    fonte_original: str
    texto_original: str
    texto_substituto: str
    confianca: float = 1.0
    corpo_original: float = 0.0
    corpo_final: float = 0.0
    aplicada: bool = True
    # Qual perfil de mapeamento decidiu esta substituição (F2.4). Vazio = o
    # padrão embutido. Sem isto, dois livros convertidos com perfis diferentes
    # produzem relatórios indistinguíveis.
    perfil: str = ""
    avisos: List[str] = field(default_factory=list)

    @property
    def encolhimento(self) -> float:
        """corpo_final / corpo_original. 1,0 = não encolheu."""
        if self.corpo_original <= 0:
            return 1.0
        return self.corpo_final / self.corpo_original


@dataclass
class RelatorioSubstituicao:
    """O que aconteceu (ou aconteceria) numa conversão inteira."""
    arquivo_entrada: str = ""
    arquivo_saida: str = ""
    dry_run: bool = False
    total_paginas: int = 0
    substituicoes: List[Substituicao] = field(default_factory=list)
    # blocos que a heurística de diagrama pulou: (página, quantos spans)
    diagramas_ignorados: List[Tuple[int, int]] = field(default_factory=list)
    fonte_saida: str = ""
    # Toda fonte que apareceu no documento, e quais delas `is_chess_font`
    # reconheceu. Sem os dois, "0 substituições" diz a mesma coisa em três casos
    # que pedem providências opostas: o livro não tem notação em fonte de
    # xadrez; tem, mas o nome da fonte veio em subset (`Fd350139`) e a detecção
    # por palavra-chave não teve em que casar; ou o PDF é digitalizado e não tem
    # camada de texto nenhuma. Medido nos três livros de `PDF/`: 39, 28 e 41
    # fontes, **nenhuma** reconhecida, e o resumo dizia "nenhum aviso".
    fontes_vistas: List[str] = field(default_factory=list)
    fontes_de_xadrez: List[str] = field(default_factory=list)

    @property
    def total_substituicoes(self) -> int:
        return len(self.substituicoes)

    @property
    def total_aplicadas(self) -> int:
        return sum(1 for s in self.substituicoes if s.aplicada)

    def com_aviso(self, chave: Optional[str] = None) -> List[Substituicao]:
        if chave is None:
            return [s for s in self.substituicoes if s.avisos]
        return [s for s in self.substituicoes if chave in s.avisos]

    def contagem_de_avisos(self) -> Dict[str, int]:
        conta = {k: 0 for k in AVISOS}
        for s in self.substituicoes:
            for a in s.avisos:
                conta[a] = conta.get(a, 0) + 1
        return conta

    def spans_de_diagrama_ignorados(self) -> int:
        return sum(n for _, n in self.diagramas_ignorados)

    @property
    def sem_camada_de_texto(self) -> bool:
        """O documento não tem texto extraível: não há span nenhum a converter."""
        return not self.fontes_vistas

    @property
    def nenhuma_fonte_de_xadrez(self) -> bool:
        """Há texto no documento, e nenhuma fonte dele foi reconhecida."""
        return bool(self.fontes_vistas) and not self.fontes_de_xadrez

    def amostra_de_fontes(self, quantas: int = 3) -> str:
        nomes = sorted(self.fontes_vistas)[:quantas]
        return ", ".join(nomes) + ("..." if len(self.fontes_vistas) > quantas else "")

    def alerta(self) -> str:
        """
        A frase que explica um resultado vazio, ou "" quando não há o que explicar.

        Existe porque zero substituições e conversão bem-sucedida saíam com a
        mesma cara. Fica separada do `resumo()` para a UI poder decidir entre
        aviso e informação a partir de um teste só.
        """
        if self.total_substituicoes:
            return ""
        if self.sem_camada_de_texto:
            return ("ATENÇÃO: o documento não tem camada de texto — não há span "
                    "algum a converter por este caminho")
        if self.nenhuma_fonte_de_xadrez:
            return (f"ATENÇÃO: nenhuma fonte de xadrez reconhecida — nada foi "
                    f"substituído ({len(self.fontes_vistas)} fonte(s) no "
                    f"documento: {self.amostra_de_fontes()})")
        return ""

    def resumo(self) -> str:
        modo = "SIMULAÇÃO (nada foi gravado)" if self.dry_run else "conversão"
        linhas = [
            f"{modo}: {self.total_paginas} página(s), "
            f"{self.total_substituicoes} substituição(ões)",
        ]
        alerta = self.alerta()
        if alerta:
            linhas.append(alerta)
        if self.diagramas_ignorados:
            linhas.append(
                f"{len(self.diagramas_ignorados)} bloco(s) de diagrama ignorados "
                f"({self.spans_de_diagrama_ignorados()} spans)")
        conta = self.contagem_de_avisos()
        for chave, n in conta.items():
            if n:
                linhas.append(f"{n} com aviso «{AVISOS[chave]}»")
        # "nenhum aviso" só faz sentido tendo havido substituição: sem nenhuma,
        # ele soava como aprovação de um trabalho que não aconteceu.
        if self.substituicoes and not any(conta.values()):
            linhas.append("nenhum aviso")
        return "; ".join(linhas)


# Ordem das colunas do CSV. Explícita, e não `asdict().keys()`: o CSV é para
# abrir numa planilha e comparar dois relatórios lado a lado, então a ordem não
# pode mudar quando alguém acrescentar um campo ao dataclass.
COLUNAS_CSV = [
    "pagina", "bbox_x0", "bbox_y0", "bbox_x1", "bbox_y1",
    "fonte_original", "texto_original", "texto_substituto",
    "confianca", "corpo_original", "corpo_final", "encolhimento",
    "aplicada", "perfil", "avisos",
]


def _linha_csv(s: Substituicao) -> dict:
    x0, y0, x1, y1 = s.bbox
    return {
        "pagina": s.pagina,
        "bbox_x0": round(x0, 2), "bbox_y0": round(y0, 2),
        "bbox_x1": round(x1, 2), "bbox_y1": round(y1, 2),
        "fonte_original": s.fonte_original,
        "texto_original": s.texto_original,
        "texto_substituto": s.texto_substituto,
        "confianca": round(s.confianca, 4),
        "corpo_original": round(s.corpo_original, 2),
        "corpo_final": round(s.corpo_final, 2),
        "encolhimento": round(s.encolhimento, 4),
        "aplicada": int(s.aplicada),
        "perfil": s.perfil,
        "avisos": "|".join(s.avisos),
    }


def caminhos_do_relatorio(saida_pdf: str, dry_run: bool = False) -> Tuple[str, str]:
    """(caminho .json, caminho .csv) ao lado do PDF de saída."""
    base = os.path.splitext(saida_pdf)[0]
    sufixo = "_simulacao" if dry_run else "_relatorio"
    return base + sufixo + ".json", base + sufixo + ".csv"


def gravar_json(caminho: str, rel: RelatorioSubstituicao) -> str:
    dados = {
        "arquivo_entrada": rel.arquivo_entrada,
        "arquivo_saida": rel.arquivo_saida,
        "dry_run": rel.dry_run,
        "fonte_saida": rel.fonte_saida,
        "total_paginas": rel.total_paginas,
        "total_substituicoes": rel.total_substituicoes,
        "total_aplicadas": rel.total_aplicadas,
        "alerta": rel.alerta(),
        # A lista inteira, e não só a contagem: quando nada casa, os nomes são a
        # única pista de por quê — `Fd350139` diz "fonte em subset" a quem sabe
        # ler, e é o que permite escrever `font_patterns` para este livro.
        "fontes_vistas": sorted(rel.fontes_vistas),
        "fontes_de_xadrez": sorted(rel.fontes_de_xadrez),
        "avisos": rel.contagem_de_avisos(),
        "legenda_dos_avisos": AVISOS,
        "diagramas_ignorados": [{"pagina": p, "spans": n}
                                for p, n in rel.diagramas_ignorados],
        "substituicoes": [asdict(s) for s in rel.substituicoes],
    }
    pasta = os.path.dirname(os.path.abspath(caminho))
    if pasta:
        os.makedirs(pasta, exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)
    return caminho


def gravar_csv(caminho: str, rel: RelatorioSubstituicao) -> str:
    pasta = os.path.dirname(os.path.abspath(caminho))
    if pasta:
        os.makedirs(pasta, exist_ok=True)
    # utf-8-sig: o Excel no Windows abre UTF-8 sem BOM como cp1252 e transforma
    # os símbolos de peça em lixo. O BOM é o que faz ele acertar.
    with open(caminho, "w", encoding="utf-8-sig", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=COLUNAS_CSV)
        escritor.writeheader()
        for s in rel.substituicoes:
            escritor.writerow(_linha_csv(s))
    return caminho


def gravar(saida_pdf: str, rel: RelatorioSubstituicao) -> Tuple[str, str]:
    """Grava os dois formatos ao lado do PDF de saída. Devolve os caminhos."""
    cj, cc = caminhos_do_relatorio(saida_pdf, rel.dry_run)
    return gravar_json(cj, rel), gravar_csv(cc, rel)
