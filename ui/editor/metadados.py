"""
A caixa "Livro → Metadados…" completa (ED-08; SPEC_EDITOR §5 `Metadados`, §9 "Metadata
Editor"): título, autores e colaboradores (um por linha: `Nome | papel | ordenar como`),
idioma, identificador, editora, data, descrição, assuntos (um por linha), direitos,
coleção e posição, capa (uma imagem do livro), fonte impressa. O que o modelo não
interpreta (`Metadados.extras`, os `refines`, os `ids` do OPF, os prefixos) **não passa
por aqui** e continua como estava — é o que AC-ED08-3 pede.

`aplicar(metadados, valores)` põe os valores no `Metadados` preservando o `id` de cada
pessoa que já existia (os `refines` apontam para ele). Constrói-se sem mostrar.
"""

from __future__ import annotations

import re
import tkinter as tk
from tkinter import ttk
from typing import Sequence

from core.editor.modelo import Metadados, Pessoa
from ui.editor.dialogos import _Dialogo

IDIOMAS = ("pt", "pt-BR", "en", "es", "fr", "de", "it", "ru", "nl")
PAPEIS = ("aut", "edt", "trl", "ill", "pbl", "ctb", "cmm", "ann", "pht", "dsr")
_RE_DATA = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")


def _linha_da_pessoa(p: Pessoa) -> str:
    partes = [p.nome]
    if p.papel and p.papel not in ("aut", "ctb"):
        partes.append(p.papel)
    elif p.file_as:
        partes.append(p.papel or "aut")
    if p.file_as:
        partes.append(p.file_as)
    return " | ".join(partes)


def pessoas_de(texto: str, papel_padrao: str, existentes: Sequence[Pessoa] = ()) -> list[Pessoa]:
    """As linhas `Nome | papel | ordenar como` → `Pessoa`s; quem já existia (mesmo nome) guarda o `id`."""
    saida: list[Pessoa] = []
    por_nome = {p.nome: p for p in existentes}
    for linha in texto.splitlines():
        if not linha.strip():
            continue
        partes = [p.strip() for p in linha.split("|")]
        nome = partes[0]
        papel = partes[1] if len(partes) > 1 and partes[1] else papel_padrao
        file_as = partes[2] if len(partes) > 2 else ""
        antiga = por_nome.get(nome)
        saida.append(Pessoa(nome=nome, papel=papel, file_as=file_as, id=antiga.id if antiga else ""))
    return saida


class DialogoDeMetadados(_Dialogo):
    def __init__(self, master: tk.Misc, metadados: Metadados, imagens: Sequence[str] = (),
                 titulo: str = "Metadados"):
        super().__init__(master, titulo)
        self.metadados = metadados
        self.imagens = list(imagens)
        self.variaveis: dict[str, tk.StringVar] = {}
        self.textos: dict[str, tk.Text] = {}

    def _construir(self) -> tk.Toplevel:
        top = self._abrir((True, True))
        corpo = ttk.Frame(top, padding=12)
        corpo.grid(row=0, column=0, sticky="nsew")
        top.rowconfigure(0, weight=1)
        top.columnconfigure(0, weight=1)
        corpo.columnconfigure(1, weight=1)
        m = self.metadados
        linha = 0

        def campo(chave: str, rotulo: str, valor: str, opcoes: Sequence[str] | None = None) -> None:
            nonlocal linha
            var = tk.StringVar(master=top, value=valor)
            self.variaveis[chave] = var
            ttk.Label(corpo, text=rotulo).grid(row=linha, column=0, sticky="w", padx=(0, 8), pady=2)
            if opcoes is not None:
                ttk.Combobox(corpo, textvariable=var, values=list(opcoes), width=44).grid(row=linha, column=1,
                                                                                         sticky="ew", pady=2)
            else:
                ttk.Entry(corpo, textvariable=var, width=46).grid(row=linha, column=1, sticky="ew", pady=2)
            linha += 1

        def texto(chave: str, rotulo: str, valor: str, altura: int = 3) -> None:
            nonlocal linha
            ttk.Label(corpo, text=rotulo).grid(row=linha, column=0, sticky="nw", padx=(0, 8), pady=2)
            caixa = tk.Text(corpo, width=46, height=altura, wrap="word", highlightthickness=2)
            caixa.insert("1.0", valor)
            caixa.grid(row=linha, column=1, sticky="ew", pady=2)
            self.textos[chave] = caixa
            linha += 1

        campo("titulo", "Título:", m.titulo)
        texto("autores", "Autores (um por linha:\nNome | papel | ordenar como):",
              "\n".join(_linha_da_pessoa(p) for p in m.autores), 3)
        texto("colaboradores", "Colaboradores:", "\n".join(_linha_da_pessoa(p) for p in m.colaboradores), 2)
        campo("idioma", "Idioma:", m.idioma, IDIOMAS)
        campo("identificador", "Identificador:", m.identificador)
        campo("editora", "Editora:", m.editora)
        campo("data", "Data (AAAA-MM-DD):", m.data)
        texto("descricao", "Descrição:", m.descricao, 4)
        texto("assuntos", "Assuntos (um por linha):", "\n".join(m.assuntos), 2)
        campo("direitos", "Direitos:", m.direitos)
        campo("colecao", "Coleção:", m.colecao[0] if m.colecao else "")
        campo("posicao", "Posição na coleção:", str(m.colecao[1]) if m.colecao and m.colecao[1] else "")
        campo("capa", "Capa (imagem do livro):", m.capa, [""] + self.imagens)
        campo("fonte_impressa", "Fonte impressa (ISBN/edição):", m.fonte_impressa)
        extras = len(m.extras)
        ttk.Label(corpo, foreground="#555555", wraplength=460, justify="left",
                  text=f"{extras} metadado(s) do OPF que o editor não interpreta ficam como estão "
                       f"(os refines, o title-type, o calibre:series…). dcterms:modified é escrito ao salvar.").grid(
            row=linha, column=0, columnspan=2, sticky="w", pady=(8, 0))
        linha += 1
        self._botoes(corpo).grid(row=linha, column=0, columnspan=2, sticky="e", pady=(12, 0))
        return top

    def definir(self, **valores: str) -> None:
        for chave, valor in valores.items():
            if chave in self.variaveis:
                self.variaveis[chave].set(valor)
            elif chave in self.textos:
                self.textos[chave].delete("1.0", "end")
                self.textos[chave].insert("1.0", valor)
            else:
                raise KeyError(chave)

    def valores(self) -> dict[str, str]:
        saida = {chave: var.get() for chave, var in self.variaveis.items()}
        saida.update({chave: caixa.get("1.0", "end-1c") for chave, caixa in self.textos.items()})
        return saida

    def _ler(self) -> dict[str, str]:
        valores = self.valores()
        validar(valores)
        return valores

    def _foco_inicial(self) -> None:
        pass


