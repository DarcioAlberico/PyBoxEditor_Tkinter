"""
A entrada de tamanho paga? Medido nas páginas rotuladas, e não suposto (F107).

A F14 nomeou o defeito e a F19 mediu o remédio errado. O defeito: `s` e `S`,
`o` e `O` e `0`, `c` e `C` são **o mesmo desenho** — o que os separa é o
tamanho, e `cv2.resize(img, (32, 32))` o descarta antes de qualquer
classificador ver. O remédio errado foi pendurar a geometria **depois**, como
desempate sobre as candidatas: mediu 0 acerto em 72 na rede, porque um
desempate só fala onde discorda da âncora, e com âncora forte esse conjunto é
quase todo erro do desempate.

O que ficou pendente nas duas é a mesma frase: **a altura tem de entrar na
rede, treinada junto**, onde o modelo aprende quanto confiar nela. Este
instrumento mede isso, e mede a única coisa que decide se vale reextrair a base:
com a entrada de tamanho, a família de caixa melhora?

    python medir_tamanho.py
    python medir_tamanho.py --epocas 40 --cru

**Por que só 30 mil caracteres, e não os 608 mil da base.** O `learn` gravava a
amostra já em 32x32 (corrigido nesta mesma fase), então nas 608 mil o tamanho
**não é recuperável** — foi descartado na gravação. Onde ele sobrevive é nos
`.box` rotulados à mão: ali estão `x1 y1 x2 y2` do caractere e a página ao lado,
que é de onde a `proporcao.ENVELOPE` já saiu. São 25 páginas.

**É pouco, e é de propósito que seja pouco.** A pergunta aqui não é "que
acurácia um modelo com tamanho atinge" — para isso 30 mil não bastam. É "a
entrada carrega o sinal que falta", que se responde com as duas redes treinadas
lado a lado no **mesmo** material, mudando só a entrada. Se não pagar aqui, não
paga com 608 mil; se pagar, aí sim vale o custo de reextrair.

**A divisão deixa um livro inteiro de fora**, e não páginas sorteadas. Duas
ocorrências do mesmo `s` na mesma página são quase a mesma imagem, então dividir
por caractere faria as redes "acertarem" por memória — mas dividir por página
não basta: com 25 páginas de 6 obras, o sorteio quase sempre põe páginas do
mesmo livro dos dois lados, e a rede é testada na tipografia que já viu. Medido
assim, a família de caixa sai a 96,2% no braço de produção e não sobra folga
para nada melhorar. **O erro que esta fase persegue é o do livro novo**, e é ele
que o turno por obra encena.

**A referência de tamanho é a mediana da altura dos boxes da página**, o mesmo
denominador de `preprocess.denoise` e de `proporcao.TAMANHO`, e pela mesma razão:
o mesmo livro a 150 e a 300 dpi tem glifos de tamanhos diferentes, e sem
normalizar a entrada nova seria uma medida de dpi. **Não é a da linha** — a F19
mediu que a faixa da linha encolhe quando falta ascendente ou descendente e
desloca todas as frações juntas, e foi isso que derrubou o desempate dela.

## O que ele mediu — e a resposta é "não decide", com motivo

Seis turnos, um por obra, 15 épocas, 29.822 caracteres:

    entrada                                 tudo    família de caixa    resto
    32x32 esticado (produção hoje)        92,01%    92,52% ±2,86%     91,55%
    32x32 esticado + tamanho              91,59%    91,01% ±4,89%     91,70%
    32x32 encaixado (proporção)+tamanho   94,31%    92,77% ±5,02%     94,38%
    32x32 esticado + tamanho, cru         93,26%    92,90% ±4,13%     93,04%

**Na família de caixa, nenhum braço se separa da dispersão.** O melhor deles
soma +0,25 ponto sobre a produção, com desvio de 5 pontos entre os turnos — e o
placar de trocas diz o mesmo: encaixado conserta 334 e quebra 286.

**Mas o sinal está sendo usado, e dá para ver onde.** Por classe, os escalares
movem justamente as maiúsculas — `S` de 50% para 74%, `W` de 33% para 83%, `0`
de 34% para 55%. O que come o ganho é o outro lado do par: `c` cai de 97,2% para
87,0% e `w` de 91,4% para 90,0%, e como a minúscula é 20x mais frequente, a
média da família não se mexe. O modelo passa a **confiar demais** na entrada
nova; não é que ela não carregue nada.

**Por que este material não pode decidir.** No teste inteiro dos seis turnos há
50 `S`, 48 `W`, 36 `O` e 52 `C`. Uma dúzia de amostras que mudam de lado move
essas linhas inteiras, e é daí que vem o desvio de 5 pontos. O que falta não é
ideia, é **maiúscula rotulada** — e é por isso que a gravação com tamanho (a
outra metade da F107) é pré-requisito desta resposta, e não consequência dela.

**O achado que não estava na pergunta.** Preservar a proporção na imagem paga
**+2,8 pontos no "resto"** — fora da família de caixa, onde ninguém a tinha
procurado. Ali não há maiúscula escassa e o ganho sai da dispersão. É o oposto
do que a F106 mediu ao trocar o esticão pela caixa *sem* retreinar; treinada
nela desde o começo, a caixa ganha. Fica registrado como fase própria, porque é
uma mudança de entrada que não depende de rerrotular nada.

Reproduz a F107 no ROADMAP.
"""

