# PyBoxEditor — Especificação de Implementação

Versão: 2.0
Data: 2026-08-03
Status: **implementado até a F8**, mais a §5.8 (F9.1) e a §5.9 (F10) — ver ressalvas
abaixo; a F9.2 é planejada e não está feita — atualizado em 2026-08-06
Substitui parcialmente: [`Substituição de Glifos de Xadrez.md`](../Substituição%20de%20Glifos%20de%20Xadrez.md) (v1.0)
Companheiro: [`ROADMAP.md`](../ROADMAP.md)

**Relação com a v1.0:** a spec v1.0 descreve apenas o módulo de substituição de glifos
e continua válida como referência de requisitos (RF-01…RF-06). Esta v2.0 cobre o sistema
inteiro, corrige decisões da v1.0 que a implementação provou erradas (§4.2) e adiciona
os contratos que faltavam. Onde houver conflito, **v2.0 prevalece**.

---

## 0. Como ler este documento hoje

Este texto foi escrito **antes** da implementação e está no futuro do imperativo
("reescrever", "a criar", "passa a"). Tudo o que ele especifica foi feito, e o registro
do que **de fato aconteceu**, com as medições, está no [`ROADMAP.md`](../ROADMAP.md).
Onde os dois discordarem, o ROADMAP é o que vale.

**Onde a implementação divergiu de propósito.** Estas são as diferenças que confundiriam
quem lesse a spec como manual:

| § | A spec dizia | Ficou | Por quê |
|---|---|---|---|
| 2.3 | recriar `core/box_io.py` | `core/formato_box.py` | o nome antigo carregava o formato de 5 campos, incompatível; reusá-lo convidaria à confusão |
| 7.5 | `Ctrl+Shift+A` | **`Ctrl+E`** | acorde de três teclas para a operação mais repetida do fluxo |
| 7.6 | `Z` para zoom | **`F4`** | com o modo digitação (§7.3) uma letra solta vira o caractere do box (F4.6) |
| 7.6 | — | **`Tab` / `Shift+Tab`** | não estavam previstos; entraram na F3.5 |
| 6.1 | `HistoryManager.is_dirty()` | `DocumentSession.is_dirty()` | quem sabe o que está salvo é o documento, não o histórico |
| 3 | separador de glifos sempre ligado | `separar_colados="auto"` | medido: sem árbitro, separar é **pior** que não separar (F1.5b) |

**O que a medição desmentiu depois de escrito**, e está corrigido no ROADMAP, não aqui:
a spec supunha que o tabuleiro viraria milhares de contornos de lixo (dá **um** box), que
o separador de glifos por projeção se pagaria (só se paga com o classificador
arbitrando), e que o custo do histórico exigiria snapshot incremental (exigia só parar de
usar `deepcopy`).

---

## 1. Escopo

Ferramenta desktop para OCR de livros de xadrez em PDF, com três capacidades:

1. **Editor de boxes** — desenhar, ajustar e rotular caixas de caractere sobre a página
2. **Reconhecimento** — cadeia neural → k-NN → EasyOCR, com aprendizado incremental
3. **Substituição de glifos** — converter notação em fonte de xadrez para Unicode

Não incluído nesta versão: extração de FEN, exportação PGN, correção por modelo de
linguagem.

> **Os três saíram de "não incluído" depois.** A **correção por modelo de linguagem**
> virou a F1.7 (validação por legalidade, que resolve o mesmo problema com regras em vez
> de estatística); a **exportação PGN** virou a F6.1, porque a F1.7 já tinha construído
> quase tudo de que ela precisava; e a **extração de FEN** virou a F7.1, porque a F1.8 já
> localizava os diagramas sem que ninguém tivesse notado — ela os *descartava* como
> "grande demais para ser caractere", e bastou recolher o que ela jogava fora.
>
> As três seguiram o mesmo caminho: o que parecia trabalho novo era, em boa parte,
> trabalho já feito por outro motivo.
>
> **A correção por modelo de linguagem saiu resolvida pela metade, e a metade que falta
> está registrada.** A legalidade cuida da notação; o texto corrido entre os lances não
> tem correção nenhuma. É a §5.8 — dicionário de palavras e palavras do usuário, no
> desenho do ABBYY —, planejada como F9 e ainda não feita. Mesmo padrão das três acima:
> a segmentação de palavras, a confiança por box e a edição que não inventa box já
> existem, escritas para a §5.6.

---

## 2. Modelo de domínio

### 2.1 `BoxEntry` — fonte única da verdade

`core/box_model.py` define um dataclass. **Não é um dicionário.** Quatro pontos do
código o tratavam como dict e falhavam em runtime — corrigidos na F0.1, travados por
`tests/test_f0_smoke.py`.

**Regra:** acesso exclusivamente por atributo. Nada de `b["x1"]` nem `b.get()`.
(`b.copy()` passou a existir e é o jeito certo de duplicar um box.)

Estado do dataclass — implementado por completo (F0.1 e F3.2):

```python
from dataclasses import dataclass, replace, field

@dataclass
class BoxEntry:
    char: str
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float = 0.0      # 0.0–1.0
    source: str = "manual"       # manual | neural | learner | easyocr | tesseract | opencv

    def copy(self) -> "BoxEntry":
        return replace(self)

    @property
    def width(self) -> int:  return self.x2 - self.x1

    @property
    def height(self) -> int: return self.y2 - self.y1

    def to_dict(self) -> dict:   # apenas na fronteira de serialização
        ...
```

`confidence` e `source` são o que viabiliza F3.2, F3.3 e F1.7. O `fallback_chain` já
produzia os dois valores e o código os descartava.

`source == ""` significa **sem informação**, não confiança baixa — é o estado de um box
novo ou carregado de um `.box` (formato que não guarda confiança). A distinção importa:
tratá-lo como suspeito encheria a tela de falso alarme ao abrir um arquivo salvo.

`source == "manual"` com `confidence = 1.0` é o que a correção do usuário grava. Sem
isso a cor não convergiria e a revisão não teria fim visível.

**`angulo: int = 0` — [feito, F8.1].** Graus anti-horários do **texto impresso**, não do
recorte, na convenção do PDF: `0` normal, `90` o texto sobe (lê-se de baixo para cima),
`270` desce. Quem classifica pede o glifo de pé a `core.vertical.endireitar`, que é o
único lugar do código que raciocina sobre o sinal do giro. O campo atravessa `as_state`,
o rascunho de autosave e o `.box` (§2.3), porque um ângulo perdido devolve o box à
leitura errada de antes — 8,4% de acerto contra 94,4%.

**`negativo: bool = False` — [feito, F10].** O glifo está impresso **claro sobre
escuro**: o nome dos jogadores na tarja preta do Yusupov, o título de seção na tarja
cinza do Kasparov. Mesma escolha do `angulo`, e pelo mesmo motivo — quem classifica quer
o glifo como o modelo o viu no treino, e `core.negativo.positivar` é a volta. As duas
voltas moram no mesmo funil, `vertical.recorte_de_pe`, e compõem: um rótulo girado
dentro de uma tarja sai de pé e positivado. O campo atravessa `as_state`, o autosave e o
`.box` (§2.3).

**Invariantes** (validar ao construir e após qualquer mutação):

- `x1 < x2` e `y1 < y2`
- coordenadas dentro dos limites da imagem
- largura e altura mínimas de 3 px
- `0.0 <= confidence <= 1.0`

### 2.2 Fronteiras de conversão

Só três lugares convertem `BoxEntry` ↔ outra representação:

| Fronteira | Função |
|-----------|--------|
| Arquivo `.box` | `core/box_io.py` (a recriar, ver §2.3) |
| Serialização de histórico | `core/services/history_service.py` |
| Interoperabilidade OpenCV | `core/services/box_service.py` |

Qualquer outro lugar que converta é bug.

### 2.3 Formato `.box` — [feito, F5.2, em `core/formato_box.py`]

Havia **dois formatos incompatíveis**: 5 campos em `box_io.py` e 6 em `main_window.py`.
A F5.1 removeu o `box_io.py`, então hoje sobra só o de 6 campos, inline no
`main_window`. Falta consolidá-lo num módulo próprio, no formato Tesseract (6 campos,
origem inferior-esquerda):

```
<char> <x1> <y_bottom> <x2> <y_top> <page>
```

Regras:

- **recriar** `core/box_io.py` como a **única** implementação, e `main_window` passa a
  chamá-lo. (O `box_io.py` original foi removido na F5.1: implementava o formato de
  5 campos, incompatível com o de 6 campos que o `main_window` realmente grava — dois
  leitores divergentes do mesmo formato é pior que nenhum. O código antigo segue
  recuperável: `git show 6a4b7a1:core/box_io.py`.)
- caractere vazio grava `~`; um `~` literal grava `\~`
- **não truncar** com `ch[0]` — ligaduras (`fi`, `ffi`) são gravadas inteiras
  (`main_window.py:709` trunca hoje, perdendo dados em silêncio)
- ler tolerando 5 ou 6 campos; escrever sempre 6
- UTF-8 sem BOM

> **Como ficou.** O módulo é `core/formato_box.py`, não `box_io.py` — o nome antigo
> carregava o formato de 5 campos e reusá-lo convidaria à confusão. O escape saiu como a
> spec pedia e cresceu: além de `\~`, também `\\`, `\s` (espaço) e `\t`. Foi por causa de
> um **terceiro** defeito que a spec não previa — um box cujo caractere é espaço deixava
> a linha com 5 campos e o leitor a descartava, perdendo o box calado. A tolerância a 5
> campos, que a spec pedia por compatibilidade, passou a significar exatamente isso: o
> primeiro campo era um espaço literal, como o Tesseract o grava.

> **O sétimo campo, da F8.1.** Um box de texto girado grava o ângulo depois do número da
> página, e **só quando ele não é zero** — página sem texto vertical continua gravando o
> arquivo byte a byte igual, e quem lê só os seis campos do Tesseract não vê diferença.
> Na leitura, um sétimo campo que não seja 0, 90, 180 ou 270 é ignorado em vez de
> derrubar a linha: o campo é extensão nossa, e perder o ângulo custa menos que perder o
> box.

> **O oitavo campo, da F10.** Mesma regra, um campo adiante: `1` quando o glifo está
> impresso claro sobre escuro, nada quando não está. Escrever o oitavo obriga a escrever
> o sétimo — um `0` de ângulo aparece nessa linha para o campo seguinte ter onde ficar, e
> é a única situação em que ele é gravado. Oitavo campo que não seja `1` é lido como
> "não é negativo", pelo mesmo motivo do sétimo.

---

## 3. Pré-processamento de imagem

Novo módulo `core/preprocess.py`. Substitui o threshold fixo `180` replicado em três
arquivos (`box_service.py:20`, `learning_service.py:127`,
`neural_pdf_processor.py:17`).

```python
def binarize(img: np.ndarray, method: str = "auto") -> np.ndarray:
    """
    auto     — Otsu se o histograma for bimodal, senão adaptativo
    otsu     — cv2.THRESH_OTSU
    adaptive — cv2.adaptiveThreshold gaussiano (páginas com iluminação irregular)
    fixed    — threshold fixo (compatibilidade com o comportamento atual)
    """

def deskew(img: np.ndarray, max_angle: float = 15.0) -> tuple[np.ndarray, float]:
    """Corrige inclinação por minAreaRect sobre os pixels de tinta. Retorna (img, ângulo)."""

def denoise(img: np.ndarray) -> np.ndarray:
    """Remove partículas menores que ~0.5% da altura mediana de caractere."""

def normalize_dpi(img: np.ndarray, source_dpi: int, target_dpi: int = 300) -> np.ndarray:
    """Reamostra para o DPI em que o modelo foi treinado."""
```

Ordem do pipeline: `normalize_dpi → deskew → denoise → binarize`.

**Implementado na F1.5** — `core/preprocess.py`. O Otsu veio do `opencv_autobox.py`
arquivado na F5.1, como previsto aqui.

**Correção desta spec:** o modo `auto` não decide por bimodalidade do histograma. Foi
o que tentei primeiro, e erra no caso que importa — com sombra de encadernação o
histograma É bimodal (metade escura contra metade clara) e o Otsu devolve 47,6% da
página como tinta. O critério avalia o **resultado**: se a fração de tinta não é
plausível para texto (0,05%–35%), cai no adaptativo.

Entrou também `BoxService.dividir_glifos_colados()`, que não constava da spec e é o
que a F1.1 apontou como limitador real: `findContours` devolvia `♞e5` como um box
só. O corte usa a **largura** do vale de tinta, não a profundidade — cortar por
profundidade partiria a coroa da dama, que tem vales fundos entre as pontas.

