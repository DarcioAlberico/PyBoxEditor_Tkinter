"""
Sanidade da base de treino.

Existe porque um defeito passou meses despercebido: a pasta `sym_f7` guardava
127 imagens da casa de xadrez "f7", mas `chr(int("f7"))` levanta ValueError e o
código devolvia "?" em silêncio. Resultado: 127 amostras ensinando o modelo a
prever "?", numa classe separada da `sym_63`, que é o "?" de verdade.

Nada disso aparecia em lugar nenhum — o treino rodava, reportava acurácia alta
e seguia em frente. Daí a regra: **problema de dados falha alto, antes do
treino**, em vez de virar ruído no modelo.
"""

import glob
import os
from dataclasses import dataclass
from typing import List, Optional

import cv2
import numpy as np

from core.learner import NomeDePastaInvalido, char_to_folder, folder_to_char


MIN_AMOSTRAS_POR_CLASSE = 10

# Arquivos suspeitos vão para cá em vez de serem apagados. Começa com '_' para
# não ser confundido com uma classe (as classes não têm esse prefixo).
PASTA_QUARENTENA = "_quarentena"


@dataclass
class Problema:
    tipo: str          # nome_invalido | pasta_vazia | colisao | poucas_amostras | png_ilegivel
    pasta: str
    detalhe: str
    grave: bool = True   # grave impede o treino; não-grave é aviso

    def __str__(self):
        marca = "ERRO " if self.grave else "aviso"
        return f"[{marca}] {self.pasta}: {self.detalhe}"


@dataclass
class Acao:
    """Uma correção proposta pela migração."""
    tipo: str          # renomear | mesclar | remover_pasta | remover_arquivo
    origem: str
    destino: Optional[str] = None
    motivo: str = ""

    def __str__(self):
        alvo = f" -> {self.destino}" if self.destino else ""
        return f"{self.tipo}: {self.origem}{alvo}  ({self.motivo})"


def _pngs(caminho: str) -> List[str]:
    return glob.glob(os.path.join(caminho, "*.png"))


def png_legivel(caminho: str) -> bool:
    """
    Verdadeiro se o arquivo é um PNG decodificável.

    NÃO usa cv2.imread: no Windows ele falha em caminhos não-ASCII e devolve
    None — o mesmo resultado de um arquivo corrompido. Confundir as duas coisas
    custou caro: a primeira versão desta migração marcou como "ilegíveis" 7
    PNGs perfeitamente válidos que estavam numa pasta chamada 'lower_ä', e os
    apagou. Ler os bytes em Python e decodificar da memória separa "não
    consegui abrir o caminho" de "não é uma imagem".
    """
    try:
        with open(caminho, "rb") as f:
            dados = f.read()
    except OSError:
        return False
    if not dados:
        return False
    return cv2.imdecode(np.frombuffer(dados, dtype=np.uint8),
                        cv2.IMREAD_GRAYSCALE) is not None


def _classes(data_dir: str) -> List[str]:
    if not os.path.isdir(data_dir):
        return []
    return sorted(d for d in os.listdir(data_dir)
                  if os.path.isdir(os.path.join(data_dir, d))
                  and not d.startswith("_"))


def nome_canonico(pasta: str) -> Optional[str]:
    """
    Nome que a pasta deveria ter. None se o nome não é decodificável.

    É o teste de ida e volta: decodifica o nome para caractere e recodifica.
    Se não bate, a pasta está num formato que o código de escrita não produz
    mais — e amostras novas do mesmo caractere iriam parar noutra pasta,
    partindo a classe em duas.
    """
    try:
        char = folder_to_char(pasta, strict=True)
    except NomeDePastaInvalido:
        return None
    if not char:
        return None
    return char_to_folder(char)


def validar_dataset(data_dir: str, min_amostras: int = MIN_AMOSTRAS_POR_CLASSE,
                    checar_pngs: bool = True) -> List[Problema]:
    """Lista tudo que está errado na base. Vazio = pode treinar."""
    problemas: List[Problema] = []
    por_caractere = {}

    for pasta in _classes(data_dir):
        caminho = os.path.join(data_dir, pasta)
        arquivos = _pngs(caminho)

        canonico = nome_canonico(pasta)
        if canonico is None:
            problemas.append(Problema(
                "nome_invalido", pasta,
                f"não corresponde a nenhum caractere ({len(arquivos)} amostras "
                "seriam treinadas como '?')"))
            continue

        if canonico != pasta:
            problemas.append(Problema(
                "nome_invalido", pasta,
                f"formato antigo; o código atual gravaria em '{canonico}', "
                "partindo a classe em duas"))

        char = folder_to_char(pasta)
        por_caractere.setdefault(char, []).append(pasta)

        if not arquivos:
            problemas.append(Problema(
                "pasta_vazia", pasta,
                "sem amostras, mas ocupa um índice de classe"))
            continue

        if len(arquivos) < min_amostras:
            problemas.append(Problema(
                "poucas_amostras", pasta,
                f"{len(arquivos)} amostras (mínimo {min_amostras})",
                grave=False))

        if checar_pngs:
            for arq in arquivos:
                if not png_legivel(arq):
                    problemas.append(Problema(
                        "png_ilegivel", pasta,
                        f"não foi possível ler {os.path.basename(arq)}"))

    for char, pastas in por_caractere.items():
        if len(pastas) > 1:
            problemas.append(Problema(
                "colisao", ", ".join(pastas),
                f"{len(pastas)} pastas para o mesmo caractere {char!r}"))

    if checar_pngs:
        # Junto do `checar_pngs` porque tem o mesmo custo: ler a base inteira.
        # Em 151 mil amostras são ~18 s, e `LearningService.validar_dados`
        # desliga essa varredura de propósito para o caminho rápido.
        problemas.extend(rotulos_contraditorios(data_dir))
    return problemas