def valores_de(m: Metadados) -> dict[str, str]:
    """Os campos da caixa a partir do `Metadados` (o inverso de `aplicar`)."""
    quebra = "\n"
    return {"titulo": m.titulo, "autores": quebra.join(_linha_da_pessoa(p) for p in m.autores),
            "colaboradores": quebra.join(_linha_da_pessoa(p) for p in m.colaboradores), "idioma": m.idioma,
            "identificador": m.identificador, "editora": m.editora, "data": m.data, "descricao": m.descricao,
            "assuntos": quebra.join(m.assuntos), "direitos": m.direitos, "colecao": m.colecao[0] if m.colecao else "",
            "posicao": str(m.colecao[1]) if m.colecao and m.colecao[1] else "", "capa": m.capa,
            "fonte_impressa": m.fonte_impressa}


def validar(valores: dict[str, str]) -> None:
    if not valores.get("titulo", "").strip():
        raise ValueError("o livro precisa de um título")
    idioma = valores.get("idioma", "").strip()
    if idioma and not re.fullmatch(r"[A-Za-z]{2,3}(-[A-Za-z0-9]+)*", idioma):
        raise ValueError(f"idioma inválido: {idioma!r} — use um código como pt, en ou pt-BR")
    data = valores.get("data", "").strip()
    if data and not _RE_DATA.match(data):
        raise ValueError(f"data inválida: {data!r} — use AAAA, AAAA-MM ou AAAA-MM-DD")
    posicao = valores.get("posicao", "").strip()
    if posicao and not posicao.isdigit():
        raise ValueError("a posição na coleção precisa ser um número inteiro")


def aplicar(m: Metadados, valores: dict[str, str]) -> Metadados:
    """Os valores da caixa no `Metadados`, sem tocar em `extras`, `ids` e `prefixos`."""
    validar(valores)
    m.titulo = valores["titulo"].strip()
    m.autores = pessoas_de(valores.get("autores", ""), "aut", m.autores)
    m.colaboradores = pessoas_de(valores.get("colaboradores", ""), "ctb", m.colaboradores)
    if valores.get("idioma", "").strip():
        m.idioma = valores["idioma"].strip()
    m.identificador = valores.get("identificador", m.identificador).strip() or m.identificador
    m.editora = valores.get("editora", "").strip()
    m.data = valores.get("data", "").strip()
    m.descricao = valores.get("descricao", "").strip()
    m.assuntos = [a.strip() for a in valores.get("assuntos", "").splitlines() if a.strip()]
    m.direitos = valores.get("direitos", "").strip()
    colecao = valores.get("colecao", "").strip()
    posicao = valores.get("posicao", "").strip()
    m.colecao = (colecao, int(posicao) if posicao else 0) if colecao else None
    m.capa = valores.get("capa", "").strip()
    m.fonte_impressa = valores.get("fonte_impressa", "").strip()
    return m


__all__ = ["DialogoDeMetadados", "aplicar", "validar", "valores_de", "pessoas_de", "IDIOMAS", "PAPEIS"]