> **A largura do vale sozinha não decide, e isso levou duas medições para aparecer.**
> Onde a figurina está isolada entre texto normal, vale de colagem e vale interno de
> glifo ficam indistinguíveis, e o separador partia mais glifo bom do que colagem:
> 182 cortes falsos contra 73 bons, custando 2,3 pontos de F1 em relação a não separar.
> Quem passou a decidir é o **classificador** (F1.5b), comparando a pontuação do box
> inteiro com a menor das partes — cortes falsos caem para 2 e o separador enfim rende.
>
> Por isso `separar_colados` **não é mais um booleano com padrão `True`**: é `"auto"`,
> e só separa se houver árbitro. Sem modelo carregado, não separar é a decisão medida
> como melhor.
>
> **Re-medido em 2026-08-06, e a decisão volta à mesa.** Com as classes de ligadura da
> §5.2 item 6, o par colado passou a ter classe própria e o árbitro recusa o corte: o
> separador rende hoje **+0,1 de F1** (94,2 contra 94,1 desligado), contra +0,3 antes.
> Ele cobra uma passada de projeção de tinta e uma classificação extra por candidato para
> isso. `"auto"` continua sendo o padrão porque não está errado — mas desligar deixou de
> ser regressão e passou a ser troca de 0,1 ponto por processamento. Números na
> ROADMAP F1.5b.

Toda a detecção de boxes passa a consumir `preprocess.binarize`. Nenhum threshold
literal deve sobrar no código.

> **O corte de linha, da F12.** `BoxService.dividir_linhas_coladas` parte o box cuja
> altura passa de 1,6 escala — dois caracteres de linhas diferentes que se tocaram no
> papel. É o corte da §3/F1.5b transposto (`_cortes_do_perfil` sobre o recorte
> transposto), e tem duas diferenças que foram medidas, não escolhidas: **a lasca da
> linha vizinha é descartada** (pedaço menor que uma escala não vira box — emiti-lo
> custa 2,2 espúrios por caractere recuperado e derruba o F1 de 94,48 para 93,95), e
> **não há árbitro** (com ele, 94,06 contra 94,48 sem — a lasca pontua baixo e a regra
> da menor parte recusa o corte certo). No pipeline completo: F1 de 94,1 para 94,4.
>
> **A régua da página, da F11.** `escala_de_texto(img_bin)` é a altura de caractere
> medida por **massa de tinta**, e ela existe porque a mediana simples das alturas não
> sobrevive a uma trama de meio-tom: no quadro de pontuação da página 18 do Yusupov,
> 95,8% dos contornos têm 6x6 px ou menos e a mediana cai para **2**, o que faz o
> descarte de bloco não-texto jogar fora os caracteres. Ponderada, a mesma página dá 25.
> Mede sobre componentes conexos (nos contornos externos o diagrama leva toda a tinta) e
> ignora componente cuja caixa passe de 1% da página, porque caractere não ocupa isso.
>
> `remover_textura(img, img_bin)` apaga o componente que é **pequeno e claro** — as duas
> coisas: pequeno sozinho comeria o ponto final, que mede o mesmo e é escuro (tom 6–29
> contra 77–112 da trama). Quem tem a imagem passa a escala adiante:
> `descartar_blocos_nao_texto(boxes, escala=...)`.

---

## 4. Processamento de PDF

### 4.1 Um único backend: PyMuPDF

Remover `pdf2image`/Poppler. O projeto já depende de PyMuPDF (`fitz`), que renderiza
páginas nativamente e elimina uma dependência binária externa — hoje fonte recorrente
de erro no Windows, a ponto de existir tratamento dedicado em `main_window.py:980`.

```python
class PDFService:
    def load(self, path: str) -> int: ...
    def render_page(self, index: int, dpi: int = 300) -> Image.Image: ...
    def page_text_spans(self, index: int) -> list[Span]: ...   # texto nativo, quando houver
    def is_scanned(self, index: int) -> bool: ...              # heurística: sem texto extraível
    def close(self): ...
```

`is_scanned` é o que permite escolher automaticamente entre o caminho de texto (§4.2) e
o caminho de OCR (§4.3), em vez de exigir que o usuário adivinhe qual menu usar.

### 4.2 Substituição de glifos em PDF de texto

Corrige o defeito mais grave do projeto: `fontname="helv"` transforma toda peça em `·`
sem levantar erro (ROADMAP F0.2).

**A v1.0 §5 recomendava DejaVu Sans. Esta máquina não tem DejaVu instalada** —
`C:\Windows\Fonts\DejaVuSans.ttf` não existe. `seguisym.ttf` (Segoe UI Symbol) está
presente e foi verificado preservando os 12 glifos. A regra passa a ser: fonte
**empacotada no projeto**, com fallback para fontes do sistema.

**Implementado na F0.2.** Duas coisas foram aprendidas ao codificar, e esta seção já
reflete as duas:

**1. Checar se o arquivo existe não basta — e a lista de candidatas era ingênua.**
Medido neste Windows sobre as 12 peças:

| Fonte | Existe no disco | Cobre as 12 peças |
|-------|-----------------|-------------------|
| `seguisym.ttf` (Segoe UI Symbol) | sim | **sim** |
| `msgothic.ttc` (MS Gothic) | sim | **sim** |
| `arial.ttf` | sim | não — 0 de 12 |
| `segoeui.ttf` | sim | não — 0 de 12 |
| `times.ttf`, `calibri.ttf`, `cambria.ttc` | sim | não — 0 de 12 |

Arial estava na lista de candidatas do rascunho: passaria no teste "o arquivo existe"
e produziria exatamente o PDF corrompido que a seção tenta evitar. Foi retirada.

**2. `has_glyph` devolve o id do glifo, não um booleano** — `0` significa ausente.
O rascunho desta spec tinha a condição invertida, o que faria a validação aprovar
justamente as fontes ruins:

```python
def missing_glyphs(font_path: str, chars: str = CHESS_UNICODE) -> list:
    font = fitz.Font(fontfile=font_path)
    return [c for c in chars if not font.has_glyph(ord(c))]   # 0 = ausente

def resolve_chess_font(chars: str = CHESS_UNICODE) -> str:
    """
    Primeira candidata que cobre TODOS os caracteres. Levanta ChessFontError com
    o diagnóstico por fonte se nenhuma servir — falhar alto aqui é proposital.
    """
```

`assets/fonts/DejaVuSans.ttf` continua **não empacotada**: hoje o código cai no Segoe
UI Symbol desta máquina. Numa máquina sem ele, agora falha com mensagem clara em vez
de corromper — mas empacotar a fonte segue pendente.

Inserção:

```python
page.insert_font(fontname="chessuni", fontfile=resolve_chess_font())
page.insert_text(origin, texto, fontname="chessuni", fontsize=size)
```

**Não usar `insert_textbox` para spans curtos.** Ele reflui o texto dentro do
retângulo e desloca a notação. Para um span inline como `♘f3`, usar `insert_text` na
`origin` (baseline) do span original — preserva o alinhamento com a linha de texto.

Ajuste de largura: glifos Unicode de xadrez costumam ser mais largos que os da fonte
original. Medir com `fitz.Font.text_length()` e, se exceder o bbox, reduzir o
`fontsize` em passos de 0.5 pt até caber (mínimo 60% do original; abaixo disso,
registrar aviso no relatório em vez de deformar).

### 4.3 PDF pesquisável (camada de texto invisível)

**Implementada na F2.1** — `core/searchable_pdf.py`. Substituiu
`neural_pdf_processor.process_scanned_pdf`, que rasterizava o documento inteiro e
destruía todo o texto selecionável; aquele módulo foi removido.

Verificado numa página real: 0 caracteres extraíveis na entrada, 3025 na saída, imagem
original preservada.

Dois cuidados que a implementação mostrou serem necessários:

- **Pular páginas que já têm texto.** É a heurística `is_scanned` de §4.1: escrever a
  camada de OCR sobre uma página digital duplicaria o conteúdo, e a busca passaria a
  devolver cada trecho duas vezes.
- **`doc.subset_fonts()` antes de salvar.** A fonte de símbolos tem 2,3 MB e seria
  embutida inteira em cada PDF gerado — 1342 KB contra 70 KB num teste de 200
  inserções.

Custo residual conhecido: ~200 bytes por caractere na camada de texto, porque cada
`insert_text` emite um bloco gráfico completo. Agrupar caracteres por linha reduziria
isso, e depende da ordem de leitura (§ROADMAP F1.6).

**Regra:** a página original nunca é rasterizada. O OCR entra como camada de texto
invisível por cima.

```python
def write_searchable_layer(page: fitz.Page, boxes: list[BoxEntry], dpi_scale: float):
    """
    Escreve o texto reconhecido com render_mode=3 (invisível) posicionado sobre
    cada box. O resultado é pesquisável e copiável; visualmente idêntico ao original.
    """
    for b in boxes:
        if not b.char:
            continue
        rect = fitz.Rect(b.x1, b.y1, b.x2, b.y2) * dpi_scale
        size = _fit_size(b.char, rect)
        page.insert_text(
            (rect.x0, rect.y1),          # baseline no rodapé do box
            b.char,
            fontname="ocruni",
            fontsize=size,
            render_mode=3,               # invisível
        )
```

Três modos de saída, escolhidos pelo usuário:

| Modo | Comportamento |
|------|---------------|
| `searchable` | Página original + camada invisível — **padrão** |
| `replace` | Substitui glifos de xadrez por Unicode visível (§4.2) |
| `both` | Substituição visível + camada pesquisável |

`resolution=200.0` fixo (`neural_pdf_processor.py:117`) deixa de existir — a
resolução da página original é preservada porque ela não é reescrita.

### 4.4 Relatório e dry-run

Requisitos RF-06 e RNF-04 da v1.0, nunca implementados.

```python
@dataclass
class Replacement:
    page: int
    bbox: tuple[float, float, float, float]
    original_font: str
    original_text: str
    replacement_text: str
    confidence: float
    warnings: list[str]
```

- `--dry-run` (e checkbox na UI): detecta, gera relatório, **não escreve o PDF**
- relatório em JSON e CSV, salvo ao lado do arquivo de saída
- avisos obrigatórios: fonte sem glifo, fonte reduzida além de 80%, confiança abaixo
  do limiar, span ignorado por heurística de diagrama

Num conversor que reescreve PDFs, dry-run é o único jeito de conferir antes de destruir.

### 4.5 Perfis de mapeamento

V1.0 §10 pede perfis por livro/editora. Hoje há um dict hardcoded
(`chess_pdf_processor.py:12`).

`config/profiles/<nome>.json`:

```json
{
  "name": "Quality Chess — Merida",
  "mode": "unicode",
  "font_patterns": ["merida", "chess"],
  "mapping": { "K": "♔", "Q": "♕", "R": "♖", "B": "♗", "N": "♘", "P": "♙",
               "k": "♚", "q": "♛", "r": "♜", "b": "♝", "n": "♞", "p": "♟" },
  "diagram_detection": { "min_lines": 4, "chess_span_ratio": 0.7 }
}
```

Seleção automática por `font_patterns`, com override manual na UI. Os limiares de
detecção de diagrama, hoje literais em `is_block_a_diagram`, passam a ser configuráveis
— fontes com subset e nome aleatório (`ABCD+F1`) precisam de ajuste por livro.

---

## 5. Reconhecimento

### 5.1 Cadeia de fallback

`OCRService.fallback_chain` já implementa neural → k-NN → EasyOCR. Manter, com
mudanças:

- **retornar sempre `(char, source, confidence)` e gravar os três no `BoxEntry`**;
  hoje a confiança é calculada e descartada
- limiares vêm de configuração, não de literais espalhados
  (0.85/0.85 em `main_window.py:475`, 0.8/0.9 em `main_window.py:530`)
- [feito] EasyOCR retornava `0.0` fixo — passou a usar a confiança real de
  `results[0][2]`. O Tesseract também reporta confiança, via `image_to_data`
  (`tesseract_ocr_conf`)

[feito] Os dois ramos duplicados do `if reader` em `ocr_service` foram unificados.

### 5.2 Dados de treino — saneamento obrigatório

Executar **antes** de qualquer novo treino:

1. [feito] **`sym_f7`** — eram 127 imagens da casa de xadrez **"f7"** (confirmado
   olhando as amostras; a hipótese de `f7` hexadecimal = `÷` estava errada).
   Renomeada para `ligature_f7`. Corrigir o rótulo no `model_meta.json` fez o modelo
   **já treinado** acertar 127/127 dessas amostras, sem retreinar.
