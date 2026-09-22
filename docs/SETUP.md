# Instalação e validação

## Ambiente recomendado

Use Python 3.11 ou 3.12. O projeto declara compatibilidade de 3.10 a 3.13,
mas PyTorch e EasyOCR precisam ser instalados de acordo com a plataforma e,
quando aplicável, com o suporte de GPU desejado.

Sempre use o mesmo interpretador para instalar e executar:

```text
python -m pip --version
python --version
```

## Instalação básica

```text
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e .
```

## Instalação completa

```text
python -m pip install -e ".[all]"
```

Para gerar e instalar um wheel independente do diretório do repositório:

```text
python -m pip install build
python -m build
python -m pip install dist/pyboxeditor-*.whl
```

O wheel inclui fontes, léxico e modelos pequenos de diagramas versionados.

Após gerar o wheel, valide a instalação mínima com:

```text
python scripts/smoke_release.py dist/pyboxeditor-*.whl
```

Pesos treinados devem ser distribuídos como pacote verificável por
`scripts/empacotar_modelo.py`, nunca apenas como um arquivo solto sem manifesto.

O Tesseract continua sendo um executável externo e precisa estar instalado no
sistema quando o caminho Tesseract for usado.

## PaddleOCR (opcional)

O reconhecimento por PaddleOCR usa o módulo `TextRecognition` e não substitui
automaticamente a cadeia neural/k-NN/EasyOCR já calibrada. Para habilitá-lo:

```text
python -m pip install -e ".[paddle]"
```

Depois, use **Ferramentas → Preencher caracteres (PaddleOCR)**. A primeira
execução pode baixar os modelos do PaddlePaddle.

## Diagnóstico

```text
python scripts/diagnostico_ambiente.py
```

## Verificações locais

```text
python -m compileall -q appy.py core ui config scripts
python -m ruff check core ui appy.py config scripts
python -m pytest --collect-only -q
python -m pytest -q -m "not ml and not gui"
```

Os testes `ml` exigem PyTorch/modelos e os testes `gui` exigem um display
Tkinter. O CI executa a parcela determinística sem GUI nem ML como verificação
obrigatória.