import argparse
import glob
import os
import sys
from collections import Counter, defaultdict
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import torch
import torch.nn as nn
import torch.nn.functional as F

from core import formato_box, vertical
from core.neural_model import get_device

#: O lado do recorte que a rede recebe. O mesmo do `NeuralPredictor`.
LADO = 32

#: As classes cuja separação **depende do tamanho** — o alvo desta medição.
#:
#: São os pares de mesmo desenho em dois corpos. `i`, `l`, `1` e `I` entram
#: porque a família é a mesma ainda que o par exato mude: a F19 mediu d' de 1,93
#: em `l/1` e 0,01 em `i/1`, e o que se quer saber é se a rede acha sozinha o
#: que aquela tabela achou à mão.
FAMILIA_DE_CAIXA = set("sSoO0cCxXzZwWvVuUpPkKiI l1".replace(" ", ""))

#: Material mínimo para um livro poder ser o turno de teste.
#:
#: Livro com menos que isto continua no treino dos outros turnos, e não vira
#: turno: a diferença entre dois braços sobre algumas dezenas de caracteres é
#: sorteio, e entraria na média com o mesmo peso de um turno de 8 mil.
MINIMO_DE_TESTE = 500

#: Classe com menos que isto no material inteiro sai da medição.
#:
#: Não por serem difíceis — por não haver como dizer nada sobre elas. Com 4
#: amostras, a divisão por página põe zero ou quatro do lado do teste, e a
#: diferença entre as duas redes naquela classe é ruído de sorteio. É a mesma
#: régua que o `relatorio_treino` imprime como "classes SEM validação".
MINIMO_POR_CLASSE = 12


def _console_em_utf8():
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _ler_cinza(caminho: str) -> Optional[np.ndarray]:
    """`imread` que sobrevive a caminho não-ASCII no Windows.

    O `cv2.imread` devolve `None` em `PDF/Darcy Lima & Júlio Lapertosa/...` —
    é o mesmo defeito que o `learner.learn` documenta do lado da gravação.
    """
    try:
        with open(caminho, "rb") as f:
            dados = f.read()
    except OSError:
        return None
    if not dados:
        return None
    return cv2.imdecode(np.frombuffer(dados, dtype=np.uint8),
                        cv2.IMREAD_GRAYSCALE)


def livro_de(caminho: str) -> str:
    """
    A obra de onde a página veio, pelo nome do arquivo.

    É o que permite a divisão que interessa — **deixar um livro inteiro de
    fora**. Dividir por página sorteada quase sempre põe páginas do mesmo livro
    dos dois lados, e aí a rede é testada em tipografia que já viu: a família de
    caixa fica fácil, não sobra folga, e a medição não responde à pergunta. O
    erro que esta fase persegue aparece justamente no livro novo.

    O `_pgNNN` sai, e o dígito ou o espaço no fim também — `... - editable 2` e
    `... - editable1` são a mesma obra que `... - editable`.
    """
    nome = os.path.splitext(os.path.basename(caminho))[0]
    nome = nome.split("_pg")[0]
    return nome.rstrip("0123456789 ")


