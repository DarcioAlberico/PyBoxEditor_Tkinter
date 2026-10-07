# Operação e release

## Dados do usuário

Configurações e falhas não são gravadas ao lado do código instalado. O caminho
é definido por `config.paths`:

- Windows: `%LOCALAPPDATA%\PyBoxEditor` (ou `%APPDATA%` como fallback);
- Linux/macOS: `$XDG_DATA_HOME/PyBoxEditor` ou `~/.local/share/PyBoxEditor`.

O `Settings.save()` escreve em arquivo temporário e faz substituição atômica,
evitando deixar JSON parcialmente escrito após uma interrupção. Antes, relê o
arquivo e aplica por cima só as chaves que aquela instância mudou: a janela
principal, o editor de livros e o `appy.py --editor` gravam o mesmo
`settings.json`, cada um com o seu `Settings`, e nenhum desfaz o que o outro
gravou — a não ser na mesma chave, em que vale a última gravação (as
preferências do editor são uma chave só, `editor`).

## Diagnóstico

```text
python scripts/diagnostico_ambiente.py
```

Em uma falha fatal da interface, o relatório fica em `crash_log.txt` dentro do
diretório de dados do usuário. O caminho exato também aparece na mensagem de
erro.

## Manutenção do cache OCR

O cache de páginas é identificado pelo conteúdo da entrada, configuração,
versão do pipeline e assinatura dos pesos. A poda é opt-in e ocorre antes do
processamento quando os limites são informados; arquivos temporários de uma
gravação interrompida não são removidos por essa rotina.

Para limitar idade e tamanho no leitor editorial:

```text
python scripts/processar_editorial.py livro.pdf -o saida.json \
  --cache-max-idade-horas 168 --cache-max-mb 2048
```

O relatório da poda fica em `metadata.cache_prune` do documento, com as
quantidades removidas e restantes e os bytes liberados. Sem essas opções o
cache continua sem poda automática.

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
python scripts/validar_documento_editorial.py documento-editorial.json \
  --exigir-resolvido -o documento-quality.json
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

O gate do documento confere o IR completo, a ordem de paginas e blocos, a
proveniencia, FENs, tabelas e sequencias que precisam carregar no
`python-chess`. `--exigir-resolvido` tambem bloqueia decisoes `unresolved`,
blocos marcados para revisao e motivos de alto impacto; avisos informativos
continuam registrados sem bloquear sozinhos. Nenhum problema e corrigido
silenciosamente.

No leitor de producao, o mesmo gate pode bloquear a exportacao antes de criar
qualquer arquivo:

```text
python scripts/processar_editorial.py livro.pdf -o saida.json \
  --validar-qualidade --exigir-resolvido
```

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
python scripts/empacotar_modelo.py text_line_model.pth \
  --meta text_line_model.json \
  --manifesto-pesos text_line_model.manifest.json \
  -o dist/line-crnn.zip --model-id line-crnn \
  --pipeline-version editorial-pipeline/v4 --exigir-portao \
  --exigir-proveniencia-dataset \
  --rodada-corpus benchmarks/rodadas/ultima.json --exigir-gate-corpus \
  --gate-editorial benchmarks/quality/ultima.json --exigir-gate-editorial
  python scripts/smoke_release.py dist/pyboxeditor-0.1.0-py3-none-any.whl
```

Comparações com engines externos devem usar o mesmo manifesto de corpus, idioma,
DPI, pré-processamento e política de revisão. ABBYY e Acrobat são adapters
opcionais: ausência do executável deve ser registrada como indisponibilidade,
nunca como resultado vazio favorável ao nosso OCR.
### Expansao segura do corpus

Antes de promover uma alteração do leitor, execute também o gate absoluto do
corpus com a mesma resolução do protocolo:

```text
python scripts/rodada_do_corpus.py --manifesto benchmarks/corpus_v2.json \
  --dpi 300 --max-cer-total 0.02 --max-cer-prosa 0.03 \
  --max-cer-notacao 0.03
