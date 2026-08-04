# PyBoxEditor — Especificação de Implementação

Versão: 2.0
Data: 2026-08-03
Status: implementável
Substitui parcialmente: [`Substituição de Glifos de Xadrez.md`](../Substituição%20de%20Glifos%20de%20Xadrez.md) (v1.0)
Companheiro: [`ROADMAP.md`](../ROADMAP.md)

**Relação com a v1.0:** a spec v1.0 descreve apenas o módulo de substituição de glifos
e continua válida como referência de requisitos (RF-01…RF-06). Esta v2.0 cobre o sistema
inteiro, corrige decisões da v1.0 que a implementação provou erradas (§4.2) e adiciona
os contratos que faltavam. Onde houver conflito, **v2.0 prevalece**.

---

## 1. Escopo

Ferramenta desktop para OCR de livros de xadrez em PDF, com três capacidades:

1. **Editor de boxes** — desenhar, ajustar e rotular caixas de caractere sobre a página
2. **Reconhecimento** — cadeia neural → k-NN → EasyOCR, com aprendizado incremental
3. **Substituição de glifos** — converter notação em fonte de xadrez para Unicode

Não incluído nesta versão: extração de FEN, exportação PGN, correção por modelo de
linguagem.

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

### 2.3 Formato `.box`

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

O antigo `core/opencv_autobox.py` já tinha uma binarização Otsu melhor que a em uso,
com filtros de tamanho relativos à página. O arquivo foi removido na F5.1 (estava morto
desde sempre), mas **essa lógica é o ponto de partida deste módulo** — recuperar com
`git show 6a4b7a1:core/opencv_autobox.py`.

Toda a detecção de boxes passa a consumir `preprocess.binarize`. Nenhum threshold
literal deve sobrar no código.

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
3. **`training_data_2/`** — 138 PNGs soltos fora do padrão de pastas por classe.
   Classificar ou descartar.
4. [feito] **`folder_to_char`** — decodificação de `ligature_hex_*` implementada,
   com hex de largura fixa (a variável era ambígua). Ganhou `strict=True`, que
   levanta em vez de devolver `"?"`: devolver `"?"` em silêncio foi o que deixou o
   defeito de `sym_f7` passar despercebido.

**Regra que saiu daqui:** nunca usar `cv2.imread`/`cv2.imwrite` como teste de
integridade de arquivo. No Windows eles falham em caminho não-ASCII e devolvem
`None`/`False`, indistinguível de "arquivo corrompido". A primeira versão da
migração caiu nisso e apagou PNGs válidos. Use `open()` + `cv2.imdecode`, e prefira
mover para quarentena a apagar.
5. **Peças pretas** — coletar amostras de ♙♚♛♜♝♞♟, **ausentes do modelo atual**.
   Sem isso, retreinar não melhora o reconhecimento de notação.

Adicionar validação que roda antes do treino e falha alto:

```python
def validate_dataset(data_dir: str) -> list[str]:
    """Erros: pasta vazia, nome irreversível, classe abaixo do mínimo, PNG ilegível."""
```

### 5.3 Balanceamento

Proporção atual: 25.075 (`lower_e`) para 1 (`upper_Z`). Com `CrossEntropyLoss` sem
pesos, classes raras nunca são previstas.

```python
from torch.utils.data import WeightedRandomSampler

counts  = np.bincount(labels)
weights = 1.0 / counts[labels]
sampler = WeightedRandomSampler(weights, num_samples=len(labels), replacement=True)
loader  = DataLoader(dataset, batch_size=64, sampler=sampler)   # sem shuffle com sampler
```

Complementar com `MIN_SAMPLES_PER_CLASS = 10`: classes abaixo do piso são excluídas do
treino e **reportadas**, em vez de entrarem como ruído.

Augmentation permanece só no treino — hoje é aplicada ao dataset inteiro
(`neural_trainer.py:181`), o que contamina qualquer avaliação futura.

### 5.4 Avaliação

Hoje: acurácia calculada sobre o treino aumentado, e "melhor modelo" escolhido por
*training loss* (`neural_trainer.py:231-234`) — critério que seleciona exatamente o
ponto de maior overfitting.

```
split estratificado 80 / 15 / 5   (treino / validação / teste)
early stopping por validation loss, paciência 5
checkpoint pelo melhor validation loss  ← não training loss
```

Relatório ao final do treino:

- acurácia global de validação
- **matriz de confusão por classe** — é ela que revela `e`↔`c`, `1`↔`l`, ♔↔`K`
- lista das 10 piores classes
- amostras de validação erradas, salvas em disco para inspeção

### 5.5 Compatibilidade de modelo