def paginas_com_box(raiz: str = ".") -> List[Tuple[str, str]]:
    """[(imagem, .box)] de todo `.box` que tenha a página ao lado."""
    achados = []
    for cx in sorted(glob.glob(os.path.join(raiz, "**", "*.box"),
                               recursive=True)):
        if ".venv" in cx or "worktrees" in cx:
            continue
        nome = os.path.splitext(cx)[0]
        img = next((nome + e for e in (".png", ".jpg", ".jpeg")
                    if os.path.exists(nome + e)), None)
        if img:
            achados.append((img, cx))
    return achados


def coletar(raiz: str = ".") -> Tuple[List[np.ndarray], List[str],
                                      List[Tuple[float, float]], List[str]]:
    """(recortes, rótulos, (larg/ref, alt/ref), livro de cada um)."""
    recortes, rotulos, tamanhos, paginas = [], [], [], []
    for i, (img_p, box_p) in enumerate(paginas_com_box(raiz)):
        img = _ler_cinza(img_p)
        if img is None:
            print(f"  ilegível, pulada: {img_p}")
            continue
        boxes = [b for b in formato_box.ler(box_p, img.shape[0])
                 if len(b.char) == 1]
        if not boxes:
            continue
        # A referência é da **página**, e não da linha. Ver o cabeçalho.
        ref = float(np.median([b.height for b in boxes])) or 1.0
        for b in boxes:
            r = vertical.recorte_de_pe(img, b)
            if r.size == 0:
                continue
            recortes.append(r)
            rotulos.append(b.char)
            tamanhos.append((b.width / ref, b.height / ref))
            paginas.append(livro_de(box_p))
    return recortes, rotulos, tamanhos, paginas


# ----------------------------------------------------------------------
# As duas entradas
# ----------------------------------------------------------------------

def esticar(r: np.ndarray) -> np.ndarray:
    """32x32 sem preservar proporção — o que produção faz hoje."""
    return cv2.resize(r, (LADO, LADO))


def encaixar(r: np.ndarray) -> np.ndarray:
    """
    32x32 **com** a proporção preservada, sobrando papel em volta.

    O terceiro braço da medição. Ele carrega a proporção dentro da imagem, sem
    escalar nenhum — é a variante que a F106 cogitou e mediu como pior *sem
    retreinar*, porque a caixa era fora da distribuição do modelo de então.
    Aqui a rede treina nela desde o começo, que é a comparação justa.
    """
    alt, larg = r.shape[:2]
    lado = max(alt, larg, 1)
    escala = LADO / lado
    novo = cv2.resize(r, (max(1, int(round(larg * escala))),
                          max(1, int(round(alt * escala)))))
    tela = np.full((LADO, LADO), 255, np.uint8)
    y = (LADO - novo.shape[0]) // 2
    x = (LADO - novo.shape[1]) // 2
    tela[y:y + novo.shape[0], x:x + novo.shape[1]] = novo
    return tela


