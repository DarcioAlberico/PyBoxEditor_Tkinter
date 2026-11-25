# PyBoxEditor

![CI](https://github.com/DarcioAlberico/PyBoxEditor_Tkinter/actions/workflows/ci.yml/badge.svg)

Editor e pipeline de OCR para livros de xadrez: lê a página digitalizada ou o PDF nascido
digital, reconhece a prosa, a notação com figurinas e os diagramas (que viram FEN), e
escreve o livro de volta em EPUB, DOCX, HTML, PDF pesquisável e PGN — com um editor de
livros para acabar o trabalho. Em Python 3.11–3.13, Tkinter, PyMuPDF, OpenCV e PyTorch;
desenvolvido e medido no Windows, testado no Linux pela CI.

## Os três fluxos

**1. O editor de boxes e o OCR da página digitalizada.** `python appy.py` abre a janela
principal. Abre-se um PDF ou uma imagem, "Detectar e reconhecer" segmenta a página e lê
cada caractere com a rede de glifos do projeto (a notação, as figurinas, os símbolos de
avaliação) e com o Tesseract (a prosa), fundindo os dois palavra a palavra; os boxes se
revisam na tela, no modo digitação, e os diagramas impressos viram posições num tabuleiro
editável. "Exportar → Livro" escreve EPUB e DOCX com a fonte de xadrez embutida;
"Exportar → Documento editorial" e "PDF pesquisável" são as outras saídas.

**2. O documento editorial.** Tudo o que foi lido vai para um documento intermediário
versionado (`core/editorial_model.py`), com a evidência de cada linha e a procedência de
cada bloco. A fila de suspeitas ("Revisar") mostra o recorte ao lado da leitura e as
alternativas; cada decisão fica num diário que não apaga a anterior. HTML, TXT, PDF
pesquisável, EPUB e DOCX saem da mesma sequência de blocos. Sem a janela:
`python scripts/processar_editorial.py livro.pdf --formato epub`.

**3. O editor de livros.** `python appy.py --editor [livro.epub]` abre o editor: lê e
escreve EPUB, DOCX, HTML, TXT, PDF e PGN, com modo texto e modo código, diagramas de
xadrez como objetos editáveis, ortografia, tipografia, sumário, índices de jogadores e
aberturas, relatórios e validação com o epubcheck. "Abrir no editor", na janela principal,
leva o documento editorial para cá.

## Instalar e rodar

```text
python -m venv .venv
.venv\Scripts\activate
python -m pip install -e ".[all]"
python appy.py
```

A instalação mínima (`pip install -e .`) roda o editor de livros e a leitura do PDF nascido
digital; `[ocr]` traz o Tesseract pelo pytesseract e o OpenCV, `[ml]` o PyTorch e o
EasyOCR, `[docx]` a escrita de DOCX, `[desktop]` o PyInstaller do bundle. O Tesseract é um
executável à parte e precisa estar instalado. Os pesos treinados grandes ficam fora do git
e viajam como pacote verificável (`scripts/empacotar_modelo.py`); sem eles o aplicativo abre
no modo básico. Detalhes, extras e o wheel: [docs/SETUP.md](docs/SETUP.md).

## Testar

```text
python -m pytest -q -m "not slow"
python -m pytest -q -m "slow and not gui"
python -m ruff check core ui appy.py config scripts tests
```

São mais de quatro mil testes em cinco minutos; os lentos (medições de desempenho, o wheel
instalado num venv limpo) rodam à parte, como na CI. Antes de um push, rode a suíte numa
exportação limpa do `HEAD` (`git archive HEAD | tar -x -C pasta`): é a condição da CI, sem
o modelo e sem o que a árvore tem a mais. Todo arquivo de texto é UTF-8 sem BOM e com LF;
`python scripts/conferir_codificacao.py --corrigir` conserta o que uma ferramenta estragar.

## O que está medido

Os números vivem nos documentos, e cada fase do roadmap diz o que mediu antes de se dar por
concluída. Na última rodada registrada (`benchmarks/rodadas/2026-11-25-1815.json`, de
2026-11-25, corpus `6d187d98`), nas quatro páginas de referência (Aagaard, Nunn e Yusupov,
a 300 dpi), o leitor de produção dá 0,91 % de erro por caractere ponderado. O 1,59 % de
2026-09-26, que este arquivo citava, é de outro corpus e de outra régua de alinhamento: os
dois números não se comparam. O livro nascido digital de Dvoretsky saía pela camada de texto em 815 de 816 páginas, com
1.273 diagramas exatos; o tabuleiro inteiro acertava 92,5 % no corpus de diagramas. Como
cada número foi obtido, e com que script, está em
[docs/ROADMAP_IMPLEMENTACAO_OCR.md](docs/ROADMAP_IMPLEMENTACAO_OCR.md).

## Onde está o quê

| Pasta | O que há |
|---|---|
| `appy.py` | A entrada: a janela principal ou, com `--editor`, o editor de livros |
| `core/` | O domínio: `livro.py` (o leitor da página), `pdf_nativo.py` (a camada do PDF), `diagrama.py` (o tabuleiro), `exportar.py`, os módulos `editorial_*` (o documento editorial), `lexico.py`, `notacao.py` |
| `core/services/` | As fachadas que a interface chama: boxes, OCR, aprendizado, PDF, tarefas em segundo plano |
| `core/editor/` | O editor de livros sem Tk: modelo, dialeto XHTML, EPUB, DOCX, HTML, PDF, PGN, ortografia, tipografia |
| `ui/`, `ui/editor/` | As janelas Tkinter: a principal e os diálogos; a janela de edição e os seus painéis |
| `config/` | Caminhos persistentes (`paths.py`) e preferências (`settings.py`) |
| `scripts/` | Os instrumentos: A/B de leitura, rodada do corpus, benchmark, treino, pacote de modelo, bundle |
| `tests/` | A suíte; `conftest.py` cria uma raiz Tk para todos e isola a pasta de dados |
| `assets/`, `fonts/`, `pieces/`, `core/dados/` | Fontes de xadrez e símbolos, léxicos, figuras das peças, os dois modelos pequenos de diagrama |
| `benchmarks/`, `Box/`, `training_data_*` | O corpus de referência, as páginas rotuladas à mão, as bases de treino conferidas |
| `scripts/medidas/` | Medições de uma fase cada, rodadas à mão da raiz do projeto (`python scripts/medidas/medir_cadeia.py --regua`) |

## Documentos

- [CONTEXT.md](CONTEXT.md): o vocabulário e as vinte invariantes do produto.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): as camadas, o caminho de produção e as fronteiras.
- [docs/SPEC.md](docs/SPEC.md), [docs/SPEC_OCR.md](docs/SPEC_OCR.md),
  [docs/SPEC_IMPLEMENTACAO_OCR.md](docs/SPEC_IMPLEMENTACAO_OCR.md),
  [docs/SPEC_EDITOR.md](docs/SPEC_EDITOR.md): as especificações.
