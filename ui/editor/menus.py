"""
Os menus da janela de edição (SPEC_EDITOR §7.3), numa tabela declarativa (ED-02).

## A tabela é a §7.3 inteira, desde já

Todo item da §7.3 existe desde a ED-02 — com o `comando` que o executa e a **fase**
que o entrega. O item cujo comando ainda não está em `janela.comandos` nasce
desabilitado, e ao ser percorrido escreve a fase na barra de status
(`<<MenuSelect>>`; o `tk.Menu` não tem dica). Cada fase seguinte não mexe na tabela:
liga os seus comandos por `janela.registrar_comandos(...)` e os itens acordam. Um
item que a §7.3 não previu entra **no fim do seu menu**, numa seção comentada com a
fase (princípio 8 do roadmap: a tabela só cresce).

## Um lar por comando

Um comando tem um item que é o seu lar; um segundo item para o mesmo comando é
declarado `alias_de` — "Inserir → Diagrama…" é alias de "Xadrez → Inserir
diagrama…". O acelerador vem de `ui/editor/atalhos.py`, a única fonte (§7.4), e é
refeito a cada troca de modo, porque `Ctrl+Enter` divide o capítulo no código e
quebra a página no texto.

## Mnemônicos

Os dos menus são os da §7.3 (**A**rquivo, **E**ditar, E**x**ibir, **I**nserir,
**F**ormatar, Xadre**z**, Ferra**m**entas, **L**ivro, Aj**u**da). Os dos itens são
escolhidos aqui: a primeira letra do rótulo que não é letra de peça em nenhum dos
dois mapas (`KQRBNP` e `RDTBCP`) e ainda não foi usada no menu; quando as letras
livres acabam, repete — o Tk vai para a primeira. `verificar` confere as regras.

## Menu de contexto

`Shift+F10` e a tecla de menu abrem o menu de contexto do editor ativo; ele é
montado **da mesma tabela** (`CONTEXTO`, por modo), e por isso toda ação de
contexto tem item de menu por construção (§7.3).
"""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from ui.editor import atalhos as atalhos_mod

AMBOS = ("texto", "codigo")
TEXTO = ("texto",)
CODIGO = ("codigo",)
#: Letras de peça nos dois mapas (inglês e português): fora dos mnemônicos.
LETRAS_PROIBIDAS = frozenset("KQRBNPDTCkqrbnpdtc")
MNEMONICOS_DOS_MENUS = {"Arquivo": "A", "Editar": "E", "Exibir": "x", "Inserir": "I", "Formatar": "F",
                        "Xadrez": "z", "Ferramentas": "m", "Livro": "L", "Ajuda": "u"}


@dataclass(frozen=True)
class Item:
    rotulo: str
    comando: str = ""
    fase: str = "ED-02"
    modos: tuple[str, ...] = AMBOS
    alias_de: str = ""                 # o comando (ou rótulo) do item que é o lar
    mnemonico: str = ""                # a letra; "" = escolhida por `_mnemonicos`
    filhos: tuple["Item", ...] = ()    # submenu ▸
    check: str = ""                    # nome da variável booleana em `janela.variaveis` (checkbutton)
    dinamico: str = ""                 # nome em `janela.itens_dinamicos` que preenche o submenu ao abrir
    tipo: str = "comando"              # "comando" | "separador" | "submenu" | "check"

    @property
    def nome(self) -> str:
        """A chave do item no mapa: o comando, ou o rótulo quando não há comando."""
        return self.comando or self.rotulo


SEP = Item("", tipo="separador")


def _i(rotulo: str, comando: str, fase: str = "ED-02", modos: tuple[str, ...] = AMBOS, **kw: Any) -> Item:
    return Item(rotulo, comando, fase, modos, **kw)


def _sub(rotulo: str, fase: str, filhos: Sequence[Item] = (), modos: tuple[str, ...] = AMBOS, **kw: Any) -> Item:
    return Item(rotulo, "", fase, modos, filhos=tuple(filhos), tipo="submenu", **kw)


def _check(rotulo: str, comando: str, variavel: str, fase: str = "ED-02", modos: tuple[str, ...] = AMBOS) -> Item:
    return Item(rotulo, comando, fase, modos, check=variavel, tipo="check")


def _placeholder(fase: str) -> tuple[Item, ...]:
    return (Item(f"(chega na {fase})", "", fase),)


# ----------------------------------------------------------------------
# A §7.3
# ----------------------------------------------------------------------

ESTILOS = ("corpo", "primeira", "titulo1", "titulo2", "titulo3", "titulo4", "titulo5", "titulo6", "notacao",
           "comentario", "legenda", "citacao", "nota", "destaque", "epigrafe", "assinatura", "cabecalho-diagrama")