class Rede(nn.Module):
    """
    A `SimpleCNN` do projeto, com uma porta para os escalares de tamanho.

    **A mesma arquitetura em todos os braços**, e os escalares entram depois da
    parte convolucional: com `escalares=0` esta rede é a `SimpleCNN`, tensor por
    tensor. É o que faz a comparação medir a entrada, e não a rede.

    **Os escalares passam por uma camada própria antes de se juntarem**, e essa
    não é uma escolha de gosto: concatenar 2 números crus a um vetor de 2.048
    os deixa sem gradiente que se note, e um resultado negativo assim mediria a
    injeção e não a informação. `--cru` refaz a versão ingênua, para a diferença
    entre as duas ficar registrada em vez de suposta.
    """

    def __init__(self, num_classes: int, escalares: int = 0,
                 largura_da_porta: int = 32):
        super().__init__()
        self.escalares = escalares
        self.porta = largura_da_porta if escalares else 0
        self.conv1 = nn.Conv2d(1, 32, 3, padding=1)
        self.conv2 = nn.Conv2d(32, 64, 3, padding=1)
        self.conv3 = nn.Conv2d(64, 128, 3, padding=1)
        if escalares and largura_da_porta:
            self.entrada = nn.Linear(escalares, largura_da_porta)
        self.fc1 = nn.Linear(128 * 4 * 4 + (self.porta or escalares), 256)
        self.dropout = nn.Dropout(0.5)
        self.fc2 = nn.Linear(256, num_classes)

    def forward(self, x, extra=None):
        x = F.max_pool2d(F.relu(self.conv1(x)), 2)
        x = F.max_pool2d(F.relu(self.conv2(x)), 2)
        x = F.max_pool2d(F.relu(self.conv3(x)), 2)
        x = x.flatten(1)
        if self.escalares:
            x = torch.cat([x, F.relu(self.entrada(extra))
                           if self.porta else extra], dim=1)
        x = F.relu(self.fc1(x))
        return self.fc2(self.dropout(x))


def treinar(Xi, Xe, y, num_classes, escalares, *, epocas, semente, device,
            porta=32):
    torch.manual_seed(semente)
    rede = Rede(num_classes, escalares, porta).to(device)
    opt = torch.optim.Adam(rede.parameters(), lr=1e-3)
    perda = nn.CrossEntropyLoss()
    n, lote = len(y), 128
    for _ in range(epocas):
        rede.train()
        ordem = torch.randperm(n)
        for i in range(0, n, lote):
            idx = ordem[i:i + lote]
            opt.zero_grad()
            saida = rede(Xi[idx], Xe[idx] if escalares else None)
            erro = perda(saida, y[idx])
            erro.backward()
            opt.step()
    return rede


@torch.no_grad()
def prever(rede, Xi, Xe, escalares, lote=512):
    rede.eval()
    saida = []
    for i in range(0, len(Xi), lote):
        s = rede(Xi[i:i + lote], Xe[i:i + lote] if escalares else None)
        saida.append(s.argmax(1).cpu())
    return torch.cat(saida).numpy()


