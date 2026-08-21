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

O que a F93 mexeu, e por quê
---------------------------

A etapa do meio é humana, e é **ela** que a coleta tem de servir. A régua nova é
`medir_coleta.py`, que pergunta o que ninguém tinha perguntado: *dos arquivos
que caíram em `revisao_ocr/lower_o/`, quantos são um `o`?* Nas 10 páginas
rotuladas, no modo "todos", **93,7% certos, 2,6% lidos errado e 3,7% sem
caractere nenhum ali**.

Quatro coisas mudaram, e todas servem à etapa humana:

1. **A mesma renderização entrava muitas vezes.** Em PDF digital o mesmo glifo
   sai byte a byte igual toda vez, e a pasta de `o` enchia de cópias. Não ensina
   nada ao modelo e gasta a grade: 300 miniaturas que são a mesma miniatura são
   300 chances a menos de o intruso aparecer. Ver `_impressao`.

2. **O teto guardava os primeiros N, que são as primeiras páginas.** Teto de 300
   dava 300 `o` das páginas 1 a 5 — uma fonte, um estado de scan, um contexto —
   e o itálico da página 200, o borrado, o quebrado eram descartados em
   silêncio. Agora o teto sorteia (amostragem de reservatório), e o que fica é
   uma amostra do **livro**, não do começo dele. Ver `_vaga`.

3. **"Mais duvidoso primeiro" não funcionava.** O nome do arquivo carregava
   página e confiança nessa ordem, então clicar em Nome no Explorer ordenava por
   página. Trocadas de lugar, a ordem prometida é a que sai. Ver `_gravar`.

4. **O índice ganhou a segunda candidata.** Quem revisa e acha um recorte na
   pasta errada quer saber para onde ele ia. Ver `detalhar` — é dado no CSV, e
   **não** régua: a F47 mediu que a margem não ganha da confiança no ponto de
   operação, e nada aqui a promove a critério.

