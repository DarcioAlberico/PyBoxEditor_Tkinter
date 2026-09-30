# Análise da janela do editor de livro — rumo a um editor profissional

**Data:** 2026-09-30 · **Base:** `master` em `fd52c11` + a árvore de trabalho ·
**Tela de referência:** 1360×768 a 125% (área útil 728 px de altura).

Pedido do usuário: (1) uma tela que mostre o **resultado** da edição do HTML em tempo
real, como o Sigil; (2) onde há código, **só código**, sem as caixinhas; (3) uma janela
profissional e fácil; (4) escolher um **PDF**, escolher páginas e editá-las no editor,
com texto, figurinas e diagramas extraídos pelo nosso OCR.

---

## 1. O que foi medido

| Medição | Resultado |
|---|---|
| Editor aberto por script DPI-aware com `Kasparov - The Dynamic Benko Gambit (2012).epub`, modo texto e depois `F11` + `F12` | a prévia abre com **~30 px de largura** na borda direita do código (só se lê "Pre") |
| `fitz.Story` (PyMuPDF 1.27.1, **já instalado**) desenhando um capítulo real do mesmo EPUB, com a `estilo.css` do livro, a fonte `SimbolosDeXadrez.ttf` e expoentes | layout de 4 páginas em **22 ms**; cada página em imagem a 110 dpi em **~35 ms**; figurinas, recuos e `<sup>` corretos |
| Captura do usuário (EPUB "Moderno Manual de Finais", saída do *immersive-translate*) | cada parágrafo é `<p class="calibre1" data-imt_insert_failed="1">` com `<span class="notranslate immersive-translate-target-…">` dentro: nada disso é dialeto, então **tudo vira ilha**; a barra diz "0 palavras" |

## 2. Diagnóstico: por que parece que falta a tela do Sigil

1. **As caixinhas não são o código — são o modo texto.** O que a captura mostra é o
   `TextoRico` desenhando ilhas (`(span)`, `(b)`, `<p class=…>`), porque a marcação que
   o tradutor automático deixou no EPUB está fora do dialeto (SPEC_EDITOR §6). O modo
   código **já é só código** (botão "Texto/Código" ou `F11`) — mas nada na tela diz isso.
2. **A prévia existe, mas não aparece.** `operacoes.previa` põe o código e a prévia com
   `pack(side="left", expand=True)`; o `tk.Text` do código pede a largura toda, o extra a
   repartir é zero, e a prévia fica com a sobra (~30 px). Não há divisória para arrastar.
3. **E, quando aparece, não é uma prévia.** Pela DEC-05, a prévia é o próprio `TextoRico`
   só de leitura: não aplica a CSS do livro e mostra **as mesmas ilhas** — ou seja, nunca
   mostra "o resultado", que é o que o Sigil faz (ele usa um navegador embutido).
4. **Ela só existe no modo código, e só pelo menu Exibir / `F12`.** Quem está no modo
   texto não tem como descobri-la.

## 3. Crítica de design da janela

### Impressão geral
A janela é **completa** (menus, atalhos, validação, xadrez de primeira classe) e isso é
raro. O problema maior não é falta de ferramenta: é que **a área de edição é pequena e o
resultado não é visível**. Numa tela de 728 px úteis, três barras (~95 px), o painel de
Busca sempre aberto (~120 px) e a barra de status deixam ~420 px para o texto; e a coluna
da direita gasta ~300 px com um painel Propriedades vazio.

### Usabilidade

| Achado | Gravidade | Recomendação |
|---|---|---|
| Prévia abre com ~30 px e sem divisória | 🔴 | `ttk.PanedWindow` código \| prévia com a divisória a 50% e a posição lembrada (ED-14) |
| Prévia não aplica CSS e mostra ilhas | 🔴 | motor de desenho real: `fitz.Story` (§4.1) |
| EPUB com marcação de tradutor/Calibre abre ilegível no modo texto, sem saída óbvia | 🔴 | "Limpar marcação importada…" com prévia das trocas e oferta automática ao abrir (ED-15) |
| O modo código e a prévia não se descobrem | 🔴 | três modos visíveis na própria aba: **Texto · Código · Dividido** (como Book/Code/Split View do Sigil) |
| Painel Busca ocupa ~120 px o tempo todo | 🟡 | recolhido por padrão; `Ctrl+F` abre uma faixa de uma linha sobre o editor; "Mais opções" expande |
| Figurinas e avaliações repetidas: barra de xadrez **e** painel Xadrez | 🟡 | uma só fonte: a barra fica com os 12 mais usados; o painel vira a paleta completa (e pode ser escondido) |
| Painel Propriedades: vazio ocupa ~300 px; numa ilha mostra um bloco de código cru | 🟡 | recolher quando "Nada sob o cursor"; ilha mostra só "Marcação fora do dialeto — Editar no código (F11)" com um botão |
| Painel Xadrez cortado embaixo (precisa rolar) | 🟡 | consequência do anterior; some quando Propriedades recolhe |
| Navegador e Sumário repetem a mesma lista (EPUB de uma página por arquivo) e cortam os nomes | 🟡 | abas na coluna esquerda (Arquivos · Sumário · Estilos) em vez de três painéis empilhados; dica com o nome inteiro |
| Botões `N I S T` não mostram estado (negrito ligado?) | 🟡 | botões de alternância (`ttk.Checkbutton` estilo *Toolbutton*) que acompanham o cursor |
| Barra de xadrez desenha `⩲`/`⩱` como `±`/`∓`: dois pares de botões idênticos | 🟡 | a fonte da interface não tem U+2A71/2A72 e o Tk cai num substituto; usar a fonte de símbolos do projeto nesses botões (ou rótulo `+=`/`=+`) |
| Painel Estilos: campo sem rótulo, "Aplica" cortado | 🟢 | rótulo "Novo estilo:"; botões com largura mínima |
| "Propriedades" escrito duas vezes (moldura e cabeçalho) | 🟢 | tirar o cabeçalho interno |

