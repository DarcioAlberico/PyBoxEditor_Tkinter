# Operação e release

## Dados do usuário

Configurações e falhas não são gravadas ao lado do código instalado. O caminho
é definido por `config.paths`:

- Windows: `%LOCALAPPDATA%\PyBoxEditor` (ou `%APPDATA%` como fallback);
- Linux/macOS: `$XDG_DATA_HOME/PyBoxEditor` ou `~/.local/share/PyBoxEditor`.

O `Settings.save()` escreve em arquivo temporário e faz substituição atômica,
evitando deixar JSON parcialmente escrito após uma interrupção.

## Diagnóstico

```text
python scripts/diagnostico_ambiente.py
```

Em uma falha fatal da interface, o relatório fica em `crash_log.txt` dentro do
diretório de dados do usuário. O caminho exato também aparece na mensagem de
erro.

## Gate de release

```text
python -m compileall -q appy.py core ui config scripts
python -m ruff check core ui appy.py config scripts
python -m pytest -q -p no:cacheprovider -o addopts="" -m "not slow"
python -m pytest -q -p no:cacheprovider -o addopts="" -m slow
python -m pip wheel . --no-deps --no-build-isolation -w dist
python scripts/smoke_release.py dist/pyboxeditor-0.1.0-py3-none-any.whl --editor
```

(`python -m build --wheel --no-isolation` também serve, com o pacote `build` instalado
— `pip install -e ".[dev]"` — e **fora** da raiz do repositório, ou depois de apagar a
pasta `build/` que o setuptools deixa: com ela na raiz, `python -m build` a importa como
pacote de namespace e falha com "No module named build.__main__".)

O CI executa os mesmos gates nos interpretadores suportados e verifica que o
wheel contém fontes, léxico e modelos pequenos de diagramas. Os testes `slow` (a
medição do editor, AC-005 e os de desempenho da ED-03/ED-04) ficam fora do gate
padrão e rodam à parte; `--editor` abre o editor de livros em subprocesso sobre um
livro sintético e exige que ele feche com código 0 sem carregar o OCR.

## Editor de livro

O editor (`appy.py --editor [arquivo] [--fechar-apos N] [--diagnostico-modulos]`, ou
Arquivo → Editor de livro… na janela principal) é a janela de edição em modo texto e
modo código sobre o mesmo livro, com a especificação em `docs/SPEC_EDITOR.md` e o
histórico das fases em `docs/ROADMAP_EDITOR.md`. O que ele lê e escreve: EPUB 3 (o
formato nativo), HTML/XHTML, TXT, DOCX (escrever sempre; ler sem `python-docx`), PDF
paginado (PyMuPDF), PGN e o JSON do documento editorial do OCR (a ponte da ED-11: salvar
grava os eventos no diário da revisão).

Dependências: Pillow, PyMuPDF e `chess` vêm em `requirements.txt`; `python-docx` só
para **escrever** DOCX (`pip install -e ".[docx]"`); `epubcheck` + Java para a validação
(`pip install -e ".[epub-validacao]"` — sem eles, a estrutura é conferida sem o
epubcheck e a caixa diz isso). As fontes de diagrama e de símbolos estão em `fonts/` e
`assets/fonts/`; a preferência de tela fica em `Settings.get("editor")`.

### Máquina de referência e orçamentos (AC-005, §13.1)

Máquina de referência: AMD Ryzen 5 3600 (6 núcleos), 16 GB, Windows 10 22H2, Python
3.13.2 (`.venv`), tema Tk `vista`. A medição roda com

```text
python scripts/medir_editor.py --livro
```

e produz a tabela do livro de 300 capítulos-página, 300 mil caracteres e 500 diagramas
(2026-09-21):

| Medida | Valor | Orçamento |
|---|---|---|
| abrir (Arquivo → Abrir) | 0,62 s | ≤ 3 s |
| abrir um capítulo | 0,07 s | ≤ 0,5 s |
| alternar o modo | 0,05 s | ≤ 1 s |
| buscar no livro inteiro | 0,01 s | ≤ 2 s |
| salvar como | 0,18 s | ≤ 5 s |
| RSS ao fim | 92 MB | ≤ 600 MB |

Os `assert` desses orçamentos estão em `tests/test_editor_ac_globais.py::test_ac005…`
(`slow`); os do capítulo de 20 páginas e da tabela 20×20 (tecla ≤ 50 ms, `dump` ≤ 100 ms,
tabela ≤ 1 s) em `tests/test_editor_desempenho.py`. Uma regressão acima do orçamento
entra no registro da fase (ED-13b) antes de qualquer release.

Roteiros manuais: `docs/roteiros/editor_teclado.md` (tudo pelo teclado, AC-006) e
`docs/roteiros/editor_docx.md` (o DOCX no Word e no LibreOffice).

## Fase 8: release e benchmark protocolado

Para empacotar pesos com manifesto e checksum:

```text
python scripts/empacotar_modelo.py text_line_model.pth -o dist/line-crnn.zip --model-id line-crnn --pipeline-version editorial-pipeline/v4
python scripts/smoke_release.py dist/pyboxeditor-0.1.0-py3-none-any.whl
```

Comparações com engines externos devem usar o mesmo manifesto de corpus, idioma,
DPI, pré-processamento e política de revisão. ABBYY e Acrobat são adapters
opcionais: ausência do executável deve ser registrada como indisponibilidade,
nunca como resultado vazio favorável ao nosso OCR.
