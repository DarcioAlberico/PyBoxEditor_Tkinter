"""As medições de uma fase cada, rodadas à mão (item 8 da análise de 2026-10-06).

Até 2026-10-06 estes 42 scripts moravam na raiz do repositório: `medir_*.py` mede uma
fase do `ROADMAP.md` contra as páginas rotuladas; `gerar_*.py` fabrica as fontes de
diagrama e de símbolos e o PDF das classes; `importar_*.py`, `calibrar_modelo.py`,
`coletar_externo.py`, `treinar_diagrama.py`, `rodar_kraken.py` e `rodar_paddle.py` são
instrumentos de uma fase. Rodam da raiz do projeto, como antes — `python
scripts/medidas/medir_cadeia.py --regua` —, e os que leem dado pelo caminho relativo
continuam lendo de lá. O que mudou neles foi só a raiz (dois níveis acima) e os imports
entre si (`from scripts.medidas import …`). O `ruff` da CI passa a lê-los: as regras de
estilo E741, E702 e E731 ficam relaxadas aqui (`pyproject.toml`), as de erro (F) não.
"""