### Hierarquia visual
- **O olho vai primeiro** para as três fileiras de botões cinza iguais — errado; deveria
  ir para o texto. Todos os botões têm o mesmo peso: "Salvar" pesa o mesmo que "Just".
- **Leitura:** esquerda (3 painéis) → centro → direita (2 painéis) → baixo (4 abas): sete
  regiões competindo numa tela pequena.
- **Ênfase certa:** a aba ativa, o modo e o estado "alterado" — hoje só na barra de status.

### Consistência
| Elemento | Problema | Correção |
|---|---|---|
| Barras | rótulos em texto ("Esq", "Centro") ao lado de ícones de figurinas | um padrão: ícone + dica, texto só onde não há ícone claro |
| Botões "Aplicar" | três, em posições diferentes (Estilos, Propriedades, Xadrez) | aplicar ao sair do campo / `Enter`; botão só onde a ação é cara |
| Modo | é da aba, mas a barra de formatação troca a janela inteira | a barra acompanha a aba (já acompanha) **e** o seletor de modo fica na aba |

### Acessibilidade
- Contraste do texto: passa (preto sobre branco); o rodapé de erro `#b00020` passa.
- Alvos: os botões de NAG têm ~28×28 px — no limite; figurinas de 16 px ficam pequenas a 125%.
- Teclado: a ED-13 já garantiu ordem de tabulação e anéis de foco; os modos novos
  precisam de atalho (`F11` alterna Texto/Código; proposta `Ctrl+F11` para Dividido).

### O que funciona bem
- Menus completos com item desabilitado que diz a fase — honesto e útil.
- Barra de status informativa (capítulo, bloco, palavras, idioma, modo, estado).
- Abas com marca de alterado; `Ctrl+W` na barra de status.
- Xadrez como cidadão de primeira classe (diagrama, posição, validar notação).
- A ponte com a revisão (`data-origem-*`, `data-suspeito`) — base pronta para o item 4.

## 4. Proposta

### 4.1 A prévia de verdade (motor `fitz.Story`)

**Por que este motor:** já é dependência obrigatória (o OCR e a ED-12 usam; o PDF
paginado da ED-12 **já é** um `Story`), não precisa de navegador, entende CSS de livro
(fontes `@font-face`, recuos, `sup`, imagens pelo `Archive`) e a prova mediu 20–60 ms por
redesenho. `tkinterweb` (CSS fraco) e WebView2/`pywebview` (não se embute num `Toplevel`
do Tk e seria dependência nova) ficam de fora; "Abrir no navegador" continua para a
fidelidade absoluta.

**Como:**
- `core/editor/previa_story.py` (sem Tk): recebe o XHTML da aba, a CSS vinculada e um
  `Archive` montado dos recursos do projeto em memória; devolve páginas (largura da tela,
  altura contínua ou paginada) e o **mapa linha → retângulo**.
- **Sincronia:** antes de desenhar, uma **cópia** do XHTML recebe `id="__l<linha>"` em cada
  elemento de bloco (a linha-fonte, que o `xhtml` já conhece); `Story.element_positions`
  devolve o retângulo de cada um. Cursor no código → rola a prévia até o bloco; clique na
  prévia → o código vai à linha. Nada disso toca o arquivo salvo.
- `ui/editor/previa.py` vira um `Canvas` rolável com as páginas em `PhotoImage`; desenha só
  as visíveis (+1), redesenha 300 ms depois da última tecla (o atraso atual), e o XHTML
  mal-formado mantém a última imagem com o erro no rodapé (AC-ED08-7 fica).
- Tema da prévia: "Tela" (largura do painel) e "Página" (formato de página da ED-12).

**Limites conhecidos:** o `Story` não faz `float`, `flex` nem `position`; num livro de
xadrez isso quase não aparece. O diagrama em fonte (F120/F122, `<pre>` com a Merida/SkakNew)
já é desenhado pelo `Story` na ED-12.

### 4.2 Código limpo e modo Dividido

