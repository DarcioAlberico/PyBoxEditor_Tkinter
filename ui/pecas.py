"""
As figuras das peças, para o tabuleiro editável (F8.2).

O tabuleiro desenhava as peças com os glifos Unicode da fonte do sistema
(`♔♕♖♗♘♙`). Funciona, mas o desenho é o que a fonte instalada tiver, e ele não
se parece com o do livro que está ao lado na mesma janela — que é justamente a
comparação que a F7.1 pôs ali para a conferência custar segundos.

As figuras vêm de `pieces/`, uma por peça, no formato `<cor><PEÇA>.png`
(`wK.png`, `bP.png`). São PNG com transparência, então a casa clara e a escura
aparecem por baixo.

**Sem a pasta, o tabuleiro volta aos glifos e diz que voltou.** Uma janela que
some com as peças porque um arquivo mudou de lugar é pior que uma janela feia;
e um aviso discreto na legenda custa menos que um diálogo modal a cada abertura.

## Por que não há cache global

`ImageTk.PhotoImage` pertence ao interpretador Tcl que estava vivo quando ela
foi criada. Guardá-la num dicionário de módulo faz a segunda janela de uma
sessão nova pedir uma imagem que já não existe — o erro aparece longe daqui e
não se parece com a causa. Carregar de novo custa poucos milissegundos.
"""

import os
from typing import Dict, Optional

#: Raiz do projeto (este arquivo está em `ui/`).
_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Onde as figuras moram.
PASTA = os.path.join(_RAIZ, "pieces")

#: Símbolo da peça -> arquivo. Maiúscula é branca, como no FEN.
ARQUIVOS = {
    "K": "wK.png", "Q": "wQ.png", "R": "wR.png",
    "B": "wB.png", "N": "wN.png", "P": "wP.png",
    "k": "bK.png", "q": "bQ.png", "r": "bR.png",
    "b": "bB.png", "n": "bN.png", "p": "bP.png",
}


def faltando(pasta: Optional[str] = None) -> list:
    """Os arquivos de peça que não estão lá. Vazio = dá para desenhar."""
    pasta = PASTA if pasta is None else pasta
    return [nome for nome in ARQUIVOS.values()
            if not os.path.isfile(os.path.join(pasta, nome))]


def carregar(lado: int, pasta: Optional[str] = None) -> Dict[str, object]:
    """
    {símbolo: PhotoImage} no tamanho pedido, ou `{}` se faltar alguma.

    Tudo ou nada de propósito: um tabuleiro com dez figuras e dois glifos
    Unicode no meio confunde mais do que doze glifos.

    Precisa de uma janela Tk viva — `PhotoImage` não existe antes disso.
    """
    pasta = PASTA if pasta is None else pasta
    if faltando(pasta):
        return {}

    from PIL import Image, ImageTk

    imagens = {}
    for simbolo, nome in ARQUIVOS.items():
        try:
            img = Image.open(os.path.join(pasta, nome)).convert("RGBA")
            if img.size != (lado, lado):
                img = img.resize((lado, lado), Image.LANCZOS)
            imagens[simbolo] = ImageTk.PhotoImage(img)
        except Exception:
            # Arquivo ilegível vale o mesmo que arquivo ausente: volta tudo
            # para os glifos, em vez de deixar o tabuleiro pela metade.
            return {}
    return imagens