def main(argv=None) -> int:
    _console_em_utf8()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--epocas", type=int, default=20)
    ap.add_argument("--cru", action="store_true",
                    help="também mede os escalares concatenados sem camada "
                         "própria — a injeção ingênua")
    args = ap.parse_args(argv)

    device = get_device()
    print(f"dispositivo: {device}\n")

    recortes, rotulos, tamanhos, paginas = coletar()
    print(f"{len(recortes)} caracteres em {len(set(paginas))} obras")

    conta = Counter(rotulos)
    vivas = {c for c, n in conta.items() if n >= MINIMO_POR_CLASSE}
    manter = [i for i, r in enumerate(rotulos) if r in vivas]
    print(f"{len(vivas)} classes com {MINIMO_POR_CLASSE}+ amostras "
          f"({len(manter)} caracteres); o resto sai da conta\n")

    classes = sorted(vivas)
    idx = {c: i for i, c in enumerate(classes)}

    # (rótulo, apelido curto, preparo do recorte, escalares, largura da porta)
    bracos = [("32x32 esticado (produção hoje)", "esticado", esticar, 0, 0),
              ("32x32 esticado + tamanho", "+tamanho", esticar, 2, 32),
              ("32x32 encaixado (proporção) + tamanho", "encaixado",
               encaixar, 2, 32)]
    if args.cru:
        bracos.append(("32x32 esticado + tamanho, cru", "cru", esticar, 2, 0))

    acumulado = {nome: {"tudo": [], "familia": [], "resto": [],
                        "consertou": 0, "quebrou": 0}
                 for nome, *_ in bracos}
    porc = defaultdict(lambda: defaultdict(lambda: [0, 0]))

    # Um turno por livro deixado de fora. Livro que não tem material bastante
    # para ser teste **não vira turno**, e continua no treino dos outros: a
    # diferença entre dois braços sobre 40 caracteres é sorteio, não medida.
    contagem = Counter(paginas[i] for i in manter)
    turnos = [(l, n) for l, n in sorted(contagem.items()) if n >= MINIMO_DE_TESTE]
    print("deixando um livro de fora por vez:")
    for l, n in turnos:
        print(f"  {n:>6} caracteres   {l[:56]}")
    fora = [(l, n) for l, n in sorted(contagem.items()) if n < MINIMO_DE_TESTE]
    for l, n in fora:
        print(f"  {n:>6} pouco para ser turno, fica só no treino: {l[:40]}")
    print()

    for de_fora, _n in turnos:
        tr = [i for i in manter if paginas[i] != de_fora]
        te = [i for i in manter if paginas[i] == de_fora]
        familia = np.array([rotulos[i] in FAMILIA_DE_CAIXA for i in te])
        semente = 0
        print(f"fora: {de_fora[:44]:<44} treino {len(tr):>6} / teste "
              f"{len(te):>5}, família {int(familia.sum()):>5}", flush=True)

        def tensores(indices, preparo):
            imgs = np.stack([preparo(recortes[i]) for i in indices])
            Xi = (torch.from_numpy(imgs).float().div_(255.0)
                  .unsqueeze(1).to(device))
            Xe = torch.tensor([tamanhos[i] for i in indices],
                              dtype=torch.float32, device=device)
            y = torch.tensor([idx[rotulos[i]] for i in indices],
                             dtype=torch.long, device=device)
            return Xi, Xe, y

        base = None
        for nome, _curto, preparo, escalares, porta in bracos:
            Xi_tr, Xe_tr, y_tr = tensores(tr, preparo)
            Xi_te, Xe_te, y_te = tensores(te, preparo)
            verdade = y_te.cpu().numpy()

            rede = treinar(Xi_tr, Xe_tr, y_tr, len(classes), escalares,
                           epocas=args.epocas, semente=semente, device=device,
                           porta=porta)
            certo = prever(rede, Xi_te, Xe_te, escalares) == verdade

            a = acumulado[nome]
            a["tudo"].append(certo.mean())
            a["familia"].append(certo[familia].mean())
            a["resto"].append(certo[~familia].mean())
            if base is None:
                base = certo
            else:
                a["consertou"] += int((~base & certo & familia).sum())
                a["quebrou"] += int((base & ~certo & familia).sum())
            for k, i in enumerate(te):
                porc[nome][rotulos[i]][0] += 1
                porc[nome][rotulos[i]][1] += int(certo[k])

    def faixa(v):
        return f"{np.mean(v):>7.2%} ±{np.std(v):>5.2%}"

    print(f"\nmédia dos {len(turnos)} turnos, um por obra deixada de fora\n")
    print(f"{'entrada':<38} {'tudo':>15} {'família de caixa':>16} {'resto':>15}")
    for nome, *_ in bracos:
        a = acumulado[nome]
        print(f"{nome:<38} {faixa(a['tudo']):>15} {faixa(a['familia']):>16}"
              f" {faixa(a['resto']):>15}")

    print("\ncontra o braço de produção, somando os turnos, na família:")
    for nome, *_ in bracos[1:]:
        a = acumulado[nome]
        print(f"  {nome:<38} consertou {a['consertou']:>4}   "
              f"quebrou {a['quebrou']:>4}")

    alvo = "sSoO0cCxXzZwW"
    print(f"\nnos pares que só o tamanho separa (somando os turnos):")
    print(f"{'classe':>8} {'n':>6}"
          + "".join(f"{curto:>13}" for _n, curto, *_ in bracos))
    for c in alvo:
        linha = [porc[nome].get(c) for nome, *_ in bracos]
        if not linha[0] or linha[0][0] < 10:
            continue
        print(f"{c!r:>8} {linha[0][0]:>6}"
              + "".join(f"{(v[1]/v[0]):>13.1%}" for v in linha))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
