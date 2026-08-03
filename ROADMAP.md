# PyBoxEditor — Roadmap

Versão do documento: 1.0
Data: 2026-08-03
Escopo: OCR de livros de xadrez em PDF (editor de boxes + rede neural + substituição de glifos)

Documento companheiro: [`docs/SPEC.md`](docs/SPEC.md) (especificação de implementação)
Spec anterior (módulo de glifos): [`Substituição de Glifos de Xadrez.md`](Substituição%20de%20Glifos%20de%20Xadrez.md)

---

## Sumário executivo

O projeto tem uma arquitetura boa (services desacoplados da UI, dataclass de domínio,
pipeline de fallback neural → k-NN → EasyOCR) e uma base de treino relevante
(127.264 amostras, 105 classes). Mas hoje **ele não roda**: cinco defeitos de
runtime bloqueiam o caminho principal, e a funcionalidade-carro-chefe
(substituição de glifos de xadrez) **corrompe o PDF em silêncio**.

Todos os itens P0 abaixo foram reproduzidos executando o código, não inferidos por leitura.

| Fase | Tema | Resultado esperado | Status |
|------|------|--------------------|--------|
| **F0** | Desbloqueio | O app abre, edita e salva sem exceção | **concluída** (branch `fix/f0-desbloqueio`) |
| **F1** | Qualidade de OCR | Acurácia medível e peças pretas funcionando | pendente |
| **F2** | Saída PDF | PDF pesquisável, sem rasterizar o documento | pendente |
| **F3** | Produtividade | Revisão de 2.000 caracteres/página deixa de ser inviável | pendente |
| **F4** | UI | Interface responsiva, sem congelar | pendente |
| **F5** | Higiene | Dependências corretas, código morto removido, testes | parcial (testes de F0 feitos) |

---

## F0 — Desbloqueio (crítico) — CONCLUÍDA

> Sem esta fase nada mais importa: o programa quebra ao carregar qualquer box.

**Aplicada em 2026-08-03**, branch `fix/f0-desbloqueio` (4 commits sobre a baseline
`54bf80d`). Cobertura em `tests/test_f0_smoke.py` — 11 testes, dos quais 9 reprovam
na baseline e passam no código corrigido.

Verificação final: fluxo completo do editor sobre uma página real de 1310×1900
(abrir → detectar 764 boxes → editar → dividir → excluir → undo/redo → arrastar →
salvar → recarregar) sem nenhuma exceção.

### F0.1 — `BoxEntry` acessado como dicionário — corrigido
`ui/main_window.py:569` faz `b['x1']` num dataclass.

```
TypeError: 'BoxEntry' object is not subscriptable
```

`update_sidebar()` roda em **todo** carregamento, seleção e edição. O app morre assim
que existe um único box. **Este é o bug que impede o uso do programa.**

Mesma falha em três outros pontos:

| Arquivo | Linha | Chamada | Erro | Recurso quebrado |
|---------|-------|---------|------|------------------|
| `ui/main_window.py` | 569 | `b['x1']` | `TypeError` | Tudo |
| `ui/canvas_view.py` | 205, 216 | `boxes[i].copy()` | `AttributeError` | Mover/redimensionar box |
| `core/services/learning_service.py` | 52–56 | `b.get("char")`, `b["x1"]` | `AttributeError` | Aprender com Página Atual |
| `core/services/learning_service.py` | 137–141 | passa `dict` a `merge_vertical_boxes` | `AttributeError` | Treinamento Batch |

**Causa raiz:** houve migração de `dict` para `BoxEntry` que parou no meio. A correção
não é só trocar sintaxe — é fechar a migração e travá-la com teste.

### F0.2 — Substituição de glifos escreve `·` no lugar das peças — corrigido

`core/chess_pdf_processor.py:92` usa `fontname="helv"` (Helvetica Base-14, Latin-1).
Essa fonte não tem os glifos U+2654–U+265F. O PyMuPDF **não levanta erro**: troca cada
peça por `·`.

Verificado:

