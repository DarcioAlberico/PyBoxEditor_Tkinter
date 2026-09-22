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
python -m pytest -q
python -m build --wheel --no-isolation
```

O CI executa os mesmos gates nos interpretadores suportados e verifica que o
wheel contém fontes, léxico e modelos pequenos de diagramas.

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
