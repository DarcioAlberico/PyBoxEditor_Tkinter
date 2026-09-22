# Spec de implementação — OCR editorial especializado em xadrez

Status: proposta técnica.  
Escopo: evolução do programa atual sem quebrar os formatos `.box`, o editor de
glifos, o treino existente ou a exportação histórica durante a migração.

Implementação atual: as Fases 0, 1, 2, 3 e 4 desta spec estão disponíveis em
`core/ocr_corpus.py`, `core/editorial_model.py` e
`core/editorial_adapters.py`, com a fachada de produção em
`core/editorial_pipeline.py` e o módulo de reconhecimento/fusão em
`core/ocr_phase3.py`; diagramas são tratados por `core/ocr_phase4.py`. O caminho histórico pode ser usado pela opção
`legacy_extractor` durante a migração.

## 1. Contrato externo

O produto deve expor uma fachada profunda e pequena:

```python
class EditorialPipeline:
    def inspect(self, source: DocumentSource) -> InspectionReport: ...
    def process(self, source: DocumentSource, options: ProcessOptions,
                cancellation: CancellationToken | None = None) -> EditorialDocument: ...
    def apply(self, document: EditorialDocument, event: ReviewEvent) -> EditorialDocument: ...
    def export(self, document: EditorialDocument, target: ExportTarget,
               options: ExportOptions) -> ExportReport: ...
```

Invariantes da interface:

- `source` é somente leitura;
- `process` devolve evidência, hipóteses, decisões e suspeitas;
- `apply` não altera o documento-fonte nem remove hipóteses;
- `export` consome o mesmo `EditorialDocument` para qualquer formato;
- cancelamento é cooperativo e deixa um checkpoint retomável;
- falha de engine opcional vira diagnóstico no resultado, não crash silencioso.

## 2. Modelo editorial

O IR deve ser independente de Tkinter, PyMuPDF, Tesseract, Torch e
`python-docx`.

```python
@dataclass(frozen=True)
class SourceRef:
    document_id: str
    page_index: int
    bbox: tuple[int, int, int, int] | None
    image_hash: str
    source_kind: str  # raster | pdf_text | manual | derived

@dataclass
class Evidence:
    ref: SourceRef
    observed_text: str = ""
    alternatives: list[Hypothesis] = field(default_factory=list)
    engine: str = ""
    model_version: str = ""
    confidence: float = 0.0
    preprocessing: str = "original"
    diagnostics: list[str] = field(default_factory=list)

@dataclass
class Decision:
    value: object
    evidence_ids: list[str]
    status: str  # automatic | reviewed | rejected | unresolved
    reason_codes: list[str]
    original_value: object | None = None

@dataclass
class EditorialBlock:
    id: str
    kind: str
    order: int
    source_refs: list[SourceRef]
    decision: Decision
    children: list[str] = field(default_factory=list)
    style: dict[str, object] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
```

Blocos mínimos: `paragraph`, `heading`, `caption`, `chess_sequence`,
`diagram`, `table`, `header`, `footer`, `page_break`, `unknown`.

O resultado da página deve manter também `glyphs`, `words`, `lines`, `regions`
e hipóteses de engine para inspeção detalhada. O IR não deve reduzir tudo a uma
string antes da exportação.

### Versionamento

O JSON deve conter:

```json
{
  "schema": "editorial-document/v1",
  "pipeline_version": "...",
  "source_sha256": "...",
  "model_manifest": "...",
  "pages": [],
  "review_events": []
}
```

Migrações de schema devem ser explícitas; um JSON antigo não pode ser aceito
como se tivesse a mesma semântica.

## 3. Ingestão e evidência

### 3.1 PDF nativo

1. calcular hash do arquivo e página;
2. extrair `page.get_text("dict")` quando disponível;
3. preservar spans, fonte, tamanho, flags, bbox e ordem original;
4. mapear fontes de xadrez para Unicode sem perder o código original;
5. renderizar a imagem somente para regiões ausentes, conflitantes ou para
   validação visual;
6. marcar a camada textual como hipótese, não como verdade automática.

### 3.2 Scan ou imagem