```
insert_text(..., "♔♕♖♗♘", fontname="helv")  →  texto extraído: '·····'
```

O usuário roda a conversão, vê "Concluído", e recebe um PDF destruído.

**Correção verificada** — embutir uma fonte Unicode:

```python
page.insert_font(fontname="chessuni", fontfile=r"C:\Windows\Fonts\seguisym.ttf")
# resultado: '♔♕♖♗♘♙♚♛♜♝♞♟'  (12/12 preservados)
```

`seguisym.ttf` existe nesta máquina. Ainda assim, a fonte deve ser **empacotada** no
projeto (`assets/fonts/`) — depender de fonte do sistema quebra em outro computador.
Ver SPEC §4.2.

### F0.3 — Undo/redo perde estado — corrigido

Verificado: o projeto mistura dois padrões incompatíveis.

- `apply_char`, `auto_fill_characters` → snapshot **depois** da mutação (correto)
- `on_mutation_start`, `delete_selected_box`, `generate_boxes_opencv` → snapshot **antes**

No padrão "antes", o estado novo nunca entra no histórico:

```
add B → undo → ['A']      (ok por acidente)
      → redo → ['A']      ✗ deveria ser ['A','B'] — o B some para sempre
```

**Correção:** um único padrão — `snapshot()` sempre *após* a mutação, com o estado
inicial gravado ao abrir a imagem. Ver SPEC §6.1.

### F0.4 — `requirements.txt` inutilizável — corrigido

- `PyMuPDF>=1.23.0` está gravado em **UTF-16**; o pip lê como `P y M u P D F`
- `torch` e `easyocr` — usados no código, **ausentes** do arquivo
- `pydantic` e `python-Levenshtein` — listados, não instalados, não usados

Ou seja: `pip install -r requirements.txt` não reproduz o ambiente.

---

## F1 — Qualidade de OCR

### F1.1 — O modelo cobre 5 das 12 peças

`neural_pdf_processor.py:11` declara `CHESS_PIECES` com 12 símbolos. O
`model_meta.json` treinado contém apenas 5:

| Peça | Status | | Peça | Status |
|------|--------|-|------|--------|
| ♔ U+2654 | treinado | | ♙ U+2659 | **ausente** |
| ♕ U+2655 | treinado | | ♚ U+265A | **ausente** |
| ♖ U+2656 | treinado | | ♛ U+265B | **ausente** |
| ♗ U+2657 | treinado | | ♜ U+265C | **ausente** |
| ♘ U+2658 | treinado | | ♝ U+265D | **ausente** |
| | | | ♞ U+265E | **ausente** |
| | | | ♟ U+265F | **ausente** |

As peças pretas — que aparecem em metade da notação de qualquer livro — nunca podem
ser reconhecidas. O filtro `char in CHESS_PIECES` simplesmente nunca casa para elas.

**Ação:** coletar amostras das 7 classes faltantes antes de qualquer novo treino.
Sem isso, treinar de novo não melhora nada nesse eixo.

### F1.2 — Desbalanceamento extremo, sem compensação

| Classe | Amostras |
|--------|---------:|
| `lower_e` | 25.075 |
| `lower_a` | 16.861 |
| `lower_h` | 10.608 |
| … | |
| `upper_X`, `upper_Y`, `upper_Z` | **1** |
| `lower_ä` | **0** (pasta vazia, mas ocupa índice de classe) |

Proporção de 25.075:1. Com `CrossEntropyLoss` sem pesos e `shuffle=True` puro
(`neural_trainer.py:186,191`), o modelo aprende a nunca arriscar classes raras —
o custo de errar um `e` domina o gradiente.

**Ação:** `WeightedRandomSampler` ou `class_weight` na loss, e piso mínimo de
amostras por classe (ver SPEC §5.3).

### F1.3 — A acurácia reportada não significa nada

`neural_trainer.py:228` calcula acurácia sobre o **próprio conjunto de treino, já
aumentado**. Não existe split de validação. O "Acc: 98%" exibido ao usuário não diz
se o modelo generaliza — e com o desbalanceamento acima, prever sempre as 10 classes
mais comuns já daria número alto.