`model_meta.json` mapeia índice → caractere. Os índices vêm de
`sorted(os.listdir(data_dir))` (`neural_trainer.py:125`). **Adicionar ou remover
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

---

## 6. Aplicação

### 6.1 Estado e histórico

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
| `paths.last_dir`, `paths.tesseract` | — |

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
│ Caractere: [_] [Aplicar] [Próximo>>] │ NAGs: ! !! ? ?? …  │
├───────────────────────────────────────────────────────────┤
│ ◀ Pág 12/248 ▶ │ 1.847 boxes │ 23 vazios │ ▓▓▓░ 68%      │
└───────────────────────────────────────────────────────────┘
```

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
- [feito] alternadores: só pendentes / só vazios / por origem
- [feito] `F3` / `Shift+F3` — próximo/anterior pendente dentro do filtro ativo,
  circular
- [feito] contador "mostrando N de M"

**Contrato que não pode ser quebrado:** com filtro ativo a lista deixa de mapear 1:1
com `self.boxes`. Toda conversão passa por `_visiveis` (índices dos boxes exibidos) e
`linha_do_box()`. Confundir linha de lista com índice de box faz o usuário editar o
caractere errado sem perceber — é o modo de falha mais perigoso desta parte da UI.

A busca trata o texto digitado como **conjunto** de caracteres, não como substring:
num editor onde cada box tem um caractere só, "aeiou" achar qualquer vogal é mais útil
que casar substrings. Diferencia maiúscula de minúscula porque o OCR diferencia
(`upper_A` e `lower_a` são classes distintas).

### 7.5 Aplicar a todos os semelhantes

Com um box selecionado e corrigido: **"Aplicar a todos os semelhantes"** (`Ctrl+Shift+A`)
encontra boxes com imagem parecida (distância L2 abaixo de um limiar ajustável), mostra
uma prévia em grade com seleção individual, e aplica em lote.

Corrigir um `e` mal reconhecido pode corrigir 300 de uma vez. É o maior ganho isolado
de produtividade do roadmap.

### 7.6 Atalhos

| Tecla | Ação |
|-------|------|
| `Ctrl+O` / `Ctrl+S` / `Ctrl+Shift+S` | Abrir / Salvar / Salvar como |
| `Ctrl+Z` / `Ctrl+Y` | Undo / Redo |
| `↑` `↓` | Box anterior / próximo |
| `PgUp` `PgDn` | Página anterior / próxima |
| `Del` | Excluir box |
| `Ctrl+D` | Dividir box |
| `F2` | Modo digitação contínua |
| `F3` / `Shift+F3` | Próximo / anterior no filtro |
| `Ctrl+Shift+A` | Aplicar a semelhantes |
| `Z` | Zoom no box selecionado |
| `Esc` | Cancelar operação em andamento |

`d` sozinho deixa de dividir box — passa a `Ctrl+D`. O guard atual
(`_on_key_split_safe`) só testa `tk.Entry` e não cobre `ttk.Entry`, `Text` ou
`Spinbox`, então digitar "d" no widget errado divide um box.

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

---

## 8. Testes

Não existe nenhum teste hoje. `test_chess_pdf.py` é um stub cuja única função está
comentada — imprime "a sintaxe está correta" e não verifica nada.

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
- `sort_boxes_reading_order`: coluna única, duas colunas, com diagrama no meio
- `binarize`: página limpa, escaneada, com iluminação irregular
- `folder_to_char` ∘ `char_to_folder` = identidade para todas as 105 classes
  (**hoje falha em `sym_f7` e em `ligature_hex_*`**)
- PDF pesquisável: texto extraível do resultado bate com os boxes de entrada

### 8.3 Regressão de OCR

Um conjunto fixo de 10 páginas com verdade-fundamental em `.box`, e um alvo de
acurácia que não pode regredir entre commits.

---

## 9. Empacotamento

### 9.1 `requirements.txt`

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

### 9.2 Estrutura

```
PyBoxEditor_Tkinter/
├── assets/fonts/DejaVuSans.ttf      ← novo, empacotado (§4.2)
├── config/{settings.py,profiles/}
├── core/
│   ├── box_model.py                             ← existe
│   ├── box_io.py  preprocess.py                 ← a criar (§2.3, §3)
│   └── services/{box,ocr,pdf,learning,history}_service.py      ← existem
│       └── document_service.py                  ← a criar (§6.4)
├── ui/
│   ├── {main_window,canvas_view}.py             ← existem
│   └── {status_bar,toolbar}.py                  ← a criar (§7.1, F4.2)
├── tests/
└── docs/{SPEC.md,ROADMAP.md}
```

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