ROTULOS_DOS_ESTILOS = {
    "corpo": "Corpo", "primeira": "Primeira linha", "titulo1": "Título 1", "titulo2": "Título 2",
    "titulo3": "Título 3", "titulo4": "Título 4", "titulo5": "Título 5", "titulo6": "Título 6",
    "notacao": "Notação", "comentario": "Comentário", "legenda": "Legenda", "citacao": "Citação", "nota": "Nota",
    "destaque": "Destaque", "epigrafe": "Epígrafe", "assinatura": "Assinatura",
    "cabecalho-diagrama": "Cabeçalho de diagrama",
}
ESTILOS_DE_CARACTERE = ("Lance", "NAG", "Figurina", "Simbolo", "Versalete", "Jogador", "Abertura")
REALCES = (("Amarelo", "#ffff00"), ("Verde", "#b6ffb6"), ("Azul", "#c6e2ff"), ("Rosa", "#ffc6e2"))

ARQUIVO = (
    _i("Novo livro", "novo"),
    _i("Novo a partir de modelo…", "novo_de_modelo"),
    _i("Abrir…", "abrir"),
    _sub("Abrir recente", "ED-02", dinamico="recentes"),
    _i("Salvar", "salvar"),
    _i("Salvar como…", "salvar_como"),
    _i("Reverter ao salvo", "reverter"),
    _sub("Ponto de verificação", "ED-02", (
        _i("Criar…", "checkpoint_criar"),
        _i("Comparar…", "checkpoint_comparar"),
        _i("Restaurar…", "checkpoint_restaurar"),
    )),
    _i("Fechar aba", "fechar_aba"),
    _i("Fechar livro", "fechar_livro"),
    SEP,
    _sub("Importar", "ED-10", (
        _i("HTML/XHTML…", "importar_html", "ED-10"),
        _i("TXT…", "importar_txt", "ED-10"),
        _i("EPUB para dentro do livro…", "importar_epub", "ED-10"),
        _i("DOCX…", "importar_docx", "ED-12"),
        _i("JSON editorial…", "importar_json", "ED-11"),
    )),
    _i("Exportar…", "exportar"),
    _i("Imprimir…", "imprimir", "ED-12"),
    SEP,
    _i("Sair", "sair"),
)

EDITAR = (
    _i("Desfazer", "desfazer"),
    _i("Refazer", "refazer"),
    _sub("Apagar palavra", "ED-02", (
        _i("Anterior", "apagar_palavra_anterior"),
        _i("Seguinte", "apagar_palavra_seguinte"),
    )),
    SEP,
    _i("Recortar", "recortar"),
    _i("Copiar", "copiar"),
    _i("Colar", "colar"),
    _i("Colar sem formatação", "colar_sem_formatacao"),
    _i("Colar como XHTML", "colar_como_xhtml", "ED-04", TEXTO),
    SEP,
    _i("Selecionar tudo", "selecionar_tudo"),
    _i("Selecionar parágrafo", "selecionar_paragrafo", "ED-02", TEXTO),
    _i("Selecionar bloco", "selecionar_bloco", "ED-02", TEXTO),
    SEP,
    _i("Localizar…", "localizar", "ED-06"),
    _i("Substituir…", "substituir", "ED-06"),
    _i("Localizar próximo", "localizar_proximo", "ED-06"),
    _i("Localizar anterior", "localizar_anterior", "ED-06"),
    _i("Ir para…", "ir_para", "ED-06"),
    _i("Seguir link", "seguir_link", "ED-04"),
    SEP,
    _sub("Maiúsculas/minúsculas", "ED-02", (
        _i("MAIÚSCULAS", "maiusculas", "ED-02", TEXTO),
        _i("minúsculas", "minusculas", "ED-02", TEXTO),
        _i("Primeira Letra Maiúscula", "capitalizar", "ED-02", TEXTO),
    ), TEXTO),
    _i("Pincel de formatação", "pincel", "ED-02", TEXTO),
    _i("Autocompletar", "autocompletar", "ED-02", CODIGO),
    _i("Comentar/descomentar", "comentar", "ED-02", CODIGO),
    SEP,
    _i("Preferências…", "preferencias", "ED-13"),
    # -- fora da §7.3: o "Go to link/style, and back" do Sigil (§9, ED-07) ------------------
    SEP,
    _i("Ir ao alvo do link", "ir_ao_alvo", "ED-02", CODIGO),
    _i("Voltar do alvo", "voltar", "ED-02", CODIGO),
    # -- ED-06: os botões do painel Busca que a §8.12 pede, com item para o teclado --------
    SEP,
    _i("Substituir e localizar", "substituir_e_localizar", "ED-06"),
    _i("Substituir todos", "substituir_todos", "ED-06"),
    _i("Contar ocorrências", "contar_ocorrencias", "ED-06"),
    _i("Listar ocorrências", "listar_ocorrencias", "ED-06"),
    _i("Marcar texto para a busca", "marcar_texto", "ED-06"),
    _i("Marcar arquivo para a busca", "marcar_arquivo", "ED-06"),
)