2. [feito] **`lower_ä`** — estava vazia porque `cv2.imwrite` falha em caminho
   não-ASCII no Windows e devolve `False` sem levantar erro. É a razão de ser da
   regra de nomes só-ASCII do `char_to_folder`.
3. ~~**`training_data_2/`** — 138 PNGs soltos fora do padrão de pastas por classe.
   Classificar ou descartar.~~ — **a descrição estava errada; ver abaixo.**

   > **Medido em 2026-08-04: não são 138 PNGs soltos.** São **70** soltos mais
   > **68 pastas de classe com 192.600 imagens** — no formato certo, e uma base
   > *maior* que a `training_data/` (103 classes, 128.850). "Classificar ou
   > descartar" descreve um serviço de meia hora; o que está ali é outra coisa.
   >
   > **E há motivo para suspeitar que os rótulos são do modelo, não de humano.**
   > O formato é exatamente o que `LearningService.batch_extract_and_classify`
   > grava (`output_dir/<classe>/<uuid>.png`, 32×32). A distribuição reforça: a
   > classe maior é `digit_1` (16.962), acima de `lower_e` (16.090) — em texto de
   > livro o `e` domina com folga, e é o que se vê na `training_data`
   > (`lower_e` 25.218 contra `digit_1` bem abaixo). Um excesso de `1` é a
   > assinatura do classificador confundindo `l`, `i` e `I`, que é a confusão
   > medida na F3.6.
   >
   > **Nada no código lê essa pasta**, então ela é inerte hoje. O risco é de
   > alguém a mesclar na `training_data/` por parecer serviço pendente: seriam
   > 192 mil rótulos do próprio modelo realimentando o treino, com os erros
   > junto. A F1.4 mostra o estrago de 127 amostras mal rotuladas.
   >
   > **Decisão pendente, e é do dono dos dados**, não deste documento: só quem
   > gerou a pasta sabe se aqueles rótulos foram conferidos. Até lá, fica de fora
   > do treino e fora do repositório (`.gitignore`).
4. [feito] **`folder_to_char`** — decodificação de `ligature_hex_*` implementada,
   com hex de largura fixa (a variável era ambígua). Ganhou `strict=True`, que
   levanta em vez de devolver `"?"`: devolver `"?"` em silêncio foi o que deixou o
   defeito de `sym_f7` passar despercebido.

**Regra que saiu daqui:** nunca usar `cv2.imread`/`cv2.imwrite` como teste de
integridade de arquivo. No Windows eles falham em caminho não-ASCII e devolvem
`None`/`False`, indistinguível de "arquivo corrompido". A primeira versão da
migração caiu nisso e apagou PNGs válidos. Use `open()` + `cv2.imdecode`, e prefira
mover para quarentena a apagar.
5. [investigado] **Peças pretas** — não existem neste domínio; não há o que coletar.
   Peão não tem letra em notação algébrica, e o livro usa um único conjunto de
   figurinas para os dois lados (verificado: em `17...♞e5 18.♛c2 ♞a6 19.♞c4`, o lance
   das pretas e o das brancas usam o mesmo glifo). O alfabeto do domínio é K Q R B N,
   que é exatamente o que o modelo tem.

   A ambiguidade branca/preta é **insolúvel visualmente** — depende da paridade do
   número do lance. É trabalho da F1.7, não do classificador.
6. [decidido — **foram intencionais**, confirmado pelo dono dos dados em 2026-08-06]
   **As 16 classes de ligadura.** O retreino daquele dia levou a base de 103 para
   **119 classes**, com pastas novas: `ligature_Th`, `ligature_an`, `ligature_ffi`,
   `ligature_fi`, `ligature_ft` — e `ligature_e4`, `ligature_f2`, `ligature_f3`,
   `ligature_f6`, `ligature_f7`, `ligature_f8`, que são **casa de xadrez**, não ligadura
   tipográfica.

   São duas famílias diferentes em espécie, e a decisão cobre as duas. `fi` e `ffi` são um
   glifo só na fonte e não existe segmentação que as separe. `e4` e `f6` são dois
   caracteres que `findContours` devolve colados. Nos dois casos, dar classe ao par é
   melhor que deixar o classificador escolher um caractere errado — que era o que
   acontecia, e é o mesmo raciocínio que fez o `ligature_f7` do item 1 valer a pena
   depois de rotulado certo. O que o item 1 mostrou não foi que classe de par é ruim: foi
   que **classe mal rotulada** é ruim.

   **O que a decisão rendeu**, com a ressalva de que os conjuntos rotulados são diferentes
   (10 páginas contra 9), o que faz a comparação indicativa e não controlada: acurácia de
   caractere na página real de 95,32% para 96,04%, e F1 do pipeline de 93,8 para 94,2
   (ROADMAP F1.9 e F1.5b, re-medidas).

   **Onde a decisão cobra**, medido em 2026-08-06 por `medir_lexico.py`: em **60 dos 336
   caracteres errados** das páginas rotuladas (18%) o modelo prediz uma ligadura onde a
   verdade tem um caractere só — `f6` no lugar de `5`, `Th` no lugar de `d` —, e cada um
   injeta um caractere no texto. É o maior balde de erro depois de palavra de prosa. Não
   reverte a decisão, que rendeu +0,4 de F1 no total; diz onde coletar amostra. Outros 8
   erros contados não são erro: são ligadura **certa** que o `comparar` de
   `core/avaliacao_pagina.py` pune, porque ele casa um box gerado com um rotulado só e o
   par colado tem dois. O metro subestima estas classes, por 2,4%.

   **A consequência a acompanhar** é que uma classe de par concorre com o separador de
   glifos colados, e o efeito está medido: a vantagem do árbitro do corte caiu de +0,3
   para +0,1 de F1, com cortes bons de 23 para 13. Como o separador rende hoje 0,1 ponto,
   `separar_colados="auto"` passou a ser candidato legítimo a desligar — decisão da §3,
   não desta seção. O que **não** dá mais para medir é a atribuição: os pesos de 103
   classes foram sobrescritos pelos dois retreinos da madrugada, sem cópia, então não há
   como rodar o modelo antigo nas mesmas 10 páginas para separar o efeito das classes do
   efeito da página nova. A F1.3 guardou `custom_model_2026-08-03_antes_f13.pth` antes de
   trocar de modelo; estes retreinos não guardaram nada.

Adicionar validação que roda antes do treino e falha alto:

```python
def validate_dataset(data_dir: str) -> list[str]:
    """Erros: pasta vazia, nome irreversível, classe abaixo do mínimo, PNG ilegível."""
```

### 5.3 Balanceamento — [feito]

Proporção atual: 25.075 (`lower_e`) para 1 (`upper_Z`). Com `CrossEntropyLoss` sem
pesos e sorteio uniforme, as classes raras não somem do modelo — o que se mede é
mais sutil: elas acertam 77,2% contra 99,9% das classes grandes, e 5 delas ficam em
zero. É a diferença entre acurácia global e recall macro.

```python
from torch.utils.data import WeightedRandomSampler

pesos   = pesos_de_amostragem(dataset.contagens, dataset.labels, modo="sqrt")
sampler = WeightedRandomSampler(torch.DoubleTensor(pesos), len(dataset),
                                replacement=True)
loader  = DataLoader(dataset, batch_size=64, sampler=sampler)  # sem shuffle com sampler
```

Medido com holdout de 20% por classe (121.020 de treino, 5.768 de avaliação,
8 epochs, mesma semente), recall macro: **88,66% → 96,71%**, e a acurácia global
sobe junto (96,58% → 98,63%).

Três correções ao que este parágrafo dizia antes:

1. **`class_weight` na loss não é alternativa equivalente ao sampler.** Medido,
   dá 88,60% — igual ao baseline. Reescalar o gradiente não resolve quando a
   classe rara aparece em 1 de cada mil lotes. O sampler muda o que o modelo vê.
2. **O peso é 1/√n, não 1/n.** O inverso puro dá 0,5pp a mais de macro e 0,7pp a
   menos de acurácia global, e derruba as classes grandes de 99,9% para 99,6% —
   e as 10 maiores sozinhas são 79,6% da base. Há um teto de repetição por amostra
   (`TETO_DE_REPETICAO`) que quase não encosta no modo padrão; ele existe para o
   modo `inverso` e para bases degeneradas.
3. **O piso (`MIN_AMOSTRAS_POR_CLASSE = 10`) reporta, não exclui.** Das 33 classes abaixo do
   piso nesta base, fazem parte `'K'` (6), `'Q'` (5) e `±` `∓` `∞` `□` `■` `△` `▼`:
   vocabulário do domínio, raro no texto e não lixo. Com balanceamento, a faixa
   abaixo de 20 amostras vai a 92,1% e nenhuma classe fica zerada. Excluir
   significaria o modelo nunca poder produzir esses caracteres — e ele não cai no
   fallback quando erra com confiança, grava o caractere errado.

**Augmentation passou a ser gerada sob demanda em `__getitem__`.** Materializá-la
no construtor custava 4,89 GB de RAM na base real (1.145.367 arrays float32 de
4 KB) contra 133 MB, e ~9,5 min por epoch contra ~70 s. Além do custo, congelar as
variantes anula o sampler: sortear a mesma amostra 50 vezes devolvia as **mesmas
9 imagens**. Sob demanda, cada sorteio é uma variante nova, por 53 µs.

Consequências a manter em vista:

- Um epoch voltou a valer **uma** passada pela base (valia nove). O diálogo de
  treino diz isso, porque muda o número de epochs que faz sentido pedir.
- `CharDataset(augment=False)` é o que a F1.3 deve usar para validação — a
  contaminação que este parágrafo alertava deixou de ser estrutural.
- 1 sorteio em 9 devolve a amostra intacta (`FRACAO_SEM_AUGMENTATION`): é a
  proporção do desenho antigo, e é imagem limpa que chega na predição.

Pastas que não são classe deixaram de virar classe: as que começam com `_`
(a `_quarentena` do §5.2 pegava o **índice 0** e deslocava o mapa inteiro) e as
que não têm nenhuma amostra legível (`lower_ä` ocupava uma saída da rede que
nunca poderia estar certa).

### 5.4 Avaliação — [feito]

Antes: acurácia calculada sobre o treino aumentado, e "melhor modelo" escolhido por
*training loss* — critério que seleciona exatamente o ponto de maior overfitting.

```
split estratificado 80 / 15 / 5   (treino / validação / teste)
early stopping por validation loss, paciência 5
checkpoint pelo melhor validation loss  ← não training loss
```

Implementado em `core/avaliacao.py` e ligado ao `NeuralTrainer`. Relatório ao
final do treino, em `relatorio_treino.txt` (+ `.json`), ao lado do modelo, e
alcançável pelo menu **Ferramentas → Relatório do último treino**:

- acurácia global de validação, **recall macro** e número de classes zeradas
- confusões mais frequentes — é o que a matriz serve para mostrar; a tabela
  103×103 é quase toda zero, então o `.json` guarda os pares fora da diagonal,
  que carregam a mesma informação (a diagonal são os acertos, já registrados)
- lista das 10 piores classes
- histórico por epoch (perda de treino, perda de validação, acurácia, macro)
- amostras de validação erradas, gravadas em `relatorio_treino_erros/`, em
  subpastas `esperado_virou_previsto/`, **com teto de 200** e priorizando os
  pares mais frequentes: um treino ruim erra milhares, e despejar tudo em disco
  transformaria o relatório em outro problema

Três decisões que não estavam aqui e vieram de olhar a base:

1. **Classe com menos de `MIN_PARA_DIVIDIR` (5) amostras não é dividida** — vai
   inteira para o treino e entra na lista de não avaliáveis, que o relatório
   mostra em primeiro lugar e o `callback` anuncia. São 24 das 103 classes.
   Tirar 15% de uma classe de 3 piora o modelo para medir mal; esconder isso
   seria o mesmo defeito que esta seção veio corrigir, com outra roupa.
2. **O conjunto de teste não tem piso de 1 amostra por classe.** Serve para um
   único número final, não para recall por classe.
3. **Os pesos do sampler (§5.3) passam a vir das contagens do treino**, não da
   base inteira — contar amostras que o modelo não vai ver subestimaria o peso
   das classes raras.

Quando a base é pequena demais para separar validação (toda classe abaixo do
mínimo), o treino continua funcionando e **avisa** que voltou a escolher o
checkpoint pela perda de treino. É o caso de uma base recém-começada.

