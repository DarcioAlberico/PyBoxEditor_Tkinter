"""Contrato de seleção do holdout real usado pelo portão editorial.

O corpus de páginas e o dataset de linhas têm responsabilidades diferentes:
o primeiro prova de onde veio a página; o segundo é o formato consumido pelo
treinador. Este módulo fecha a seam entre eles sem transformar uma página
planejada, sintética ou ainda não revisada em evidência de generalização.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from core.ocr_corpus import CorpusManifest, carregar_manifesto


LINE_HOLDOUT_SCHEMA = "pyboxeditor.ocr-line-holdout/v1"


@dataclass(frozen=True)
class HoldoutPage:
    """Página humana e fisicamente disponível que pode compor o holdout."""

    document_id: str
    page_id: str
    page_index: int
    image: Path
    reference: Path
    language: str
    domains: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "page_id": self.page_id,
            "page_index": self.page_index,
            "image": str(self.image),
            "reference": str(self.reference),
            "language": self.language,
            "domains": list(self.domains),
        }


@dataclass(frozen=True)
class HoldoutSelection:
    """Seleção imutável e auditável extraída de um manifesto de corpus."""

    manifest: Path
    corpus_sha256: str
    pages: tuple[HoldoutPage, ...]

    @property
    def document_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(page.document_id for page in self.pages))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "pyboxeditor.ocr-holdout/v1",
            "manifest": str(self.manifest),
            "corpus_sha256": self.corpus_sha256,
            "documents": list(self.document_ids),
            "pages": [page.to_dict() for page in self.pages],
        }

    def salvar(self, destino: str | Path) -> Path:
        caminho = Path(destino)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return caminho


def _verdadeiro(valor: Any) -> bool:
    return valor is True or (isinstance(valor, str) and valor.strip().lower() in {
        "1", "true", "yes", "sim"
    })


def _revisao_confirmada(valor: Any) -> bool:
    return isinstance(valor, str) and valor.strip().lower() in {
        "reviewed", "approved", "revisado", "aprovado"
    }


def selecionar_holdout(caminho: str | Path) -> HoldoutSelection:
    """Valida e seleciona somente páginas reais, isoladas e revisadas.

    A validação exige imagem e referência porque o holdout precisa medir o
    resultado contra pixels reais e ground truth humano. A função não cria,
    corrige nem promove arquivos; ela apenas produz uma seleção assinada pelo
    hash do manifesto carregado.
    """
    manifesto_path = Path(caminho).resolve()
    manifesto: CorpusManifest = carregar_manifesto(
        manifesto_path, validate_paths=True, require_files=True
    )
    documentos_holdout = [
        documento for documento in manifesto.documents if documento.split == "holdout"
    ]
    if not documentos_holdout:
        raise ValueError("o manifesto não contém documentos no split holdout")

    paginas: list[HoldoutPage] = []
    base = manifesto_path.parent
    for documento in documentos_holdout:
        if _verdadeiro(documento.metadata.get("synthetic")):
            raise ValueError(f"documento de holdout é sintético: {documento.id}")
        if not documento.source:
            raise ValueError(f"documento de holdout sem fonte real: {documento.id}")
        for page in documento.pages:
            if _verdadeiro(page.metadata.get("synthetic")):
                raise ValueError(f"página sintética não pode ser holdout: {page.id}")
            if not _revisao_confirmada(page.metadata.get("annotation_status")):
                raise ValueError(
                    f"página de holdout sem revisão humana confirmada: {page.id}"
                )
            if not page.image:
                raise ValueError(f"página de holdout sem imagem real: {page.id}")
            if not page.reference:
                raise ValueError(f"página de holdout sem ground truth: {page.id}")
            paginas.append(HoldoutPage(
                document_id=documento.id,
                page_id=page.id,
                page_index=page.page_index,
                image=(base / page.image).resolve(),
                reference=(base / page.reference).resolve(),
                language=documento.language,
                domains=tuple(page.domains),
            ))
    if not paginas:
        raise ValueError("o split holdout não contém páginas")
    return HoldoutSelection(
        manifest=manifesto_path,
        corpus_sha256=manifesto.corpus_sha256 or manifesto.digest(base),
        pages=tuple(paginas),
    )


def carregar_selecao(caminho: str | Path) -> HoldoutSelection:
    """Revalida uma seleção materializada antes de anexá-la a um treino."""
    selecao_path = Path(caminho).resolve()
    try:
        dados = json.loads(selecao_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as erro:
        raise ValueError(f"seleção de holdout ilegível: {selecao_path}") from erro
    if not isinstance(dados, dict) or dados.get("schema") != "pyboxeditor.ocr-holdout/v1":
        raise ValueError("schema de seleção de holdout não suportado")
    manifest = dados.get("manifest")
    if not manifest:
        raise ValueError("seleção de holdout sem manifesto de origem")
    selecao = selecionar_holdout(manifest)
    if str(dados.get("corpus_sha256", "")) != selecao.corpus_sha256:
        raise ValueError("seleção de holdout está desatualizada em relação ao corpus")
    ids_declarados = tuple(str(item) for item in dados.get("documents", ()))
    if ids_declarados != selecao.document_ids:
        raise ValueError("seleção de holdout não corresponde aos documentos do corpus")
    paginas_declaradas = tuple(
        str(item.get("page_id")) for item in dados.get("pages", ())
        if isinstance(item, dict)
    )
    if paginas_declaradas != tuple(page.page_id for page in selecao.pages):
        raise ValueError("seleção de holdout não corresponde às páginas do corpus")
    return selecao


def _sha256(caminho: Path) -> str:
    digest = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def _caminho_relativo(valor: Any, campo: str) -> str:
    texto = str(valor or "").strip()
    posix = PurePosixPath(texto.replace("\\", "/"))
    windows = PureWindowsPath(texto)
    if (not texto or Path(texto).is_absolute() or posix.is_absolute()
            or windows.is_absolute() or windows.drive
            or ".." in posix.parts or ".." in windows.parts):
        raise ValueError(f"{campo} precisa ser um caminho relativo dentro do dataset")
    return posix.as_posix()


def _manifesto_de_linhas(raiz: Path) -> dict[str, str]:
    caminho = raiz / "rec_gt.txt"
    if not caminho.is_file():
        raise ValueError(f"holdout de linhas sem rec_gt.txt: {caminho}")
    resultado: dict[str, str] = {}
    for bruto in caminho.read_text(encoding="utf-8").splitlines():
        if not bruto.strip():
            continue
        if "\t" not in bruto:
            raise ValueError("rec_gt.txt do holdout contém linha malformada")
        imagem, texto = bruto.split("\t", 1)
        relativo = _caminho_relativo(imagem, "imagem")
        if relativo in resultado:
            raise ValueError(f"imagem duplicada no rec_gt.txt: {relativo}")
        if not texto.strip():
            raise ValueError(f"linha sem transcrição no rec_gt.txt: {relativo}")
        if not (raiz / relativo).is_file():
            raise FileNotFoundError(f"imagem ausente no holdout: {raiz / relativo}")
        resultado[relativo] = texto.strip()
    if not resultado:
        raise ValueError("rec_gt.txt do holdout não contém linhas")
    return resultado


def validar_proveniencia_de_linhas(dataset: str | Path,
                                   selecao: HoldoutSelection) -> dict[str, Any]:
    """Valida a ligação entre um dataset de linhas e páginas do holdout.

    O arquivo ``provenance.json`` do dataset declara, para cada recorte, a
    página de origem, o hash dos pixels dessa página e a caixa usada para o
    recorte. Isso não substitui a auditoria visual da linha, mas impede que um
    ``rec_gt.txt`` arbitrário seja apresentado como evidência das páginas
    selecionadas. A função é somente validação: não cria nem altera amostras.
    """
    raiz = Path(dataset).resolve()
    caminho = raiz / "provenance.json"
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError) as erro:
        raise ValueError(f"proveniência de linhas ilegível: {caminho}") from erro
    if not isinstance(dados, dict) or dados.get("schema") != LINE_HOLDOUT_SCHEMA:
        raise ValueError("schema de proveniência de linhas não suportado")
    if str(dados.get("corpus_sha256", "")) != selecao.corpus_sha256:
        raise ValueError("proveniência de linhas aponta para outro corpus")

    paginas = {page.page_id: page for page in selecao.pages}
    registros = dados.get("lines")
    if not isinstance(registros, list) or not registros:
        raise ValueError("proveniência de linhas sem registros")
    gt = _manifesto_de_linhas(raiz)
    declaradas: dict[str, dict[str, Any]] = {}
    for registro in registros:
        if not isinstance(registro, dict):
            raise ValueError("registro de proveniência de linha inválido")
        imagem = _caminho_relativo(registro.get("image"), "imagem")
        if imagem in declaradas:
            raise ValueError(f"imagem duplicada na proveniência: {imagem}")
        declaradas[imagem] = registro
        if imagem not in gt:
            raise ValueError(f"proveniência sem entrada correspondente no rec_gt.txt: {imagem}")
        page_id = str(registro.get("page_id", ""))
        page = paginas.get(page_id)
        if page is None:
            raise ValueError(f"linha aponta para página fora do holdout: {page_id}")
        if str(registro.get("document_id", "")) != page.document_id:
            raise ValueError(f"documento divergente na proveniência: {imagem}")
        try:
            page_index = int(registro.get("page_index", -1))
        except (TypeError, ValueError) as erro:
            raise ValueError(f"índice inválido na proveniência: {imagem}") from erro
        if page_index != page.page_index:
            raise ValueError(f"índice divergente na proveniência: {imagem}")
        esperado = _sha256(page.image)
        informado = str(registro.get("source_image_sha256", "")).lower()
        if not informado or informado != esperado:
            raise ValueError(f"hash da página de origem divergente: {page_id}")
        bbox = registro.get("bbox")
        try:
            caixa = tuple(float(valor) for valor in bbox)
        except (TypeError, ValueError) as erro:
            raise ValueError(f"caixa inválida na proveniência: {imagem}") from erro
        if (len(caixa) != 4 or any(valor < 0 for valor in caixa)
                or caixa[2] <= caixa[0] or caixa[3] <= caixa[1]):
            raise ValueError(f"caixa inválida na proveniência: {imagem}")

    if set(declaradas) != set(gt):
        faltantes = sorted(set(gt) - set(declaradas))
        extras = sorted(set(declaradas) - set(gt))
        raise ValueError(
            f"proveniência não cobre exatamente o rec_gt.txt; faltantes={faltantes}, extras={extras}"
        )
    from core.linha_trainer import fingerprint_dataset
    page_ids = list(dict.fromkeys(str(item["page_id"]) for item in declaradas.values()))
    return {
        "schema": LINE_HOLDOUT_SCHEMA,
        "corpus_sha256": selecao.corpus_sha256,
        "dataset_sha256": fingerprint_dataset(raiz),
        "lines": len(gt),
        "page_ids": page_ids,
    }