EXIBIR = (
    _i("Modo texto", "modo_texto"),
    _i("Modo código", "modo_codigo"),
    _i("Alternar modo", "alternar_modo"),
    _i("Prévia", "previa", "ED-08", CODIGO),
    SEP,
    _i("Capítulo seguinte", "capitulo_seguinte"),
    _i("Capítulo anterior", "capitulo_anterior"),
    _i("Painel seguinte", "painel_seguinte"),
    _i("Painel anterior", "painel_anterior"),
    _i("Foco no editor", "foco_no_editor"),
    SEP,
    _check("Navegador", "painel_navegador", "navegador"),
    _check("Sumário", "painel_sumario", "sumario"),
    _check("Estilos", "painel_estilos", "estilos"),
    _check("Propriedades", "painel_propriedades", "propriedades"),
    _check("Xadrez", "painel_xadrez", "xadrez"),
    _check("Busca e mensagens", "painel_busca", "busca"),
    _check("Barra de formatação", "barra_de_formatacao", "barra_de_formatacao"),
    _check("Barra de xadrez", "barra_de_xadrez", "barra_de_xadrez"),
    SEP,
    _check("Mostrar invisíveis", "invisiveis", "invisiveis", "ED-02", TEXTO),
    _check("Quebra automática de linha", "quebra_automatica", "quebra_automatica"),
    _sub("Largura de leitura", "ED-02", (
        _i("Toda a janela", "largura_toda", "ED-02", TEXTO),
        _i("60 caracteres", "largura_60", "ED-02", TEXTO),
        _i("80 caracteres", "largura_80", "ED-02", TEXTO),
        _i("100 caracteres", "largura_100", "ED-02", TEXTO),
    ), TEXTO),
    _sub("Zoom", "ED-02", (
        _i("Aumentar", "zoom_mais"),
        _i("Diminuir", "zoom_menos"),
        _i("Tamanho original (100%)", "zoom_zero"),
    )),
    _check("Tela cheia", "tela_cheia", "tela_cheia"),
    _check("Números de linha", "numeros_de_linha", "numeros_de_linha", "ED-02", CODIGO),
    _check("Realce da linha atual", "realce_da_linha", "realce_da_linha", "ED-02", CODIGO),
)

INSERIR = (
    _i("Diagrama…", "inserir_diagrama", "ED-05", alias_de="inserir_diagrama"),
    _i("Imagem…", "inserir_imagem", "ED-04"),
    _i("Tabela…", "inserir_tabela", "ED-04", TEXTO),
    _i("Link…", "inserir_link", "ED-04"),
    _i("Referência…", "inserir_referencia", "ED-05", TEXTO),
    _i("Âncora (id)…", "inserir_ancora", "ED-04"),
    _i("Nota de rodapé", "nota_de_rodape", "ED-04", TEXTO),
    _i("Nota de fim", "nota_de_fim", "ED-04", TEXTO),
    SEP,
    _i("Quebra de linha", "quebra_de_linha", "ED-04", TEXTO),
    _i("Quebra de página", "quebra_de_pagina", "ED-04", TEXTO),
    _i("Separador", "inserir_separador", "ED-04", TEXTO),
    _i("Ilha de XHTML…", "inserir_ilha", "ED-04", TEXTO),
    SEP,
    _i("Espaço inseparável", "espaco_inseparavel", "ED-02"),
    _i("Hífen inseparável", "hifen_inseparavel", "ED-02"),
    _i("Hífen opcional", "hifen_opcional", "ED-02"),
    _i("Código Unicode ↔ caractere", "codigo_unicode", "ED-06", TEXTO),
    SEP,
    _i("Capítulo novo", "novo_capitulo", "ED-08", alias_de="novo_capitulo"),
    _i("Dividir capítulo aqui", "dividir_capitulo", "ED-04"),
    _i("Sumário como página do livro", "sumario_como_pagina", "ED-08"),
    SEP,
    _sub("Figurina", "ED-05", _placeholder("ED-05")),
    _sub("NAG", "ED-05", _placeholder("ED-05")),
    _i("Símbolo…", "inserir_simbolo", "ED-06"),
    _sub("Clipe", "ED-02", dinamico="clipes"),
)