Pendente: retreinar depois de encontrar a melhor epoch, usando 100% dos dados.
Recuperaria os 20% separados, ao custo de dobrar o tempo de treino.

### 5.5 Compatibilidade de modelo — [feito, F7.3]

`model_meta.json` mapeia índice → caractere. Os índices vêm de
`sorted(os.listdir(data_dir))` (`neural_trainer.py:220`). **Adicionar ou remover
qualquer pasta desloca todos os índices seguintes** — e um `custom_model.pth` antigo
passa a devolver caracteres errados, sem nenhum erro.

Correção: gravar no meta a versão do schema e um hash da lista de classes; recusar
carregar modelo cujo hash não bata com o dataset.

```json
{ "schema_version": 2,
  "classes_hash": "sha256:…",
  "trained_at": "2026-08-03T…",
  "num_classes": 105,
  "idx_to_char": { … } }
```

> **Como ficou, e por que o campo principal é outro.** Os nomes saíram em português
> (`classes_sha256`, `treinado_em`) e entrou um campo que a spec não previa:
> **`modelo_sha256`**, a impressão dos próprios pesos. É ele que fecha o buraco real.
>
> A spec supunha que o perigo era o `idx_to_char` ficar defasado em relação à base. Não
> é: o metadado **leva o `idx_to_char` junto**, então a predição é auto-consistente
> mesmo com a base mudada. O perigo é o `.pth` estar pareado com o metadado **de outra
> rodada** — cenário que o próprio `.gitignore` cria, já que o metadado é versionado e os
> pesos não. `classes_sha256` ficou, mas como informação, não como trava.

### 5.6 Validação por legalidade — [feito]

`core/notacao.py` reconstrói o texto a partir dos boxes, lê a notação e confronta cada
lance com as regras (`python-chess`). Menu **Ferramentas → Validar notação de xadrez**;
37 ms para 1.487 boxes, então roda na thread da UI.

```python
analise = notacao.analisar(boxes)      # -> Analise(lances, correcoes, ...)
notacao.aplicar(boxes, analise.correcoes)
```

Contratos que a implementação estabeleceu, todos vindos de medição na página real:

1. **Espaço é inferido pela lacuna, com uma segunda passada só para números.** Os
   algarismos desta fonte têm avanço tabular (lacuna mediana de 10 px depois de `'1'`,
   contra 1–2 px depois de letras), e nenhum limiar único separa "15" de "c4 c5".
2. **Box sem caractere ocupa espaço.** A lacuna entre dois vizinhos é a **maior** do
   caminho, não a distância direta — senão esvaziar um box abriria um espaço no meio
   da palavra.
3. **O lance não é reconhecido por expressão regular**, e sim entregue inteiro à
   legalidade. Casar a forma exata do SAN quebra no primeiro caractere errado, que é
   justamente o caso a corrigir.
4. **Uma posição só, ou nada.** Depois de uma variante o texto volta à linha principal
   sem marcar; quando mais de uma posição explica o mesmo número de lance, o
   analisador se declara incerto e reporta em vez de corrigir.
5. **Só box sobrando vira edição.** Caractere faltando não tem box para apontar.

O peso da confiança (F3.2) está em `custo_da_troca` e hoje é inerte: medido, o modelo
erra com confiança mediana 1,000. Ver F1.9 no ROADMAP.

### 5.7 Texto impresso na vertical — [feito, F8.1, em `core/vertical.py`]

Rótulo girado ao lado do diagrama (*"Analysis diagram"*). Não estava na spec, e o custo
de não tratá-lo é calado: o classificador acerta 94,4% do recorte de pé e **8,4%** do
mesmo recorte deitado — devolvendo outra letra, com confiança normal.

O contrato, todo ele vindo de medição:

1. **A geometria propõe, o classificador dispõe.** `candidatos` recolhe pilhas
   plausíveis; o ângulo é escolhido pela confiança **média da pilha**, e 0° (não é
   girado) ganha por padrão — só perde por uma margem. **Sem árbitro, nada acontece**,
   como em `dividir_glifos_colados` (F1.5b).
2. **A pilha é uma unidade** em tudo que a toca: fora do merge vertical (que a colaria),
   fora do corte de glifo colado (que a cortaria no eixo errado), e um elemento só na
   ordem de leitura (senão cada letra cai numa linha de texto diferente).
3. **Girar é transposição.** Só múltiplos de 90°; nada de interpolação antes de
   classificar. `endireitar` é o único lugar que raciocina sobre o sinal do giro.
4. **Quem consome box pede o recorte de pé** — a cadeia de fallback, a base de
   referência do k-NN e o PDF pesquisável, que escreve a camada invisível girada
   (`insert_text(rotate=...)`, com a convenção conferida contra o texto extraído).

`medir_vertical.py` refaz as quatro medições da fase.

### 5.8 Léxico do texto corrido — [a fazer, F9]

Dicionário de palavras sobre os pedaços de **prosa**, no lugar que a §5.6 deixou vazio:
a legalidade cuida da notação e nada cuida do texto entre os lances. Módulo novo
`core/lexico.py`.

Os contratos, e nenhum deles é preferência de estilo — todos saem de defeito já pago:

1. **A fronteira com a notação é a que já existe.** `notacao._fatiar` tipa cada pedaço
   em `lance` ou `outro` e `parece_lance` é a peneira. O léxico só vê `outro`. Aplicar
   lista de palavras a `Bxf6` ou `exd5` destruiria a notação, porque nenhum deles é
   palavra de idioma nenhum — e a legalidade é um dicionário melhor, por ser dependente
   de contexto: `Nf3` é válido numa posição e impossível na seguinte.
2. **Fora do dicionário significa "não mexer".** Palavra desconhecida é **sinalizada**,
   nunca aproximada da mais parecida. `Nimzowitsch` não está em lista alguma, e forçar a
   troca entregaria prosa limpa e falsa — a forma de falha da §4.2 (o `·` da Helvetica) e
   da §3 (o separador que partia glifo bom sem ninguém ver).
3. **Os candidatos vêm do classificador, não do alfabeto** — o padrão de árbitro da §3 e
   da §5.7. Falta o pré-requisito: `NeuralPredictor.predict` e
   `LearningService.predict_neural` devolvem `Tuple[str, float]`, um caractere só. Sem
   `predict_topk`, trocar `l` por `1` e por `q` custam o mesmo e a correção inventa
   caractere que nenhum box sustenta. A triagem do item 5 **não** depende disso.
4. **Só box sobrando vira edição** — item 5 da §5.6, pelo mesmo motivo. Caractere
   faltando não tem box para apontar, e vira sugestão.
5. **O produto principal é triagem, não correção.** A F1.9 mediu que a confiança só
   ordena (AUROC 0,86–0,87): no corte 0,90 da §7.2, revisando 2,4% da página o revisor
   acha 39,7% dos erros, e para achar metade é preciso ir a 0,99 (re-medida de
   2026-08-06). Não há corte que ache o resto por preço aceitável. "Fora do dicionário" é
   um sinal **independente da confiança** — pega o erro lido com confiança 1,000 — e
   entra como filtro na §7.4.
6. **Nada acontece sem dicionário carregado.** Padrão é não agir, como
   `separar_colados="auto"`.

   > **Precisão que a F9.2 obrigou:** "carregado" quer dizer **a lista geral**
   > (`Lexico.sinaliza`), não qualquer lista. Com o dicionário do livro ao lado e o do
   > idioma ausente, `vazio` diria falso e a página inteira acenderia — dezenas de
   > palavras contra centenas. As duas fronteiras (`juntar_hifenizadas`,
   > `partir_colada`) continuam olhando `vazio`: elas só agem quando o resultado **é**
   > palavra conhecida, então lista curta as deixa quietas.
7. **O idioma é escolha do perfil (§4.5), não adivinhação.** Estes livros são em inglês;
   dicionário do idioma errado é pior que nenhum.

Sem dependência nova: um `set` de palavras mais os candidatos do top-k. `pyspellchecker`
e `hunspell` ficam **descartados de propósito** — o gerador de candidatos deles varre o
alfabeto inteiro, que é o modo de falha do contrato 3.

**A lista está empacotada** em `assets/lexico/`, em dois arquivos gerados por
`importar_lexico.py` a partir do dicionário que o usuário mantinha para o ABBYY
FineReader:

| | palavras | | |
|---|---:|---|---|
| `en.txt.gz` | 73.447 | 0,21 MB | vocabulário do idioma |
| `nomes.txt.gz` | 237.018 | 0,74 MB | nome próprio |

A divisão sai da **caixa da entrada original** no arquivo do ABBYY, que guarda palavra
comum nas duas caixas (`build` e `Build`) e nome próprio só na Capitalizada (`Andretti`).
`carregar(nomes=False)` deixa os nomes de fora, e a troca está medida (ROADMAP F9.1,
medida 3): só o idioma dá 58,5% de recall com 12,1% de alarme falso; com os nomes, 53,8% e
5,8%. **Nome próprio baixa o alarme e esconde erro**, e não há joelho na curva onde a
escolha se faça sozinha.

Duas notas de formato. O `.gz` existe porque 0,94 MB foi o que tirou o tamanho do caminho
— a lista da medida 2 tinha 4,23 MB e não entrou; `_ler` decide pelo sufixo e continua
abrindo texto puro. E as 73 mil do idioma dão o mesmo alarme falso que as 370 mil de lá,
sem o defeito de ser americana: `manoeuvres` está nesta. Fica a ressalva da §9.2 — a
`assets/fonts/DejaVuSans.ttf` também deveria estar empacotada e não está.

`palavras_da_pagina`, `Simbolo`, `custo_da_troca`, `Correcao` e `aplicar` (§5.6) são
reusados inteiros — segmentação de palavra, confiança por box, distância de edição
ponderada e edição que não inventa box já estão escritos.

**Na revisão** — `lexico.suspeitas_da_pagina(boxes, lex)` é o único caminho da UI até
o dicionário, e existe para o contrato 1 valer num lugar só: ela roda
`notacao._fatiar` e entrega ao léxico apenas o que ele tipa `outro`. Escrever esse
filtro de novo em cada chamador é como a F1.5 acabou medindo uma coisa e a aplicação
fazendo outra.

O sinal aparece em três lugares, e em nenhum deles rouba a cor da §7.2:

| onde | como |
|---|---|
| canvas | sublinhado roxo sob o box, como corretor ortográfico |
| lista lateral | uma coluna `*` à esquerda, largura fixa — a segunda, depois da seta de seleção da §7.11 |
| contador | "N fora do dicionário" — palavras, não boxes |

**A cor do contorno continua sendo só a confiança**, porque os dois eixos são
independentes e o caso que só o dicionário pega é justamente o box verde de
confiança 1,000. Pintá-lo apagaria o dado que já estava lá para mostrar outro.

Custo: 9,5 ms numa página de 1.589 boxes, e `update_sidebar` roda a cada tecla do
modo digitação (§7.3) — é a ordem do `deepcopy` que a §6.1 teve de tirar desse
caminho. Fica em cache com chave `(char, x1, y1)` por box, que custa 0,36 ms; a
posição entra na chave porque mover um box muda onde a `notacao` corta as palavras.
A carga das listas é preguiçosa: 150 ms que não se pagam em quem só abre um `.box`.

**Dicionário do usuário — [feito, F9.2].** As palavras que uma lista genérica não tem são
as que se repetem num livro de xadrez: jogador (Yusupov, Nimzowitsch), abertura (Benoni,
Grünfeld, Najdorf), vocabulário do jogo (zugzwang, fianchetto, prophylaxis), editora. Sem
elas o sinal do contrato 5 acusa erro em toda página e o revisor aprende a ignorá-lo. A
lista cresce pela correção do usuário, como em §7.5 e §7.10 — com a regra da §7.10 valendo
aqui também: **silêncio não é confirmação**, só entra a palavra digitada à mão.

