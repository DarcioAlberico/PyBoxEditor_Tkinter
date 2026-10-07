"""Planejamento seguro de páginas para ampliar o corpus OCR.

O módulo trabalha antes da transcrição humana. Ele combina a cobertura já
medida com candidatos preliminares de layout e devolve uma seleção determinística
para revisão. Candidato nunca vira referência ou holdout automaticamente.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from core import familias_de_pagina


def _familias(item: Mapping[str, Any]) -> set[str]:
    valores = item.get("familias") or ()
    if isinstance(valores, str):
        valores = (valores,)
    return {str(valor) for valor in valores if str(valor) in familias_de_pagina.FAMILIAS}


def _documento(item: Mapping[str, Any]) -> str:
    return str(item.get("documento") or "?")


def _contagem(paginas: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    saida: dict[str, dict[str, int]] = {}
    for pagina in paginas:
        documento = _documento(pagina)
        valores = saida.setdefault(
            documento, {familia: 0 for familia in familias_de_pagina.FAMILIAS})
        for familia in _familias(pagina):
            valores[familia] += 1
    return saida


def _faltantes(contagem: Mapping[str, Mapping[str, int]], minimo: int
               ) -> dict[str, list[str]]:
    return {
        documento: [familia for familia in familias_de_pagina.FAMILIAS
                    if valores.get(familia, 0) < minimo]
        for documento, valores in sorted(contagem.items())
        if any(valores.get(familia, 0) < minimo
               for familia in familias_de_pagina.FAMILIAS)
    }


def planejar_amostragem(paginas: Iterable[Mapping[str, Any]],
                        candidatos: Iterable[Mapping[str, Any]], *,
                        minimo: int = 3,
                        limite: int | None = None) -> dict[str, Any]:
    """Seleciona candidatos que cobrem o maior déficit por livro/família.

    ``paginas`` são páginas já presentes no corpus medido. ``candidatos`` são
    páginas apenas inspecionadas pelo layout, ainda sem referência humana. O
    empate é resolvido pelo ``id`` para que a mesma entrada produza o mesmo
    plano em qualquer execução.
    """
    if int(minimo) < 1:
        raise ValueError("minimo deve ser positivo")
    if limite is not None and int(limite) < 0:
        raise ValueError("limite não pode ser negativo")
    minimo = int(minimo)
    limite = None if limite is None else int(limite)

    paginas = list(paginas)
    candidatos_normalizados: list[dict[str, Any]] = []
    ids_existentes = {str(item.get("id")) for item in paginas
                      if item.get("id") is not None}
    paginas_existentes = {
        (_documento(item), int(item["page_index"]))
        for item in paginas
        if item.get("page_index") is not None
    }
    ids_candidatos: set[str] = set()
    paginas_candidatas: set[tuple[str, int]] = set()
    for item in candidatos:
        if not isinstance(item, Mapping):
            raise ValueError("candidato de corpus inválido")
        if "reference" in item or "holdout" in item:
            raise ValueError(
                "candidato de corpus não pode conter reference ou holdout")
        status = str(item.get("status") or "unreviewed")
        if status != "unreviewed":
            raise ValueError(
                "candidato de corpus precisa estar com status unreviewed")
        identificador = str(item.get("id", "")).strip()
        if not identificador:
            raise ValueError("candidato de corpus precisa de id")
        if identificador in ids_candidatos:
            raise ValueError(f"candidato de corpus duplicado: {identificador}")
        ids_candidatos.add(identificador)
        candidato = dict(item)
        candidato["id"] = identificador
        candidato["documento"] = _documento(item)
        if item.get("page_index") is not None:
            try:
                page_index = int(item["page_index"])
            except (TypeError, ValueError) as erro:
                raise ValueError(
                    f"page_index inválido no candidato: {identificador}") from erro
            chave_pagina = (candidato["documento"], page_index)
            if chave_pagina in paginas_existentes:
                raise ValueError(
                    f"candidato aponta para página já presente: {identificador}")
            if chave_pagina in paginas_candidatas:
                raise ValueError(
                    f"candidatos apontam para a mesma página: {identificador}")
            paginas_candidatas.add(chave_pagina)
        candidato["familias"] = sorted(_familias(item))
        candidatos_normalizados.append(candidato)

    contagem = _contagem(paginas)
    for candidato in candidatos_normalizados:
        contagem.setdefault(
            candidato["documento"],
            {familia: 0 for familia in familias_de_pagina.FAMILIAS})
    necessidades_iniciais = _faltantes(contagem, minimo)
    selecionados: list[dict[str, Any]] = []
    disponiveis = [item for item in candidatos_normalizados
                   if item["id"] not in ids_existentes]

    while disponiveis and (limite is None or len(selecionados) < limite):
        faltantes = {(documento, familia)
                     for documento, familias in _faltantes(contagem, minimo).items()
                     for familia in familias}
        if not faltantes:
            break
        pontuados = []
        for candidato in disponiveis:
            documento = candidato["documento"]
            ganho = sum((documento, familia) in faltantes
                        for familia in candidato["familias"])
            if ganho:
                pontuados.append((ganho, candidato["id"], candidato))
        if not pontuados:
            break
        melhores = sorted(pontuados, key=lambda item: (-item[0], item[1]))
        escolhido = melhores[0][2]
        disponiveis.remove(escolhido)
        contagem[escolhido["documento"]] = dict(contagem[escolhido["documento"]])
        for familia in escolhido["familias"]:
            contagem[escolhido["documento"]][familia] += 1
        selecionado = dict(escolhido)
        selecionado["status"] = "unreviewed"
        selecionado["motivo"] = "cobertura_por_livro_e_familia"
        selecionados.append(selecionado)

    return {
        "minimo_por_familia": minimo,
        "necessidades_iniciais": necessidades_iniciais,
        "selecionados": selecionados,
        "faltando": _faltantes(contagem, minimo),
    }