FORMATAR = (
    _i("Fonte…", "fonte", "ED-02", TEXTO),
    _i("Negrito", "negrito"),
    _i("Itálico", "italico"),
    _i("Sublinhado", "sublinhado"),
    _i("Tachado", "tachado", "ED-02", TEXTO),
    _i("Versalete", "versalete", "ED-02", TEXTO),
    _i("Sobrescrito", "sobrescrito", "ED-02", TEXTO),
    _i("Subscrito", "subscrito", "ED-02", TEXTO),
    _i("Aumentar fonte", "aumentar_fonte", "ED-02", TEXTO),
    _i("Diminuir fonte", "diminuir_fonte", "ED-02", TEXTO),
    _i("Cor…", "cor", "ED-02", TEXTO),
    _sub("Realce", "ED-02", tuple(_i(rotulo, f"realce_{rotulo.lower()}", "ED-02", TEXTO) for rotulo, _c in REALCES)
         + (_i("Nenhum", "realce_nenhum", "ED-02", TEXTO),), TEXTO),
    SEP,
    _i("Parágrafo…", "paragrafo", "ED-02", TEXTO),
    _sub("Alinhar", "ED-02", (
        _i("Esquerda", "alinhar_esquerda", "ED-02", TEXTO),
        _i("Centro", "alinhar_centro", "ED-02", TEXTO),
        _i("Direita", "alinhar_direita", "ED-02", TEXTO),
        _i("Justificar", "justificar", "ED-02", TEXTO),
    ), TEXTO),
    _i("Recuar", "recuar", "ED-02", TEXTO),
    _i("Diminuir recuo", "diminuir_recuo", "ED-02", TEXTO),
    _sub("Entrelinha", "ED-02", (
        _i("Simples", "entrelinha_1", "ED-02", TEXTO),
        _i("1,5 linha", "entrelinha_15", "ED-02", TEXTO),
        _i("Dupla", "entrelinha_2", "ED-02", TEXTO),
    ), TEXTO),
    _i("Marcadores", "marcadores", "ED-02", TEXTO),
    _i("Numeração", "numeracao", "ED-02", TEXTO),
    SEP,
    _sub("Estilo", "ED-02", tuple(_i(ROTULOS_DOS_ESTILOS[e], f"estilo_{e}", "ED-02", TEXTO) for e in ESTILOS),
         TEXTO),
    _sub("Aplicar estilo de caractere", "ED-02",
         tuple(_i(e, f"caractere_{e.lower()}", "ED-02", TEXTO) for e in ESTILOS_DE_CARACTERE), TEXTO),
    _i("Novo estilo a partir da seleção…", "novo_estilo", "ED-02", TEXTO),
    _i("Modificar estilo…", "modificar_estilo", "ED-02", TEXTO),
    _i("Selecionar tudo com este estilo", "selecionar_com_estilo", "ED-02", TEXTO),
    _i("Limpar formatação de caractere", "limpar_caractere", "ED-02", TEXTO),
    _i("Limpar formatação de parágrafo", "limpar_paragrafo", "ED-02", TEXTO),
    SEP,
    _i("Propriedades do objeto…", "propriedades_do_objeto", "ED-04", TEXTO),
    _i("Propriedades do diagrama…", "editar_posicao", "ED-05", TEXTO, alias_de="editar_posicao"),
    # -- ED-04: o submenu Tabela (§8.6) --------------------------------------------------
    _sub("Tabela", "ED-04", (
        _i("Inserir fila acima", "tabela_fila_acima", "ED-04", TEXTO),
        _i("Inserir fila abaixo", "tabela_fila_abaixo", "ED-04", TEXTO),
        _i("Inserir coluna à esquerda", "tabela_coluna_esquerda", "ED-04", TEXTO),
        _i("Inserir coluna à direita", "tabela_coluna_direita", "ED-04", TEXTO),
        _i("Excluir fila", "tabela_excluir_fila", "ED-04", TEXTO),
        _i("Excluir coluna", "tabela_excluir_coluna", "ED-04", TEXTO),
        _i("Primeira fila é cabeçalho", "tabela_cabecalho", "ED-04", TEXTO),
        _i("Excluir tabela", "tabela_excluir", "ED-04", TEXTO),
    ), TEXTO),
    _i("Folhas de estilo do livro…", "folhas_de_estilo", "ED-08"),
    # -- fora da §7.3: a ação principal da ilha tem item (toda ação de contexto tem item; ED-04) --
    SEP,
    _i("Editar ilha de XHTML…", "editar_ilha", "ED-04", TEXTO),
    _i("Apagar nota", "apagar_nota", "ED-04", TEXTO),
)