> **Correção desta spec: não é por perfil, é por documento.** A §4.5 escolhe perfil por
> **padrão de fonte**, não por livro — `perfis.escolher` casa `font_patterns` contra o nome
> da fonte, e dois livros compostos na mesma fonte cairiam na mesma lista, que é o
> contrário do motivo do item. A lista ficou ao lado do documento, como o rascunho da §6.4:
> `livro.pdf` → `livro.lexico.txt`, e `pasta/pagina-0012.jpg` → `pasta/lexico.txt`, porque
> um livro digitalizado é uma pasta e não uma página. Texto puro, ordenado, uma por linha:
> é assim que se tira à mão a palavra que entrou errada, e não há tela que faça isso.
>
> **O que não entra é metade do desenho**, porque palavra errada na lista cala o alarme em
> silêncio: a que ninguém tocou (ainda que com confiança 1,000), a que tem box vazio dentro
> — achado pela geometria, já que box vazio não vira símbolo —, a que tem dígito no meio, e
> notação. Medido nas 10 páginas rotuladas com o protocolo de deixar-uma-de-fora, o ganho é
> **9,2% do alarme falso**: das 128 palavras distintas que acendem, 124 aparecem numa
> página só, e essas nenhuma lista alcança (ROADMAP F9.2).

O `nomes.txt.gz` acima **não** é este dicionário, e a diferença importa: ele vem
empacotado e cobre os oito primeiros exemplos deste parágrafo, mas `do_usuario` guarda o
que **este** usuário digitou. Misturar os dois apagaria a única pergunta que `procedencia`
existe para responder — se o acerto veio da lista dele ou de uma de prateleira —, que é
como se sabe se a lista do usuário está fazendo trabalho.

**Medir antes de escrever**, na ordem, e a primeira medição pode encerrar o item:
quantos caracteres errados das 9 páginas rotuladas caem dentro de palavra de prosa (fora
de lance, fora de pontuação); a precisão da sinalização; e F1 com e sem o léxico **mais**
correções boas e ruins contadas em separado, na forma da tabela da F1.5b — medir só por
recall foi o que deixou o defeito da §3 passar. `core/avaliacao_pagina.py` é o arnês.

Alcance conhecido, das confusões que a §5.4 mediu: `1`↔`l` e a ligadura `f`→`f7` são
visíveis ao léxico; `,`↔`'`, `.`↔`-` e `✝`↔`+` não são, porque pontuação não está dentro
de palavra. E palavra partida por hífen no fim da linha só existe depois da ordenação de
leitura (ROADMAP F1.6).

### 5.9 Texto em negativo — [feito, F10, em `core/negativo.py`]

Nome dos jogadores em branco sobre tarja preta (Yusupov), título de seção em branco sobre
tarja cinza (Kasparov). Não estava na spec, e o custo de não tratá-lo é **perda total**,
não erro: `binarize` deixa a tinta em branco, a tarja inteira vira um borrão, o
RETR_EXTERNAL devolve **um** box e os caracteres de dentro não chegam a existir. Medido
na página 33 do *Chess Evolution 1*: 6 tarjas, 6 boxes, zero caracteres.

O contrato, todo ele vindo de medição:

1. **A polaridade é do box, não da página.** `BoxEntry.negativo` (§2.1) e
   `negativo.positivar` no funil da §5.7. Inverter a página inteira seria mais simples e
   está descartado: o usuário confere o box contra a página impressa, e mexer no que ele
   vê para consertar o que o modelo lê troca um problema de leitura por um de revisão.
2. **A geometria propõe, o conteúdo dispõe** — o padrão da §3 e da §5.7, com o árbitro
   trocado pelo teste de resultado de `preprocess.tinta_plausivel`: inverte-se a faixa e
   pergunta-se se o que apareceu tem tamanho de caractere *em relação à altura dela*.
   Foto, logotipo e bloco de ruído caem aqui.
3. **Duas réguas separam tarja de palavra em negrito**, e ambas saem de tabela: proporção
   ≥ 4:1 (tarja 5,34–13,70; palavra sublinhada 3,00–4,72) e altura ≥ 2 caracteres
   medianos da página (tarja 2,57–28,50; palavra 0,41–1,21). O risco que elas cobrem é o
   pior da fase: aceitar uma palavra sublinhada **substituiria por lixo um texto que o
   caminho normal já lia certo**.
4. **A faixa é aparada antes de ser lida.** Tira decorativa hachurada encosta no topo das
   letras e funde meia linha num componente só — 88 componentes numa tarja de 20
   caracteres, dois deles com metade da tarja cada. Aparar **não** é condição de aceite:
   tarja de tom fraco não tem linha cheia nenhuma, e exigi-la perdia tarja legível. Onde
   a apara não pega — tira escura, 3 das 438 tarjas do Yusupov — a rede é `na_linha`: os
   componentes que já se sabe serem caractere dizem onde está a linha, e o que cai fora
   dela é decoração.
5. **O que sai da faixa é box comum**, e passa por tudo que box passa — merge do pingo
   do 'i', corte de glifo colado (com o `th` da faixa invertido, senão o vale entre duas
   letras é um pico), ordem de leitura. Filtrar ali seria refazer, pior, o que o pipeline
   já faz.
6. **A lista volta ordenada por (y1, x1).** `merge_vertical_boxes` aceita distância
   vertical negativa; fora de ordem, uma letra da tarja casa com um box do outro lado da
   página e a caixa resultante absorve a coluna inteira — medido, 1.889 boxes viraram 27.

`medir_negativo.py` refaz as medições da fase, e aceita `--imagens` para rodar sobre
scans em vez de PDF.

### 5.10 Texto sobre trama — [feito, F11, em `core/trama.py`]

O quadro de pontuação que fecha cada capítulo do Yusupov é um painel chapado que o
escaneamento devolve como nuvem de pontos. O custo é perda total, como na §5.9, mas por
dois caminhos: a trama **envenena a régua** da página (§3) e **solda** o texto ao fundo —
o painel sai como um contorno de 1049x390 e o que está escrito nele não vira box.

O contrato:

1. **Rebinarizar o recorte desfaz a solda**, e é a manobra da §5.9 com a polaridade
   normal. Na página inteira o papel domina e o Otsu global corta abaixo da trama; dentro
   do painel sobram trama (tom ~99) e texto (tom ~5), e o Otsu local corta em 143 — acima
   da trama. Medido: 71 componentes de tamanho de caractere onde havia zero.
2. **Tabuleiro é quadrado; painel é largo.** É o que impede o diagrama de virar uma caixa
   por peça, contra o que a F1.8 fixou. Medido: diagramas em 1,00–1,01 de proporção,
   painel em 2,69; o limiar é 1,5 e o vão entre as populações é inteiro.
3. **Só se olha dentro de bloco que o descarte ia jogar fora**, o que torna a fase segura
   por construção — o pior caso é o estado anterior a ela.
4. **A régua dos glifos de dentro é a da página**, não a do bloco: o painel tem 390 px de
   altura para texto de 30, e medir contra ele recusaria tudo. É a diferença para a §5.9,
   onde a tarja tem a altura de uma linha.

Não entrega palavra separada em caracteres dentro do painel — a trama liga letra a letra
e o que sai são caixas de palavra. Três discriminadores alternativos foram medidos e
recusados (densidade de vizinhos, porosidade, segundo Otsu global); estão na ROADMAP F11.

---

## 6. Aplicação

### 6.1 Estado e histórico — [feito, F0.3 e F3.8]

Padrão único: **snapshot após a mutação**.

```
abrir arquivo         → snapshot(estado inicial)
qualquer mutação      → aplica; snapshot(novo estado)
undo                  → índice−1
redo                  → índice+1
```

Remover `on_mutation_start` e todas as chamadas de snapshot pré-mutação. Hoje os dois
padrões coexistem e o redo perde estado permanentemente (verificado — ROADMAP F0.3).

`HistoryManager` passa a expor `is_dirty()`, consumido por §6.4 e pelo autosave.

> **Duas correções.** O `is_dirty()` ficou no `DocumentSession`, não no
> `HistoryManager`: quem sabe o que está gravado em disco é o documento, e o histórico
> não tem como saber onde ficou o último salvamento. E o snapshot guarda **tuplas**, não
> `BoxEntry` — `copy.deepcopy` de uma lista de dataclasses custava 15,8 ms numa página
> de 2.000 boxes, isto é, por tecla no modo digitação da §7.3. Ver ROADMAP F3.8, que
> inclui o motivo de o "snapshot incremental" previsto na F3.4 **não** ter sido feito.

### 6.2 Concorrência

**Implementado na F4.1** — `core/services/task_service.py`.

Nenhum trabalho pesado na thread da UI. Nenhuma chamada a `self.parent.update()`
dentro de laço de processamento — além de congelar, o `update()` reentrante pode
reentrar num handler no meio da mutação da lista de boxes.

```python
class BackgroundTask:
    def start(self, fn, on_progress, on_done, on_error): ...
    def cancel(self): ...          # cooperativo, via threading.Event
```

- worker em `threading.Thread`; comunicação por `queue.Queue`
- UI consome a fila com `widget.after(50, ...)`
- toda operação longa é **cancelável**: OCR de página, treino, lote, conversão de PDF
- barra de progresso real na status bar (`ui/status_bar.py`, recriado como `Frame`)

Regra que não pode ser quebrada: **a função de trabalho nunca toca em widget.** Ela
calcula e devolve dados; quem mexe na tela é `on_done`, na thread da UI.

Corolário prático: dados compartilhados com a UI são copiados antes de ir para a thread.
Os recortes dos boxes viram `numpy` em `_recortes_dos_boxes()`, e `save_all_pages` copia
`self.image` — senão o worker e o `redraw` do canvas leriam a mesma `PIL.Image`.

`is_running()` fica verdadeiro até o resultado ter sido **entregue**, não só até a thread
morrer. Consultar `thread.is_alive()` é cedo demais: a thread termina ao enfileirar o
resultado, e `on_done` só roda no ciclo seguinte de `after` — nessa janela dava para
disparar outra tarefa por cima de um estado ainda não aplicado.

`shutdown()` solta o `after` pendente antes de destruir a janela; sem isso o callback
agendado dispara contra uma aplicação que já não existe.

Trabalho de CPU pesada (OpenCV, PyTorch) libera o GIL, então threads bastam —
`multiprocessing` só se o perfil apontar necessidade.

### 6.3 Configuração

`config/settings.py` já existe e não é usado por ninguém. Ligar de fato:

| Chave | Padrão |
|-------|--------|
| `ocr.neural_threshold` | 0.80 |
| `ocr.learner_threshold` | 0.90 |
| `ocr.easyocr_gpu` | false |
| `preprocess.binarize_method` | "auto" |
| `preprocess.target_dpi` | 300 |
| `pdf.render_dpi` | 300 |
| `pdf.output_mode` | "searchable" |
| `ui.autosave_interval` | 25 (alterações) |
| `ui.zoom_on_select` | false |
| `ui.confidence_colors` | true |
| `lexico.ativo` (§5.8) | true |
| `lexico.idioma` (§5.8) | "en" — o idioma dos livros, não o do programa |
| `lexico.nomes` (§5.8) | true — os 237 mil nomes próprios junto do idioma |
| `paths.last_dir`, `paths.tesseract`, `paths.dicionario_usuario` | — |

Eliminar todo literal de limiar espalhado pelo código.

### 6.4 Ciclo de vida do documento

**Implementado na F3.7** (`core/services/document_service.py`), exceto o autosave,
que continua pendente na F3.4. Corrigia perda silenciosa de trabalho: `_load_pdf_page`
fazia `self.boxes = []` sem aviso — trocar de página apagava tudo que foi digitado.

```python
class DocumentSession:
    """Um PDF/imagem aberto. Mantém os boxes de TODAS as páginas visitadas."""
    pages: dict[int, list[BoxEntry]]
    dirty_pages: set[int]

    def switch_page(self, index: int): ...   # preserva os boxes da página que sai
    def save_all(self, path: str): ...
    def autosave(self): ...                  # sidecar .pyboxsession.json
```

Regras:

- [feito] trocar de página **preserva** os boxes da página anterior
- [feito] confirmar antes de sair/abrir outro arquivo com trabalho não salvo
- [feito] título da janela marca estado sujo com `*`
- [feito] **salvar todas as páginas** — um par `.box`/`.png` por página com boxes,
  em `<base>_pgNNN`. Sem isso a persistência seria uma armadilha: trabalho acumulado
  em várias páginas sem forma de gravá-lo
- [feito] autosave a cada N alterações (25), em sidecar ao lado do arquivo
- [feito] ao abrir, detectar sidecar e oferecer recuperação

**O sidecar não passa pelo `BackgroundTask`.** Autosave não é operação do usuário: não
tem progresso, não é cancelável e não pode disputar a vaga única de tarefa em primeiro
plano com o OCR ou o carregamento de página. Usa uma thread própria, fila de tamanho 1
(o pedido novo descarta o antigo) e escrita atômica (temporário + `os.replace`) — travar
durante o autosave não pode corromper justamente o arquivo de recuperação.