1. preservar bytes e dimensões;
2. gerar variantes sem sobrescrever a original;
3. guardar DPI real ou estimado;
4. registrar rotação, negativo, trama e correção de perspectiva;
5. reprocessar apenas a região alterada quando possível.

### 3.3 Cache

A chave deve incluir hash de entrada, versão de schema, versão de pipeline,
configuração normalizada, DPI, pré-processamento, engine, idioma e assinatura
criptográfica do modelo. Caminho/mtime podem ser metadados auxiliares, nunca a
única identidade do modelo.

## 4. Layout e ordem de leitura

`LayoutAnalyzer` deve devolver:

- regiões com papel semântico e confiança;
- linhas e colunas;
- relações de continuidade entre blocos;
- blocos que atravessam colunas;
- tabela e diagrama como áreas que consomem seus filhos;
- cabeçalho/rodapé com escopo de página ou capítulo;
- ordem linear e grafo de leitura para casos ambíguos.

### Heurísticas obrigatórias

- não tratar calha entre colunas como texto;
- não deixar caixas internas de tabela escaparem para a prosa;
- não reconhecer filetes como glifos;
- separar legenda do diagrama pela relação espacial;
- respeitar rotação de texto vertical;
- usar a camada PDF para confirmar ordem quando ela existir;
- emitir suspeita quando duas ordens tiverem pontuação próxima.

O algoritmo deve ser testado com duas colunas, cabeçalho spanning, rodapé,
tabela, painel sobre trama, diagrama com legenda e texto vertical.

## 5. Roteamento por domínio

```text
body/heading/caption/quote -> linha + camada PDF + léxico
notation                  -> glifo + linha + parser de xadrez
diagram                   -> detector de tabuleiro + classificador de casas
table                     -> grade/célula + linha local
header/footer             -> camada PDF ou linha com política própria
unknown                   -> múltiplas hipóteses, sempre suspeita
```

O `RoutingDecision` deve conter região, caminho primário, fallbacks, motivo,
versão da regra e custo esperado. A decisão deve ser serializada no relatório.

## 6. Reconhecimento e fusão

### Adapters

Cada adapter implementa uma interface pequena:

```python
class Recognizer(Protocol):
    name: str
    capabilities: frozenset[str]

    def recognize(self, crop: ImageLike, context: RecognitionContext
                  ) -> list[Hypothesis]: ...
```

Capabilities incluem `line`, `word`, `glyph`, `script`, `confidence` e
`coordinates`. Tesseract, EasyOCR, PaddleOCR, modelo CRNN/CTC e camada PDF são
adapters. O registry deve carregar sob demanda e declarar indisponibilidade.

### Fusão

O decisor deve combinar, com pesos calibrados:

- evidência visual;
- qualidade da caixa;
- confiança calibrada do engine;
- consenso entre engines;
- linguagem/lexicografia;
- domínio da região;
- legalidade da notação ou posição;
- compatibilidade de ordem e geometria.

Saída mínima:

```text
chosen, alternatives, calibrated_confidence, reason_codes,
original_text, warnings, evidence_ids
```

Regras de segurança:

- não aceitar palavra fora do léxico como erro por si só;
- não aceitar SAN só porque é legal se contradiz a imagem;
- não remover símbolo que não foi compreendido;
- não apagar caixa, espaço ou hífen sem evento de decisão;
- conflito entre fonte PDF e pixels vai para revisão.

## 7. Módulo de notação de xadrez

O parser deve normalizar sem destruir a grafia impressa:

- SAN, LAN, figurinas e variantes entre parênteses;
- números de lance, reticências, comentários e NAGs;
- captura, promoção, roque, xeque e mate;
- símbolos de avaliação e convenções editoriais;
- erros tipográficos prováveis como candidatos, não como correção imediata.

Para cada sequência, produzir:

- tokens originais;
- tokens normalizados;
- árvore de variantes;
- posição inicial/final quando determinável;
- erros de legalidade e ambiguidades;
- mapeamento token → região → evidência.

Um token “corrigido” só pode substituir o original após decisão automática com
regra explícita ou revisão humana, e sempre mantém `original_value`.

## 8. Módulo de diagramas

O objeto `Diagram` deve conter:

- bbox e imagem original do diagrama;
- orientação do tabuleiro;
- 64 casas com top-k de peça/cor/vazio;
- FEN candidato e confiança;
- lado a jogar, roque e en passant quando visíveis ou inferidos;
- coordenadas, setas, círculos, destaques e legenda;
- inconsistências legais;
- estado de revisão.

### Decisão

O modelo visual gera candidatos. As regras de xadrez filtram e ranqueiam, mas
não inventam peças ausentes. Se nenhuma posição atingir o limiar, o diagrama
fica `unresolved` e aparece na fila.

### Métricas

- acerto por casa;
- FEN exato;
- orientação exata;
- lado a jogar;
- detecção da bbox;
- associação da legenda;
- setas/destaques quando anotados.

## 9. Revisão humana

### Fila

Ordenar por impacto estimado:

```text
FEN incorreto > ordem de leitura > notação ilegal > palavra ambígua
> símbolo isolado > estilo/caixa
```

Desempates: baixa confiança calibrada, número de dependências downstream,
proximidade de capítulo e densidade de erros.

### Tela

Três áreas sincronizadas:

1. página original com overlay de regiões e seleção;
2. recorte ampliado e alternativas lado a lado;
3. documento editorial, motivo, confiança, efeitos e ações.

Comandos: aceitar, editar, rejeitar, adiar, aceitar semelhantes, desfazer,
abrir origem e saltar para próximo. Ações em lote exigem amostra e confirmação.

### Eventos

```python
ReviewEvent(
    event_id, document_id, page_id, target_id,
    before, after, status, reason_codes,
    user, created_at, model_version, source_refs
)
```

Eventos são append-only no arquivo de trabalho; o estado atual é uma projeção.
Isso permite undo, auditoria e reconstrução do dataset.

## 10. Documento editorial e exportadores

### HTML de referência

- HTML5 semântico;
- `lang`, headings hierárquicos e navegação por capítulo;
- âncoras `page-N` e `region-ID`;
- diagramas com imagem, FEN em `data-fen` e alt text;
- notação em elementos identificáveis por token;
- CSS responsivo para duas colunas, tabelas e diagramas;
- modo fiel, limpo e acessível;
- relatório de suspeitas opcional, nunca misturado ao texto limpo.

### EPUB

Derivar XHTML/CSS/recursos do HTML de referência. Validar EPUB 3, manifesto,
nav, fontes, MIME, idioma, alt text e links internos. O conteúdo não deve ser
reconstruído de `PageResult.text`.

### DOCX

Mapear blocos para estilos e runs:

- headings para estilos Heading;
- parágrafos preservando negrito/itálico e símbolos;
- `ChessSequence` com estilo de notação e texto acessível;
- `Diagram` como imagem, tabela ou fonte, conforme opção;
- `Table` como tabela real;
- notas de origem somente em modo auditável;
- propriedades de idioma e metadados do livro.

### PDF pesquisável

Manter a imagem original. Inserir camada invisível usando coordenadas de linha ou
palavra, fonte compatível, idioma e rotação. Registrar contagem de inseridos e
falhos, e gerar JSON de auditoria por página.

## 11. Benchmark e testes TDD

### Seams públicas a testar

1. `DocumentSource` → `PageEvidence`;
2. `LayoutAnalyzer` → `PageLayout`;
3. `Recognizer` → hipóteses;
4. roteador → `RoutingDecision`;
5. pipeline → `EditorialDocument`;
6. revisão → projeção atual + evento;
7. IR → cada exportador;
8. manifesto → métricas reproduzíveis.

Testes devem usar fontes de verdade independentes: transcrição anotada, FEN
conferido e arquivos exportados validados por parser/leitor. Não testar métodos
privados nem mocks da implementação interna.

### Gates

- unitários para contratos e regras;
- integração com PDFs reais representativos;
- aceitação de uma página completa por domínio;
- regressão de quatro páginas difíceis atuais;
- livro inteiro em amostra reduzida;
- XML/ZIP/EPUBCheck/DOCX reopen;
- comparação visual por renderização;
- benchmark com CER/WER, FEN, ordem, latência, memória e revisão humana.

### Critério quantitativo inicial