XADREZ = (
    _i("Inserir diagrama…", "inserir_diagrama", "ED-05"),
    _i("Editar posição…", "editar_posicao", "ED-05"),
    _i("Diagrama a partir dos lances", "diagrama_dos_lances", "ED-05"),
    _i("Girar", "girar_diagrama", "ED-05"),
    _i("Coordenadas", "coordenadas_do_diagrama", "ED-05"),
    _sub("Lado a jogar", "ED-05", _placeholder("ED-05")),
    _i("Marcas e setas…", "marcas_e_setas", "ED-05b"),
    SEP,
    _i("Validar notação", "validar_notacao", "ED-05"),
    _check("Figurinas ao digitar", "figurinas_ao_digitar", "figurinas_ao_digitar", "ED-05"),
    _sub("Figurinas ↔ letras", "ED-05", _placeholder("ED-05")),
    _i("Marcar lances", "marcar_lances", "ED-05"),
    _i("Marcar NAGs", "marcar_nags", "ED-05"),
    _i("Marcar jogador/abertura…", "marcar_jogador", "ED-05"),
    _sub("Numerar", "ED-05", _placeholder("ED-05")),
    _i("Cabeçalho em legenda", "cabecalho_em_legenda", "ED-05"),
    _i("Legenda sugerida", "legenda_sugerida", "ED-05b"),
    SEP,
    _i("Paleta de figurinas", "paleta_de_figurinas", "ED-05"),
    _i("Paleta de NAGs", "paleta_de_nags", "ED-05"),
    _i("Fonte dos símbolos…", "fonte_dos_simbolos", "ED-05"),
    _i("Fonte de diagrama do livro…", "fonte_de_diagrama", "ED-05"),
    _i("Chave de símbolos", "chave_de_simbolos", "ED-05b"),
    SEP,
    _sub("Índice", "ED-12", _placeholder("ED-12")),
    _i("Exportar PGN do capítulo…", "exportar_pgn", "ED-12"),
)

FERRAMENTAS = (
    _i("Verificar ortografia…", "ortografia", "ED-06"),
    _i("Dicionário do livro…", "dicionario", "ED-06"),
    _i("Tipografia…", "tipografia", "ED-06b"),
    _i("Juntar palavras hifenizadas", "juntar_hifenizadas", "ED-06b"),
    SEP,
    _i("Contagem de palavras", "contagem", "ED-02"),
    _i("Estatísticas do livro…", "estatisticas", "ED-06"),
    _i("Buscas salvas…", "buscas_salvas", "ED-06b"),
    _sub("Relatórios", "ED-08", _placeholder("ED-08")),
    SEP,
    _i("Verificar bem-formado", "bem_formado", "ED-02", CODIGO),
    _i("Consertar HTML", "consertar", "ED-02", CODIGO),
    _i("Reformatar XHTML", "reformatar", "ED-02", CODIGO),
    _i("Reformatar CSS", "reformatar_css", "ED-02", CODIGO),
    _i("Validar EPUB", "validar_epub", "ED-08"),
    SEP,
    _i("Apagar recursos não usados…", "apagar_recursos", "ED-08"),
    _i("Apagar classes CSS não usadas…", "apagar_classes", "ED-08"),
    _i("Clipes…", "clipes", "ED-02"),
)

LIVRO = (
    _i("Metadados…", "metadados", "ED-02"),
    _i("Capa…", "capa", "ED-08"),
    _sub("Sumário", "ED-08", (
        _i("Gerar…", "sumario_gerar", "ED-08"),
        _i("Editar…", "sumario_editar", "ED-08"),
        _i("Gravar", "sumario_gravar", "ED-08"),
    )),
    _sub("Semântica do capítulo", "ED-08", _placeholder("ED-08")),
    _i("Marcos…", "marcos", "ED-08"),
    _i("Vincular folhas de estilo…", "vincular_folhas", "ED-08"),
    SEP,
    _i("Adicionar arquivo…", "adicionar_arquivo", "ED-08"),
    _i("Adicionar cópia", "adicionar_copia", "ED-08"),
    _i("Novo capítulo", "novo_capitulo", "ED-08"),
    _i("Nova folha de estilo", "nova_folha", "ED-08"),
    _i("Renomear…", "renomear", "ED-08"),
    _i("Renomear vários…", "renomear_varios", "ED-08"),
    _i("Excluir", "excluir", "ED-08"),
    _i("Mover para cima", "mover_para_cima", "ED-08"),
    _i("Mover para baixo", "mover_para_baixo", "ED-08"),
    SEP,
    _i("Juntar com o anterior", "juntar_com_anterior", "ED-04"),
    _i("Juntar em capítulos por título…", "juntar_por_titulo", "ED-10"),
    _i("Dividir em capítulos por título…", "dividir_por_titulo", "ED-10"),
    _i("Dividir nos marcadores", "dividir_nos_marcadores", "ED-10"),
    _i("Ordenar por nome", "ordenar_por_nome", "ED-08"),
    _i("Abrir com…", "abrir_com", "ED-08"),
    SEP,
    _i("Formato de página…", "formato_de_pagina", "ED-12"),
)

