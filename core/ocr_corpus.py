"""Manifesto versionado de corpus e execução de baseline OCR.

O manifesto é a seam da Fase 0: descreve documentos, páginas, ground truth,
camada textual, imagens e previsões sem conhecer nenhum engine. A divisão é por
documento, nunca por recorte, para evitar vazamento de fonte e layout entre
treino, validação e teste.
"""

from __future__ import annotations

import copy
import hashlib
import json
import random
from dataclasses import dataclass, field, replace
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Mapping


SCHEMA = "pyboxeditor.ocr-corpus/v1"
SPLITS = frozenset(("train", "validation", "test", "holdout", "unsplit"))


def _path_relativo(value: str | Path | None, nome: str) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    texto = str(value)
    janela = PureWindowsPath(texto)
    posix = PurePosixPath(texto.replace("\\", "/"))
    # `is_absolute()` não basta: no Windows `/Windows/win.ini` não é absoluto
    # (não tem drive), mas `base / "/Windows/win.ini"` ancora na raiz do
    # drive e sai do corpus — e `executar_corpus` lê o arquivo para dentro do
    # relatório. Raiz, drive e `..` são recusados, venham de que sistema
    # vierem.
    if (Path(texto).is_absolute() or janela.is_absolute() or janela.drive
            or janela.root or posix.is_absolute() or ".." in posix.parts
            or ".." in janela.parts):
        raise ValueError(f"{nome} precisa ser um caminho relativo dentro do corpus")
    return posix.as_posix()


def _ler_json(caminho: Path) -> dict[str, Any]:
    with caminho.open(encoding="utf-8") as arquivo:
        valor = json.load(arquivo)
    if not isinstance(valor, dict):
        raise ValueError(f"Esperado objeto JSON em {caminho}")
    return valor


def _ler_predicao(caminho: Path) -> dict[str, Any]:
    """Lê JSON estruturado ou texto puro usado no corpus histórico."""
    if caminho.suffix.casefold() == ".txt":
        return {"text": caminho.read_text(encoding="utf-8")}
    return _ler_json(caminho)


def _atualizar_arquivo(digest: hashlib._Hash, base: Path, relativo: str | None) -> None:
    if relativo is None:
        return
    caminho = base / relativo
    digest.update(relativo.encode("utf-8") + b"\0")
    if not caminho.is_file():
        digest.update(b"MISSING\0")
        return
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)


