"""O portão do retreino: o peso novo só fica no lugar do anterior se não ler pior (PD-23).

O treino da rede de glifos grava o peso por cima do `custom_model.pth`. Até a
PD-23 era só isso — e o retreino de 2026-11-09 entrou em produção com 99,7% de
validação no split e, no corpus de referência, a notação com o dobro de erro
(CER 0,97% → 1,99%, `h` lido `b`, as reticências do lance das pretas perdidas).
O peso anterior sobreviveu por acaso, numa cópia esquecida num worktree.

Daqui saem as duas coisas que faltavam:

- **o par anterior guardado** (`guardar_anterior`) antes de o treino começar, com
  data no nome, ao lado dos backups que o usuário já faz à mão;
- **a medida dos dois pesos no mesmo código** (`avaliar`), pela rodada do corpus
  (`core/rodada.py`), e a decisão com a régua do portão da rodada: uma página que
  piora mais que a tolerância, ou o total, e o peso novo é recusado — vai para
  `custom_model_<data>_recusado.pth` e o anterior volta ao lugar.

Medir contra a rodada gravada, e não rodar o anterior de novo, mediria o código
junto com o peso: o leitor muda entre um treino e outro. Rodar os dois custa uns
dois minutos, contra as horas do treino.

Sem corpus — o manifesto sem os PDFs, que não são versionados, ou alguma página
que não se mediu — o peso novo fica, como sempre ficou, e o veredito diz que não
houve medida. Não há régua para recusar, e recusar sem régua tiraria o treino de
quem não tem os livros.
"""

from __future__ import annotations

import datetime
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from core.log import logger

log = logger(__name__)

#: A mesma tolerância da rodada do corpus (`--tolerancia`): 0,1 ponto de CER.
TOLERANCIA = 0.001

PROMOVIDO = "promovido"
RECUSADO = "recusado"
SEM_MEDIDA = "sem_medida"


@dataclass
class Veredito:
    """O que o portão decidiu, e com que números."""

    situacao: str
    motivo: str = ""
    anterior: Optional[Path] = None      # o par anterior guardado (o `.pth`)
    recusado: Optional[Path] = None      # onde o peso recusado ficou (o `.pth`)
    cer_anterior: Optional[dict] = None  # totais da rodada: prose/notation/total
    cer_novo: Optional[dict] = None
    pioras: list[str] = field(default_factory=list)

    def mensagem(self) -> str:
        """Em frase, para o log do treino e para a janela."""
        linhas = []
        if self.situacao == RECUSADO:
            linhas.append("O modelo novo foi RECUSADO: ele lê o corpus de referência "
                          "pior que o anterior, que voltou a ser o de produção.")
        elif self.situacao == PROMOVIDO:
            linhas.append("O modelo novo passou no corpus de referência e é o de produção.")
        else:
            linhas.append("O modelo novo é o de produção, mas não foi medido no "
                          f"corpus de referência: {self.motivo}")
        if self.cer_anterior and self.cer_novo:
            for chave, nome in (("total", "total"), ("prose", "prosa"),
                                ("notation", "notação")):
                a = self.cer_anterior[chave]["cer"] * 100
                n = self.cer_novo[chave]["cer"] * 100
                linhas.append(f"  CER {nome}: {a:.2f}% → {n:.2f}%")
        linhas.extend(f"  piorou: {p}" for p in self.pioras)
        if self.recusado:
            linhas.append(f"O modelo recusado ficou em {self.recusado.name}.")
        if self.anterior:
            linhas.append(f"O modelo anterior está guardado em {self.anterior.name}.")
        return "\n".join(linhas)


def _par(model_path: Path, meta_path: Path, sufixo: str) -> tuple[Path, Path]:
    """`custom_model_<sufixo>.pth` e `model_meta_<sufixo>.json`, sem pisar em nenhum."""
    pasta = model_path.parent
    for n in range(1, 1000):
        rotulo = sufixo if n == 1 else f"{sufixo}_{n}"
        pth = pasta / f"{model_path.stem}_{rotulo}{model_path.suffix}"
        meta = meta_path.parent / f"{meta_path.stem}_{rotulo}{meta_path.suffix}"
        if not pth.exists() and not meta.exists():
            return pth, meta
    raise FileExistsError(f"mil pares {sufixo} em {pasta}")


def _hoje(quando: Optional[datetime.date]) -> str:
    return (quando or datetime.date.today()).isoformat()