AJUDA = (
    _i("Atalhos de teclado…", "atalhos"),
    _i("O dialeto do livro", "dialeto"),
    _i("Sobre", "sobre"),
)

#: (rótulo do menu, itens), na ordem da barra.
MENUS: tuple[tuple[str, tuple[Item, ...]], ...] = (
    ("Arquivo", ARQUIVO), ("Editar", EDITAR), ("Exibir", EXIBIR), ("Inserir", INSERIR), ("Formatar", FORMATAR),
    ("Xadrez", XADREZ), ("Ferramentas", FERRAMENTAS), ("Livro", LIVRO), ("Ajuda", AJUDA),
)

#: O menu de contexto de cada modo: nomes de comando (e "-" para separador), todos com item na barra.
CONTEXTO = {
    "texto": ("desfazer", "refazer", "-", "recortar", "copiar", "colar", "colar_sem_formatacao", "colar_como_xhtml",
              "-", "selecionar_tudo", "selecionar_paragrafo", "-", "negrito", "italico", "sublinhado", "-",
              "seguir_link", "editar_ilha", "propriedades_do_objeto"),
    "codigo": ("desfazer", "refazer", "-", "recortar", "copiar", "colar", "-", "selecionar_tudo", "-",
               "comentar", "reformatar", "bem_formado", "consertar", "-", "ir_ao_alvo"),
}


# ----------------------------------------------------------------------
# Consultas
# ----------------------------------------------------------------------

def todos_os_itens(itens: Sequence[Item] | None = None) -> list[Item]:
    """Os itens de comando e de check, recursivamente, de `itens` (ou de toda a barra)."""
    saida: list[Item] = []
    fontes = [itens] if itens is not None else [i for _r, i in MENUS]
    for grupo in fontes:
        for item in grupo:
            if item.tipo in ("comando", "check"):
                saida.append(item)
            elif item.tipo == "submenu":
                saida.extend(todos_os_itens(item.filhos))
    return saida


def item_de(comando: str) -> Item | None:
    """O lar do comando: o primeiro item com esse comando que não é alias."""
    candidatos = [i for i in todos_os_itens() if i.comando == comando]
    for i in candidatos:
        if not i.alias_de:
            return i
    return candidatos[0] if candidatos else None


def _mnemonicos(itens: Sequence[Item]) -> list[int]:
    """A posição sublinhada de cada item (−1 para separador), única no menu quando dá."""
    usadas: set[str] = set()
    saida: list[int] = []
    for item in itens:
        if item.tipo == "separador":
            saida.append(-1)
            continue
        rotulo = item.rotulo
        escolhida = -1
        if item.mnemonico:
            escolhida = rotulo.lower().find(item.mnemonico.lower())
        if escolhida < 0:
            livres = [k for k, c in enumerate(rotulo) if c.isalpha() and c not in LETRAS_PROIBIDAS
                      and c.lower() not in usadas]
            permitidas = [k for k, c in enumerate(rotulo) if c.isalpha() and c not in LETRAS_PROIBIDAS]
            escolhida = livres[0] if livres else (permitidas[0] if permitidas else -1)
        if escolhida >= 0:
            usadas.add(rotulo[escolhida].lower())
        saida.append(escolhida)
    return saida


def verificar() -> list[str]:
    """As regras da §7.3 sobre a tabela: mnemônicos, lares e aliases. Vazio é o que se quer."""
    problemas: list[str] = []
    for rotulo, itens in MENUS:
        letra = MNEMONICOS_DOS_MENUS[rotulo]
        if letra in LETRAS_PROIBIDAS or letra.lower() not in rotulo.lower():
            problemas.append(f"mnemônico do menu {rotulo!r}: {letra!r}")
        pilha = [(itens, rotulo)]
        while pilha:
            grupo, caminho = pilha.pop()
            for item, posicao in zip(grupo, _mnemonicos(grupo)):
                if item.tipo == "separador":
                    continue
                if posicao < 0 or item.rotulo[posicao] in LETRAS_PROIBIDAS:
                    problemas.append(f"{caminho} → {item.rotulo}: sem mnemônico permitido")
                if item.tipo == "submenu":
                    pilha.append((item.filhos, f"{caminho} → {item.rotulo}"))
    lares: dict[str, Item] = {}
    for item in todos_os_itens():
        if not item.comando:
            continue
        if item.alias_de:
            if item.alias_de != item.comando and item_de(item.alias_de) is None:
                problemas.append(f"{item.rotulo}: alias de {item.alias_de!r}, que não existe")
            continue
        if item.comando in lares and lares[item.comando].rotulo != item.rotulo:
            problemas.append(f"{item.rotulo!r} e {lares[item.comando].rotulo!r}: dois lares para {item.comando!r}")
        lares.setdefault(item.comando, item)
    for modo, nomes in CONTEXTO.items():
        for nome in nomes:
            if nome != "-" and item_de(nome) is None:
                problemas.append(f"contexto ({modo}): {nome!r} não tem item de menu")
    return problemas


