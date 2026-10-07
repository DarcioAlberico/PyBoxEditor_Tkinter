"""A biblioteca de inspeção: o que não é o caminho de produção, num lugar com nome.

O leitor de produção é `core/livro.py` (com `pdf_nativo.py` e `diagrama.py`), e a fachada
editorial de produção nasce de `core.editorial_legacy.pipeline_de_producao`. O que está
aqui é o resto das Fases 3 e 4 do OCR editorial, que a revisão de 2026-09-18 rebaixou a
biblioteca (`docs/REVISAO_MODOS_OCR.md` §4.11; a tabela de quem chama cada peça e por que
não é produção está em `docs/ROADMAP_IMPLEMENTACAO_OCR.md`, "A biblioteca"):

- `ocr_phase3`: `Phase3Processor`, `FusionEngine`, `NotationParser`, `align_text` e os
  adapters de linha — a fusão é por linha inteira, e a linha destes livros é mista;
- `ocr_phase4`: `DiagramProcessor`, `resolve_position`, `Phase4Processor` — um segundo
  resolvedor de posição, sem o porteiro, a orientação e o redesenho de `core/diagrama.py`;
- `ocr_layout`: `LayoutAnalyzer` — só `EditorialPipeline._raster_specs` o usa, numa página
  sem camada de texto;
- `abbyy_ocr`: a integração opcional com o FineReader instalado, que ninguém chama.

A fachada sem leitor atravessa esta biblioteca — é o caminho do `inspect`, dos testes das
fases e da comparação de motores por script (`processar_editorial.py --biblioteca`). Produto
novo não se liga aqui (item 4 da `docs/ANALISE_GERAL_2026-10-06.md`); `ocr_structure`, que
só o teste alcançava, foi apagado quando o pacote nasceu.
"""