def guardar_anterior(model_path, meta_path,
                     quando: Optional[datetime.date] = None) -> Optional[tuple[Path, Path]]:
    """Copia o par de produção antes do treino; `None` se ainda não há um.

    Copia, e não move: se o treino falhar antes de gravar, a produção segue
    intacta, sem depender de alguém desfazer nada.
    """
    model_path, meta_path = Path(model_path), Path(meta_path)
    if not model_path.is_file() or not meta_path.is_file():
        return None
    pth, meta = _par(model_path, meta_path, f"{_hoje(quando)}_antes_do_retreino")
    shutil.copy2(model_path, pth)
    shutil.copy2(meta_path, meta)
    log.info("par anterior guardado em %s", pth.name)
    return pth, meta


def medir_par(model_path, meta_path, manifesto: Path, ocr_service=None) -> list[dict]:
    """A medida do corpus com este par de pesos, no código de agora."""
    from core import rodada
    from core.services.learning_service import LearningService

    servico = LearningService(model_path=str(model_path), meta_path=str(meta_path))
    if not servico.load_predictor():
        raise RuntimeError(servico.motivo_do_modelo() or f"{model_path} não carregou")
    if ocr_service is None:
        from core.services.ocr_service import OCRService
        ocr_service = OCRService()
    return rodada.medir_paginas(rodada.paginas_do_manifesto(manifesto),
                                servico, ocr_service)


def _nao_medidas(medidas: list[dict]) -> list[str]:
    return [f"{m['id']}: {m.get('erro') or 'sem medida'}"
            for m in medidas if not m.get("metricas")]


def comparar(antes: list[dict], depois: list[dict],
             tolerancia: float = TOLERANCIA) -> list[str]:
    """O que piorou do par anterior para o novo, em frase; vazio se nada piorou."""
    from core import rodada

    saida = rodada.pioras(depois, rodada._cer_por_pagina({"paginas": antes}), tolerancia)
    a = rodada._totais(antes)["total"]["cer"]
    n = rodada._totais(depois)["total"]["cer"]
    if n > a + tolerancia:
        saida.append(f"corpus inteiro: {a * 100:.2f}% → {n * 100:.2f}%")
    return saida


def avaliar(model_path, meta_path, anterior: Optional[tuple[Path, Path]],
            manifesto: Optional[Path] = None,
            callback: Optional[Callable[[str], None]] = None,
            medir: Callable = medir_par,
            quando: Optional[datetime.date] = None,
            tolerancia: float = TOLERANCIA) -> Veredito:
    """Mede o par novo (no lugar de produção) contra o anterior guardado, e decide.

    Recusado, o par novo vai para `_recusado` e o anterior é copiado de volta para
    o lugar de produção — o guardado fica onde está, como registro.
    """
    model_path, meta_path = Path(model_path), Path(meta_path)
    avisar = callback or (lambda _texto: None)
    if anterior is None:
        return Veredito(SEM_MEDIDA, "não havia modelo anterior com que comparar.")
    anterior = (Path(anterior[0]), Path(anterior[1]))
    if manifesto is None:
        from config.paths import manifesto_do_corpus
        manifesto = manifesto_do_corpus()
    manifesto = Path(manifesto)
    if not manifesto.is_file():
        return Veredito(SEM_MEDIDA, f"o manifesto {manifesto.name} não existe.",
                        anterior=anterior[0])

    try:
        avisar("Medindo o modelo anterior no corpus de referência...")
        antes = medir(anterior[0], anterior[1], manifesto)
        avisar("Medindo o modelo novo no corpus de referência...")
        depois = medir(model_path, meta_path, manifesto)
    except Exception as erro:
        log.warning("o portão do retreino não mediu o corpus; o modelo novo fica "
                    "sem medida: %s", erro, exc_info=True)
        return Veredito(SEM_MEDIDA, f"a medida falhou ({erro}).", anterior=anterior[0])

    faltam = _nao_medidas(antes) + _nao_medidas(depois)
    if faltam or not antes:
        motivo = ("o manifesto não tem página com referência." if not antes
                  else f"{len(faltam)} página(s) sem medida, como {faltam[0]}.")
        log.info("portão do retreino sem medida: %s", motivo)
        return Veredito(SEM_MEDIDA, motivo, anterior=anterior[0])

    from core import rodada
    veredito = Veredito(PROMOVIDO, anterior=anterior[0],
                        cer_anterior=rodada._totais(antes),
                        cer_novo=rodada._totais(depois),
                        pioras=comparar(antes, depois, tolerancia))
    if veredito.pioras:
        veredito.situacao = RECUSADO
        pth, meta = _par(model_path, meta_path, f"{_hoje(quando)}_recusado")
        shutil.move(str(model_path), pth)
        shutil.move(str(meta_path), meta)
        shutil.copy2(anterior[0], model_path)
        shutil.copy2(anterior[1], meta_path)
        veredito.recusado = pth
        log.warning("o modelo novo foi recusado pelo corpus (%s) e ficou em %s",
                    "; ".join(veredito.pioras), pth.name)
    return veredito