Pior: `torch.save` em `neural_trainer.py:234` usa *training loss* como critério de
"melhor modelo". Isso seleciona o ponto de maior overfitting.

**Ação:** split estratificado 80/15/5, early stopping por *validation* loss,
matriz de confusão por classe no relatório. SPEC §5.4.

### F1.4 — Classe corrompida no dataset

A pasta `training_data/sym_f7/` tem **127 amostras**. Mas:

```python
folder_to_char("sym_f7")  →  chr(int("f7"))  →  ValueError  →  "?"
```

São 127 amostras treinando o modelo a prever literalmente `"?"`. O nome veio de um
`char_to_folder` hexadecimal antigo que o `folder_to_char` atual não sabe reverter
(`core/learner.py:69-73`).

O mesmo caminho engole erro em `ligature_hex_*`, que retorna `"?"` por TODO
não implementado (`learner.py:56`).

### F1.5 — Pré-processamento fraco para material escaneado

Threshold fixo em **180**, replicado em três lugares
(`box_service.py:20`, `learning_service.py:127`, `neural_pdf_processor.py:17`).

Sem: Otsu, threshold adaptativo, deskew, remoção de ruído, normalização de DPI.
Para páginas escaneadas com iluminação irregular — o caso normal em livro digitalizado —
isso perde caracteres inteiros nas bordas.

Detalhe irônico: `core/opencv_autobox.py:17` **já implementa Otsu** com filtros de
tamanho melhores. O arquivo nunca é importado. Está morto.

### F1.6 — Ordenação de leitura ignora colunas

`sort_boxes_reading_order` (`box_service.py:36`) agrupa por sobreposição vertical.
Livros de xadrez são fortemente diagramados, muitos em duas colunas. O algoritmo vai
intercalar as colunas linha a linha, produzindo texto embaralhado.

---

## F2 — Saída de PDF

### F2.1 — O PDF de saída é rasterizado (maior lacuna de OCR do projeto)

`neural_pdf_processor.py:104-118` converte cada página em imagem RGB, desenha os
símbolos por cima e salva tudo como PDF de imagens.

Consequências:

- **texto selecionável some** — inclusive o texto que estava perfeito no original
- **busca deixa de funcionar** no arquivo inteiro
- **tamanho explode** (páginas viram bitmaps)
- não há **camada de texto** — o resultado não é um PDF de OCR, é um álbum de fotos

Para uma ferramenta cujo propósito é OCR, essa é a lacuna estrutural mais séria.

**Ação:** camada de texto invisível (`render_mode=3`) sobre a página original
preservada, via PyMuPDF. SPEC §4.3.

### F2.2 — Dependência do Poppler é desnecessária

`pdf_service.py` usa `pdf2image`, que exige o binário externo **Poppler** no PATH —
fonte recorrente de erro no Windows (o próprio código tem tratamento especial para
isso em `main_window.py:980-986`).

Mas o projeto **já depende de PyMuPDF**, que renderiza páginas nativamente:

```python
pix = page.get_pixmap(dpi=300)
```

Unificar em PyMuPDF elimina uma dependência nativa e simplifica a instalação.

### F2.3 — Faltam relatório e dry-run

A spec v1.0 pede (RF-06 e RNF-04) e não foram implementados:

- relatório JSON/CSV das substituições (página, bbox, fonte, antes, depois, avisos)
- modo dry-run que detecta e reporta sem alterar o arquivo

Num conversor que reescreve PDFs, dry-run não é conforto — é a única forma de conferir
antes de destruir.

### F2.4 — Perfis de mapeamento por fonte

A spec v1.0 §10 pede perfis por livro/editora. O código tem um único
`DEFAULT_MAPPING_PROFILE` hardcoded (`chess_pdf_processor.py:12`). Fontes que mapeiam
peças fora do padrão KQRBNP (comum em Chess Diagram TTF) ficam sem solução.

---

## F3 — Produtividade