O snapshot é montado na thread da UI, porque precisa de uma visão consistente; só o
encode e a escrita saem dela. Cada box vira **tupla**, não dict: medido em 40 mil boxes,
`asdict` custava 98 ms contra 23 ms das tuplas, e o arquivo cai de 3,9 MB para 1,7 MB.
Resultado final: 22,9 ms de bloqueio, contra 292 ms da versão ingênua.

O sidecar guarda `confidence` e `source`, resolvendo para o caminho de recuperação a
limitação registrada em §2.3 (o `.box` do Tesseract não tem onde guardá-los).

Detalhe de implementação que vale registrar: `store()` guarda a lista recebida **sem
copiar**, e `boxes_for()` devolve a própria lista. Copiar a cada tecla numa página de
2.000 boxes seria caro. O contrato é que todo ponto que *reatribui* `self.boxes` chame
`store()` em seguida — é o que `_commit_change()` e `_sync_session()` garantem
(este último cobre undo/redo, que reatribuem a lista).

Armadilha encontrada ao implementar: `prev_page`/`next_page` alteravam
`self.current_pdf_page` **antes** de chamar `_load_pdf_page`. Como a nova versão usa
esse campo para saber qual página arquivar, o trabalho seria gravado sob o índice
errado. A navegação passa o índice de destino como argumento e quem atualiza o campo
é `_load_pdf_page`.

---

## 7. Interface

### 7.1 Layout

```
┌─ Menu ────────────────────────────────────────────────────┐
├─ Barra de ferramentas ────────────────────────────────────┤
│  [Abrir] [Salvar] │ [Detectar] [OCR] │ [Undo] [Redo]      │
├──────────────────────────────────────┬────────────────────┤
│                                      │ Filtro: [        ] │
│                                      │ ☐ só vazios        │
│              Canvas                  │ ☐ conf < 90%       │
│                                      ├────────────────────┤
│                                      │  0001 'e'  98% ██  │
│                                      │  0002 '?'  --  ░░  │
│                                      │  0003 'c'  71% ▓▓  │
├──────────────────────────────────────┴────────────────────┤
│ Caractere: [_] [Aplicar] [Próximo>>]                      │
│ NAGs: Avaliação ⩲ ⩱ ± ∓ +- -+ = ∞ │ Lance ! !! ? ?? !? …  │
│       Ideia ≡ ⇄ ⌓ Δ ⨀ │ Lado △ ▼                          │
├───────────────────────────────────────────────────────────┤
│ ◀ Pág 12/248 ▶ │ 1.847 boxes │ 23 vazios │ ▓▓▓░ 68%      │
└───────────────────────────────────────────────────────────┘
```

**Os NAGs são a tabela do "Key to symbols used" destes livros**, em quatro famílias
— avaliação, lance, ideia e lado a jogar — e em **duas linhas**: os 23 em fila única
pedem 1.076 px contra os 1.024 da janela mínima, e `pack(side="left")` corta o
excesso à direita sem avisar. Mesmo defeito que `appy._geometria_que_cabe` existe
para não repetir.

Símbolo novo na tabela **tem de ser conferido contra a fonte** (`missing_glyphs`, da
§9.2): `Segoe UI Symbol` desenha os 23, mas `MS Gothic` — a candidata seguinte da
cadeia — não tem `⩲`, `⩱`, `⌓` nem `⨀`. Glifo ausente vira caixa vazia sem erro
nenhum, que é o defeito do `·` da §4.2. `tests/test_nags.py` trava isso.

Uma aproximação registrada: `≡` (com compensação) não é o símbolo do Informator, que
não tem ponto de código próprio em Unicode — três barras é como estes livros o
imprimem.

#### O menu Notação — a tabela completa do padrão PGN

A barra rápida tem os 23 que se digitam o dia inteiro. O menu **Notação** tem os 169
do padrão PGN (`core/nags.py`), que é outra coisa: o símbolo que aparece uma vez em
duzentas páginas, e a resposta para "o que é `$26`". São as duas listas da Wikipedia
— a padrão (`$0`–`$139`) e a que o ChessPad acrescentou (`$140`–`$148`, `$220`–`$221`,
`$238`–`$255`). As faixas que a especificação reserva sem definir não entram.

**Em 22 submenus por família, não em coluna única.** Cento e sessenta e nove itens a
~20 px pedem 3.400 px de altura; o Tk não avisa que não cabe — quebra o menu em
colunas lado a lado e a lista perde a ordem. Montar tudo custa 4 ms.

**Clicável só quem tem o que escrever no box**, e o rótulo diz por quê:

| rótulo | o que é | quantos |
|---|---|---|
| `$14 ⩲ Brancas ligeiramente melhor` | tem símbolo e tem fonte | 43 |
| `$24 — Brancas com leve vantagem de espaço` | o padrão definiu sem forma impressa | 121 |
| `$249 ⯺ Peões ligados (sem fonte)` | símbolo existe, nenhuma fonte o desenha | 5 |

A terceira linha é a que importa: `U+2BF9`–`U+2BFE`, o bloco que o Unicode 11
reservou para xadrez, não é coberto por nenhuma candidata de `CHESS_FONT_CANDIDATES`
numa instalação Windows típica — nem pelo próprio Tk, que os mostra como retângulo
vazio no menu. Deixá-los clicáveis escreveria no box um caractere invisível no PDF
final, sem erro no caminho. `nags.sem_glifo()` **mede** em vez de decorar (17 ms, uma
vez por processo), então a restrição some sozinha se uma fonte que os cubra chegar a
`assets/fonts/`.

**Onde as duas tabelas se encontram, o ponto de código é o da barra rápida.** `Δ`
(U+0394) e `∆` (U+2206) têm o mesmo desenho e códigos diferentes, e o mesmo vale para
`⇄` (U+21C4) contra `⇆` (U+21C6) do `$132`, para `!!` contra `‼` (U+203C) do `$3` e
para o hífen de `+-` contra o U+2212 do `$18`. Deixar os dois entrarem em `.box`
diferentes daria **duas classes ensinando o mesmo glifo** ao modelo. `$44` vai além:
troca o `⯹` do padrão pelo `≡` da barra, que é o mesmo conceito e tem fonte.
`tests/test_nags.py` trava cada um desses pares.

### 7.2 Confiança visível

**Implementada na F3.2** — `ui/confidence.py` centraliza limiares, cores e o teste
`precisa_revisao()`, usado pelo canvas, pela lista lateral e pelo contador.

| Confiança | Cor do box | Significado |
|-----------|-----------|-------------|
| ≥ 0.90 | verde | provavelmente certo |
| 0.70–0.89 | amarelo | conferir |
| < 0.70 | vermelho | conferir obrigatoriamente |
| vazio | cinza tracejado | não reconhecido |
| sem informação | azul | não avaliado (ex.: carregado de `.box`) |

Mesma escala na lista lateral. É isso que transforma "reler 2.000 caracteres" em
"conferir 80".

### 7.3 Modo digitação contínua

**Implementado na F3.1.** Ativável por `F2`. Com ele ligado, a tecla digitada aplica o
caractere e avança sozinha — sem Enter. Numa página de 2.000 caracteres, elimina 2.000
teclas.

`Espaço` pula sem alterar, `Backspace` volta um box, `Esc` sai do modo.

O Espaço não constava do rascunho e mudou o fluxo de revisão: como a maioria dos
caracteres já está certa, passar por eles sem digitar nada é o caso comum.

Dois requisitos de implementação que não são opcionais:

- **O foco tem de sair do campo de texto** (vai para o canvas). Em Tk os bindings
  disparam na ordem widget → classe → toplevel; com o `Entry` focado, ele insere o
  caractere antes de o binding da janela ver o evento, e devolver `"break"` no nível do
  toplevel não desfaz a inserção.
- **Nenhuma tecla nua pode disparar comando.** `d` dividia box na janela inteira; com o
  modo ligado, digitar 'd' partiria um box. Passou para `Ctrl+D`.

Teclas de controle (setas, `F3`, `Ctrl+algo`) têm `event.char` vazio ou não imprimível,
então o filtro `isprintable()` as deixa passar para os seus próprios atalhos sem
tratamento especial.

### 7.4 Filtros de navegação

**Implementados na F3.3.**

- [feito] caixa de busca por caractere (`Ctrl+F` foca nela)
- [feito] alternadores: só pendentes / só vazios / **só fora do dicionário** / por origem
- [feito] `F3` / `Shift+F3` — próximo/anterior pendente dentro do filtro ativo,
  circular
- [feito] contador "mostrando N de M", mais "N fora do dicionário"

**O filtro do léxico (F9) troca o critério do `F3`, e não é detalhe de conforto.**
Com ele ligado, `F3` anda por *todos* os visíveis em vez de só pelos que
`precisa_revisao` aponta. Uma palavra fora do dicionário costuma vir com confiança
alta — 1,000 é a mediana de um erro, pela F1.9 —, então o critério de sempre
responderia "nada pendente" com a tela cheia de marcas. São dois eixos, e quando o
usuário escolhe o do dicionário é esse que tem de mandar.

**Contrato que não pode ser quebrado:** com filtro ativo a lista deixa de mapear 1:1
com `self.boxes`. Toda conversão passa por `_visiveis` (índices dos boxes exibidos) e
`linha_do_box()`. Confundir linha de lista com índice de box faz o usuário editar o
caractere errado sem perceber — é o modo de falha mais perigoso desta parte da UI.

A busca trata o texto digitado como **conjunto** de caracteres, não como substring:
num editor onde cada box tem um caractere só, "aeiou" achar qualquer vogal é mais útil
que casar substrings. Diferencia maiúscula de minúscula porque o OCR diferencia
(`upper_A` e `lower_a` são classes distintas).

### 7.5 Aplicar a todos os semelhantes — [feito, F3.6]

Com um box selecionado e corrigido: **"Aplicar a todos os semelhantes"** (`Ctrl+E`)
encontra boxes com imagem parecida (distância L2 abaixo de um limiar ajustável), mostra
uma prévia em grade com seleção individual, e aplica em lote.

Corrigir um `e` mal reconhecido pode corrigir 300 de uma vez. É o maior ganho isolado
de produtividade do roadmap.

> **O que a medição acrescentou ao contrato.** O critério não é só a imagem: é imagem
> **mais** o caractere que os candidatos ainda mostram, e essa segunda metade é o que
> segura a precisão em 99,3% quando se afrouxa o limiar. E a prévia deixou de ser
> conveniência para ser obrigatória: ~1 em 145 boxes do lote sai errado, por homóglifo
> (`0`×`o`, `1`×`i`), e nenhum limiar resolve. A grade sai **ordenada por distância**,
> com o duvidoso no fim. Números no ROADMAP F3.6.

### 7.6 Atalhos — [feito, F3.5]

| Tecla | Ação |
|-------|------|
| `Ctrl+O` / `Ctrl+S` / `Ctrl+Shift+S` | Abrir / Salvar página / Salvar todas |
| `Ctrl+Z` / `Ctrl+Y` | Undo / Redo |
| `↑` `↓` | Box anterior / próximo |
| `Tab` / `Shift+Tab` | Box próximo / anterior, com o foco pronto para digitar |
| `PgUp` `PgDn` | Página anterior / próxima |
| `Ctrl+G` | Ir para uma página do PDF (F3.9) |
| `Del` | Excluir box |
| `Ctrl+D` | Dividir box |
| `Ctrl+B` | Gravar rascunho agora |
| `Ctrl+F` | Focar a busca |
| `F2` | Modo digitação contínua |
| `F3` / `Shift+F3` | Próximo / anterior no filtro |
| `Ctrl+E` | Aplicar a semelhantes |
| `F4` | Zoom no box selecionado |
| `Esc` | Sair do modo digitação / cancelar |

`d` sozinho deixa de dividir box — passa a `Ctrl+D`. O guard atual
(`_on_key_split_safe`) só testa `tk.Entry` e não cobre `ttk.Entry`, `Text` ou
`Spinbox`, então digitar "d" no widget errado divide um box.

**O campo do caractere é a exceção do guard — [feito, F4.7].** Calar o atalho em todo
campo de texto está certo para a busca e o número da página, que não têm box por trás;
o campo do caractere é o oposto — ele *é* o box selecionado, e é onde a mão do revisor
está quando ele descobre que a caixa tem duas letras. A binding é do **widget**, não da
janela, e devolve `"break"`: a tecla passa pelo widget, pela classe e só então pelo
toplevel, e a binding de classe do `Entry` trata `Control-d` apagando o caractere à
direita do cursor. Tratado só na janela, o atalho dividiria o box **e** comeria o que
estava escrito.