```

Para um A/B entre engines ou modelos, informe o JSON exato do baseline com
`--comparar-com`. O comando confere o hash do corpus, grava o caminho e a
quantidade de páginas comparadas em `comparison` e inclui regressões de página
em `quality_gate.failures`:

```text
python scripts/rodada_do_corpus.py --manifesto benchmarks/corpus_v2.json \
  --comparar-com benchmarks/rodadas/corpus_v2_dpi300/2026-09-26-0119.json \
  --usar-ensemble --dpi 300
```

O resultado é arquivado mesmo quando reprova. `--exigir-cobertura` deve ser
usado apenas quando o corpus já tiver o número mínimo de páginas por família.

Uma pÃ¡gina cujo `reference` termina em `.json` pode trazer, alÃ©m de `text`,
`notation`, `diagrams` e `regions`. A rodada de produÃ§Ã£o projeta a saÃ­da do
`livro.extrair` para esses mesmos domÃ­nios e aplica os gates semÃ¢nticos no mesmo
artefato:

```text
python scripts/rodada_do_corpus.py --manifesto benchmarks/corpus_v2.json \
  --min-fen-exato 1.0 --min-notacao-legal 0.99 \
  --exigir-ordem-layout
```

Para manifestos estruturados, `scripts/benchmark_ocr.py` tambem aplica limites
semanticos de diagramas, notacao e ordem de layout:

```text
python scripts/benchmark_ocr.py benchmarks/manifest.json \
  --min-diagram-exact 1.0 --min-notation-legal 0.99 \
  --exigir-ordem-layout -o benchmarks/relatorio.json
```

CER textual igual nao aprova uma posicao FEN errada, uma sequencia ilegal ou
uma inversao de regioes.

A rodada tambem reprova falhas de integridade: PDF ou referencia ausente e
quantidade de paginas retornadas pelo extrator diferente da quantidade do
manifesto ficam registrados por pagina, nunca descartados silenciosamente.

A ampliacao do corpus ocorre em quatro comandos separados. A descoberta le as
paginas reais pelo mesmo `core.livro.extrair` da exportacao, mas grava somente
candidatos preliminares:

```text
python scripts/descobrir_candidatos_corpus.py livro.pdf \
  --documento aagaard --paginas 30 31 32 -o benchmarks/candidatos_aagaard.json
python scripts/planejar_corpus.py --rodada benchmarks/rodadas/ultima.json \
  --candidatos benchmarks/candidatos_aagaard.json benchmarks/candidatos_nunn.json \
  -o benchmarks/plano.json
python scripts/preparar_revisao_corpus.py --plano benchmarks/plano.json --output benchmarks/fila_revisao.json
```

O primeiro arquivo carrega sinais automaticos de layout e, quando informado,
rotulos declarados. Seu estado e sempre `unreviewed`; ele nao contem
`reference` nem `holdout`; tambem registra `page_index_base` e o SHA-256 do PDF
de origem. O segundo aceita varias filas, rejeita a mesma pagina fisica repetida,
cruza o resultado com o deficit por livro e familia e produz a fila deterministica
para revisao humana. `preparar_revisao_corpus.py` materializa status
`pending_review`, rascunho, roteamento e hash da fonte; nao cria referencia
nem holdout. Somente depois
da conferencia contra a imagem a transcricao pode ser promovida ao manifesto
oficial e ao fluxo da Fase 7.

A promoção exige um arquivo separado de revisões, por exemplo:

```json
{"revisoes": [{"id": "aagaard-p030", "documento": "aagaard",
  "page_index": 30, "reference": "referencia/aagaard-p030.txt",
  "familias": ["prosa", "notacao"], "principal": "notacao",
  "status": "reviewed", "revisor": "nome", "revisado_em": "2026-09-26T12:00:00Z"}]}
```

```text
python scripts/promover_corpus.py --manifesto benchmarks/corpus_v2.json \
  --revisoes benchmarks/revisoes.json --revisor "nome" \
  --candidatos benchmarks/candidatos_v2/aagaard_p32_p33.json benchmarks/candidatos_v2/nunn_p234_p236.json \
  --output benchmarks/corpus_v3.json