def rotulos_contraditorios(data_dir: str, limite: int = 12) -> List[Problema]:
    """
    A **mesma imagem**, byte a byte, rotulada de duas formas.

    Achado ao montar a matriz do k-NN (F7.2): na base real são 16 casos, e não
    são aleatórios — `0`/`o`, `1`/`l`, `4`/`d`. São os homóglifos que a medição
    da F3.6 já tinha isolado, aqui em sua forma mais dura: depois do recorte na
    moldura do glifo e do redimensionamento para 32x32, o que distinguia os dois
    caracteres não existe mais, e alguém rotulou o mesmo pixel de dois jeitos.

    **Não é grave, e o motivo importa.** Nenhum treino melhora removendo um dos
    lados: os dois rótulos estão certos para *alguma* ocorrência daquele
    desenho. O que o classificador não tem é como escolher — quem escolhe é o
    contexto, que é trabalho da F1.7. Reportar serve para o número parar de
    surpreender, não para virar tarefa.
    """
    porimagem = {}
    for pasta in _classes(data_dir):
        char = folder_to_char(pasta)
        for arq in _pngs(os.path.join(data_dir, pasta)):
            img = cv2.imread(arq, cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue
            if img.shape != (32, 32):
                img = cv2.resize(img, (32, 32))
            porimagem.setdefault(img.tobytes(), set()).add(char)

    pares = {}
    for rotulos in porimagem.values():
        if len(rotulos) > 1:
            pares[tuple(sorted(rotulos))] = pares.get(tuple(sorted(rotulos)), 0) + 1

    if not pares:
        return []

    maiores = sorted(pares.items(), key=lambda kv: -kv[1])[:limite]
    detalhe = ", ".join(f"{'/'.join(p)} ({n})" for p, n in maiores)
    if len(pares) > limite:
        detalhe += f" e mais {len(pares) - limite}"
    return [Problema(
        "rotulo_contraditorio", "(base inteira)",
        f"{sum(pares.values())} imagem(ns) idêntica(s) com rótulos diferentes: "
        f"{detalhe}", grave=False)]


def planejar_migracao(data_dir: str) -> List[Acao]:
    """Correções necessárias, sem aplicar nada."""
    acoes: List[Acao] = []
    existentes = set(_classes(data_dir))

    for pasta in sorted(existentes):
        caminho = os.path.join(data_dir, pasta)
        arquivos = _pngs(caminho)

        for arq in arquivos:
            if not png_legivel(arq):
                acoes.append(Acao("quarentena", os.path.join(pasta, os.path.basename(arq)),
                                  motivo="PNG ilegível"))

        if not arquivos:
            acoes.append(Acao("remover_pasta", pasta,
                              motivo="vazia, ocupa índice de classe à toa"))
            continue

        canonico = nome_canonico(pasta)
        if canonico is None or canonico == pasta:
            continue

        tipo = "mesclar" if canonico in existentes else "renomear"
        acoes.append(Acao(tipo, pasta, canonico,
                          motivo=f"nome antigo de {folder_to_char(pasta)!r}"))

    return acoes


def aplicar_migracao(data_dir: str, acoes: List[Acao]) -> List[str]:
    """Executa as ações. Devolve o registro do que foi feito."""
    import shutil
    import uuid

    feito = []
    for a in acoes:
        origem = os.path.join(data_dir, a.origem)
        try:
            if a.tipo == "quarentena":
                # Mover, não apagar. Uma migração que deleta arquivo do usuário
                # precisa errar para o lado seguro: se a detecção estiver
                # errada, o dado ainda está lá para ser recuperado.
                quarentena = os.path.join(data_dir, PASTA_QUARENTENA)
                os.makedirs(quarentena, exist_ok=True)
                shutil.move(origem, os.path.join(
                    quarentena, f"{a.origem.replace(os.sep, '_')}"))
            elif a.tipo == "remover_pasta":
                os.rmdir(origem)
            elif a.tipo == "renomear":
                os.rename(origem, os.path.join(data_dir, a.destino))
            elif a.tipo == "mesclar":
                destino = os.path.join(data_dir, a.destino)
                os.makedirs(destino, exist_ok=True)
                for arq in _pngs(origem):
                    # Nome novo: os arquivos são UUID, mas colisão sairia cara
                    # (perda silenciosa de amostra).
                    shutil.move(arq, os.path.join(destino, f"{uuid.uuid4()}.png"))
                os.rmdir(origem)
            else:
                continue
            feito.append(str(a))
        except OSError as e:
            feito.append(f"FALHOU {a}: {e}")
    return feito
