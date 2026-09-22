# Revisão geral — OCR editorial especializado em livros de xadrez

Data: 2026-09-17  
Escopo: estado atual do repositório, incluindo alterações locais presentes no
momento da auditoria.  
Documentos de implementação: [roadmap](ROADMAP_IMPLEMENTACAO_OCR.md) e
[spec](SPEC_IMPLEMENTACAO_OCR.md).

## Resultado executivo

O projeto tem uma base acima da média para um editor especializado: modelos
próprios para glifos e diagramas, reconhecimento híbrido, regras de notação,
léxico, revisão humana, exportação editorial, PDF pesquisável e 2.201 testes.
Ele ainda não pode ser declarado superior ao ABBYY FineReader ou Acrobat no
geral. Hoje a vantagem demonstrável é mais estreita e mais valiosa: preservar
figurinas, posições, FEN, tabelas e convenções de livros de xadrez.

O principal risco não é falta de mais um engine OCR. É haver dois caminhos de
produto: o pipeline novo (`PageResult`, layout, engines, fusão e runtime) e o
pipeline histórico de `core/livro.py`/`core/exportar.py`. A qualidade futura
depende de um documento editorial intermediário único e de uma decisão de
roteamento que seja realmente usada na produção.

## Evidência observada

- `python -m pytest -q`: **2201 passed, 1 skipped em 121,33 s**.
- Ruff e `compileall`: passaram.
- `python -m build --wheel --no-isolation`: passou.
- A suíte cobre muitos contratos, mas a validação editorial ponta a ponta ainda
  está concentrada em páginas e fixtures selecionadas.
- Os documentos existentes registram resultados muito diferentes por página:
  há amostras próximas de 0,71–2,50% CER total e uma página de tabela ainda em
  torno de 8,19%. Isso é progresso real, não evidência suficiente de
  superioridade comercial em um corpus inteiro.
- O wheel produzido inclui os modelos de diagrama em `core/dados`, mas os pesos
  de OCR de linha `text_line_model.pth` e os pesos neurais na raiz não são
  incluídos pelo `pyproject.toml`.
- `core/ocr_export.py` oferece JSON, DOCX e PDF pesquisável; EPUB e a exportação
  editorial histórica continuam em `core/exportar.py`, e HTML não é ainda um
  alvo de primeira classe do IR novo.

## Revisão 1 — arquitetura, domínio e manutenibilidade

### Pontos fortes

- `DocumentController`, `NavigationController` e `TaskController` já criam
  seams melhores entre estado, navegação e trabalho em segundo plano.
- `PageResult` e `OCRTrace` são bons contratos de rastreabilidade.
- Engines opcionais estão atrás de adapters e falhas individuais não derrubam o
  lote.
- O vocabulário do domínio está agora consolidado em [`CONTEXT.md`](../CONTEXT.md).

### Achados

1. **P0 — decisão duplicada**: `core/livro.py` ainda concentra reconhecimento,
   reconstrução editorial, tabelas e regras de fusão, enquanto o pipeline
   `ocr_layout`/`ocr_structure`/`ocr_hybrid` expõe outra árvore. O caller não tem
   uma interface única para “processar um documento”.
2. **P0 — exportadores divergentes**: o resultado em `PageResult` não é a mesma
   entrada de EPUB/HTML que o exportador de `PaginaExtraida` usa. Correções podem
   aparecer em um formato e faltar em outro.
3. **P1 — módulos rasos e monolíticos**: `ui/main_window.py`, `core/livro.py` e
   `core/services/box_service.py` têm milhares de linhas e misturam orquestração,
   política, estado e apresentação. São módulos profundos em comportamento, mas
   com interface pública grande e difícil de testar.
4. **P1 — configuração implícita**: idioma, caminho de pesos, DPI, engine,
   domínio e modo de exportação circulam como strings e defaults espalhados.
5. **P1 — proveniência incompleta**: o modelo guarda hipóteses e metadados, mas
   não tem uma entidade explícita de decisão/correção com versão, usuário,
   timestamp, motivo e vínculo de exportação.

### Direção recomendada

Criar um módulo profundo `EditorialPipeline` com uma interface pequena:

```python
result = pipeline.process(document_source, options, cancellation=token)
pipeline.review.apply(correction)
pipeline.export(result.document, target, export_options)
```

Internamente ele pode continuar usando adapters históricos por fases. A seam é o
documento editorial; os exportadores, a UI e os benchmarks deixam de conhecer
detalhes de `core/livro.py`.