@dataclass
class CorpusPage:
    id: str
    page_index: int
    image: str | None = None
    reference: str | None = None
    pdf_text: str | None = None
    predictions: dict[str, str] = field(default_factory=dict)
    domains: tuple[str, ...] = ()
    printed_page: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = str(self.id).strip()
        if not self.id:
            raise ValueError("página precisa de id")
        self.page_index = int(self.page_index)
        if self.page_index < 0:
            raise ValueError("page_index não pode ser negativo")
        self.image = _path_relativo(self.image, "image")
        self.reference = _path_relativo(self.reference, "reference")
        self.pdf_text = _path_relativo(self.pdf_text, "pdf_text")
        self.predictions = {
            str(engine): _path_relativo(path, f"prediction[{engine}]") or ""
            for engine, path in dict(self.predictions or {}).items()
        }
        self.domains = tuple(str(domain) for domain in self.domains)
        self.metadata = dict(self.metadata or {})

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "page_index": self.page_index,
            "image": self.image,
            "reference": self.reference,
            "pdf_text": self.pdf_text,
            "predictions": dict(self.predictions),
            "domains": list(self.domains),
            "printed_page": self.printed_page,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CorpusPage":
        return cls(
            id=str(data["id"]),
            page_index=int(data.get("page_index", 0)),
            image=data.get("image"),
            reference=data.get("reference"),
            pdf_text=data.get("pdf_text"),
            predictions=dict(data.get("predictions", {})),
            domains=tuple(data.get("domains", ())),
            printed_page=data.get("printed_page"),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class CorpusDocument:
    id: str
    title: str
    language: str
    source_kind: str
    source: str | None
    split: str
    pages: list[CorpusPage]
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = str(self.id).strip()
        self.title = str(self.title)
        self.language = str(self.language)
        self.source_kind = str(self.source_kind)
        self.source = _path_relativo(self.source, "source")
        self.split = str(self.split)
        self.pages = list(self.pages)
        self.metadata = dict(self.metadata or {})
        if not self.id:
            raise ValueError("documento precisa de id")
        if self.split not in SPLITS:
            raise ValueError(f"split inválido: {self.split!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "language": self.language,
            "source_kind": self.source_kind,
            "source": self.source,
            "split": self.split,
            "pages": [page.to_dict() for page in self.pages],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CorpusDocument":
        return cls(
            id=str(data["id"]),
            title=str(data.get("title", data["id"])),
            language=str(data.get("language", "und")),
            source_kind=str(data.get("source_kind", "unknown")),
            source=data.get("source"),
            split=str(data.get("split", "unsplit")),
            pages=[CorpusPage.from_dict(item) for item in data.get("pages", [])],
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class CorpusManifest:
    name: str
    documents: list[CorpusDocument]
    schema: str = SCHEMA
    version: str = "1"
    corpus_sha256: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.name = str(self.name).strip()
        self.documents = list(self.documents)
        self.schema = str(self.schema)
        self.version = str(self.version)
        self.corpus_sha256 = str(self.corpus_sha256 or "")
        self.metadata = dict(self.metadata or {})
        if not self.name:
            raise ValueError("manifesto precisa de nome")
        if self.schema != SCHEMA:
            raise ValueError(f"schema de corpus não suportado: {self.schema!r}")

    def validate(self, base_dir: str | Path | None = None,
                 *, require_files: bool = False) -> list[str]:
        avisos: list[str] = []
        document_ids: set[str] = set()
        page_ids: set[str] = set()
        base = Path(base_dir) if base_dir is not None else None
        for document in self.documents:
            if document.id in document_ids:
                raise ValueError(f"documento duplicado: {document.id}")
            document_ids.add(document.id)
            if document.split not in SPLITS:
                raise ValueError(f"split inválido: {document.split!r}")
            if not document.pages:
                avisos.append(f"documento sem páginas: {document.id}")
            if base is not None and document.source and not (base / document.source).is_file():
                mensagem = f"arquivo-fonte ausente para {document.id}: {document.source}"
                if require_files:
                    raise FileNotFoundError(mensagem)
                avisos.append(mensagem)
            indices: set[int] = set()
            for page in document.pages:
                if page.id in page_ids:
                    raise ValueError(f"página duplicada: {page.id}")
                page_ids.add(page.id)
                if page.page_index in indices:
                    raise ValueError(f"page_index duplicado em {document.id}: {page.page_index}")
                indices.add(page.page_index)
                page_split = page.metadata.get("split")
                if page_split is not None and page_split != document.split:
                    raise ValueError(
                        f"split da página {page.id} contradiz o split do documento")
                caminhos = [page.image, page.reference, page.pdf_text]
                caminhos.extend(page.predictions.values())
                if base is not None:
                    for relativo in caminhos:
                        if relativo and not (base / relativo).is_file():
                            mensagem = f"arquivo ausente para {page.id}: {relativo}"
                            if require_files:
                                raise FileNotFoundError(mensagem)
                            avisos.append(mensagem)
        return avisos

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        data = {
            "schema": self.schema,
            "name": self.name,
            "version": self.version,
            "documents": [document.to_dict() for document in self.documents],
            "metadata": dict(self.metadata),
        }
        if include_hash and self.corpus_sha256:
            data["corpus_sha256"] = self.corpus_sha256
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CorpusManifest":
        return cls(
            name=str(data["name"]),
            version=str(data.get("version", "1")),
            documents=[CorpusDocument.from_dict(item)
                       for item in data.get("documents", [])],
            schema=str(data.get("schema", SCHEMA)),
            corpus_sha256=str(data.get("corpus_sha256", "")),
            metadata=dict(data.get("metadata", {})),
        )

    def digest(self, base_dir: str | Path) -> str:
        """Assina definição e bytes do corpus, sem incluir o próprio hash."""
        base = Path(base_dir)
        digest = hashlib.sha256(b"pyboxeditor-ocr-corpus-v1\0")
        canonical = json.dumps(self.to_dict(include_hash=False), ensure_ascii=False,
                               sort_keys=True, separators=(",", ":"))
        digest.update(canonical.encode("utf-8"))
        for document in sorted(self.documents, key=lambda item: item.id):
            _atualizar_arquivo(digest, base, document.source)
            for page in sorted(document.pages, key=lambda item: item.id):
                for relativo in (page.image, page.reference, page.pdf_text):
                    _atualizar_arquivo(digest, base, relativo)
                for engine, relativo in sorted(page.predictions.items()):
                    digest.update(engine.encode("utf-8") + b"\0")
                    _atualizar_arquivo(digest, base, relativo)
        return digest.hexdigest()


def salvar_manifesto(manifesto: CorpusManifest, caminho: str | Path, *,
                     base_dir: str | Path | None = None) -> Path:
    destino = Path(caminho)
    base = Path(base_dir) if base_dir is not None else destino.parent
    manifesto.validate(base)
    manifesto.corpus_sha256 = manifesto.digest(base)
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_suffix(destino.suffix + ".tmp")
    temporario.write_text(json.dumps(manifesto.to_dict(), ensure_ascii=False,
                                     indent=2) + "\n", encoding="utf-8")
    temporario.replace(destino)
    return destino


def carregar_manifesto(caminho: str | Path, *, validate_paths: bool = False,
                       require_files: bool = False) -> CorpusManifest:
    destino = Path(caminho)
    manifesto = CorpusManifest.from_dict(_ler_json(destino))
    base = destino.parent
    manifesto.validate(base if validate_paths else None,
                       require_files=require_files)
    if manifesto.corpus_sha256 and validate_paths:
        atual = manifesto.digest(base)
        if atual != manifesto.corpus_sha256:
            raise ValueError("hash do corpus não corresponde aos arquivos declarados")
    return manifesto


def dividir_documentos(manifesto: CorpusManifest, *,
                       validation_fraction: float = 0.15,
                       test_fraction: float = 0.15,
                       seed: int = 42) -> CorpusManifest:
    """Atribui splits de forma determinística, mantendo cada livro inteiro."""
    if not 0 <= validation_fraction < 1 or not 0 <= test_fraction < 1:
        raise ValueError("frações de split devem estar entre 0 e 1")
    if validation_fraction + test_fraction >= 1:
        raise ValueError("frações de validação e teste devem deixar treino")
    resultado = copy.deepcopy(manifesto)
    # O holdout não entra na repartição: é o conjunto que nunca vira treino,
    # e redistribuí-lo aqui era o que apagava o isolamento dele em silêncio.
    reservados = [d for d in resultado.documents if d.split == "holdout"]
    documentos = [d for d in resultado.documents if d.split != "holdout"]
    if len(documentos) >= 3:
        ordem = list(range(len(documentos)))
        random.Random(seed).shuffle(ordem)
        n_teste = max(1, round(len(documentos) * test_fraction)) if test_fraction else 0
        n_validacao = max(1, round(len(documentos) * validation_fraction)) if validation_fraction else 0
        while n_teste + n_validacao >= len(documentos):
            if n_validacao > 0:
                n_validacao -= 1
            elif n_teste > 0:
                n_teste -= 1
            else:
                break
        test_ids = {documentos[index].id for index in ordem[:n_teste]}
        validation_ids = {
            documentos[index].id for index in ordem[n_teste:n_teste + n_validacao]
        }
        novos = []
        for documento in documentos:
            split = ("test" if documento.id in test_ids else
                     "validation" if documento.id in validation_ids else "train")
            paginas = [replace(page, metadata={**page.metadata, "split": split})
                       for page in documento.pages]
            novos.append(replace(documento, split=split, pages=paginas))
        resultado.documents = novos + reservados
    resultado.corpus_sha256 = ""
    return resultado


def executar_corpus(caminho: str | Path, *, engine: str,
                    ignorar_maiusculas: bool = False,
                    split: str | None = None):
    """Executa as métricas do benchmark sobre um manifesto de corpus."""
    from core.ocr_benchmark import agregar, medir_pagina

    manifesto = carregar_manifesto(caminho, validate_paths=True, require_files=True)
    if split is not None and split not in SPLITS:
        raise ValueError(f"split inválido: {split!r}")
    base = Path(caminho).parent
    resultados = []
    documentos: list[str] = []
    for documento in manifesto.documents:
        if split is not None and documento.split != split:
            continue
        documentos.append(documento.id)
        for page in documento.pages:
            if page.reference is None:
                raise ValueError(f"página sem ground truth: {page.id}")
            predicao = page.predictions.get(engine)
            if not predicao:
                raise ValueError(f"página {page.id} sem previsão do engine {engine!r}")
            referencia = _ler_predicao(base / page.reference)
            predicao_json = _ler_predicao(base / predicao)
            metadata = {
                "document_id": documento.id,
                "document_title": documento.title,
                "language": documento.language,
                "split": documento.split,
                "page_index": page.page_index,
                "domains": list(page.domains),
                **page.metadata,
            }
            resultados.append(medir_pagina(
                page.id, referencia, predicao_json,
                ignorar_maiusculas=ignorar_maiusculas, metadata=metadata))
    return agregar(resultados, metadata={
        "manifest": str(Path(caminho)),
        "corpus_sha256": manifesto.corpus_sha256,
        "engine": engine,
        "split": split,
        "documents": documentos,
        "ignore_case": ignorar_maiusculas,
    })