```

O comando valida o arquivo de referência, o documento, o índice e duplicatas,
grava auditoria no `metadata` da página e recalcula o SHA-256. O manifesto
original permanece intacto; só depois dessa promoção a rodada do corpus e a
preparação da Fase 7 podem consumir a página.

Com `--candidatos`, cada revisao precisa declarar `candidate_id` e
`source_pdf_sha256`. A promocao confere documento, pagina, estado `unreviewed`
e o hash atual do PDF; o resumo persistente fica em
`metadata.promotion_provenance`.

O fluxo operacional de revisao OCR-14 separa a quarentena da decisao humana.
Primeiro gere um mapa explicito `arquivo -> rotulo` (ou um JSON com
`revisoes`), depois materialize o artefato versionado:

```text
python scripts/revisar_ocr14.py preview_ocr/ocr14/relatorio.json \
  preview_ocr/ocr14/rotulos.json --revisor "nome" \
  -o preview_ocr/ocr14/relatorio-revisado.json
```

O comando exige, por padrao, um rotulo para cada recorte e rejeita arquivos que
nao pertencem ao relatorio. `--permitir-pendentes` existe apenas para uma
revisao parcial declarada; esse artefato fica com status `pending_review` e nao
deve ser promovido ao treino.

Para importar recortes OCR-14 revisados com verificacao fisica dos arquivos:

```text
python scripts/preparar_fase7.py ocr14 preview_ocr/ocr14/relatorio-revisado.json \
  --base-dir . --exigir-arquivos --exigir-proveniencia \
  -o benchmarks/ocr14-reviewed.json
```

`--exigir-arquivos` recusa caminho relativo fora do `--base-dir`, arquivo ausente
e registra o SHA-256 de cada recorte no dataset. Em uma importacao operacional,
acrescente `--exigir-registros` para falhar se o relatorio nao tiver nenhum
recorte confirmado; sem essas opcoes, a biblioteca continua disponivel para
inspecao de relatorios portateis.

`--exigir-proveniencia` confere os SHA-256 do relatorio de quarentena e do
arquivo de rotulos gravados pela revisao; se qualquer fonte mudou, a promocao
falha antes de criar o dataset.
O subcomando `split` tambem recusa datasets OCR-14 sem essa marca verificada,
evitando que um artefato montado fora do fluxo contorne o portao.

O treino de linhas tambem usa a fachada integrada da Fase 7:

```text
python scripts/treinar_ocr_linhas.py --dataset training_data_linhas \
  --holdout training_data_linhas_holdout \
  --versao-dataset correcoes-v3 --manifesto-pesos text_line_model.manifest.json \
  --exigir-portao
```

Esse comando encaminha o treino para `core.ocr_training.treinar_pacote`, que
grava lexico, estado, relatorio e manifesto ao lado do modelo. O modelo so e
aceito pela producao se passar posteriormente pelo portao de
`linha_trainer.modelo_utilizavel`.

Para calibrar a confianca por dominio, passe um dataset independente com
``--calibracao``. Ele nao pode ser o treino nem o holdout; o relatorio
``*_calibration.json`` e o SHA-256 entram no metadata e no manifesto de pesos.
O treinador tambem recusa imagens repetidas ou o mesmo grupo de origem
(``prefixo_linha``) atravessando treino, validacao, calibracao e holdout.
Para promover usando o split da Fase 7, passe ``--split-manifest`` e
``--exigir-split``; o schema, os grupos, o holdout e o SHA-256 sao verificados
antes de o pacote ser marcado como elegivel.
O vínculo físico é criado explicitamente, sem inferência de origem:
``python scripts/vincular_datasets_linhas.py split.json -o line-binding.json
--dataset train=... --dataset holdout=... --grupo grupo=item``; no treino,
use ``--line-binding --exigir-line-binding``.

Quando o treino incorpora correcoes OCR-14, acrescente
`--dataset-proveniencia benchmarks/ocr14-reviewed.json
--exigir-proveniencia-dataset`. O SHA-256 e o status da revisao entram no
metadata do modelo e podem ser exigidos no empacotamento com
`--exigir-proveniencia-dataset`.

`--holdout` e obrigatorio para a promocao de pacotes novos: a base deve ser
independente, revisada e nunca reutilizada no treino. Sem ele, o treino pode
gerar artefatos para inspecao, mas o estado fica reprovado no portao.

Na janela **Treinar OCR de linhas**, o mesmo contrato aparece antes do treino:
ela oferece a selecao do holdout real e, opcionalmente, de um dataset de
calibracao. Se o usuario optar por continuar sem holdout, o resultado fica
explicitamente marcado como experimental e a janela nao afirma que o modelo
sera usado automaticamente.

Quando o holdout de linhas vier de paginas de um manifesto de corpus, valide
tambem a ligacao fisica entre os recortes e as paginas antes do treino:

```text
python scripts/validar_holdout_corpus.py benchmarks/corpus_v2.json \
  --saida benchmarks/corpus_v2.selection.json \
  --dataset-linhas training_data_linhas_holdout