## Revisão 2 — OCR, visão computacional e domínio do xadrez

### Pontos fortes

- A estratégia linha para prosa e glifo para notação é correta para o produto.
- `OCRHypothesis` preserva origem, confiança, alternativas e pré-processamento.
- Há treino de linhas, dados sintéticos, diagnóstico e revisão de amostras.
- A detecção de diagramas já incorpora ocupação, fontes, validação legal e
  edição manual.
- A regra mais importante está correta: contexto pode complementar a evidência,
  mas não deve apagar a leitura visual.

### Achados

1. **P0 — ground truth insuficiente para promessa global**: quatro páginas
   representativas ajudam a direcionar engenharia, mas não medem capítulos,
   editoras, fontes, idiomas, scans, tabelas e diagramas suficientes.
2. **P0 — risco de leakage**: o split deve ser por documento-fonte, não por
   recorte; linhas do mesmo livro compartilham fonte, ruído e layout.
3. **P0 — diagrama ainda precisa de métrica própria**: CER não captura FEN exato,
   cor/turno, casas vazias, orientação, coordenadas e setas.
4. **P1 — confiança não calibrada por domínio**: uma confiança de engine de prosa
   não é comparável diretamente com uma confiança de glifo de figurina ou com a
   legalidade de uma posição.
5. **P1 — decodificação deve ser conservadora**: legalidade de xadrez deve reduzir
   candidatos impossíveis, não “consertar” uma linha para uma partida plausível
   sem manter a forma original e a suspeita.
6. **P1 — layout novo ainda é simplificado**: `ocr_layout.py` detecta regiões por
   geometria, mas páginas com cabeçalho spanning, tabela, painel sobre trama,
   legenda junto de diagrama e duas colunas exigem uma decisão de ordem de
   leitura mais rica que a ordenação por coluna.

### Direção recomendada

Adotar reconhecimento em camadas:

1. extrair camada textual existente do PDF como uma hipótese adicional;
2. detectar regiões e seus papéis;
3. reconhecer por domínio;
4. gerar candidatos por engine e por caractere/token;
5. validar notação, posição e relações de diagrama;
6. calibrar confiança e formar a fila de revisão;
7. nunca substituir a evidência original.

## Revisão 3 — conversão editorial e fidelidade de saída

### Pontos fortes

- O exportador histórico já trata EPUB/DOCX, fontes de símbolos, tabelas,
  diagramas e metadados com muitos testes de regressão.
- O PDF pesquisável mantém a imagem original e adiciona camada invisível.
- Há validação estrutural de ZIP/XML e integração opcional com `epubcheck`.

### Achados

1. **P0 — falta de IR único**: DOCX/EPUB/HTML não podem reconstruir o livro a
   partir de strings diferentes e perder coordenadas, estilo, notação ou
   proveniência.
2. **P0 — HTML ainda não é contrato**: precisa de semântica, CSS, alt text/FEN,
   navegação, âncoras por página e modo acessível.
3. **P1 — PDF pesquisável por palavra é incompleto**: a camada deve carregar
   língua, fonte, baseline, direção, relação com região e relatório de itens que
   falharam.
4. **P1 — conversão não deve “embelezar” antes de revisar**: normalização de
   caixa, espaços, hífens e símbolos deve ser uma decisão editorial registrada,
   não um efeito colateral do escritor do formato.
5. **P1 — comparação visual ausente como gate**: validar XML/ZIP não garante que
   o livro exportado manteve ordem, diagramas e tabelas.

### Direção recomendada

Definir `EditorialDocument` com blocos tipados: `Paragraph`, `Heading`,
`ChessSequence`, `Diagram`, `Table`, `Caption`, `PageBreak`, `Header`, `Footer`
e `Unknown`. Todos os alvos devem consumir esse contrato. O HTML deve ser o
formato de referência legível e acessível; EPUB deriva dele; DOCX mapeia os
mesmos blocos; PDF usa imagem original mais camada e/ou composição revisada.

## Revisão 4 — interface e revisão humana

### Pontos fortes

- A aplicação já tem navegação, autosave, histórico, tarefas em background,
  filtros de confiança e diálogos para linhas e diagramas.
- A revisão de linha inteira é melhor para prosa que obrigar o usuário a corrigir
  centenas de glifos isolados.
- A paleta de símbolos e atalhos atendem ao vocabulário específico de xadrez.

### Achados

1. **P0 — a fila de revisão ainda não é o centro do produto**: revisão de linhas,
   boxes, diagramas e notação aparecem em fluxos separados, sem uma fila global
   de suspeitas ordenada por impacto.
