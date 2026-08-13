"""
Coleta dos recortes que o modelo não soube ler (F2.7).

Quando o livro inteiro passa pela extração, o modelo já diz onde é fraco: são os
caracteres abaixo do piso de confiança. Medido no Chess Evolution 1, **3.943
deles em 264 páginas** — material de treino que hoje é jogado fora e que teria
de ser recaçado na tela, um a um.

**A quarentena não é zelo, é a única forma correta de fazer isto.** O recorte de
baixa confiança é, por definição, aquele em que o modelo errou ou hesitou.
Gravá-lo em `training_data/<palpite>/` seria treinar o modelo no próprio erro —
e este projeto tem cicatriz dessa classe de defeito: o `folder_to_char`
documenta que devolver "?" em silêncio "permitiu 127 amostras treinarem a classe
errada sem ninguém notar", e a suíte tem uma guarda de sessão inteira contra
gravação indevida na base de ocupação.

Então o fluxo tem duas etapas, e a do meio é humana:

    extração  ->  revisao_ocr/<palpite>/  ->  [você olha]  ->  training_data/

Corrigir um rótulo é **mover o arquivo de pasta**; descartar é apagá-lo. O
`promover` lê o nome da pasta como rótulo, então o que você fizer com o mouse é
o que entra na base.
"""

import csv
import os
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import cv2
import numpy as np

from core.learner import CharacterLearner, char_to_folder, folder_to_char


#: Onde a quarentena mora. Fora de `training_data` de propósito: uma pasta que o
#: treino varre não pode conter amostra por conferir.
PASTA_PADRAO = "revisao_ocr"

#: O índice, ao lado dos recortes.
NOME_DO_INDICE = "indice.csv"

#: Teto por classe. `None` — o padrão — **não limita**.
#:
#: Uma classe ruim inunda a pasta e esconde as outras, e revisar 4.000 recortes
#: de `o` não ensina mais que revisar algumas centenas: é para isso que o teto
#: existe, e ele ainda mantém a revisão balanceada, que é o que o treino quer.
#:
#: Só que **quanto** é demais depende do que se está fazendo, e os dois usos são
#: opostos: bater o olho numa grade de miniaturas cansa em algumas centenas por
#: classe, enquanto engordar a base com um livro inteiro quer tudo o que ele
#: tiver. Um número fixo aqui decidia isso por quem coleta e jogava fora o resto
#: em silêncio — o preço de rodar o livro todo de novo para conseguir o que já
#: passara pela extração uma vez. Agora o teto é escolhido na hora, e **não
#: escolher nada é não ter teto**: o padrão nunca descarta.
MAX_POR_CLASSE: Optional[int] = None

#: Confiança abaixo da qual o recorte é guardado. `None` guarda **todos**.
#:
#: As duas revisões são diferentes e as duas servem:
#:
#: - **só os duvidosos** mostra onde o modelo é fraco. É o material de treino
#:   mais denso, mas a pasta fica sem contraste: se quase tudo ali está errado,
#:   não há o que comparar.
#: - **todos** enche a pasta de acertos com alguns intrusos no meio, que é
#:   exatamente a forma de achar erro batendo o olho numa grade de miniaturas.
#:
#: A segunda opção é a que pede teto: um livro inteiro dá ~260 mil recortes, e
#: algumas centenas por classe já são mais do que se olha de uma vez. Quem está
#: engordando a base, porém, quer justamente os 260 mil — ver `MAX_POR_CLASSE`.
LIMIAR_PADRAO = 0.5

COLUNAS = ["arquivo", "palpite", "confianca", "pagina", "origem"]

#: O que se escreve no campo do teto para dizer "não limite". Vazio é o
#: principal; o resto é para quem prefere escrever a palavra a apagar o campo.
SEM_TETO = {"-", "ilimitado", "sem limite", "sem teto", "tudo", "todos", "nenhum"}


