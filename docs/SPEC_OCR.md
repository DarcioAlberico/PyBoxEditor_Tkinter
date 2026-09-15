# Especificação — OCR de texto geral

Versão: 1.0  
Data: 2026-09-10  
Status: proposta de implementação  
Roadmap: [`ROADMAP_OCR.md`](ROADMAP_OCR.md)

## 1. Escopo

Este documento especifica a evolução do OCR para texto corrido, mantendo a
compatibilidade com o editor de boxes, a substituição de glifos, a notação de
xadrez, diagramas e a exportação de PDF.

Incluído:

- pré-processamento adaptativo;
- análise de layout;
- linhas, palavras e parágrafos;
- reconhecimento híbrido;
- PaddleOCR, EasyOCR e Tesseract como adapters opcionais;
- fusão de hipóteses;
- decodificação linguística;
- suspeitas e revisão;
- active learning;
- métricas de OCR;
- PDF pesquisável e exportações estruturadas.

Fora do escopo inicial:

- promessa de equivalência universal a ABBYY ou Acrobat;
- treinamento de um modelo gigante end-to-end;
- correção silenciosa de texto sem preservar o original;
- dependência obrigatória de GPU ou internet.

## 2. Princípios de projeto

1. **Imagem original é imutável.** Todo processamento gera derivados.
2. **Toda hipótese é rastreável.** O resultado final guarda origem e confiança.
3. **Engines opcionais são isolados.** Falha do PaddleOCR, EasyOCR ou Tesseract não
   pode quebrar o fluxo principal.
4. **O contexto complementa o visual.** Nunca deve apagar a evidência visual sem
   registrar a decisão.
5. **Métricas precedem otimização.** Nenhuma mudança será considerada melhoria sem
   comparação no corpus fixo.
6. **Domínios diferentes usam regras diferentes.** Prosa, notação, diagramas e
   títulos não devem ser tratados como um único tipo de texto.
7. **Revisão humana é parte do produto.** Casos difíceis devem ser localizáveis,
   corrigíveis e reaproveitáveis no treinamento.

## 3. Modelo de dados

### 3.1 `OCRHypothesis`

Representa uma possibilidade produzida por um engine.

```python
@dataclass
class OCRHypothesis:
    text: str
    confidence: float
    source: str
    bbox: tuple[int, int, int, int] | None = None
    alternatives: list[str] = field(default_factory=list)
    model_version: str = ""
    preprocessing: str = "original"
    metadata: dict[str, object] = field(default_factory=dict)
```

Valores esperados para `source`:

```text
neural | learner | easyocr | paddleocr | tesseract | line | manual | fused
```

### 3.2 `GlyphResult`

Representa um glifo detectado ou rotulado.

Campos obrigatórios:

- identificador;
- bounding box;
- texto principal;
- confiança;
- hipóteses alternativas;
- linha e palavra associadas;
- fonte do resultado;
- flag de suspeita.

### 3.3 `WordResult`

```python
@dataclass
class WordResult:
    text: str
    confidence: float
    bbox: tuple[int, int, int, int]
    glyph_ids: list[str]
    line_id: str
    source: str
    alternatives: list[OCRHypothesis]
    warnings: list[str]
    original_text: str | None = None
```

`original_text` deve ser preenchido quando o decodificador alterar o texto
visualmente reconhecido.

### 3.4 `LineResult`, `RegionResult` e `PageResult`

Cada nível deve conter:

- texto concatenado;
- bounding box;
- confiança agregada;
- filhos ordenados;
- tipo semântico;
- hipóteses;
- avisos;
- metadados de processamento.

Tipos de região:

```text
body | heading | header | footer | caption | table | diagram |
notation | sidebar | quote | unknown
```

## 4. Pipeline funcional

### 4.1 Entrada

Entradas aceitas:

- imagem raster;
- página de PDF;
- documento com múltiplas páginas;
- recorte selecionado pelo usuário.

Parâmetros:

- idioma;
- modo de domínio;
- DPI desejado;
- engines habilitados;
- nível de diagnóstico;
- geração de PDF pesquisável;
- revisão automática ou manual.

### 4.2 Pré-processamento

Interface proposta:

```python
class Preprocessor(Protocol):
    def generate_variants(
        self, image: ImageLike, config: PreprocessConfig
    ) -> list[ImageVariant]: ...

    def select_best(
        self, variants: list[ImageVariant], evidence: PageEvidence
    ) -> ImageVariant: ...
```

Nenhuma transformação deve substituir a imagem original.

### 4.3 Layout

Interface proposta:

```python
class LayoutAnalyzer(Protocol):
    def analyze(self, image: ImageLike) -> PageLayout: ...
```

O resultado deve conter regiões ordenadas e relações de continuação entre blocos.

### 4.4 Linhas e palavras

O agrupamento deve usar combinação de:

- sobreposição vertical;
- linha de base;
- altura relativa;
- distância horizontal;
- espaços estimados;
- região de layout;
- orientação do texto.

O algoritmo deve preservar caracteres que cruzam a fronteira entre linhas e permitir
reprocessamento local sem refazer a página inteira.

### 4.5 Reconhecimento

Adapter comum:

```python
class OCRReader(Protocol):
    name: str

    def recognize_line(
        self, image: ImageLike, *, language: str, config: OCRConfig
    ) -> OCRHypothesis: ...

    def recognize_word(
        self, image: ImageLike, *, language: str, config: OCRConfig
    ) -> OCRHypothesis: ...
```

Características:

- carregamento lazy;
- cache por configuração;
- timeout ou cancelamento;
- erro encapsulado como resultado de engine indisponível;
- nenhuma importação obrigatória de dependência opcional na inicialização da UI.

## 5. Fusão e decisão

### 5.1 Pontuação

A pontuação final de uma hipótese deve combinar:

```text
score_visual
score_engine
score_geometrico
score_linguistico
score_dominio
score_consenso
```

Os pesos devem ser configuráveis e calibrados no benchmark, não definidos apenas
por julgamento visual.

### 5.2 Regras de segurança

- Uma palavra válida não deve ser alterada apenas por baixa frequência.
- Correção contextual deve manter `original_text`.
- Hipótese com baixa confiança deve ser marcada, não descartada.
- Divergência entre engines deve gerar aviso.
- O resultado manual possui precedência sobre qualquer reprocessamento automático,
  salvo solicitação explícita do usuário.

### 5.3 Decodificador

Implementação inicial recomendada:

1. gerar até `N` alternativas por glifo;
2. formar candidatos de palavra;
3. descartar combinações geometricamente impossíveis;
4. pontuar pelo dicionário e idioma;
5. aplicar beam search;
6. validar regras de domínio;
7. emitir resultado e alternativas.

## 6. Benchmark e métricas

### 6.1 Corpus

O corpus deve conter páginas por classe de dificuldade e ser dividido por documento:

- treino;
- validação;
- teste final intocado.

Recortes do mesmo livro não podem aparecer simultaneamente em treino e teste quando
isso permitir vazamento de fonte ou layout.

### 6.2 Métricas obrigatórias

- CER normalizado;
- WER normalizado;
- precisão, recall e F1 de caixas;
- acerto exato de linha;
- acerto exato de parágrafo;
- ordem de leitura;
- regiões corretamente classificadas;
- caracteres inseridos, removidos e substituídos;
- suspeitas corretas e incorretas;
- latência e memória.

O relatório deve separar pelo menos `prosa`, `notacao`, `titulo`, `tabela` e
`diagrama`.

## 7. Suspeitas e revisão

Uma palavra deve ser marcada quando ocorrer qualquer condição:

- confiança abaixo do limite;
- engines discordantes;
- palavra fora do dicionário;
- baixa pontuação linguística;
- geometria anormal;
- caracteres improváveis para o idioma;
- conflito com regras de notação.

A revisão deve oferecer imagem, texto, alternativas e motivo. A correção do usuário
deve ser armazenada como evento:

```python
CorrectionEvent(
    page_id=..., word_id=..., before=..., after=...,
    source_image=..., accepted_at=..., user=...
)
```

## 8. Exportação

### Texto simples

Deve respeitar ordem de leitura, parágrafos, espaços e quebras de linha.

### JSON

Deve conter a árvore completa:

```text
page -> region -> line -> word -> glyph -> hypotheses
```

### PDF pesquisável

- manter imagem original;
- adicionar camada invisível de texto;
- preservar coordenadas;
- permitir seleção e busca;
- incluir metadados de engine e versão;
- nunca descartar o texto original sem registrar a transformação.

## 9. Testes

### Unitários

- normalização de hipóteses;
- agrupamento de linhas;
- agrupamento de palavras;
- ordenação de regiões;
- fusão de scores;
- beam search;
- dicionários;
- suspeitas;
- serialização;
- adapters de engines.

### Integração

- página simples;
- duas colunas;
- texto inclinado;
- texto negativo;
- texto sobre trama;
- baixa resolução;
- notação de xadrez;
- diagrama;
- cabeçalho e rodapé;
- PDF pesquisável.

### Não regressão

Cada alteração deve comparar CER, WER, F1, tempo e memória com a baseline. Uma
melhoria em uma página isolada não é suficiente para aprovar a alteração.

## 10. Configuração inicial

Exemplo conceitual:

```toml
[ocr]
language = "auto"
domain = "auto"
enable_paddle = true
enable_easyocr = true
enable_tesseract = true
confidence_threshold = 0.75
suspect_threshold = 0.60
max_hypotheses = 5
diagnostics = false
preserve_original = true

[ocr.layout]
detect_columns = true
detect_headers = true
detect_footers = true
detect_tables = true

[ocr.output]
searchable_pdf = true
include_metadata = true
include_suspects = true
```

## 11. Definição de pronto

Uma fase está pronta somente quando:

1. o código está implementado;
2. os testes unitários e de integração passam;
3. o benchmark foi executado;
4. não houve regressão além do limite acordado;
5. a documentação foi atualizada;
6. os resultados podem ser reproduzidos;
7. casos de erro e dependências opcionais foram tratados.

## 12. Política de roteamento por domínio

O reconhecimento não deve usar um único engine para toda a página.

| Região | Caminho principal | Caminho de validação |
|---|---|---|
| `body` | OCR de linha | glifos próprios |
| `heading` | OCR de linha | glifos próprios |
| `caption` | OCR de linha | glifos próprios |
| `quote` | OCR de linha | glifos próprios |
| `notation` | glifos próprios + regras de xadrez | OCR de linha como hipótese |
| `symbol` | classificador próprio | engines externos |
| `diagram` | detector/FEN/recorte | nenhum OCR de prosa |
| `table` | células/linhas por região | OCR de linha local |
| `unknown` | glifos próprios | OCR de linha sob baixa confiança |

O resultado do roteamento deve ser persistido:

```python
RoutingDecision(
    domain="prose",
    primary="line",
    fallback="glyph",
    reason="region_type=body",
    confidence=0.90,
)
```

## 13. Contrato do OCR de linha híbrido

```python
class HybridLineReader(Protocol):
    def recognize(
        self,
        image,
        glyph_hypotheses: Sequence[Sequence[OCRHypothesis]],
        *,
        domain: str,
    ) -> LineResult: ...
```

Regras obrigatórias:

1. A leitura por glifo é a âncora geométrica.
2. A leitura por linha fornece contexto e alternativas.
3. O texto de linha é alinhado por edição, não distribuído por largura ingênua.
4. Inserções e remoções não deslocam silenciosamente os glifos seguintes.
5. Confiança de linha não é copiada cegamente para cada caractere.
6. Divergência acima do limite gera `line_glyph_disagreement`.
7. Região de notação não pode ser substituída por uma linha sem validação de
   legalidade ou padrão de domínio.

## 14. Métricas de decisão

Toda comparação A/B deve apresentar, no mínimo:

- CER/WER da prosa;
- CER/WER da notação;
- acerto de glifos;
- acerto de linhas;
- ordem de leitura;
- quantidade de divergências linha/glifo;
- palavras suspeitas corretas e falsas;
- tempo por etapa;
- memória de pico;
- quantidade de páginas processadas por cache.

Uma alteração só pode ser promovida se:

- melhorar prosa no holdout;
- não reduzir a qualidade de glifos/notação;
- não aumentar falsos positivos acima do limite definido;
- manter exportação e ordem de leitura;
- possuir fallback funcional quando engine opcional estiver ausente.

