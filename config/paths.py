"""Caminhos persistentes da aplicação, separados do código instalado."""

from __future__ import annotations

import os
import sys
from pathlib import Path


APP_NAME = "PyBoxEditor"


def projeto_dir() -> Path:
    """Diretório do projeto/aplicação onde ficam os pesos empacotados."""
    return Path(__file__).resolve().parent.parent


def _raizes_de_recursos() -> tuple[Path, ...]:
    """Raízes de dados em ordem de precedência, incluindo um wheel instalado."""
    candidatos = (
        Path.cwd(),
        projeto_dir(),
        Path(sys.prefix) / "share" / APP_NAME,
        Path(sys.prefix) / "share" / APP_NAME.lower(),
    )
    resultado = []
    for raiz in candidatos:
        raiz = raiz.resolve()
        if raiz not in resultado:
            resultado.append(raiz)
    return tuple(resultado)


def _primeiro_arquivo(nome: str, fallback: Path | None = None) -> Path:
    for raiz in _raizes_de_recursos():
        candidato = raiz / nome
        if candidato.is_file():
            return candidato
    return fallback or (projeto_dir() / nome)


def caminhos_modelo_linha() -> tuple[Path, Path]:
    """Localiza os pesos do OCR de linhas independentemente do cwd.

    A UI pode ser aberta por atalho, IDE ou pelo terminal. Nesses casos o
    diretório de trabalho nem sempre é a raiz do projeto, embora os pesos
    continuem ao lado do código. Mantemos compatibilidade com um modelo
    criado no cwd quando ele existe e, caso contrário, usamos a raiz real.
    """
    candidatos = _raizes_de_recursos()
    for raiz in candidatos:
        modelo, meta = raiz / "text_line_model.pth", raiz / "text_line_model.json"
        if modelo.exists() and meta.exists():
            return modelo, meta
    raiz = projeto_dir()
    return raiz / "text_line_model.pth", raiz / "text_line_model.json"


def completar_modelo_linha(modelo: str | Path | None = None,
                           meta: str | Path | None = None) -> tuple[Path, Path]:
    """Os caminhos do modelo de linha pedidos, com os de `caminhos_modelo_linha`
    onde faltarem.

    É o padrão de todo `destino`/`meta`/`model_path` do treino e da leitura de
    linha. Eram nomes soltos (`"text_line_model.pth"`), e o treino gravava no
    cwd de quem abriu o programa enquanto a leitura procurava na raiz.
    """
    if modelo is None or meta is None:
        padrao, padrao_meta = caminhos_modelo_linha()
        modelo = padrao if modelo is None else modelo
        meta = padrao_meta if meta is None else meta
    return Path(modelo), Path(meta)


def dado_do_projeto(nome: str) -> Path:
    """Um arquivo ou pasta de dados que vive ao lado do código, sem depender do cwd.

    É a mesma regra de `caminhos_modelo_linha`, para as bases que o treino de
    linhas lê: a rotulada e a sintética. Com o nome solto
    (`Path("training_data_linhas")`), o app aberto por atalho rotulava linhas
    numa pasta e treinava de outra (item 9 da `docs/REVISAO_MODOS_OCR.md`).
    Vale o que já existe no cwd — quem roda de outra pasta com os dados dela
    continua como antes —, e senão a raiz do projeto, que é onde tudo nasce
    quando o cwd é outro. O que o treino **grava** fica ao lado do modelo
    (`relatorio_de_linhas`, `modelo_de_lingua`).
    """
    local = Path.cwd() / nome
    return local if local.exists() else projeto_dir() / nome


def pasta_de_linhas() -> Path:
    """A base de linhas rotuladas (`rec_gt.txt` + `images/`)."""
    return dado_do_projeto("training_data_linhas")


def pasta_de_linhas_sinteticas() -> Path:
    """As variações sintéticas que o treino usa quando a base é pequena."""
    return dado_do_projeto("training_data_linhas_sintetico")