# ----------------------------------------------------------------------
# Montagem
# ----------------------------------------------------------------------

class Menus:
    """
    A barra montada: `barra` (o `tk.Menu`), `mapa` `(menu, índice) → nome do comando`,
    `atualizar(modo)` para habilitar o que existe no modo, e o menu de contexto.

    `janela` fornece `comandos`, `modos_do_comando`, `executar(nome)`, `variaveis`,
    `itens_dinamicos` e `status(texto)`.
    """

    def __init__(self, janela: Any, comandos: dict[str, Callable[..., Any]] | None = None,
                 tabela: Sequence[tuple[str, tuple[Item, ...]]] = MENUS):
        self.janela = janela
        self.comandos = comandos if comandos is not None else janela.comandos
        self.tabela = tabela
        self.barra = tk.Menu(janela, tearoff=0)
        self.mapa: dict[tuple[tk.Menu, int], str] = {}
        self.itens: dict[str, list[tuple[tk.Menu, int, Item]]] = {}
        self.menus: dict[str, tk.Menu] = {}
        self._contexto: tk.Menu | None = None
        for rotulo, itens in tabela:
            menu = tk.Menu(self.barra, tearoff=0)
            self._preencher(menu, itens)
            self.barra.add_cascade(label=rotulo, menu=menu, underline=rotulo.lower().find(
                MNEMONICOS_DOS_MENUS.get(rotulo, "").lower()))
            self.menus[rotulo] = menu

    def _preencher(self, menu: tk.Menu, itens: Sequence[Item]) -> None:
        menu.bind("<<MenuSelect>>", self._ao_percorrer)
        for item, posicao in zip(itens, _mnemonicos(itens)):
            if item.tipo == "separador":
                menu.add_separator()
                continue
            comuns: dict[str, Any] = {"label": item.rotulo, "underline": posicao}
            if item.tipo == "submenu":
                sub = tk.Menu(menu, tearoff=0)
                if item.dinamico:
                    sub.configure(postcommand=lambda s=sub, n=item.dinamico: self._preencher_dinamico(s, n))
                    sub.add_command(label="(vazio)", state="disabled")
                else:
                    self._preencher(sub, item.filhos)
                menu.add_cascade(menu=sub, **comuns)
                self._registrar(menu, item)
                continue
            comuns["accelerator"] = atalhos_mod.acelerador(item.comando) if item.comando else ""
            comuns["command"] = (lambda n=item.comando: self.janela.executar(n)) if item.comando else None
            if item.tipo == "check":
                variavel = self.janela.variaveis.setdefault(item.check, tk.BooleanVar(master=self.janela,
                                                                                       value=False))
                menu.add_checkbutton(variable=variavel, onvalue=True, offvalue=False, **comuns)
            else:
                menu.add_command(**comuns)
            self._registrar(menu, item)

    def _registrar(self, menu: tk.Menu, item: Item) -> None:
        indice = menu.index("end")
        self.mapa[(menu, indice)] = item.nome
        self.itens.setdefault(item.nome, []).append((menu, indice, item))

    def _preencher_dinamico(self, sub: tk.Menu, nome: str) -> None:
        sub.delete(0, "end")
        entradas = []
        preencher = getattr(self.janela, "itens_dinamicos", {}).get(nome)
        if preencher is not None:
            try:
                entradas = list(preencher())
            except Exception as erro:      # noqa: BLE001 — um submenu que falha ao abrir não derruba a barra
                entradas = [(f"(erro: {erro})", None)]
        if not entradas:
            sub.add_command(label="(vazio)", state="disabled")
            return
        for rotulo, acao in entradas:
            sub.add_command(label=rotulo, command=acao, state="normal" if acao else "disabled")

    # -- estado --------------------------------------------------------------

    def disponivel(self, item: Item, modo: str) -> bool:
        if item.tipo == "submenu":
            return True
        if not item.comando or modo not in item.modos:
            return False
        if item.comando not in self.comandos:
            return False
        modos = getattr(self.janela, "modos_do_comando", {}).get(item.comando)
        return modos is None or modo in modos

    def motivo(self, item: Item, modo: str) -> str:
        """O que a barra de status diz de um item desabilitado."""
        if not item.comando:
            return f"{item.rotulo}: chega na {item.fase}"
        if modo not in item.modos:
            outro = "código" if modo == "texto" else "texto"
            return f"{item.rotulo}: só no modo {outro}"
        if item.comando not in self.comandos:
            return f"{item.rotulo}: chega na {item.fase}"
        modos = getattr(self.janela, "modos_do_comando", {}).get(item.comando)
        if modos is not None and modo not in modos:
            nome_do_modo = "texto" if modo == "texto" else "código"
            return f"{item.rotulo}: no modo {nome_do_modo} chega na {item.fase}"
        return ""

    def atualizar(self, modo: str) -> None:
        """Habilita o que existe no modo e refaz o acelerador (que pode mudar com o modo)."""
        for nome, entradas in self.itens.items():
            for menu, indice, item in entradas:
                if item.tipo == "separador":
                    continue
                estado = "normal" if self.disponivel(item, modo) else "disabled"
                opcoes: dict[str, Any] = {"state": estado}
                if item.comando and item.tipo != "submenu":
                    opcoes["accelerator"] = acelerador_no_modo(item.comando, modo)
                try:
                    menu.entryconfigure(indice, **opcoes)
                except tk.TclError:
                    pass

    def _ao_percorrer(self, evento: Any) -> None:
        """
        `<<MenuSelect>>`: o Tk não ativa entrada desabilitada (`activate` numa delas
        deixa a ativa em `none`), então a entrada sob o mouse vem de `@y` — o `y` do
        evento, ou o do ponteiro.
        """
        menu = evento.widget
        try:
            indice = menu.index("active")
            if indice is None or indice == "none":
                y = getattr(evento, "y", None)
                if y is None or y < 0:
                    y = menu.winfo_pointery() - menu.winfo_rooty()
                indice = menu.index(f"@{int(y)}") if y is not None and y >= 0 else None
        except tk.TclError:
            return
        if indice is None or indice == "none":
            return
        nome = self.mapa.get((menu, int(indice)))
        if nome is None:
            return
        for m, i, item in self.itens.get(nome, ()):
            if m is menu and i == int(indice):
                modo = self.janela.modo_atual() if hasattr(self.janela, "modo_atual") else "texto"
                if not self.disponivel(item, modo):
                    self.janela.status(self.motivo(item, modo))
                elif item.comando:
                    atalho = acelerador_no_modo(item.comando, modo)
                    self.janela.status(f"{item.rotulo}" + (f"  ({atalho})" if atalho else ""))
                return

    def lar(self, nome: str) -> tuple[tk.Menu, int, Item]:
        """A entrada que é o lar do comando (a que não é alias); `KeyError` se não há item."""
        entradas = [e for e in self.itens.get(nome, ()) if e[2].tipo in ("comando", "check")]
        if not entradas:
            raise KeyError(f"não há item de menu para {nome!r}")
        return next((e for e in entradas if not e[2].alias_de), entradas[0])

    def invocar(self, nome: str) -> None:
        """Invoca o lar do comando pelo menu — é o caminho do teste (AC-ED02-1)."""
        menu, indice, _item = self.lar(nome)
        menu.invoke(indice)

    def estado(self, nome: str) -> str:
        menu, indice, _item = self.lar(nome)
        return str(menu.entrycget(indice, "state"))

    # -- contexto ------------------------------------------------------------

    def contexto(self, modo: str) -> tk.Menu:
        """O menu de contexto do modo, montado da tabela (`CONTEXTO`); um `tk.Menu` novo a cada chamada."""
        if self._contexto is not None:
            try:
                self._contexto.destroy()
            except tk.TclError:
                pass
        menu = tk.Menu(self.janela, tearoff=0)
        for nome in CONTEXTO.get(modo, ()):
            if nome == "-":
                menu.add_separator()
                continue
            item = item_de(nome)
            if item is None:
                continue
            menu.add_command(label=item.rotulo, accelerator=acelerador_no_modo(nome, modo),
                             command=lambda n=nome: self.janela.executar(n),
                             state="normal" if self.disponivel(item, modo) else "disabled")
        self._contexto = menu
        return menu


def acelerador_no_modo(comando: str, modo: str) -> str:
    """O atalho do comando **neste modo**; sem um deste modo, o primeiro que houver."""
    for a in atalhos_mod.TABELA:
        if a.comando == comando and a.tipo == "comando" and modo in a.modos:
            return a.atalho
    return atalhos_mod.acelerador(comando)


def montar(janela: Any, comandos: dict[str, Callable[..., Any]] | None = None) -> tuple[tk.Menu, dict]:
    """`(barra, mapa)` — o contrato do roadmap; a instância inteira fica em `janela.menus`."""
    menus = Menus(janela, comandos)
    janela.menus = menus
    return menus.barra, menus.mapa


__all__ = ["Item", "MENUS", "CONTEXTO", "LETRAS_PROIBIDAS", "MNEMONICOS_DOS_MENUS", "Menus", "montar",
           "todos_os_itens", "item_de", "verificar", "acelerador_no_modo", "ESTILOS", "ROTULOS_DOS_ESTILOS",
           "ESTILOS_DE_CARACTERE", "REALCES"]