def teto_de_texto(texto: Optional[str]) -> Optional[int]:
    """
    Lê o teto por classe do que foi digitado. Em branco é sem teto.

    **Campo de texto, e não `askinteger`, porque "sem teto" precisa ser
    dizível.** O `askinteger` devolve o mesmo `None` para campo vazio e para o
    botão Cancelar, e por ali "não quero limite" e "desisti" viram a mesma
    coisa — o pior par possível de confundir, porque um manda gravar 260 mil
    recortes e o outro manda não gravar nenhum.

    O que não é número é **recusado, não adivinhado**, pelo mesmo motivo que o
    `folder_to_char` tem modo estrito: um `l` digitado no lugar do `1` viraria
    ilimitado calado, e o disco só contaria a história no fim do livro.
    """
    if texto is None:
        return None
    limpo = texto.strip().lower()
    if not limpo or limpo in SEM_TETO:
        return None
    # Separador de milhar sai: quem digita um teto grande escreve "5.000", e
    # recusar isso seria implicância com a mão de quem revisa.
    numero = limpo.replace(".", "").replace(",", "").replace(" ", "")
    # `isascii` junto porque `isdigit` aceita '²' e '٣', que o `int` recusa: a
    # recusa tem de sair daqui com a mensagem, e não como traceback lá dentro.
    if not (numero.isascii() and numero.isdigit()):
        raise ValueError(f"{texto.strip()!r} não é um número de recortes.")
    # Zero cai no mesmo lugar que o campo vazio; ver `Coletor.__post_init__`.
    return int(numero) or None


@dataclass
class Coletor:
    """
    Recebe os recortes reprovados e os grava para revisão.

    Tem a forma de um `callable` porque é assim que a extração o usa: ela chama
    `coletor(recorte, palpite, confiança, página)` e não sabe — nem precisa
    saber — se ele grava em disco, conta, ou não faz nada.
    """
    pasta: str = PASTA_PADRAO
    origem: str = ""
    #: `None` não limita; um número é o máximo de recortes por classe.
    max_por_classe: Optional[int] = MAX_POR_CLASSE
    #: `None` guarda todos os recortes; um número guarda só abaixo dele.
    limiar: Optional[float] = LIMIAR_PADRAO
    gravados: Dict[str, int] = field(default_factory=dict)
    ignorados_por_teto: int = 0
    linhas: List[dict] = field(default_factory=list)

    def __post_init__(self):
        # Teto zero — ou negativo — não é teto, é desligar a coleta, e quem
        # quer desligá-la não passa coletor nenhum. Vindo de um campo em branco
        # lido como número, ou de um `0` que escapou, gravaria zero recorte e
        # chamaria isso de limite. Sem teto tem **uma** forma de se dizer aqui:
        # `None`, e é a que o resto da classe pergunta.
        if self.max_por_classe is not None and self.max_por_classe <= 0:
            self.max_por_classe = None

    def __call__(self, recorte: np.ndarray, palpite: str,
                 confianca: float, pagina: int) -> Optional[str]:
        # **Quem filtra por confiança é o coletor, não a extração.** A extração
        # entrega tudo que classificou; o que fazer com isso é política de quem
        # coleta, e é o que permite a mesma chamada servir para "só os
        # duvidosos" e para "todos, para bater o olho".
        if self.limiar is not None and confianca >= self.limiar:
            return None
        if recorte is None or getattr(recorte, "size", 0) == 0:
            return None

        classe = char_to_folder(palpite) if palpite else "unknown"
        if (self.max_por_classe is not None
                and self.gravados.get(classe, 0) >= self.max_por_classe):
            self.ignorados_por_teto += 1
            return None

        destino = os.path.join(self.pasta, classe)
        os.makedirs(destino, exist_ok=True)
        # O nome carrega página e confiança para a revisão poder ordenar por
        # "mais duvidoso primeiro" sem abrir o índice.
        nome = f"p{pagina + 1:04d}_c{int(round(confianca * 100)):03d}_{uuid.uuid4().hex[:8]}.png"
        caminho = os.path.join(destino, nome)

        imagem = recorte
        if imagem.ndim == 3:
            imagem = cv2.cvtColor(imagem, cv2.COLOR_RGB2GRAY)
        # Gravado **no tamanho em que foi recortado**, e não no da rede: quem
        # revisa precisa enxergar o glifo, e o `learn` redimensiona de novo na
        # hora de promover. Guardar já em 32 px jogaria fora o que decide a
        # dúvida.
        if not cv2.imwrite(caminho, imagem):
            return None

        self.gravados[classe] = self.gravados.get(classe, 0) + 1
        self.linhas.append({"arquivo": os.path.join(classe, nome),
                            "palpite": palpite, "confianca": round(confianca, 4),
                            "pagina": pagina + 1, "origem": self.origem})
        return caminho

    @property
    def total(self) -> int:
        return sum(self.gravados.values())

    def gravar_indice(self) -> Optional[str]:
        """O CSV ao lado dos recortes. Devolve o caminho, ou None se nada foi gravado."""
        if not self.linhas:
            return None
        os.makedirs(self.pasta, exist_ok=True)
        caminho = os.path.join(self.pasta, NOME_DO_INDICE)
        novo = not os.path.exists(caminho)
        # utf-8-sig e append: a coleta de um segundo livro soma à do primeiro em
        # vez de apagá-la, e o Excel do Windows abre sem transformar os símbolos
        # de peça em lixo.
        with open(caminho, "a", encoding="utf-8-sig", newline="") as f:
            escritor = csv.DictWriter(f, fieldnames=COLUNAS)
            if novo:
                escritor.writeheader()
            escritor.writerows(self.linhas)
        return caminho

    def resumo(self) -> str:
        if not self.total:
            return "nenhum recorte de baixa confiança"
        piores = sorted(self.gravados.items(), key=lambda kv: -kv[1])[:5]
        detalhe = " ".join(f"{folder_to_char(c)}×{n}" for c, n in piores)
        linhas = [f"{self.total} recorte(s) em {len(self.gravados)} classe(s)",
                  f"mais frequentes: {detalhe}"]
        if self.ignorados_por_teto:
            linhas.append(f"{self.ignorados_por_teto} além do teto de "
                          f"{self.max_por_classe} por classe")
        return "; ".join(linhas)


