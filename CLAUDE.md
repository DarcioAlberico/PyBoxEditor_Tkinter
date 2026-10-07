# PyBoxEditor — regras para quem trabalha neste repositório

OCR de livros de xadrez com editor de livros, em Python e Tkinter. Três fluxos numa base
só: a janela principal (boxes e OCR da página digitalizada), o documento editorial (fila de
suspeitas e exportação) e o editor de livros (`appy.py --editor`). O mapa está em
[README.md](README.md) e [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md); o vocabulário e as
invariantes, em [CONTEXT.md](CONTEXT.md).

## Rodar e testar

- O aplicativo roda com o Python do sistema, onde está o torch que ele usa:
  `py -3.13 appy.py` (ou `--editor livro.epub`). A suíte roda no `.venv`:
  `.venv\Scripts\python.exe -m pytest -q -m "not slow"` (uns cinco minutos) e, à parte,
  `-m "slow and not gui"`. Em testes avulsos, `-p no:cacheprovider` evita o cache de um
  processo anterior.
- **Não edite arquivos enquanto a suíte roda**: `inspect.getsource` lê o arquivo novo
  contra o módulo velho e o teste fica vermelho sem defeito nenhum.
- O gate da CI (`.github/workflows/ci.yml`) é `compileall`, `ruff check core ui appy.py
  config scripts` (E e F, 120 colunas), a coleta, o wheel e os dois passos do pytest, em
  Linux com Xvfb. Rode o `ruff` antes de todo commit.
- Antes de um push, exporte o `HEAD` limpo (`git archive HEAD | tar -x -C pasta`) e rode a
  suíte lá: sem o `custom_model.pth`, sem arquivos sem rastreio — é o que a CI vê. Testes
  que dependem de dado fora do git pulam com `skipif`, nunca falham.
- Janela do Tk só se mede com o processo DPI-aware, como o `appy` faz; senão sai 25 %
  maior. A conferência de DOCX é pelo Word por COM; a de HTML, pelo Edge headless.

## Código

- Português em nomes, docstrings e mensagens. O docstring de módulo diz o que o módulo é,
  por que existe e em que fase entrou (F-nn no `ROADMAP.md`, ED-nn no do editor, PD-nn
  nas pendências); o roadmap registra o que foi medido antes de dar a fase por concluída.
- **Caminho de produção e biblioteca de inspeção são coisas distintas.** O leitor é
  `core/livro.py` (com `pdf_nativo.py` e `diagrama.py`); a fachada editorial de produção
  nasce de `core.editorial_legacy.pipeline_de_producao`. O pacote `core/biblioteca/`
  (`ocr_phase3`, `ocr_phase4`, `ocr_layout`, `abbyy_ocr`) é biblioteca de inspeção: não
  ligue produto novo nele (`docs/ROADMAP_IMPLEMENTACAO_OCR.md`). EPUB e DOCX do OCR saem
  por `core/exportar.py`; os do editor, por `core/editor/` — dois escritores, por decisão
  medida (ED-12).
- Cor de interface só em `ui/tema.py` (um teste recusa `#RRGGBB` à mão em `ui/*.py`);
  caminho de dado só por `config.paths`, nunca um nome solto resolvido no cwd; a suíte
  nunca grava na pasta de dados do usuário (`tests/conftest.py` a reaponta).
- Toda mudança na leitura vem com número: o A/B das páginas de referência
  (`scripts/ab_ocr_livro.py`), a rodada do corpus (`scripts/rodada_do_corpus.py`) ou a
  medida da fase. "Medido, não estimado" é a regra dos documentos.
- Codificação: UTF-8 sem BOM e LF em todo texto (`.gitattributes` normaliza;
  `tests/test_codificacao.py` falha com mojibake ou byte fora de UTF-8;
  `python scripts/conferir_codificacao.py --corrigir` conserta). Mojibake de propósito leva
  `mojibake intencional` na linha. Patch com acento ou figurina vai por arquivo, nunca por
  heredoc no console cp1252. Script em Python que regrava texto abre com
  `newline="\n"`: o modo texto do Windows troca `\n` por CRLF e desfaz a normalização.
- Trabalho pesado nunca toca em widget: passa por `TaskService`/`_run_task`, e o callback
  volta na thread do Tk.

## Git

- Commits direto no `master`, sem branch de trabalho, salvo pedido explícito. `git add` com
  caminhos explícitos, nunca `-A` nem `.`: bases de treino soltas, PDFs de livros, pesos e
  saída de treino ficam fora (ver `.gitignore`). Push só quando pedido.
- A mensagem é uma frase que diz o que mudou para quem usa o programa, depois o porquê e o
  que foi medido, e fecha com `Suíte: N passed`. Nada de "fix", "wip" ou "update".
- Não se commita `*.pth` (fora `core/dados/`), PDF de livro, base sintética nem relatório
  de treino.

## Onde está o quê

| Quero… | Olho em… |
|---|---|
| mudar a leitura da página digitalizada | `core/livro.py`, `core/services/ocr_service.py`, `core/geometria_da_linha.py` |
| mudar a leitura do PDF nascido digital | `core/pdf_nativo.py` |
| mudar o diagrama | `core/diagrama.py`, `core/deteccao_de_tabuleiro.py`, `core/render_diagrama.py` |
| mudar a exportação EPUB/DOCX do OCR | `core/exportar.py` (o escritor de produção) |
| mudar o documento editorial ou a fila | `core/editorial_model.py`, `editorial_adapters.py`, `editorial_review.py`, `editorial_suspeitas.py` |
| mudar o editor de livros | `core/editor/` (sem Tk) e `ui/editor/` (a janela) |
| mudar a janela principal | `ui/main_window.py`; diálogos em `ui/dialogo_*.py` |
| medir | `scripts/` e os `medir_*.py` da raiz |