O gargalo real: uma página de livro tem ~2.000 caracteres. Hoje a revisão é
**um Enter por caractere**, sem filtro, sem pistas visuais.

| # | Melhoria | Impacto |
|---|----------|---------|
| F3.1 | **Modo digitação contínua** — tecla aplica e avança sozinha, sem Enter | Corta metade das teclas |
| F3.2 | **Cor por confiança** — vermelho <70%, amarelo <90%, verde ≥90% | O olho vai direto ao suspeito |
| F3.3 | **Filtros na lista** — só vazios / só baixa confiança / busca por caractere | Revisar 80 boxes em vez de 2.000 |
| F3.4 | **Autosave** a cada N alterações + recuperação de crash | O `crash_log.txt` existe por um motivo |
| F3.5 | **Atalhos** — Ctrl+S, Ctrl+O, PgUp/PgDn (páginas), Tab/Shift+Tab | Fluxo sem mouse |
| F3.6 | **Aplicar a todos os semelhantes** — corrigiu um `e`, corrige os 300 iguais | Ganho de ordem de grandeza |
| F3.7 | **Boxes persistem por página de PDF** — hoje trocar de página descarta tudo | Evita perda silenciosa de trabalho |

Sobre F3.2: o pipeline **já calcula** a confiança em `fallback_chain` e a descarta em
`main_window.py:525` (`char, source, _`). O dado mais útil para revisão de OCR está
sendo jogado fora.

Sobre F3.7 — merece destaque: `_load_pdf_page` faz `self.boxes = []` sem aviso nem
confirmação. Navegar para a próxima página apaga tudo que foi digitado. Silenciosamente.

---

## F4 — Interface

### F4.1 — A UI congela em toda operação pesada

Todo processamento roda na thread do Tkinter com `self.parent.update()` no meio do
laço (`main_window.py:436, 491, 546`). Durante OCR de uma página, treino ou lote:

- janela marcada como "Não Responde" pelo Windows
- **não há como cancelar**
- `update()` reentrante durante processamento é uma fonte clássica de corrupção de
  estado no Tk (pode reentrar num handler no meio da mutação da lista de boxes)

**Ação:** worker em `threading.Thread` + fila; UI só lê a fila via `after()`. SPEC §6.2.

### F4.2 — Progresso comunicado pelo título da janela

`self.parent.title(f"Processando... ({i+1}/{total})")` é um recurso improvisado.
Existe um `ui/status_bar.py` no projeto — nunca usado.

### F4.3 — Zoom automático desorienta

`select_box` (`main_window.py:588`) chama `zoom_to_box` **em toda seleção**, com
`margin = 10.0` e zoom mínimo forçado de 1.5×. Navegar com as setas faz a imagem
saltar e re-enquadrar a cada tecla. Perde-se completamente o contexto da linha.

**Ação:** rolar o mínimo necessário para o box ficar visível; zoom só sob comando
explícito (tecla `Z` ou duplo-clique).

### F4.4 — `update_sidebar` reconstrói a lista inteira a cada tecla

`delete(0,"end")` + N `insert()` a cada seleção (`main_window.py:564`). Com 2.000
boxes, cada seta pressionada refaz 2.000 linhas. A digitação engasga.

**Ação:** atualizar só as linhas alteradas, ou migrar para `ttk.Treeview` virtualizado.

### F4.5 — Sem indicação de trabalho não salvo

Nenhum marcador de "sujo", nenhuma confirmação ao sair, ao abrir outro arquivo ou ao
trocar de página. Combinado com F3.7, é perda de trabalho garantida.

### F4.6 — Colisão de tecla

`d` está ligado a "dividir box" na janela inteira (`main_window.py:209`). O guard
`_on_key_split_safe` só testa `isinstance(focus_widget, tk.Entry)` — não cobre
`ttk.Entry`, `Text` ou `Spinbox`. Digitar "d" no lugar errado divide um box.

---

## F5 — Higiene do código

### F5.1 — Código morto (7 arquivos, ~180 linhas)