@dataclass
class Promocao:
    aprendidos: int = 0
    classes: int = 0
    ilegiveis: List[str] = field(default_factory=list)
    recusados: List[str] = field(default_factory=list)


def promover(pasta: str = PASTA_PADRAO, data_dir: str = "training_data",
             learner: Optional[CharacterLearner] = None,
             apagar: bool = False) -> Promocao:
    """
    Move o que sobreviveu à revisão para a base de treino.

    **O rótulo é o nome da pasta**, e é isso que faz a revisão ser trabalho de
    mouse: confirmar é deixar onde está, corrigir é arrastar para outra pasta,
    descartar é apagar o arquivo.

    Pasta com nome que não é rótulo é **recusada, não adivinhada** — pelo mesmo
    motivo que o modo estrito do `folder_to_char` existe: um "?" em silêncio já
    treinou 127 amostras na classe errada.

    **A checagem é de ida e volta, e não `strict=True`.** O modo estrito do
    `folder_to_char` tem um ramo final de compatibilidade — "formato antigo,
    pasta = caractere" — que devolve o nome cru sem passar pelo `falhar()`, e
    por ali uma pasta chamada `amostras soltas` vira um rótulo de quinze
    caracteres. Exigir que `char_to_folder` reconstrua o mesmo nome fecha isso
    sem mexer no comportamento de que o resto do projeto depende.
    """
    learner = learner or CharacterLearner(data_dir=data_dir)
    resultado = Promocao()
    if not os.path.isdir(pasta):
        return resultado

    for nome in sorted(os.listdir(pasta)):
        caminho = os.path.join(pasta, nome)
        if not os.path.isdir(caminho):
            continue
        try:
            char = folder_to_char(nome, strict=True)
        except Exception:
            char = ""
        if not char or char_to_folder(char) != nome:
            resultado.recusados.append(nome)
            continue

        aprendidos = 0
        for arquivo in sorted(os.listdir(caminho)):
            if not arquivo.lower().endswith(".png"):
                continue
            completo = os.path.join(caminho, arquivo)
            imagem = cv2.imread(completo, cv2.IMREAD_GRAYSCALE)
            if imagem is None:
                resultado.ilegiveis.append(completo)
                continue
            learner.learn(imagem, char)
            aprendidos += 1
            if apagar:
                try:
                    os.remove(completo)
                except OSError:
                    pass

        if aprendidos:
            resultado.aprendidos += aprendidos
            resultado.classes += 1

    return resultado