```

Esse dataset precisa conter `rec_gt.txt` e `provenance.json` com o schema
`pyboxeditor.ocr-line-holdout/v1`. Cada entrada de `lines` informa `image`,
`document_id`, `page_id`, `page_index`, `bbox` e `source_image_sha256`.
O hash da pagina e comparado ao corpus selecionado; sem essa ligacao,
`--holdout-proveniencia` nao permite promocao.

Os metadados do treino tambem guardam o SHA-256 do `.pth`, o fingerprint dos
pixels e rotulos do dataset e a lista deterministica da validacao. O portao
recusa um JSON mais antigo que o peso ou cujo hash nao corresponda; portanto,
copiar um `.pth` sem seu `.json` correspondente nunca promove silenciosamente
Para empacotar pesos com manifesto e checksum:

```text
python scripts/empacotar_modelo.py text_line_model.pth \
  --meta text_line_model.json \
  --manifesto-pesos text_line_model.manifest.json \
  -o dist/line-crnn.zip --model-id line-crnn \
  --pipeline-version editorial-pipeline/v4 --exigir-portao \
  --exigir-proveniencia-dataset \
  --rodada-corpus benchmarks/rodadas/ultima.json --exigir-gate-corpus \
  --gate-editorial benchmarks/quality/ultima.json --exigir-gate-editorial
  python scripts/smoke_release.py dist/pyboxeditor-0.1.0-py3-none-any.whl
```

Na caixa principal de exportaÃ§Ã£o, a opÃ§Ã£o **Combinar engines independentes**
ativa o mesmo consenso conservador do script: Tesseract, EasyOCR e PaddleOCR
sÃ£o consultados nas faixas de fallback; apenas duas fontes concordantes
substituem a leitura da cadeia prÃ³pria. Conflitos e engines indisponÃ­veis ficam
registrados na evidÃªncia e entram na fila de revisÃ£o.

Quando `--meta` referencia `dataset_provenance_path`, `calibration_report`,
`split_manifest`, `line_binding` ou `holdout_provenance`, o empacotador copia
essas evidências para `metadata/artifacts/` e registra seus SHA-256 em
`manifest.json`. Os caminhos originais continuam sendo a proveniência externa
dos datasets; o ZIP carrega as evidências verificáveis, não as imagens inteiras
do corpus. `ModelPackage.verify` confere também essa correspondência entre a
lista de evidências e os arquivos efetivamente declarados no pacote.

Comparações com engines externos devem usar o mesmo manifesto de corpus, idioma,
DPI, pré-processamento e política de revisão. ABBYY e Acrobat são adapters
opcionais: ausência do executável deve ser registrada como indisponibilidade,
nunca como resultado vazio favorável ao nosso OCR.
um modelo. `--avaliar` mede o arquivo atual, mas essa medicao nao reescreve a
proveniencia nem substitui um holdout revisado.