- Cada aba ganha o seletor **Texto · Código · Dividido** (três botões de alternância no
  alto da aba). **Dividido** = código à esquerda, prévia à direita, divisória arrastável.
- Ao abrir um capítulo com mais de N% de ilhas, a aba abre em **Dividido** e a barra de
  mensagens oferece "Limpar marcação importada…".
- **Limpar marcação importada** (Ferramentas): desembrulha `span` sem significado,
  apaga `data-imt*`, classes `notranslate`/`immersive-translate-*`, atributos vazios,
  e mapeia `calibreN` para estilos do dialeto pela regra CSS equivalente (negrito,
  itálico, recuo) — com a lista de trocas antes de aplicar, contagem por capítulo e um
  ponto de verificação criado antes (`checkpoint_criar`). Depois disso o modo texto
  deixa de mostrar caixinhas.

### 4.3 Janela compacta (sem tirar ferramenta nenhuma)

- Uma barra só (arquivo + formatação/código conforme o modo) e a barra de xadrez
  **recolhível**; ícones com dica.
- Busca recolhida numa faixa de uma linha (`Ctrl+F`/`Ctrl+H`), com "Mais opções".
- Coluna esquerda em abas (Arquivos · Sumário · Estilos); coluna direita recolhível;
  Propriedades encolhe quando vazio.
- "Modo foco" (esconde as colunas laterais) e lembrança do layout por modo.
- Meta: ≥ 560 px de altura de edição em 1360×768 (hoje ~420).

### 4.4 PDF → editor, por páginas, pelo nosso OCR

O que já existe e se reaproveita:
- `scripts/processar_editorial.py origem.pdf --formato json --paginas N… --camada auto`
  — o pipeline inteiro (camada do PDF quando nasceu digital, OCR neural quando não),
  com cache;
- `core/editor/importar_ir.de_documento(dividir="pagina")` — o caminho medido em 09-22
  como o melhor (marcas de página, orientação e lado dos diagramas, `data-origem-*`);
- `importar_ir.gravar_eventos` — a volta das correções para a revisão.

O que falta:
1. **Arquivo → Abrir PDF…**: diálogo com miniaturas (o `fitz` desenha a 30 dpi em
   milissegundos), seleção por clique ou faixa ("30-45, 60"), e o aviso "PDF nascido
   digital: usar o texto do PDF" / "PDF digitalizado: OCR" (`pdf_nativo`).
2. **Rodar fora do processo do editor.** O editor é leve de propósito (DEC-07: sem
   `torch`); o OCR vai num subprocesso do `processar_editorial.py`, com progresso por
   página no painel Mensagens e botão cancelar.
3. **Resultado:** um capítulo por página (ou por título), **anexado ao livro aberto** ou
   num livro novo; diagramas como `Diagrama` com FEN, figurinas como texto.
4. **Painel "Original"** (a terceira vista, junto de Texto/Código/Dividido): a página do
   PDF ao lado do texto, com a **caixa do bloco sob o cursor destacada**
   (`data-origem-caixa`) e os blocos `data-suspeito` marcados; `F4` vai à próxima
   suspeita. É o modo de conferência do ABBYY FineReader.
5. **Reler do PDF**: selecionar um bloco ou uma página e refazer só ele (subprocesso com
   `--paginas`), trocando o bloco no livro.

## 5. Fases propostas (continuam a numeração do `ROADMAP_EDITOR.md`)

| Fase | Entrega | Depende de | Tamanho |
|---|---|---|---|
| **ED-14** | Prévia real: `previa_story.py`, `Previa` em `Canvas`, sincronia por `__l<linha>`, divisória arrastável; corrige os 30 px | — | M |
| **ED-15** | Seletor Texto · Código · Dividido na aba; "Limpar marcação importada…" com trocas e ponto de verificação; abrir em Dividido quando há muitas ilhas | ED-14 | M |
| **ED-16** | Janela compacta: barra única, busca em faixa, colunas em abas e recolhíveis, Propriedades que encolhe, ⩲/⩱ na fonte certa, botões de estado | — (paralela) | M |
| **ED-17** | Abrir PDF…: diálogo de páginas, subprocesso com progresso/cancelar, anexar ao livro | — (paralela) | M |
| **ED-18** | Painel Original com a caixa destacada, navegação por suspeitas, Reler do PDF | ED-17 | M |

Ordem sugerida: **ED-14 → ED-15** (resolve a queixa principal), ED-16 e ED-17 em
paralelo, ED-18 por último. Cada fase com os ACs no formato do roadmap (teste sem
display onde der; captura DPI-aware a 1360×768 como gate visual).

## 6. Decisões (2026-09-30)

1. Prévia em **rolagem contínua**, como o Sigil.
2. Ao limpar a marcação importada, as classes `calibreN` **viram estilos do dialeto**.
3. PDF aberto no editor vira **livro novo**.

## 7. Andamento

| Fase | Estado |
|---|---|
| ED-14 | **implementada** 2026-09-30, sem commit — ver `ROADMAP_EDITOR.md` |
| ED-15 … ED-18 | a fazer |