| Arquivo | Situação |
|---------|----------|
| `ui/sidebar.py` | Nunca importado. Ainda chama `controller.apply_char(c)` com assinatura errada |
| `ui/menu_bar.py` | Nunca importado — menu está inline em `main_window` |
| `ui/status_bar.py` | Nunca importado (e faz falta, ver F4.2) |
| `core/opencv_autobox.py` | Nunca importado — **e tem a melhor binarização do projeto** (F1.5) |
| `core/box_io.py` | Nunca importado. Formato de 5 campos, **incompatível** com o de 6 campos usado em `main_window` |
| `core/image_loader.py` | 6 linhas, nunca importado |
| `core/tesseract_utils.py` | Nunca importado |

`box_io.py` é o mais perigoso: dois formatos `.box` incompatíveis convivendo no mesmo
projeto. Quem usar o módulo errado lê lixo.

### F5.2 — Formato `.box` perde dados

`_save_box_to_path` (`main_window.py:709`) grava `ch[0]` — **trunca ligaduras
silenciosamente**. Um box marcado como `fi` é salvo como `f`. E `~` é usado como
marcador de vazio, então um `~` real vira vazio na volta.

### F5.3 — Sem testes

Nenhum teste automatizado. `test_chess_pdf.py` é um stub que imprime "a sintaxe está
correta" e não testa nada — a função de teste está comentada. `test_draw.py` e
`test_fonts.py` são scripts manuais.

Os quatro bugs de F0.1 seriam pegos por um único teste que constrói um `BoxEntry` e
chama `update_sidebar`.

### F5.4 — Arquivos de desenvolvimento no repositório

`debug_imports.py`, `debug_runner.py`, `debug_simulation.py`, `debug_tk.py`,
`crash_log.txt`, `full_log.txt`, `test_image.png`, `test_emj.png`, `test_sym.png`,
`Novo Documento de Texto.txt`, `training_data_2/` (138 PNGs soltos, fora do padrão
de pastas por classe).

O projeto também **não é um repositório git**. Sem controle de versão, refatorar é
apostar.

---

## Ordem de execução sugerida

```
[FEITO] F0.1  BoxEntry (4 pontos)
[FEITO] F0.2  fonte Unicode do PDF
[FEITO] F0.4  requirements.txt
[FEITO] F5.3  teste de fumaça mínimo   ← trava as correções acima
[FEITO] F0.3  undo/redo
      ↓
F5.1  remover código morto       ← reduz superfície antes de refatorar
F3.7  boxes por página + aviso   ← evita perda de trabalho
      ↓
F1.4  limpar sym_f7              ─┐
F1.1  coletar peças pretas        ├── precisam vir antes do próximo treino
F1.2  balanceamento               │
F1.3  split de validação         ─┘
      ↓
F2.1  PDF pesquisável            ← a maior lacuna funcional
F2.2  remover Poppler
      ↓
F4.1  threads                    ← precisa vir antes de F3 (UI travada)
F3.1–F3.6  produtividade
F4.2–F4.6  polimento de UI
```

**Dependência que importa:** F1.1 (coletar peças pretas) precisa preceder qualquer
retreino, senão o esforço de treino é desperdiçado. E F4.1 (threads) precisa preceder
F3, porque adicionar recursos numa UI que congela só piora a experiência.

Uma observação sobre priorização: F0.1 é meia hora de trabalho e devolve o programa ao
usuário. Vale fazer isolado, hoje, antes de qualquer planejamento maior.

---

## Fora de escopo (registrado para depois)

- Extração de FEN dos diagramas (a spec v1.0 §3 já marca como fase posterior)
- Exportação PGN da notação reconhecida
- Modelo de linguagem sobre notação de xadrez para corrigir OCR por contexto
  (`Nf3` é válido, `Nf9` não — corretor gratuito de alta precisão)
- Substituição do k-NN linear de `CharacterLearner` (varre 127k referências por
  predição — O(n) por caractere) por índice FAISS/KD-tree
- Empacotamento com PyInstaller