- [ROADMAP.md](ROADMAP.md) (fases F), [docs/ROADMAP_EDITOR.md](docs/ROADMAP_EDITOR.md) (ED),
  [docs/ROADMAP_PENDENCIAS.md](docs/ROADMAP_PENDENCIAS.md) (PD),
  [docs/ROADMAP_IMPLEMENTACAO_OCR.md](docs/ROADMAP_IMPLEMENTACAO_OCR.md): o que cada fase entregou e mediu.
- [docs/REVISAO_MODOS_OCR.md](docs/REVISAO_MODOS_OCR.md): a revisão de 2026-09-18 dos modos de leitura.
- [docs/OPERATIONS.md](docs/OPERATIONS.md): o gate de release, o cache, o bundle, os dados do usuário.
- [docs/ANALISE_GERAL_2026-10-06.md](docs/ANALISE_GERAL_2026-10-06.md): o estado da base e o que fazer.
- [docs/SPEC_REVISAO_GERAL_2.md](docs/SPEC_REVISAO_GERAL_2.md) (R) e
  [docs/ROADMAP_REVISAO_GERAL_2.md](docs/ROADMAP_REVISAO_GERAL_2.md) (RG): a revisão geral
  2, de 2026-11-20 a 2026-11-25 — os defeitos achados, o veredito do crítico e o que cada
  fase fez e mediu.
- [CLAUDE.md](CLAUDE.md): as regras para quem (ou o que) trabalha neste repositório.