def relatorio_de_linhas(extensao: str = ".txt", modelo: str | Path | None = None) -> Path:
    """O relatório do treino de linhas (`.txt` para ler, `.json` para máquina).

    Mora **ao lado do modelo** que o treino gerou, como o
    `ocr_training_state.json` e o manifesto dos pesos: o pacote do modelo de
    linha fica junto, e um treino apontado para outra pasta — a do teste, a de
    um experimento — não escreve na raiz do projeto.
    """
    return completar_modelo_linha(modelo)[0].with_name("text_line_training_report" + extensao)


def avaliacao_de_linhas(modelo: str | Path | None = None) -> Path:
    """O resultado de "Avaliar modelo de linhas", ao lado do modelo avaliado."""
    return completar_modelo_linha(modelo)[0].with_name("text_line_evaluation.json")


def modelo_de_lingua(modelo: str | Path | None = None) -> Path:
    """O léxico estatístico que o treino do pacote grava, ao lado do modelo."""
    return completar_modelo_linha(modelo)[0].with_name("ocr_language_model.json")


def caminhos_dos_pesos() -> dict[str, Path]:
    """Os três pesos que decidem a leitura de uma página.

    São eles que o cache do caminho novo tem de levar na chave: trocar o modelo
    e reaproveitar o resultado gravado é servir a leitura do modelo velho como
    se fosse a do novo (item 7 da revisão de 2026-09-18). Os nomes são os
    mesmos de `core.diagrama.CAMINHO_MODELO`/`CAMINHO_OCUPACAO` e do padrão do
    `LearningService` — e há teste que prende os três a estes caminhos, porque
    a duplicação aqui é o preço de não importar `cv2` para saber onde eles
    estão.
    """
    raiz = projeto_dir()
    return {"glifos": _primeiro_arquivo("custom_model.pth"),
            "diagrama": _primeiro_arquivo("core/dados/diagrama_modelo.pth",
                                          raiz / "core" / "dados" / "diagrama_modelo.pth"),
            "ocupacao": _primeiro_arquivo("core/dados/ocupacao_modelo.pth",
                                          raiz / "core" / "dados" / "ocupacao_modelo.pth")}


def caminhos_modelo_glifos() -> tuple[Path, Path]:
    """Modelo e metadados da rede de glifos, também quando instalada via wheel."""
    modelo = caminhos_dos_pesos()["glifos"]
    return modelo, _primeiro_arquivo("model_meta.json", modelo.parent / "model_meta.json")


def cache_ocr_dir() -> Path:
    """Onde o resultado por página do caminho novo é guardado.

    Fora do projeto, junto do resto do que é do usuário: o cwd de quem abre o
    programa por atalho não é a raiz, e um cache que cai na pasta corrente é um
    cache que nunca acerta duas vezes. `PYBOXEDITOR_CACHE_DIR` reaponta a pasta
    — é o que mantém a suíte de testes fora do `AppData` de quem a roda.

    **Ele não é podado por ninguém.** Cada página guardada é um JSON de alguns
    KB, e a chave inclui os pesos, então uma troca de modelo deixa o que ficou
    para trás sem uso — apagar a pasta é seguro a qualquer momento.
    """
    base = os.environ.get("PYBOXEDITOR_CACHE_DIR")
    return (Path(base) if base else data_dir() / "cache") / "ocr"


def data_dir() -> Path:
    """Diretório gravável por usuário para configurações e diagnósticos."""
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base) / APP_NAME
    elif os.environ.get("XDG_DATA_HOME"):
        return Path(os.environ["XDG_DATA_HOME"]) / APP_NAME
    return Path.home() / ".local" / "share" / APP_NAME


def settings_path() -> Path:
    return data_dir() / "settings.json"


def crash_log_path() -> Path:
    return data_dir() / "crash_log.txt"


def ensure_data_dir() -> Path:
    caminho = data_dir()
    caminho.mkdir(parents=True, exist_ok=True)
    return caminho