E uma quinta que **não** mudou, porque a medição não deixou: a porta que recusaria
o recorte que não é caractere. Ver o bloco de `motivo_de_recusa`.
"""

import csv
import hashlib
import os
import random
import uuid
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

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
#: A segunda opção é a que pede teto: um livro inteiro dá centenas de milhares de
#: recortes — 425.550 medidos nas 322 páginas do Benko escaneado, 1.322 por
#: página —, e algumas centenas por classe já são mais do que se olha de uma vez.
#: Quem está engordando a base, porém, quer justamente todos eles — ver
#: `MAX_POR_CLASSE`.
#:
#: A primeira rende pouco e rende denso: no mesmo livro, **4.765 recortes abaixo
#: do piso**, 1,1% da pilha e 14,8 por página.
LIMIAR_PADRAO = 0.5

COLUNAS = ["arquivo", "palpite", "confianca", "segunda", "p2", "margem",
           "pagina", "origem"]

#: O que se escreve no campo do teto para dizer "não limite". Vazio é o
#: principal; o resto é para quem prefere escrever a palavra a apagar o campo.
SEM_TETO = {"-", "ilimitado", "sem limite", "sem teto", "tudo", "todos", "nenhum"}


# ----------------------------------------------------------------------
# A porta que não paga — o instrumento fica, a conclusão é não (F93)
# ----------------------------------------------------------------------
#
# A hipótese era boa e está errada, e a medição a derrubou nas 10 páginas
# rotuladas: **o recorte que não cerca caractere é, na geometria, o mesmo que o
# que cerca.** Lado 16 contra 17, área 380 contra 380, tinta 0,505 contra 0,491,
# proporção 1,366 contra 1,364, confiança 0,997 contra 1,000 — as medianas
# coincidem em todas as réguas, e não há corte com troca acima de 1x: o melhor
# deles pega 11 espúrios e leva 49 caracteres de verdade junto.
#
# **O motivo é estrutural, e é a parte que vale guardar.** Quando esta pilha
# chega, o `caixas_e_diagramas` já tirou os respingos (abaixo de `MIN_AREA_GLIFO`)
# e já tirou o miolo dos diagramas. O que sobra sem rótulo não é lixo: é tinta
# com forma de texto que o rotulador humano não rotulou — cabeça de página,
# número de folha, nota de rodapé. Nenhuma régua de geometria separa isso de
# texto, porque **é** texto.
#
# Fica ligável (`Coletor(filtrar=True)`) e fica medido: é a mesma decisão da F47
# com a margem, e o que mudaria a conclusão é uma pilha em que o espúrio de
# verdade sobreviva à exclusão de diagrama — um scan sujo, uma página com trama.
# Reproduzir: `python medir_coleta.py --varrer`.

#: Lado mínimo do recorte, em pixels.
LADO_MINIMO = 4

#: Contraste (max - min) abaixo do qual o recorte **está em branco**.
#:
#: **Não dá para perguntar isto ao Otsu.** Num recorte uniforme o Otsu parte o
#: ruído no meio e devolve ~50% de tinta — o mesmo número de um glifo gordo. O
#: contraste responde antes, e responde certo. É o mesmo raciocínio do
#: `preprocess.tinta_plausivel`: avaliar o **resultado**, não o histograma.
#:
#: Na página real ele nunca dispara, e a medição diz por quê: o box nasce de um
#: componente conexo de tinta, então há sempre tinta e sempre papel dentro dele.
#: A mediana do contraste é 255 dos dois lados. Recorte sem contraste é caso de
#: chamada errada, não de página.
CONTRASTE_MINIMO = 25

#: Fração de tinta plausível dentro de um recorte de caractere.
#:
#: Medida nas 10 páginas: 0,49 no caractere e 0,51 no espúrio. **Num recorte
#: justo o Otsu parte perto da metade seja o que for que esteja lá dentro** —
#: a fração de tinta só informaria num box folgado, e estes não são.
TINTA_DO_RECORTE = (0.02, 0.90)


def _cinza(recorte) -> Optional[np.ndarray]:
    """O recorte em cinza, ou `None` se não há recorte nenhum."""
    if recorte is None or getattr(recorte, "size", 0) == 0:
        return None
    imagem = np.asarray(recorte)
    if imagem.ndim == 3:
        imagem = cv2.cvtColor(imagem, cv2.COLOR_RGB2GRAY)
    if imagem.dtype != np.uint8:
        imagem = np.clip(imagem, 0, 255).astype(np.uint8)
    return imagem if imagem.size else None


def fracao_de_tinta(imagem: np.ndarray) -> float:
    """Quanto do recorte é tinta, pelo Otsu do próprio recorte."""
    _, binaria = cv2.threshold(imagem, 0, 255,
                               cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    return float((binaria > 0).mean())


def motivo_de_recusa(imagem: np.ndarray) -> str:
    """
    Por que este recorte **não** é material de revisão. `""` se for.

    Devolve o motivo e não um booleano porque o resumo precisa dizer o que
    recusou: "3.400 recortes fora" sem dizer de quê é o tipo de silêncio que
    esta fase existe para acabar.
    """
    if imagem is None or imagem.size == 0:
        return "vazio"
    if min(imagem.shape[:2]) < LADO_MINIMO:
        return "minúsculo"
    if int(imagem.max()) - int(imagem.min()) < CONTRASTE_MINIMO:
        return "sem contraste"
    tinta = fracao_de_tinta(imagem)
    if tinta < TINTA_DO_RECORTE[0]:
        return "quase sem tinta"
    if tinta > TINTA_DO_RECORTE[1]:
        return "mancha sólida"
    return ""


#: O lado da imagem que a rede recebe. O mesmo do `NeuralPredictor._probabilidades`.
LADO_DA_REDE = 32


def _impressao(imagem: np.ndarray) -> str:
    """
    A identidade do recorte **para o modelo**.

    É o hash dos 32x32 que a rede vai receber — literalmente a entrada dela. Dois
    recortes com a mesma impressão não são "parecidos": são o **mesmo tensor**, e
    treinar nos dois ensina exatamente o que treinar num deles ensina. É por isso
    que a régua é essa e não uma distância perceptual: aqui não se está
    adivinhando semelhança, está-se constatando igualdade, e a constatação não
    tem como colapsar duas amostras que o modelo saiba distinguir.
    """
    pequena = cv2.resize(imagem, (LADO_DA_REDE, LADO_DA_REDE))
    return hashlib.blake2b(pequena.tobytes(), digest_size=16).hexdigest()


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


#: A semente do sorteio do teto. Fixa, para a mesma coleta dar a mesma pasta.
#:
#: Amostra aleatória e resultado reproduzível não se opõem: o que o sorteio
#: precisa é não depender da **ordem das páginas**, e não é sortear diferente a
#: cada rodada. Semente fixa deixa comparar duas coletas do mesmo livro sem que
#: a diferença entre elas seja o dado.
SEMENTE_PADRAO = 20260820


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
    #: Recusa na porta o que não é recorte de caractere. **Desligada**, e o
    #: motivo está medido: ver `motivo_de_recusa` e a F93 no ROADMAP.
    filtrar: bool = False
    #: Grava uma vez só cada entrada distinta da rede. Ver `_impressao`.
    deduplicar: bool = True
    #: As candidatas do modelo para o recorte, `[(char, prob), ...]`. Só é
    #: chamada para o recorte que **vai ser gravado**, então custa uma inferência
    #: por arquivo em disco e não por box da página.
    detalhar: Optional[Callable[[np.ndarray], Sequence[Tuple[str, float]]]] = None
    semente: int = SEMENTE_PADRAO

    gravados: Dict[str, int] = field(default_factory=dict)
    ignorados_por_teto: int = 0
    trocados_pelo_teto: int = 0
    ignorados_por_repeticao: int = 0
    #: Motivo -> quantos. Ver `motivo_de_recusa`.
    recusados: Dict[str, int] = field(default_factory=dict)

    def __post_init__(self):
        # Teto zero — ou negativo — não é teto, é desligar a coleta, e quem
        # quer desligá-la não passa coletor nenhum. Vindo de um campo em branco
        # lido como número, ou de um `0` que escapou, gravaria zero recorte e
        # chamaria isso de limite. Sem teto tem **uma** forma de se dizer aqui:
        # `None`, e é a que o resto da classe pergunta.
        if self.max_por_classe is not None and self.max_por_classe <= 0:
            self.max_por_classe = None
        #: classe -> linhas do índice, na ordem em que estão em disco. É o
        #: reservatório: o sorteio do teto troca um elemento **desta** lista, e
        #: o arquivo correspondente sai do disco junto.
        self._reservatorio: Dict[str, List[dict]] = {}
        #: classe -> quantos candidatos chegaram (não quantos ficaram). É o `n`
        #: da amostragem de reservatório.
        self._candidatos: Dict[str, int] = {}
        #: classe -> impressões já vistas.
        self._impressoes: Dict[str, set] = {}
        self._sorteio = random.Random(self.semente)

    # ------------------------------------------------------------------
    # A chamada da extração
    # ------------------------------------------------------------------

    def __call__(self, recorte: np.ndarray, palpite: str,
                 confianca: float, pagina: int) -> Optional[str]:
        # **Quem filtra por confiança é o coletor, não a extração.** A extração
        # entrega tudo que classificou; o que fazer com isso é política de quem
        # coleta, e é o que permite a mesma chamada servir para "só os
        # duvidosos" e para "todos, para bater o olho".
        if self.limiar is not None and confianca >= self.limiar:
            return None

        imagem = _cinza(recorte)
        if imagem is None:
            return None

        if self.filtrar:
            motivo = motivo_de_recusa(imagem)
            if motivo:
                self.recusados[motivo] = self.recusados.get(motivo, 0) + 1
                return None

        classe = char_to_folder(palpite) if palpite else "unknown"

        # A dedução vem **antes** do teto de propósito: contar cópia como
        # candidato faria o sorteio gastar as vagas do reservatório com o mesmo
        # tensor repetido, que é o defeito que a dedução existe para tirar.
        if self.deduplicar:
            chave = _impressao(imagem)
            vistas = self._impressoes.setdefault(classe, set())
            if chave in vistas:
                self.ignorados_por_repeticao += 1
                return None
            vistas.add(chave)

        vaga = self._vaga(classe)
        if vaga is None:
            self.ignorados_por_teto += 1
            return None

        caminho = self._gravar(imagem, classe, confianca, pagina)
        if caminho is None:
            # Não gravou: a vaga que o sorteio abriu não pode ficar contada.
            # `_vaga` já tirou o antigo do disco quando devolveu um índice, e
            # refazer isso aqui seria pior que aceitar o buraco — o reservatório
            # só encolhe, e o resumo continua contando o que existe.
            return None

        linha = {"arquivo": os.path.join(classe, os.path.basename(caminho)),
                 "palpite": palpite, "confianca": round(float(confianca), 4),
                 "segunda": "", "p2": "", "margem": "",
                 "pagina": pagina + 1, "origem": self.origem,
                 "_caminho": caminho}
        self._detalhar(linha, imagem, palpite)

        reserva = self._reservatorio.setdefault(classe, [])
        if vaga == len(reserva):
            reserva.append(linha)
        else:
            reserva[vaga] = linha
        self.gravados[classe] = len(reserva)
        return caminho

    # ------------------------------------------------------------------
    # O teto, por amostragem de reservatório
    # ------------------------------------------------------------------

    def _vaga(self, classe: str) -> Optional[int]:
        """
        Em que posição do reservatório este recorte entra, ou `None`.

        **Sortear, e não pegar os primeiros.** Com teto de 300 e primeiro-a-
        chegar, a pasta de `o` fica com 300 `o` das páginas 1 a 5: uma fonte, um
        estado de scan, um contexto — e o itálico da página 200, o borrado e o
        quebrado, que são exatamente o que a revisão quer ver, eram jogados fora
        em silêncio depois que o teto enchia. A amostragem de reservatório
        troca isso por uma amostra uniforme do **livro inteiro**, com o mesmo
        custo de memória e sem precisar de uma segunda passada.

        Quando devolve o índice de um elemento existente, o arquivo daquele
        elemento **já saiu do disco**: quem chama grava por cima da vaga.
        """
        reserva = self._reservatorio.setdefault(classe, [])
        n = self._candidatos.get(classe, 0) + 1
        self._candidatos[classe] = n

        teto = self.max_por_classe
        if teto is None or len(reserva) < teto:
            return len(reserva)

        # A partir daqui o reservatório está cheio: o candidato n entra com
        # probabilidade teto/n, no lugar de um sorteado.
        j = self._sorteio.randrange(n)
        if j >= teto:
            return None
        antigo = reserva[j]
        try:
            os.remove(antigo["_caminho"])
        except OSError:
            pass
        self.trocados_pelo_teto += 1
        return j

    # ------------------------------------------------------------------
    # Disco e índice
    # ------------------------------------------------------------------

    def _gravar(self, imagem: np.ndarray, classe: str,
                confianca: float, pagina: int) -> Optional[str]:
        destino = os.path.join(self.pasta, classe)
        os.makedirs(destino, exist_ok=True)
        # **A confiança vem antes da página, e a ordem importa.** O nome sempre
        # carregou as duas, e a intenção sempre foi "ordenar por mais duvidoso
        # primeiro sem abrir o índice" — só que com a página na frente o
        # Explorer ordena por página, e dentro de cada página por confiança. O
        # revisor que abre a pasta e clica em Nome recebia a ordem do livro, que
        # é exatamente a que não ajuda: o recorte mais duvidoso da classe pode
        # estar na página 240, no fim da lista. Trocadas de lugar, o clique em
        # Nome dá a fila certa, e a página continua ali para desempatar.
        nome = (f"c{int(round(confianca * 100)):03d}_p{pagina + 1:04d}"
                f"_{uuid.uuid4().hex[:8]}.png")
        caminho = os.path.join(destino, nome)
        # Gravado **no tamanho em que foi recortado**, e não no da rede: quem
        # revisa precisa enxergar o glifo, e o `learn` redimensiona de novo na
        # hora de promover. Guardar já em 32 px jogaria fora o que decide a
        # dúvida.
        return caminho if cv2.imwrite(caminho, imagem) else None

    def _detalhar(self, linha: dict, imagem: np.ndarray, palpite: str) -> None:
        """
        Põe na linha do índice a segunda candidata e a margem.

        **É dado, e não régua.** A F47 mediu as duas curvas e concluiu que no
        ponto de operação a margem empata com a confiança; nada aqui a promove a
        critério. O que ela resolve é outra coisa: quem revisa e acha um recorte
        na pasta errada quer saber para onde ele ia, e ordenar o CSV por
        `margem` agrupa os pares que o modelo confunde — o `c`/`C`, o `l`/`1` —
        em vez de espalhá-los pela pasta.
        """
        if self.detalhar is None:
            return
        try:
            topo = list(self.detalhar(imagem))
        except Exception:
            return
        # A vencedora pode não ser o palpite quando quem detalha não é quem
        # classificou; nesse caso a "segunda" é a primeira que não é o palpite.
        p1 = next((p for c, p in topo if c == palpite),
                  topo[0][1] if topo else 0.0)
        segunda = next(((c, p) for c, p in topo if c != palpite), None)
        if segunda is None:
            return
        linha["segunda"], linha["p2"] = segunda[0], round(float(segunda[1]), 4)
        linha["margem"] = round(1.0 - segunda[1] / p1, 4) if p1 > 0 else 0.0

    @property
    def linhas(self) -> List[dict]:
        """As linhas do índice, na ordem das classes. Só o que está em disco."""
        return [l for reserva in self._reservatorio.values() for l in reserva]

    @property
    def total(self) -> int:
        return sum(self.gravados.values())

    @property
    def descartados(self) -> int:
        """
        Tudo que chegou e não está no disco — a soma que o resumo detalha.

        `total + descartados` é o número de recortes que passaram pela chamada,
        e é essa identidade que garante que nada some sem nome. **O trocado
        conta aqui**: o sorteio do teto grava por cima de um recorte anterior,
        e o anterior chegou e não ficou como qualquer outro descarte.
        """
        return (sum(self.recusados.values()) + self.ignorados_por_repeticao
                + self.ignorados_por_teto + self.trocados_pelo_teto)

    def gravar_indice(self) -> Optional[str]:
        """O CSV ao lado dos recortes. Devolve o caminho, ou None se nada foi gravado."""
        linhas = self.linhas
        if not linhas:
            return None
        os.makedirs(self.pasta, exist_ok=True)
        caminho = os.path.join(self.pasta, NOME_DO_INDICE)
        novo = not os.path.exists(caminho)
        # utf-8-sig e append: a coleta de um segundo livro soma à do primeiro em
        # vez de apagá-la, e o Excel do Windows abre sem transformar os símbolos
        # de peça em lixo.
        with open(caminho, "a", encoding="utf-8-sig", newline="") as f:
            escritor = csv.DictWriter(f, fieldnames=COLUNAS,
                                      extrasaction="ignore")
            if novo:
                escritor.writeheader()
            escritor.writerows(linhas)
        return caminho

    def resumo(self) -> str:
        """
        Uma linha com o que ficou — e com o que **não** ficou, e por quê.

        O detalhe do descarte não é enfeite: o padrão desta fase é "nada some em
        silêncio", e o mesmo número escondido ("3.400 recortes fora") é o que
        deixaria uma porta mal calibrada passar despercebida por um livro
        inteiro.
        """
        partes = []
        if self.total:
            piores = sorted(self.gravados.items(), key=lambda kv: -kv[1])[:5]
            detalhe = " ".join(f"{folder_to_char(c)}×{n}" for c, n in piores)
            partes += [f"{self.total} recorte(s) em {len(self.gravados)} classe(s)",
                       f"mais frequentes: {detalhe}"]
        else:
            partes.append("nenhum recorte de baixa confiança")

        if self.ignorados_por_repeticao:
            partes.append(f"{self.ignorados_por_repeticao} repetido(s) "
                          f"(mesma imagem para a rede)")
        recusados = sum(self.recusados.values())
        if recusados:
            porque = ", ".join(f"{n} {motivo}" for motivo, n
                               in sorted(self.recusados.items(),
                                         key=lambda kv: -kv[1]))
            partes.append(f"{recusados} não eram caractere ({porque})")
        fora = self.ignorados_por_teto + self.trocados_pelo_teto
        if fora:
            partes.append(f"{fora} além do teto de {self.max_por_classe} por "
                          f"classe, sorteado sobre o livro inteiro")
        return "; ".join(partes)


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