## 15. Política de dados e treinamento

- Separar datasets por livro/documento.
- Nunca usar recortes da mesma linha em treino e teste final.
- Guardar imagem, transcrição, fonte, DPI, transformação e origem.
- Correções manuais entram como dados somente após confirmação explícita.
- O texto original e a correção devem permanecer disponíveis para auditoria.
- Dados sintéticos devem variar fonte, escala, blur, ruído, contraste, rotação,
  compressão e fundo.

## 16. Política de exportação após OCR híbrido

- EPUB/DOCX usam parágrafos reconstruídos e ordem de layout.
- Notação e símbolos preservam o texto normalizado do domínio.
- PDF pesquisável mantém a imagem original e insere a camada invisível por
  palavra/linha.
- Suspeitas são exportadas como metadados, nunca como texto corrigido silencioso.
- Toda saída registra versão do pipeline, modelo, idioma, DPI e configuração.

## 17. Plano de validação das páginas 30–31

As páginas 30 e 31 do livro Aagaard — Calculation são o primeiro caso de
regressão real. Devem ser processadas em três modos:

1. pipeline atual por glifo;
2. OCR de linha;
3. pipeline híbrido roteado.

O resultado deve ser comparado por transcrição manual e conferência visual do
DOCX/EPUB. O fato de os glifos já terem sido conferidos sem erros é uma condição
de proteção: nenhuma melhoria de prosa pode quebrar esse resultado.

## 18. Contratos implementados OCR-11 a OCR-13

`comparar_modos` recebe casos imutáveis (`ABCase`) e dois callbacks. Ambos recebem exatamente a mesma entrada; erro de callback interrompe o benchmark para impedir comparação com populações diferentes. O relatório (`ABReport`) expõe resultados agregados, delta CER/WER, indicação de melhoria e JSON.

`HybridOCRPipeline.read_line` primeiro calcula a âncora de glifos. Para regiões de prosa, tenta a faixa completa e conserva espaços; para `notation` e `symbol`, a saída é exclusivamente a âncora de glifos. Exceções ou recortes inválidos no caminho de linha geram warning e não apagam a leitura de glifos.

`ContextDecoder` só altera palavra desconhecida quando existe candidata no vocabulário dentro da distância máxima e com ganho mínimo configurável. A leitura anterior fica em `original_text`, e cada troca fica em `context_corrections`, permitindo auditoria e desfazer.

## 19. Contrato da fusão por palavra (produção)

`livro.extrair_pagina(..., ler_pagina, fusao="palavra")` lê a página inteira
uma vez pelo motor contextual (`OCRService.tesseract_pagina_detalhada_conf`,
que devolve linhas com as palavras e as caixas delas) e, linha a linha:

1. lê a âncora pela cadeia própria (`_texto_da_linha`), um item por box;
2. classifica o domínio da linha pelos tokens da âncora
   (`_dominio_da_linha`) e pede a decisão ao `OCRRouter` — a linha só de
   notação fica com a âncora e não paga o motor;
3. casa o registro do motor pela geometria (`_casar_linha_ocr`) e o aceita só
   com semelhança de letras e dígitos ≥ 0,5 (`_semelhanca_de_linha`); o
   rejeitado não é consumido;
4. funde (`_fundir_por_palavra`): token com forma de lance
   (`notacao.e_token_de_notacao`) fica; token de prosa é trocado pelas
   palavras do motor no mesmo lugar em x, com confiança ≥ 0,5 e dentro da
   faixa vertical da linha; a palavra do motor que toca um lance é do lance;
5. corrige a prosa (`_corrigir_prosa_contextual`) pulando o lance;
6. registra em `PaginaExtraida.roteamento` domínio, leitor principal, motivo,
   fonte do texto (`glyph`/`fusao`/`line`), âncora, linha do motor,
   confiança, semelhança e as contas da fusão.

`fusao="linha"` conserva o modo anterior (linha inteira do motor, figurinas
repostas por coordenada) para o A/B; sem `ler_pagina` a página é só da cadeia.
`ocr_ab.medir_por_dominio` mede prosa e notação em separado.