Os limiares finais devem vir da baseline congelada. Até lá, nenhuma mudança pode
ser chamada de melhoria sem:

- resultado agregado e por domínio;
- intervalo/variação por documento;
- contagem de páginas e caracteres;
- tempo e memória;
- lista de regressões exemplificadas;
- artefatos para reproduzir a rodada.

## 12. Migração do código atual

1. adicionar IR e adaptadores sem remover `PaginaExtraida`;
2. fazer `core/livro.py` produzir IR além do formato histórico;
3. mover decisões de texto para `EditorialPipeline`;
4. adaptar `core/exportar.py` para consumir IR;
5. manter `exportar` histórico como adapter até todos os testes migrarem;
6. extrair controllers de revisão da `MainWindow`;
7. empacotar modelos por manifesto e validar instalação limpa;
8. somente depois remover caminhos duplicados.

Cada passo deve ser uma fatia vertical com teste vermelho, implementação mínima,
teste verde e revisão de seam. Não fazer uma reescrita completa antes de existir
um resultado comparável.

## 13. Riscos e ADRs necessários

- escolha do IR e compatibilidade com o formato histórico;
- política para usar camada textual do PDF;
- limite entre correção automática e revisão;
- formato de pacote dos modelos grandes;
- biblioteca/adapter de parser SAN e variantes;
- representação de diagramas com setas e metadados;
- fidelidade versus reflow no EPUB/DOCX;
- política de benchmark comercial e licenciamento.

## 14. Não objetivos

- prometer perfeição em qualquer livro, idioma ou scan;
- substituir revisão editorial por uma pontuação de confiança;
- treinar um modelo gigante antes de fechar corpus e métricas;
- apagar o caminho histórico antes de haver paridade de saída;
- tratar uma posição legal como prova de que a leitura visual está correta.

## 15. Implementação das Fases 5 e 6

As seams previstas acima estão implementadas em `core/editorial_review.py` e
`core/editorial_export.py`. A Fase 5 fornece fila global priorizada por impacto,
projeção de eventos JSONL, retomada, ações individuais, lote confirmado e undo
append-only. A Fase 6 usa a mesma ordem do documento para HTML semântico,
EPUB3, DOCX e PDF pesquisável, com modos `faithful`, `clean` e `hybrid`.

O pipeline e `scripts/processar_editorial.py` aceitam `json`, `html`, `txt`,
`epub`, `docx` e `pdf`; a janela principal expõe a revisão editorial e atalhos
`A`, `E`, `R`, `D` e `U`. Os testes de contrato ficam em
`tests/test_editorial_review_phase5.py` e `tests/test_editorial_export_phase6.py`.

## 16. Implementacao da Fase 7

`core/ocr_phase7.py` concentra o seam de dados para correcoes confirmadas,
selecao ativa, split por livro/editor/fonte/layout, holdout real separado de
dados sinteticos, calibracao por dominio e confiabilidade. `WeightManifest`
registra checksum SHA-256, schema, pipeline, configuracao e dominios dos pesos;
`OCRTrainingSummary` pode publicar o manifesto produzido pelo treino.

O corpus derivado de correcoes e serializavel, versionado e verificavel. Nenhum
item sintetico entra no holdout real, e componentes que compartilham livro,
editor, fonte ou layout nao sao separados entre treino, validacao e teste.
`evaluate_holdout` registra a métrica antes/depois, delta, tamanho e decisão de
melhoria; uma rodada só é promovida quando melhora no holdout independente.

## 17. Implementação da Fase 8

`core/ocr_phase8.py` define o contrato semântico de cache, o orçamento de
recursos por engine, o pacote verificável de modelos, o smoke test de wheel e o
protocolo de benchmark. `compare_engines` executa runners próprios, ABBYY ou
Acrobat sobre os mesmos casos e registra CER/WER, latência, memória e custo de
revisão; a integração comercial é opcional e não altera o resultado quando um
runner não está instalado.

Os comandos `scripts/empacotar_modelo.py` e `scripts/smoke_release.py` tornam a
distribuição auditável. O runtime aplica `effective_workers` quando um limite de
memória é informado, e a chave do cache inclui versão de código, schema, modelo
e configuração.