> **Duas teclas mudaram em relação ao que está escrito acima**, e pelo mesmo motivo: com
> o modo digitação da §7.3, **tecla nua não pode ser comando** — ela precisa poder virar
> o caractere do box. Por isso o zoom é `F4` e não `Z` (F4.6). E `Ctrl+Shift+A` virou
> `Ctrl+E`: acorde de três teclas não serve para a operação mais repetida do fluxo.
>
> `Tab`/`Shift+Tab` não estavam previstos. O custo deles é real e vale saber: eles
> devolvem `"break"` e com isso **desligam a travessia de foco do Tk** na janela
> principal. Os diálogos não são afetados — binding de tecla sobe pelo *toplevel* do
> widget em foco.

### 7.7 Comportamento do zoom

`select_box` **não** deve mais chamar `zoom_to_box`. Hoje toda seleção re-enquadra a
imagem com zoom mínimo forçado de 1.5×, e navegar com as setas faz a página saltar a
cada tecla.

Novo comportamento: rolar o mínimo necessário para o box ficar visível, mantendo o
nível de zoom. Zoom explícito só com `Z` ou duplo-clique. Configurável por
`ui.zoom_on_select`.

### 7.8 Desempenho da lista

`update_sidebar` refaz a listbox inteira a cada seleção (`delete(0,"end")` + N inserts).
Com 2.000 boxes, cada seta reconstrói 2.000 linhas e a digitação engasga.

Migrar para `ttk.Treeview` e atualizar **só as linhas alteradas**.

> **Andar de box custa duas linhas, e não zero — [F4.7].** A seta de seleção da §7.11
> mora no texto da linha, então trocar a seleção reescreve a que perdeu a seta e a que
> ganhou: seis operações de lista por tecla, contra as 2.000 que esta seção existe para
> não deixar voltar. O teste da F4.4 que afirmava "zero" passou a afirmar esse teto.

### 7.9 Tabuleiro editável — [feito, F8.2, em `core/tabuleiro_edicao.py`]

A janela de diagrama da F7.1 era só de leitura, e a leitura acerta 94,5% das
casas: conferir sem poder corrigir devolve o trabalho para fora do programa.

O contrato:

1. **O estado mora fora do widget.** As 64 casas, o desfazer, o FEN e a legalidade
   ficam em `core/tabuleiro_edicao.py`; o diálogo desenha e despacha cliques. Mesma
   separação da F7.1 entre `core/diagrama.py` e a janela, e pelo mesmo motivo: o que
   tem regra precisa de teste, e teste de widget não é teste de regra.
2. **A edição não toca a `Leitura`.** Fechar sem confirmar não pode ter mudado nada —
   a leitura é o que o programa leu, a edição é o que o usuário quis.
3. **Clicar seleciona, não escreve.** Quem escreve é a tecla (maiúscula = branca) ou
   a paleta escolhida. Botão direito esvazia, arrastar move, `Ctrl+Z` desfaz.
4. **A casa corrigida vira autoridade** (confiança 1,0, cor própria) e deixa de contar
   como arbitrada pela legalidade — aquela marca deixou de ser verdade.
5. **A legalidade é a do `python-chess` inteira** (`Board.status()`), e não só a
   contagem da F7.1: com o lado a jogar informado, o xeque do lado errado passa a ser
   decidível. Só se oferece o roque que a posição comporta.
6. **O desfazer guarda o estado inteiro** (64 casas, lado e roque), pelo que a F3.8
   mediu: estado incremental teria estado próprio para errar.

### 7.10 Base e treino dos diagramas — [feito, F8.3, em `core/treino_diagrama.py`]

O ciclo que faltava: corrijo, guardo, treino, melhora.

1. **A amostra é o resíduo** (`casa - fundo`), no formato que a F7.1 já usava —
   deslocado de 128 para poder ser olhado como imagem. O recorte cru traria o papel
   do livro junto.
2. **Silêncio não é confirmação.** Só a casa corrigida vira amostra; as demais entram
   por um "conferi o diagrama inteiro" explícito. Casa esvaziada não vira amostra:
   não há classe de casa vazia.
3. **O nome carrega a procedência e é determinístico.** Regravar substitui, e gravar
   numa classe apaga a mesma procedência das outras — senão a mesma imagem ficaria
   rotulada duas vezes (F1.4).
4. **O progresso é medido em diagramas que ficaram fora do treino** (F7.4). Era
   leave-one-out, e a §7.12 mostra o quanto aquilo inflava: 20% dos **diagramas** vão
   para o teste, duas redes são treinadas por rodada — a que mede não viu o teste, a
   que fica viu tudo —, e o relatório continua declarando o que o número não cobre.
5. **O relatório diz o que uma correção faz, e isso mudou junto com o classificador.**
   Com o k-NN era aritmética: uma correção não virava a casa, duas viravam. Com a rede
   uma amostra entre centenas é diluída, e o que move o ponteiro é conferir diagramas
   inteiros. O aviso vem junto do número porque é aí que a expectativa se forma.
6. **O `.pth` guarda a impressão da base** que o gerou (F7.3 aplicada aqui), e treinar
   faz o leitor esquecer o modelo em memória — senão o treino não valeria até
   reiniciar o programa.

### 7.12 A rede que lê as peças — [feito, F7.4, em `core/neural_model.RedeDiagrama`]

Era HOG + PCA para 32 dimensões + voto dos 3 vizinhos mais próximos. O argumento
contra a rede estava escrito no `treinar_diagrama.py` — "são poucas centenas de
amostras de dois livros, e uma rede treinada nisso decoraria" — e a medição o
desmentiu.

**Três protocolos, e a distância entre eles é a lição:**

| protocolo | k-NN | rede |
|---|---:|---:|
| leave-one-out solto (o que o relatório mostrava) | 93,5% | — |
| 5 folds agrupados por diagrama | 93,8% | 98,8% |
| **um livro inteiro deixado de fora** | **86,9%** | **98,0%** |

A vantagem da rede **cresce** no teste difícil (+5,0 → +11,1 pontos), que é o
contrário do que a decoreba produziria. E não era o PCA: com 256 componentes, ou sem
PCA nenhuma sobre o HOG cru e um vizinho só, o melhor que o k-NN faz num livro novo é
89,2%. O que ele errava eram as peças de desenho detalhado — dama 80,8%, cavalo
83,7% —, exatamente o que uma silhueta de gradientes borra.

**A rede foi dimensionada pelo arquivo, e isso é decisão de produto.** O `.gitignore`
manda `*.pth` para fora porque o modelo de caracteres tem 2,6 MB; o banco de vizinhos
que a rede substitui tinha 231 KB e vinha no repositório, então um clone novo lia
diagramas sem baixar nada. Medido, a `SimpleCNN` de 126 classes (2.423 KB) faz 97,8%
e uma rede de 35.820 parâmetros (140 KB) faz 98,0% — a camada densa grande daquela
não paga aqui. A exceção nominal no `.gitignore` é o que mantém a propriedade.

**Trocar o achatamento por média global custa 16,6 pontos** (98,0% → 81,4%), e é a
variante que ensina o porquê: onde a tinta está dentro da casa é informação.

**Três consequências que não estavam no pedido e vieram junto:**

1. **A temperatura da F1.9 passou a valer aqui.** A rede acerta 98% e diz 99,9% de
   confiança em quase tudo, e é dessa confiança que a janela tira o laranja de
   "duvidoso". A temperatura é ajustada nos diagramas de teste (1,41 na base atual) e
   viaja no `.pth`. Não muda leitura nenhuma — divide todos os logitos —, muda o
   número exibido.
2. **O árbitro da legalidade passou a custar em logaritmo.** "Quanto custa trocar esta
   casa" é razão entre evidências, não diferença: com a rede confiante,
   `0,9999 − 0,0000001` empata com `0,999 − 0,001` em ponto flutuante e o "mais
   barato" viraria o primeiro índice da lista.
3. **O treino passou de 2 s para ~40 s**, e o comando da janela ganhou progresso.
   Quarenta segundos sem sinal de vida parecem travamento.

**O que a troca não conserta, e o número que prova.** Nas 11 páginas rotuladas, 25
diagramas: 15 saem com posição possível **antes** do árbitro (o k-NN fazia 17, e a
diferença é ruído em 25) e 25 depois (o k-NN fazia 23). A legalidade mede sobretudo a
decisão vazia/ocupada — um rei que o Otsu não viu quebra a posição por mais certo que
o classificador esteja —, e essa decisão é a mesma de antes. O ganho da rede está em
qual peça é, não em se há peça.

Um caso conferido à mão fecha o argumento e reforça a §7.9: o primeiro diagrama da
página 0013 do Kasparov sai com FEN legal, sem nenhuma casa arbitrada, e tem duas casas
erradas — um peão branco em f5 que a leitura não viu (casa clara, peça vazada) e um peão
que ela inventou em h2. As provas passaram porque a omissão e o falso positivo se
compensam na contagem. **Passar nas provas não é prova de estar certo**, e o próximo
ganho está no Otsu de ocupação, não no classificador. *(Foi o que a §7.13 fez: as duas
casas saem certas agora.)*

### 7.13 A ocupação deixa de ser um limiar — [feito, F7.5]

Quem decide se a casa tem peça era o Otsu de `_residuos`, intacto desde a F7.1, e
**nenhum número media essa decisão** — os 94,5% por casa da §7.9 misturavam ocupação e
identidade, e a §7.12 melhorou só a segunda.

**A fase começa por um gabarito, e ele é o entregável duradouro.** As 1.600 casas dos 25
diagramas rotulados, transcritas à mão em `tests/dados/ocupacao_diagramas.txt`, 25 linhas
de 64 caracteres. A transcrição foi cruzada com a base da F7.1 — que, descobriu-se, cobre
estes mesmos 25 diagramas — e as duas se corrigiram: três erros de digitação meus e um
falso positivo do Otsu que estava rotulado como peão numa casa vazia.

| decisão | omissões | falsos+ | acerto |
|---|---:|---:|---:|
| Otsu (F7.1) | 86 | 38 | 92,25% |
| **melhor limiar possível, com o gabarito na mão** | — | — | **98,25%** |
| rede dedicada | 6 | 5 | **99,31%** |

**A linha do meio é o achado metodológico.** O oráculo já ficava 6 pontos acima do Otsu:
a *medida* não era o problema, achar o corte **sem rótulo** era. Nenhuma regra sem
supervisão passa de 93,6% (Otsu no log, mediana + MAD, maior salto relativo, limiar fixo
sobre medida adimensional), e nenhuma das nove medidas alternativas testadas fecha a
distância.

**Duas redes e duas bases, e as duas separações foram medidas.** Uma classe "vazia" a
mais na rede das peças dá 97,81% contra 99,31% da rede dedicada. E treinar a rede de
ocupação com as amostras de peça que já existiam dá **91,88%** — quase o Otsu de volta —
porque aquelas peças são justamente as que o Otsu já achava. A rede só aprende a achar o
que o leitor perde se vir as casas que ele perdeu, e é por isso que a base de ocupação
guarda **tabuleiro inteiro conferido**, não recorte de peça.

Consequência no ciclo da §7.10: `colher` passa a gravar as 64 casas na base de ocupação.
O contrato "casa esvaziada não vira amostra" caiu — era o buraco mais caro que o ciclo
tinha, porque nenhuma das 124 correções de ocupação chegava a modelo nenhum.

Ponta a ponta, nos 25 diagramas: **posição possível sem o árbitro vai de 15/25 para
23/25**, e é essa linha que diz que a leitura melhorou, não que o árbitro remendou mais.

### 7.11 O corte do Ctrl+D e a seta da lista — [feito, F4.7]

**O corte olha a tinta, não a proporção do box.** A regra antiga era "mais largo que
alto corta em X, senão em Y, sempre no meio", e num box com `ba`, `it`, `is` ou `ll` —
letra alta ao lado de letra baixa — a caixa sai mais **alta** que larga: as duas metades
vinham uma embaixo da outra. Agora `BoxService.split_box` mede o perfil de tinta nos dois
eixos, procura o vale mais nítido de cada um e corta no do eixo vencedor; sem imagem, ou
sem vale em eixo nenhum, vale a regra antiga.

**A fundura do vale é medida contra o menor dos dois picos que o ladeiam**, e é isso que
distingue um vale de uma descida — o perfil por linha de `ba` cai na faixa do ascendente
do `b`, e comparado com o pico geral aquilo pontuaria como vale fundo.