2. **P0 — falta comparação de hipóteses**: o revisor precisa ver original,
   recorte, texto escolhido, alternativas, motivo e efeito na notação/FEN em uma
   única tela.
3. **P1 — `MainWindow` é uma seam ruim para UI**: handlers conhecem OCR,
   treinamento, exportação, persistência e detalhes de boxes; isso dificulta
   testes de fluxo sem display.
4. **P1 — confiança precisa de linguagem humana**: “0,62” não diz se é erro
   provável, divergência de engines, texto fora do léxico ou posição ilegal.
5. **P1 — revisão em lote precisa de guarda**: aceitar automaticamente correções
   de baixa ambiguidade deve mostrar amostra, contagem, reversibilidade e criar
   eventos de auditoria.

### Fluxo recomendado

`Importar → Diagnóstico → Processar → Revisar suspeitas → Validar notação/diagramas
→ Pré-visualizar saída → Exportar → Relatório`. A tela de revisão deve ser
   orientada por tarefa, com sincronização página/região/saída e atalhos para
   aceitar, rejeitar, editar, pular e voltar.

## Revisão 5 — qualidade, testes, operação e distribuição

### Pontos fortes

- A suíte é extensa, o Ruff está verde e o build é reproduzível no ambiente
  atual.
- Runtime já possui cache, cancelamento cooperativo, execução em lote e profiling.
- Há manifesto de benchmark e métricas CER/WER por página.

### Achados

1. **P0 — falta um gate de qualidade de livro**: a suíte passa sem provar que a
   saída de um livro inteiro possui ordem, FEN, sequência de lances e diagramas
   corretos.
2. **P0 — artefatos de modelo não têm release contract**: pesos usados pela UI
   ficam fora do wheel; instalar a aplicação em outra máquina pode produzir
   fallback silencioso ou falha tardia.
3. **P1 — cache não é claramente invalidado por versão semântica**: assinatura
   de caminho/tamanho/mtime é útil, mas precisa incluir versão do pipeline,
   código de normalização e schema do resultado.
4. **P1 — concorrência de engines pesadas**: workers paralelos podem duplicar
   leitores, memória e processos externos; o limite de memória precisa ser uma
   política efetiva, não apenas configuração.
5. **P1 — carregamento de pesos heterogêneo**: os caminhos neurais devem usar
   carregamento seguro, metadados compatíveis e checksum; `torch.load` sem
   política uniforme é risco operacional e de supply chain.
6. **P2 — benchmark comercial ainda não está protocolado**: comparar com ABBYY
   ou Acrobat exige mesma entrada, mesma resolução, mesma segmentação, idioma,
   pós-processamento equivalente e critérios publicados.

### Direção recomendada

Criar uma matriz de release por corpus e por alvo, com bloqueios objetivos:

- nenhuma regressão acima do limite por domínio;
- FEN exato e legalidade dentro do alvo acordado;
- leitura de colunas e blocos sem inversões;
- exportadores reimportáveis/validáveis;
- pesos e versões presentes no artefato instalado;
- trace e relatório de suspeitas reproduzíveis.

## Priorização consolidada

| Prioridade | Trabalho | Por que agora |
|---|---|---|
| P0 | IR editorial único | evita que cada formato tenha uma verdade diferente |
| P0 | Corpus fechado por documento + ground truth | transforma “parece melhor” em medição |
| P0 | Pipeline único de produção | impede que o caminho novo fique só em testes |
| P0 | Fila de revisão com proveniência | torna precisão prática e auditável |
| P0 | Empacotamento versionado de pesos | instala o mesmo sistema que foi medido |
| P1 | Diagrama/notação com métricas próprias | mede o diferencial de xadrez |
| P1 | HTML acessível como saída de referência | simplifica EPUB e inspeção visual |
| P1 | extração da camada textual do PDF | reduz OCR desnecessário e erros previsíveis |
| P1 | decomposição da UI e `core/livro.py` | melhora localidade e testabilidade |
| P2 | benchmark comercial publicado | posiciona o produto com honestidade |

## Critério para a promessa “superior”

Não usar uma afirmação genérica. A meta deve ser: “superior em livros de xadrez
no conjunto de métricas X, Y e Z, no corpus C, com revisão humana limitada a R”.
Só liberar essa mensagem quando o corpus de teste estiver congelado, o protocolo
for reproduzível e os resultados forem melhores que as baselines em pelo menos
três famílias de livro, sem regressão grave em outra família.
