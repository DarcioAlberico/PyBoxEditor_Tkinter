# Skill: Substituição de glifos de xadrez por letras ou símbolos Unicode em PDFs
Versão: 1.0  
Status: Especificação completa (implementável)  

> **Nota (2026-08-03):** este documento cobre apenas o módulo de substituição de glifos e
> segue válido como referência de requisitos (RF-01…RF-06). A especificação do sistema
> completo está em [`docs/SPEC.md`](docs/SPEC.md) (v2.0), que **prevalece em caso de conflito**.
>
> Duas decisões desta v1.0 foram corrigidas na v2.0 após verificação em runtime:
> - **§5 recomenda DejaVu Sans**, ausente nesta máquina. A v2.0 §4.2 usa uma cadeia de
>   fallback com validação obrigatória de cobertura de glifos — a fonte `helv` que a
>   implementação acabou usando troca toda peça por `·` **sem levantar erro**.
> - **§9 Solução A (substituição por span com bbox)** desloca a notação inline. A v2.0
>   §4.2 usa `insert_text` na baseline (`origin`) do span, não `insert_textbox`.
>
> Plano de execução: [`ROADMAP.md`](ROADMAP.md).

Linguagem: Python 3.10+  
Plataforma: Windows/Linux  
Foco do projeto: **substituir notações feitas com glifos/fontes de xadrez no meio do texto** por **texto Unicode (♔♕♖♗♘♙ / ♚♛♜♝♞♟)** ou por **letras (KQBNRP)**. **Diagramas de tabuleiro devem ser mantidos intactos (ignorados).**

---

## 1) Objetivo
Criar uma aplicação que:
1. Abre um PDF (escaneado ou digital).
2. Identifica regiões/textos onde há **glifos de xadrez** (ex.: fontes tipo “Chess”, “Merida”, “DiagramTTF”, etc., ou letras codificadas que viram peças pelo font).
3. Extrai o conteúdo (texto + fonte + tamanho + posicionamento).
4. Reconstrói o mesmo conteúdo usando:
   - **Unicode chess symbols** (U+2654..U+265F) e uma fonte compatível
   - ou **letras KQBNRP** (opção “ASCII”)
5. Escreve um PDF novo com a substituição:
   - preservando a posição no texto
   - sem “quebrar” o layout da página
6. (Opcional) Interface para revisão/ajuste manual de substituições.

---

## 2) Conceitos-chave (o que realmente acontece nesses PDFs)
Muitos PDFs de xadrez “digitais” não têm imagem do tabuleiro. Eles têm:
- **texto** desenhado com uma fonte que mapeia letras para peças (ex.: "K" desenha rei, "p" desenha peão, etc.)
- ou um conjunto de glifos proprietários (ex.: `\x6b` vira uma peça por causa do font)

Isso significa que:
- o PDF *tem texto*, mas o texto “não parece texto” sem a fonte correta.
- a substituição ideal é **re-escrever texto** no mesmo local, com outra fonte.

---

## 3) Escopo
### Inclui
- PDFs digitais com glifos (texto) e fontes de xadrez usados de forma inline (no texto)
- substituição por Unicode (♟ etc.) ou letras (KQBNRP)
- preservação de posicionamento/tamanho/escala
- heurística para **ignorar** diagramas de tabuleiro desenhados com fontes de xadrez
- batch (várias páginas, vários PDFs)
- cache e relatório de substituições

### Opcional (fases posteriores)
- conversão de texto inline para imagens SVG caso Unicode não atenda
- extração de FEN de diagramas intocados para outras finalidades

---

## 4) Stack recomendada
### Núcleo PDF
- **PyMuPDF (fitz)**: leitura de texto, spans, fonte, bbox, escrita de overlays e inserção de texto

### Tipografia / fontes
- Fonte Unicode robusta:
  - **DejaVu Sans** (geralmente tem ♔♕♖♗♘♙ / ♚♛♜♝♞♟)
  - ou **Noto Sans Symbols 2** (excelente cobertura)
- (Opcional) fallback: desenhar como vetores via SVG → inserir como forma (mais complexo)

### UI (opcional)
- PySide6 (Qt) ou Tkinter (mais simples)

---

## 5) Requisitos funcionais
### RF-01: Abrir PDF e enumerar páginas
- carregar PDF
- obter contagem de páginas
- para cada página: extrair blocos de texto e suas propriedades

### RF-02: Detectar texto “suspeito” de glifo de xadrez no texto
Detectar candidatos usando **heurísticas**:
- nome da fonte contém termos como:
  - `chess`, `merida`, `diagram`, `figurine`, `skak`, `cburnett`, `alpha`, `leipzig` (lista configurável)
- o span **NÃO** está dentro de uma região quadrada/retangular típica de diagrama (comum em tabuleiros 8x8).
- excluir blocos onde múltiplas linhas seguidas com a mesma fonte de xadrez formam uma grelha estruturada (tabuleiro).

Saída: lista de `CandidateSpan` contendo apenas glifos de anotações soltas (inline).

### RF-03: Extrair spans com posicionamento preciso
Para cada span candidato coletar:
- `page_number`
- `text`
- `font_name`
- `font_size`
- `color`
- `bbox` (x0,y0,x1,y1)
- `origin` / baseline (se disponível)
- `matrix` (transformação/rotação) quando houver

### RF-04: Converter glifo → Unicode ou letra
Criar um “Mapeador” configurável:
- Modo A: **Unicode**
- Modo B: **Letras**