Medido nas 9 páginas rotuladas, unindo cada par de caracteres vizinhos da verdade
rotulada num box só — que é exatamente o box que o usuário manda dividir. "Corte bom" é
cair a menos de 10% do lado do box da fronteira verdadeira:

| regra | lado a lado (n=5.747) | | empilhados (n=57) | |
|---|---|---|---|---|
| | eixo errado | corte bom | eixo errado | corte bom |
| geometria | 9,3% | 61,6% | 0,0% | 94,7% |
| vale de tinta | 0,3% | 98,6% | 0,0% | 94,7% |

A coluna dos empilhados é a que prova que não houve troca de um erro por outro: o eixo Y
continua sendo escolhido onde ele é o certo.

**A lista lateral ganha uma seta na linha selecionada**, `►` (U+25BA) numa coluna fixa à
esquerda da marca do léxico. Não é enfeite do realce do Listbox: é o que sobra dele. O
`tk.Listbox` nasce com `exportselection` ligado, então o realce some assim que outro
widget toma a seleção do sistema — e é o que acontece a cada `char_entry.select_range`,
isto é, a cada Tab e a cada Enter do fluxo de revisão.

`▶` (U+25B6) é o desenho óbvio e **não existe na Consolas**: o Tk cairia numa fonte de
reserva não monoespaçada e a coluna sairia do prumo. Medido, não suposto — é a mesma
disciplina do `·` da §4.2 e dos NAGs sem fonte da §7.1.

O preço está na §7.8: andar de box passa a reescrever duas linhas em vez de zero, porque
a seta mora no texto da linha. Duas, não duas mil.

---

## 8. Testes — [feito]

Não existe nenhum teste hoje. `test_chess_pdf.py` é um stub cuja única função está
comentada — imprime "a sintaxe está correta" e não verifica nada.

> **Hoje são 533**, um arquivo por item do roadmap, em `tests/`. O `test_chess_pdf.py`
> e os outros scripts manuais da raiz saíram na F5.4 — um deles, `test_draw.py`, chegava
> a quebrar a coleta do `pytest` chamado da raiz. Há um `pytest.ini` com
> `testpaths = tests` para isso não voltar.
>
> Duas convenções que valem para quem for escrever mais: os testes de UI usam Tk de
> verdade, com uma **raiz compartilhada** por `tests/conftest.py` (uma raiz por teste
> fazia o Tcl reler os temas do ttk milhares de vezes e a suíte falhava
> intermitentemente); e o que não dá para observar numa janela retirada da tela — o foco,
> tipicamente — é verificado espiando a chamada, não consultando o Tk.

### 8.1 Mínimo para desbloquear (fazer junto com F0)

```python
def test_box_entry_nao_e_dict():
    """Trava os 4 bugs de F0.1 de uma vez."""
    b = BoxEntry("a", 1, 2, 3, 4)
    assert b.x1 == 1 and b.copy().x1 == 1
    with pytest.raises(TypeError):
        b["x1"]

def test_update_sidebar_com_boxes():
    """Reproduz o TypeError que impede o uso do programa."""

def test_fonte_de_xadrez_cobre_12_pecas():
    """Reproduz o bug do '·'. Falha com helv, passa com fonte Unicode."""
    font = resolve_chess_font()
    assert_glyph_coverage(font, "♔♕♖♗♘♙♚♛♜♝♞♟")

def test_undo_redo_ida_e_volta():
    """add → undo → redo devolve o estado. Hoje falha."""

def test_box_roundtrip():
    """salvar → carregar preserva coordenadas e ligaduras."""
```

### 8.2 Cobertura seguinte

- `merge_vertical_boxes`: `i`, `j`, `:`, `;`, `?`, `!` fundem corretamente
- [feito] `sort_boxes_reading_order`: coluna única, duas colunas, com diagrama no
  meio. `detectar_colunas()` projeta a ocupação dos **boxes** no eixo X e acha as
  calhas em qualquer posição e em qualquer número — a abordagem do DocuVision, que
  mede a brancura de uma faixa fixa entre 42% e 58% da largura, só acha duas
  colunas simétricas. Elementos que atravessam a calha viram separadores
  horizontais. Medido numa página real: 9 → 1 saltos entre colunas
- `binarize`: página limpa, escaneada, com iluminação irregular
- `folder_to_char` ∘ `char_to_folder` = identidade para todas as 105 classes
  (**hoje falha em `sym_f7` e em `ligature_hex_*`**)
- PDF pesquisável: texto extraível do resultado bate com os boxes de entrada

### 8.3 Regressão de OCR

Um conjunto fixo de 10 páginas com verdade-fundamental em `.box`, e um alvo de
acurácia que não pode regredir entre commits.

---

## 9. Empacotamento

### 9.1 `requirements.txt` — [feito, F0.4]

Reescrever — o arquivo atual está em UTF-16 na última linha (o pip lê
`PyMuPDF>=1.23.0` como `P y M u P D F`), omite `torch` e `easyocr` que o código usa,
e lista `pydantic` e `python-Levenshtein` que não estão instalados nem são usados.

```
Pillow>=10.0
numpy>=1.26
opencv-python>=4.8
PyMuPDF>=1.23
torch>=2.0
easyocr>=1.7
pytesseract>=0.3.10     # opcional — só o caminho Tesseract
```

Gravar em **UTF-8 sem BOM**. Fixar versões em `requirements.lock.txt`.

Removidos: `pdf2image` (§4.1), `imutils`, `pydantic`, `python-Levenshtein`, `rich`,
`PyYAML`, `platformdirs` — nenhum é importado pelo código de produção.

> **O que faltava:** a spec não previu dependência de desenvolvimento, e o `pytest`
> ficou fora de qualquer arquivo — quem clonasse o repositório não tinha como saber o
> que instalar para rodar a suíte. Entrou `requirements-dev.txt`, que puxa o de produção
> e acrescenta o `pytest`. O `requirements.lock.txt` continua não existindo.

### 9.2 Estrutura — [feito]

Como ficou:

```
PyBoxEditor_Tkinter/
├── appy.py                    ← ponto de entrada (o nome é histórico)
├── calibrar_modelo.py         ← ferramentas de medição; produzem os
├── medir_paginas.py             números do ROADMAP
├── medir_negativo.py
├── pytest.ini  requirements.txt  requirements-dev.txt
├── config/{settings.py, profiles/}
├── core/
│   ├── box_model.py  formato_box.py  preprocess.py  semelhanca.py
│   ├── vertical.py  negativo.py  lexico.py  nags.py
│   ├── notacao.py  calibracao.py  perfis.py
│   ├── avaliacao.py  avaliacao_pagina.py  dataset_check.py
│   ├── neural_model.py  neural_trainer.py  learner.py
│   ├── chess_pdf_processor.py  searchable_pdf.py  relatorio_pdf.py
│   └── services/{box,ocr,pdf,learning,history,document,task}_service.py
├── ui/
│   ├── main_window.py  canvas_view.py  status_bar.py
│   └── confidence.py  dialogo_semelhantes.py
├── tests/                     ← conftest.py + um arquivo por item do roadmap
├── Box/                       ← páginas rotuladas à mão (verdade de campo)
└── docs/SPEC.md
```

Diferenças em relação ao previsto: `box_io.py` virou `formato_box.py` (§2.3) e
`toolbar.py` não foi criado — a barra de status da F4.2 cobriu a necessidade.

`assets/fonts/DejaVuSans.ttf` **continua sendo o primeiro caminho** que
`resolve_chess_font` procura (`chess_pdf_processor.py:32`), e é o que um empacotamento
deveria incluir; ele só não está no repositório, e por isso hoje a busca cai numa fonte
do sistema. Não é o mesmo que a spec ter sido abandonada nesse ponto — é ela ainda não
ter sido cumprida.

Fora do repositório, por tamanho ou direito autoral (ver `.gitignore`):
`training_data/`, `ilovepdf_pages-to-jpg/`, `*.pth`, relatórios de treino.

**Removidos na F5.1** (7 módulos, 211 linhas): `ui/sidebar.py`, `ui/menu_bar.py`,
`ui/status_bar.py`, `core/opencv_autobox.py`, `core/box_io.py`, `core/image_loader.py`,
`core/tesseract_utils.py`.

> **Correção desta spec.** A v2.0 recomendava *ligar* `sidebar.py`, `menu_bar.py` e
> `status_bar.py` em vez de apagá-los. Ao executar a F5.1 ficou claro que nenhum dos
> três é aproveitável como está:
>
> - `sidebar.py` chama `controller.apply_char(c)` com um argumento; `MainWindow.apply_char`
>   não aceita nenhum — quebraria ao ser ligado.
> - `menu_bar.py` chama `controller.load_box_dialog` e `controller.generate_autobox`,
>   **métodos que não existem**. Também quebraria.
> - `status_bar.py` é um `tk.Label`, e a F4.2 precisa de uma barra que comporte um
>   `ttk.Progressbar` — ou seja, um `Frame`, não um `Label`.
>
> `tesseract_utils.py` tinha `menu_bar.py` como único consumidor, então caiu junto.
> A configuração do caminho do Tesseract continua prevista em §6.3 (`paths.tesseract`)
> e será reescrita lá, ligada de verdade.

Recuperar do histórico quando for preciso:

```bash
git show 6a4b7a1:core/opencv_autobox.py   # binarização Otsu, insumo da §3
git show 6a4b7a1:core/box_io.py           # leitor/escritor .box antigo (5 campos)
```

Ainda pendente (F5.4, fora da F5.1): `debug_*.py`, `crash_log.txt`, `full_log.txt`,
`test_{image,emj,sym}.png`, `Novo Documento de Texto.txt`, `test_chess_pdf.py`.

### 9.3 Controle de versão

O projeto **não é um repositório git**. Antes de qualquer refatoração desta spec:

```bash
git init && git add -A && git commit -m "baseline antes da refatoração"
```

`.gitignore`: `.venv/`, `__pycache__/`, `*.pth`, `training_data*/`, `crash_log.txt`,
`*.pyboxsession.json`, `.idea/`.

`custom_model.pth` (2,5 MB) e as 127 mil imagens de treino não pertencem ao git —
distribuir por release ou armazenamento externo.

---

## 10. Critérios de aceitação

### F0 — desbloqueio
- [ ] Abrir imagem com 500 boxes, editar, salvar, recarregar — sem exceção
- [ ] Mover e redimensionar box com o mouse funciona
- [ ] "Aprender com Página Atual" e "Treinamento Batch" concluem sem erro
- [ ] PDF convertido contém `♔♕♖♗♘♙♚♛♜♝♞♟` extraíveis — **nenhum `·`**
- [ ] `pip install -r requirements.txt` reproduz o ambiente em máquina limpa

### F1 — qualidade
- [ ] Modelo reconhece as 12 peças, pretas inclusive
- [ ] Nenhuma classe com menos de 10 amostras entra no treino
- [ ] Acurácia reportada vem de conjunto de validação separado
- [ ] `folder_to_char ∘ char_to_folder` = identidade para as 105 classes

### F2 — saída
- [ ] PDF de saída mantém o texto original selecionável
- [ ] Texto de OCR é pesquisável no PDF resultante
- [ ] Dry-run gera relatório sem escrever arquivo
- [ ] Poppler não é mais necessário

### F3/F4 — produtividade e UI
- [ ] Nenhuma operação bloqueia a UI por mais de 100 ms
- [ ] Toda operação longa é cancelável
- [ ] Trocar de página preserva os boxes da anterior
- [ ] Crash com trabalho pendente permite recuperação pelo sidecar
- [ ] Revisão de uma página de 2.000 caracteres cabe em 15 minutos

O último critério é o que resume o projeto. Hoje ele é inatingível — porque o programa
não abre.

### F9 — léxico (§5.8)
- [x] Nenhuma palavra é reescrita sem que os candidatos venham do `predict_topk`
- [x] Palavra fora do dicionário é sinalizada, nunca trocada pela mais parecida
- [x] Sem dicionário carregado, o léxico não altera um caractere
- [x] `Bxf6`, `exd5`, `O-O` e os demais pedaços tipados `lance` não passam pelo léxico
- [x] A precisão da sinalização está medida nas páginas rotuladas, com a fatia de erro
      alcançável contada **antes** de o léxico ser escrito
- [x] A lista do usuário só recebe palavra que ele digitou, e o ganho dela está medido
      com uma página fora da amostra (F9.2: 9,2% do alarme falso)