Exemplo (depende do PDF/fonte real):
- entrada: `"KQRBNP"` → saída Unicode `"♔♕♖♗♘♙"`
- entrada: `"kqrbnp"` → saída Unicode `"♚♛♜♝♞♟"`
- se o PDF usa outra codificação (ex.: `A`=rei, `B`=dama...), você cria uma tabela para aquela fonte.

Saída: `replacement_text`.

### RF-05: Substituir no PDF sem quebrar layout
Método robusto (“overlay”):
1. Desenhar um retângulo branco (ou da cor do fundo) cobrindo `bbox` do span original
2. Inserir `replacement_text` na mesma região, ajustando:
   - fonte destino (Unicode) + tamanho aproximado
   - alinhamento (baseline/top-left)
   - tracking/escala horizontal se necessário

Saída: PDF novo.

### RF-06: Relatório de substituições
Gerar JSON/CSV contendo:
- página
- bbox
- fonte original
- texto original
- texto substituído
- warnings (ex.: “fonte Unicode sem glifo ♞”, “ajuste de escala aplicado”)

---

## 6) Requisitos não-funcionais
- RNF-01: Processar PDF de 200+ páginas de forma estável (sem vazar memória)
- RNF-02: Suportar batch (múltiplos arquivos)
- RNF-03: Determinístico (mesma entrada → mesma saída)
- RNF-04: “Dry-run” (modo que só detecta e reporta, sem alterar)
- RNF-05: Configuração por projeto (perfil por livro/fonte)

---

## 7) Arquitetura (módulos)
### 7.1 `pdf_io.py`
- `open_pdf(path) -> doc`
- `iter_pages(doc) -> page`
- `extract_text_spans(page) -> list[Span]`

### 7.2 `detector.py`
- `is_chess_font(font_name) -> bool`
- `score_span_as_chess(span) -> float`
- `find_candidates(spans, threshold) -> list[CandidateSpan]`

### 7.3 `mapper.py`
- `load_mapping(profile.json)`
- `map_text(text, mode="unicode|letters") -> mapped_text`
- suporte a múltiplas fontes: `mapping[font_name][char] -> replacement`

### 7.4 `renderer.py`
- `pick_unicode_font()`
- `fit_text_to_bbox(text, bbox, base_size) -> (font_size, x, y, xscale)`
  - regra: reduzir/aumentar font_size até caber na largura do bbox
  - aplicar `render_mode` (fill/stroke) se preciso

### 7.5 `patcher.py`
- `cover_bbox(page, bbox, color)`
- `insert_text(page, text, pos, font, size, color, xscale=1.0, rotate=0)`
- `apply_replacements(doc, replacements)`

### 7.6 `pipeline.py`
- orquestra:
  - extrai spans
  - detecta candidatos
  - mapeia
  - substitui
  - salva
  - gera relatório

### 7.7 `ui/` (opcional)
- viewer de página
- lista de candidatos
- editor rápido do mapping por fonte
- botão “aplicar” por página/diagrama

---

## 8) Estratégia de detecção (como acertar na prática)
### Nível 1 (Identificar e Isolar Diagramas)
- Agrupar spans por proximidade → formar “regiões de diagrama”.
- Se uma região tem múltiplos spans com fonte de xadrez organizados em grid, ou forma um bloco grande, **marcar essa região para ser IGNORADA**.

### Nível 2 (Filtragem para Texto Inline)
- Fora das regiões de diagrama, detectar `font_name` de xadrez.
- Tratar apenas spans curtos que acompanham o texto normal (ex: "1. ♘f3").

### Nível 3 (casos chatos)
- PDF com fontes subset e nomes aleatórios (ex.: `ABCD+F1`)
  - solução: manter “assinatura”:
    - largura média dos glifos
    - repetição de padrões
    - uso concentrado em áreas quadradas

---

## 9) Estratégia de substituição (o ponto mais crítico)
### Problema
O texto original pode ter:
- espaçamento customizado (cada peça em uma posição exata)
- rotação/escala
- renderização por “glyph positioning” (não só texto simples)

### Soluções (em ordem de complexidade)
**Solução A: Substituição por span (simples)**
- cobre bbox do span e reescreve um texto “equivalente”
- funciona quando o span já representa uma linha/trecho inteiro

**Solução B: Substituição por glifo unitário (precisa)**
- o span contém letras que representam peças com espaçamento “monoespaçado”
- você substitui caractere por caractere:
  - mede largura de cada “slot”
  - escreve Unicode peça a peça em posições calculadas
- ideal para tabuleiros feitos em texto

**Lidando com Diagramas (Ignorar)**
- Como o escopo não envolve substituir tabuleiros inteiros, a principal missão aqui é **Detecção Falso-Positivo**:
- Identificar a estrutura visual 8x8 (muitas quebras de linha com caracteres uniformes) para aplicar uma máscara de "skip" ou exclusão naquela `bbox`.

---

## 10) Perfis de mapeamento (essencial)
Criar perfis por livro/editora.
Exemplo `profile.json`:
```json
{
  "mode_default": "unicode",
  "fonts": {
    "Merida": {
      "K": "♔", "Q": "♕", "R": "♖", "B": "♗", "N": "♘", "P": "♙",
      "k": "♚", "q": "♛", "r": "♜", "b": "♝", "n": "♞", "p": "♟",
      ".": "·", "-": " "
    },
    "ChessDiagramTTF": {
      "A": "♔",
      "B": "♕"
    }
  }
}