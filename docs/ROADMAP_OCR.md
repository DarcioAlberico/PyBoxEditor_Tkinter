# Roadmap — OCR de texto geral

Versão: 1.0  
Data: 2026-09-10  
Status: planejado  
Documento complementar a [`ROADMAP.md`](../ROADMAP.md) e [`SPEC_OCR.md`](SPEC_OCR.md)

## Objetivo

Evoluir o reconhecimento atual de glifos para um OCR completo de documentos, com
qualidade mensurável em texto corrido, preservação de layout, ordem de leitura,
revisão de suspeitas e aprendizado a partir das correções do usuário.

O classificador de glifos continuará sendo utilizado onde é mais forte: fontes
específicas, símbolos, notação de xadrez e validação de caracteres. O OCR de texto
geral será construído como uma camada híbrida sobre ele.

## Estado conhecido

- Classificador de recortes já segmentados: aproximadamente 99,8% de acurácia.
- Pipeline completo medido em páginas rotuladas: aproximadamente 94,4 F1,
  94,9% de recall e 94,0% de precisão.
- O principal déficit atual está em segmentação, agrupamento, layout, contexto e
  ordem de leitura, não na classificação isolada do glifo.
- EasyOCR, Tesseract e PaddleOCR estão disponíveis como engines auxiliares.
- PaddleOCR deve ser tratado inicialmente como fonte de hipóteses e fallback,
  não como substituto automático do pipeline próprio.

## Critérios globais de sucesso

### Qualidade

Metas iniciais para páginas limpas e representativas:

- CER abaixo de 3%.
- WER abaixo de 8%.
- Box F1 acima de 97%.
- Ordem de leitura correta acima de 98% em páginas simples.
- Redução de pelo menos 50% nas palavras suspeitas.

Metas avançadas:

- CER entre 1% e 2% em scans limpos.
- WER entre 3% e 5%.
- Box F1 acima de 98%.
- Layout preservado em páginas com duas colunas, títulos e elementos auxiliares.

As metas devem ser comparadas no mesmo conjunto de páginas e não podem ser
interpretadas como garantia de equivalência universal a produtos comerciais.

### Operação

- Nenhum erro silencioso em processamento normal.
- Toda decisão deve possuir confiança e origem.
- Processamento em lote com cache de modelos.
- Execução funcional em CPU; GPU opcional.
- Regressão automática de qualidade, tempo e memória.
- Exportação de texto, JSON estruturado, DOCX e PDF pesquisável.

## Fases

### OCR-00 — Benchmark e ground truth

**Prioridade:** P0  
**Dependências:** nenhuma  
**Resultado:** baseline reproduzível

#### Entregas

- Corpus fixo de 30–50 páginas representativas.
- Transcrição de referência revisada.
- Anotação de regiões, linhas, palavras, caixas e ordem de leitura.
- Ferramenta de avaliação com CER, WER, precisão, recall, F1 e métricas de layout.
- Relatório comparando engine atual, PaddleOCR, EasyOCR, Tesseract e, quando
  disponível, Acrobat/ABBYY.
- Versionamento do corpus, configuração e modelo usado em cada medição.

#### Critérios de aceite

- Duas execuções com a mesma entrada produzem o mesmo relatório.
- O relatório identifica página, região, linha e palavra problemáticas.
- A medição diferencia erro de reconhecimento, segmentação e ordem de leitura.

---

### OCR-01 — Modelo de dados e observabilidade

**Prioridade:** P0  
**Dependência:** OCR-00 parcialmente

#### Entregas

- Objetos `PageResult`, `RegionResult`, `LineResult`, `WordResult`,
  `GlyphResult` e `OCRHypothesis`.
- Confiança, origem, alternativas, bounding box, versão do modelo e pipeline.
- Modo diagnóstico com imagens intermediárias e resultados de cada engine.
- Logs estruturados sem depender da UI.

#### Critérios de aceite

- Cada palavra final pode ser rastreada até suas hipóteses de origem.
- Resultados podem ser serializados e recarregados.
- O modo normal não grava artefatos pesados sem solicitação do usuário.

---

### OCR-02 — Pré-processamento adaptativo

**Prioridade:** P0  
**Dependência:** OCR-00, OCR-01

#### Entregas

- Normalização de DPI.
- Correção de rotação e perspectiva.
- Correção de iluminação e contraste.
- Binarização global e adaptativa.
- Redução de ruído e bleed-through.
- Tratamento de texto claro sobre fundo escuro.
- Geração de poucas variantes controladas.
- Seleção automática por estabilidade geométrica, confiança e coerência textual.

#### Critérios de aceite

- Melhora mensurável em páginas inclinadas, pequenas e com iluminação irregular.
- Nenhuma regressão significativa em páginas limpas.
- Cada variante e decisão de seleção aparece no diagnóstico.

---

### OCR-03 — Análise de layout

**Prioridade:** P0  
**Dependência:** OCR-01, OCR-02

#### Entregas

- Detecção de regiões.
- Classificação de corpo, título, cabeçalho, rodapé, legenda, tabela, diagrama,
  notação, nota lateral e região desconhecida.
- Detecção de colunas.
- Grafo de ordem de leitura.
- Exclusão ou tratamento especial de regiões não textuais.

#### Critérios de aceite

- Páginas de duas colunas são lidas na ordem correta.
- Cabeçalho e rodapé não são inseridos no meio do parágrafo.
- Diagramas e tabelas não contaminam o texto corrido.

---

### OCR-04 — Linhas, palavras e parágrafos

**Prioridade:** P0  
**Dependência:** OCR-03

#### Entregas

- Detecção de linhas.
- Agrupamento de glifos por linha.
- Detecção de palavras por espaçamento e alinhamento.
- Reconstrução de parágrafos.
- Tratamento de pontuação e caracteres colados/divididos.
- Regras para linhas que cruzam regiões ou caixas de layout.

#### Critérios de aceite

- Redução de boxes espúrios e caracteres colados.
- Espaços e quebras de linha preservados em texto simples.
- Cada palavra possui associação à linha e à região de origem.

---

### OCR-05 — Reconhecimento híbrido

**Prioridade:** P1  
**Dependência:** OCR-04

#### Entregas

- Adapter comum para engine próprio, PaddleOCR, EasyOCR e Tesseract.
- PaddleOCR como reconhecedor de linha e fallback.
- Execução sob demanda conforme confiança e divergência.
- Normalização dos formatos de saída.
- Cache de modelos e resultados.

#### Critérios de aceite

- Engine próprio continua prioritário para glifos e notação.
- PaddleOCR melhora ou mantém CER/WER nas páginas de prosa.
- Falha de engine opcional não interrompe o processamento principal.

---

### OCR-06 — Fusão e decodificação contextual

**Prioridade:** P1  
**Dependência:** OCR-05

#### Entregas

- Múltiplas hipóteses por caractere, palavra e linha.
- Beam search ou Viterbi.
- Pontuação visual, geométrica, linguística e de domínio.
- Fusão entre glifos e OCR de linha.
- Regras específicas para notação de xadrez.
- Preservação do resultado original quando houver correção contextual.

#### Critérios de aceite

- Erros de `O/0`, `I/l/1`, `S/5`, pontuação e caracteres semelhantes são reduzidos.
- Correção linguística não substitui palavras válidas sem evidência.
- Toda alteração contextual é auditável.

---

### OCR-07 — Linguagem, dicionários e treinamento de linhas

**Prioridade:** P1  
**Dependência:** OCR-06

#### Entregas

- Dicionários por idioma e domínio.
- Lista de nomes próprios e termos de xadrez.
- Modelo de caracteres/palavras.
- Dataset sintético de palavras e linhas.
- Dataset real anotado.
- Treinamento ou fine-tuning de reconhecimento de palavras e linhas.
- Divisão de treino/teste por documento, evitando vazamento.

#### Critérios de aceite

- Ganho estatisticamente significativo em CER e WER.
- Melhoria preservada em documentos não usados no treinamento.
- Palavras raras e nomes próprios não são destruídos pelo corretor.

---

### OCR-08 — Suspeitas, revisão e active learning

**Prioridade:** P1  
**Dependência:** OCR-06

#### Entregas

- Detecção de palavras suspeitas.
- Navegação visual pelas suspeitas.
- Comparação de alternativas e engines.
- Correção manual sem alterar a imagem original.
- Inclusão opcional em dicionário.
- Exportação das correções para novo dataset.

#### Critérios de aceite

- Usuário consegue revisar apenas casos de baixa confiança.
- Cada correção pode ser desfeita.
- Correções não alteram silenciosamente outras páginas.

---

### OCR-09 — Exportação e fidelidade documental

**Prioridade:** P1  
**Dependência:** OCR-03, OCR-04, OCR-08

#### Entregas

- Texto simples com ordem correta.
- JSON com regiões, linhas, palavras e coordenadas.
- DOCX estruturado.
- PDF pesquisável com imagem original e camada invisível.
- Metadados de confiança e suspeitas.
- Preservação de parágrafos, títulos, colunas e regiões especiais.

#### Critérios de aceite

- Seleção e busca funcionam no PDF.
- Copiar texto respeita a ordem de leitura.
- A imagem original não é degradada no PDF pesquisável.

---

### OCR-10 — Performance, robustez e distribuição

**Prioridade:** P2  
**Dependência:** OCR-05 a OCR-09

#### Entregas

- Processamento em lote.
- Cancelamento seguro.
- Cache por hash de imagem e configuração.
- Perfil CPU/GPU.
- Limites de memória.
- Relatório de tempo por etapa.
- Empacotamento das dependências opcionais.

#### Critérios de aceite

- Página simples em até 3 segundos na configuração de referência.
- Página complexa em até 8 segundos, salvo engines externos explicitamente lentos.
- Processamento interrompido não corrompe documentos nem cache.

## Ordem de execução recomendada

1. OCR-00 — benchmark.
2. OCR-01 — contratos e observabilidade.
3. OCR-02 — pré-processamento.
4. OCR-03 — layout.
5. OCR-04 — linhas e palavras.
6. OCR-05 — engines híbridos.
7. OCR-06 — fusão contextual.
8. OCR-07 — linguagem e treinamento.
9. OCR-08 — revisão e active learning.
10. OCR-09 — exportação.
11. OCR-10 — otimização e distribuição.

Cada fase deve atualizar o benchmark antes de ser considerada concluída.

---

# Revisão extraordinária após a validação das páginas 30–31

Em uma conversão real do livro *Aagaard — Grandmaster Preparation —
Calculation*, a conferência manual mostrou que os glifos de xadrez no DOCX não
apresentaram erros perceptíveis, enquanto a prosa saiu com erros sistemáticos
como confusão entre `l/1/I`, `o/0`, `rn/m`, pontuação e maiúsculas.

## Revisão 1 — precisão do reconhecimento

1. O classificador de glifos não deve ser retreinado como primeira reação: ele
   já é o componente validado.
2. O caminho de exportação de livros usa principalmente reconhecimento por
   recorte; isso elimina o contexto de linha que resolve justamente os erros
   observados.
3. OCR de linha deve ser o caminho principal para `body`, `heading`, `caption` e
   `quote`.
4. Notação, símbolos, diagramas e regiões especiais devem continuar ancorados
   no reconhecedor próprio.
5. A linha reconhecida não pode substituir cegamente os glifos: deve ser alinhada
   à sequência geométrica e gerar alternativas auditáveis.
6. CER/WER devem ser medidos por domínio, pois acerto de glifos não representa
   acerto de prosa.
7. Correção por dicionário deve ser limitada por evidência visual e sempre
   preservar o texto anterior.

## Revisão 2 — layout, exportação e operação

1. O roteamento deve acontecer antes do engine e ser reproduzível no JSON.
2. Cabeçalhos, rodapés, duas colunas e títulos precisam ter política própria;
   misturá-los à prosa causa erros de ordem mesmo quando cada caractere está certo.
3. Linhas com texto pequeno, negativo, inclinado ou sobre trama devem escolher
   pré-processamento por região, não por página inteira.
4. Divergência entre glifos e linha deve virar suspeita, não correção silenciosa.
5. EPUB/DOCX precisam receber parágrafos reconstruídos, e o PDF pesquisável deve
   manter a imagem original com camada invisível coordenada.
6. Cache deve incluir versão do modelo, configuração, DPI e variante de imagem;
   cache antigo não pode contaminar uma medição nova.
7. O benchmark precisa guardar texto de referência, hipótese por engine e
   resultado final para permitir auditoria página a página.

## Novas fases de integração

### OCR-11 — Roteamento por domínio e benchmark A/B

**Prioridade:** P0  
**Dependência:** OCR-00, OCR-03, OCR-05, OCR-06

- classificar regiões em `prose`, `heading`, `caption`, `notation`, `symbol`,
  `diagram`, `table` e `unknown`;
- executar modo atual e modo linha em páginas iguais;
- registrar decisão de roteamento e motivo;
- medir CER/WER separado para prosa e notação;
- não alterar o caminho de glifos neste primeiro passo.

**Aceite:** o benchmark prova qual modo vence em prosa nas páginas 30–31 e o
roteador envia regiões de notação para o caminho antigo.

### OCR-12 — OCR de linha em produção

**Prioridade:** P0  
**Dependência:** OCR-11

- recortar a faixa inteira da linha;
- usar EasyOCR/PaddleOCR conforme disponibilidade;
- manter o engine próprio como âncora por glifo;
- alinhar string da linha aos glifos;
- aceitar a linha somente quando comprimento, geometria e confiança forem
  compatíveis;
- fallback imediato para glifos em caso de falha.

**Aceite:** nenhuma região de notação perde caracteres e a prosa melhora CER/WER
sem piorar os glifos.

### OCR-13 — Alinhamento e decodificação de linha robustos

**Prioridade:** P0  
**Dependência:** OCR-12

- alinhamento com inserções, remoções e ligaduras;
- distribuição de confiança por caractere sem inventar precisão;
- beam search usando alternativas dos dois caminhos;
- detecção de conflitos de espaço e pontuação;
- marcação de divergências.

### OCR-14 — Modelo linguístico e dados reais

**Prioridade:** P1  
**Dependência:** OCR-13

- ampliar léxicos por idioma, livro e domínio;
- incluir nomes próprios e termos de xadrez;
- dataset sintético de linhas com fontes, blur, ruído, escala e inclinação;
- dataset real anotado por livro;
- fine-tuning de reconhecimento de linha;
- validação separada por documento para evitar vazamento.

### OCR-15 — Layout especial e pré-processamento por região

**Prioridade:** P1  
**Dependência:** OCR-11, OCR-12

- política para duas colunas e leitura por bloco;
- detecção de tabelas, diagramas e legendas;
- processamento distinto para negativo, trama e texto inclinado;
- exclusão de cabeçalhos/rodapés conforme o tipo;
- benchmark de ordem de leitura.

### OCR-16 — Revisão visual de texto corrido

**Prioridade:** P1  
**Dependência:** OCR-08, OCR-13

- fila de palavras suspeitas;
- comparação imagem/OCR de linha/glifo;
- correção manual com undo;
- inclusão no léxico;
- exportação automática para active learning.

### OCR-17 — Exportação final e comparação comercial

**Prioridade:** P1  
**Dependência:** OCR-14, OCR-15, OCR-16

- reconverter as páginas 30–31 e o corpus completo;
- comparar modo atual, modo híbrido, Acrobat e ABBYY quando disponíveis;
- validar busca, cópia, ordem, DOCX e EPUB;
- registrar CER, WER, layout e tempo por domínio.

## Nova ordem de execução

1. OCR-11 — roteamento e A/B.
2. OCR-12 — OCR de linha em produção.
3. OCR-13 — alinhamento contextual.
4. OCR-14 — dados e treinamento.
5. OCR-15 — layout especial.
6. OCR-16 — revisão visual.
7. OCR-17 — exportação e comparação final.

As OCR-00–OCR-10 permanecem como fundação implementada. Cada nova fase deve
preservar os 2.000+ testes atuais e anexar o relatório do benchmark correspondente.

## Status de implementação OCR-11 a OCR-13

As três fases foram implementadas na camada de domínio e estão cobertas por testes unitários:

- OCR-11: `core/ocr_routing.py` mantém o roteamento por domínio e `core/ocr_ab.py` compara baseline e candidato sobre o mesmo conjunto de páginas, com CER/WER, métricas estruturais e delta serializável.
- OCR-12: `core/ocr_hybrid.py` usa OCR de linha para prosa e preserva o reconhecedor por glifo para notação/símbolos. Falha do engine de linha cai explicitamente para a âncora de glifos e deixa aviso rastreável.
- OCR-13: `core/ocr_context.py` aplica decodificação contextual conservadora por palavra, somente para candidatos próximos do vocabulário, preservando o texto original e as correções no metadata.

O passo seguinte era ligar o roteamento ao fluxo de extração de livro e
executar o A/B real das páginas 30–31 com referência revisada. Está feito, e a
seção abaixo registra o que a página exigiu de diferente do plano.

## OCR-11 e OCR-12 em produção — o roteamento é por palavra, e não por linha

Data: 2026-09-15

### O que a página 30 mostrou

A linha destes livros é **mista**: `25.♖xc7! Amazingly Gashimov missed his
chance and only drew on move 40 after: 25.g4? ♖g6 26.♘g3⩲`. Rotear a linha
inteira para um leitor — o plano da OCR-11 — perde de um lado ou do outro:
a cadeia própria acerta o lance e escreve `1n.ssed b.s cbance`; o Tesseract
acerta a prosa e escreve `25.¢4? ♖g6 26.♘g3t` (a figurina não existe no modelo
latino e é omitida, o `⩲` vira `t`). Das 25 linhas da página, 23 são mistas,
1 é só notação e 1 é só prosa.

Junto disso, dois defeitos do modo anterior (`fusao="linha"`), que substituía
a linha inteira pela do Tesseract e repunha as figurinas por coordenada:

- o corretor de prosa corria sobre a linha inteira, e a busca aproximada
  trocava `axb4` por `ab4` e `cxd5` por `cd5` (`ab` está no vocabulário, `ab4`
  não);
- o piso de confiança era o da **linha**, e a média era puxada para baixo pelos
  lances que o Tesseract lê sem figurina (`27.Eg7t` a 0,0): a linha
  `28.♕a7 is just mate.` ficava inteira com a cadeia, `1s jus [nate.` incluído.

### O que foi feito

- `notacao.e_token_de_notacao`: a peneira estrita do que é lance, número de
  lance, sinal de avaliação ou resultado. Mais estrita que `parece_lance`, que
  aceita `a1]d` (o `and` lido com `1]`) — errar para o lado do lance custa a
  palavra, e o Tesseract lê `and`.
- `livro._fundir_por_palavra`: a caminhada é pela âncora da cadeia própria,
  que tem um item por box. Cada token dela ou tem forma de lance e fica, ou é
  trocado pelas palavras do Tesseract que ocupam o mesmo lugar em x (metade
  da largura da mais estreita). A palavra do motor que não coincide com token
  nenhum entra no lugar dela (o caractere derrubado por confiança); a que
  toca um lance é do lance (`after:25.g4?` não escreve o lance duas vezes);
  a abaixo de 0,5 de confiança e a fora da faixa vertical da linha ficam de
  fora.
- `livro._dominio_da_linha` + `OCRRouter`: o domínio da linha (`notation`,
  `prose`, `mixed`, `unknown`) vira um `RegionResult` e o roteador da OCR-11
  decide. A linha só de lances nem paga o motor; a de domínio desconhecido só
  o paga com a âncora fraca. Cada linha deixa um registro em
  `PaginaExtraida.roteamento` (domínio, leitor principal, motivo, fonte do
  texto, as duas leituras, a semelhança e as contas da fusão).
- `livro._semelhanca_de_linha`: o registro do Tesseract só é aceito quando as
  letras e dígitos concordam com a âncora em pelo menos 0,5 — é o que recusa
  o registro da linha errada (a segunda passada sobre a trama devolveu
  `The unprotected knight on G is a target. 18.223 Wh6…` para a linha
  `9. El Debs – Valhondo Morales`, com 0,25). O registro rejeitado não é
  consumido, e a linha de baixo ainda o encontra.
- O corretor pula o token de notação.
- `ocr_ab.medir_por_dominio`: CER e WER de prosa e notação em separado, pelo
  alinhamento de Levenshtein dos tokens, com a tipografia dobrada dos dois
  lados (traço, aspa, `†`→`+`).
- `scripts/ab_ocr_livro.py`: os três modos sobre as mesmas páginas, com o
  Tesseract rodando uma vez por página; grava texto e roteamento por modo e
  imprime a tabela contra `--referencia <pasta do livro>/pNNN.txt`
  (`preview_ocr/referencia/<livro>/`).

### O A/B da página 30

Referência: `preview_ocr/referencia/p030.txt`, transcrita da imagem em
2026-09-15 e relida no mesmo dia em tiras a 220 dpi (900 dpi nos símbolos),
com uma correção — `26.♘g3±`, e não `⩲`, que era o que a cadeia tinha lido e
eu tinha seguido. Nos dois pontos que o scan deixa ambíguos (`58...♕e1`,
`27.♘e5`) a lógica dos lances decide: `e1→g3` e `e5→f7` são movimentos
possíveis, `c1→g3` e `c5→f7` não. A conferência contra o livro impresso
continua em aberto. São 207 tokens de prosa e 88 de notação; a página 31 é
só diagramas e não entra.

| modo | CER prosa | WER prosa | CER notação | WER notação | CER total | s |
|---|---:|---:|---:|---:|---:|---:|
| `glifo` (só a cadeia) | 31,60% | 61,84% | 10,67% | 20,45% | 24,74% | 1,7 |
| `linha` (modo anterior) | 5,71% | 6,28% | 17,15% | 38,64% | 9,46% | 4,5 |
| `palavra` (novo, padrão) | **5,30%** | **4,83%** | **7,53%** | **17,05%** | **6,03%** | 3,2 |

O modo `palavra` ganha nas cinco colunas. Na notação ele ganha até da cadeia
sozinha, o que parece errado e não é: os tokens da notação são os mesmos nos
dois, e a diferença é a prosa vizinha — no modo `glifo` a palavra partida
(`20] 2`) e o lixo inserido caem no alinhamento como erro do token de trás.

O que sobra no modo `palavra`, token a token (25 de 295):

- 14 são da cadeia própria, no lance: `25♖xc7!` sem o ponto, `25.g4.` por
  `25.g4?`, `⩲` por `±`, `gxh5` lido `a6`, `♕e1`/`♘e5` lidos `♕c1`/`♘c5`,
  `26...g16` por `26...gxh6`, `1–0` lido `1`. É o assunto da OCR-14 (dados e
  treino), e a métrica agora o separa.
- 8 são de uma linha só, o cabeçalho `9. El Debs – Valhondo Morales,
  Gibraltar 2012`, para o qual o Tesseract não devolveu registro na primeira
  passada; a segunda deu lixo, a semelhança o recusou, e a linha ficou com a
  cadeia (`Bl Ibet Valhndo Morales' Gibra]tar 201 2`) — sete de prosa e o
  traço entre os nomes, que a peneira conta como sinal.
- 3 são do Tesseract na prosa: `[n` por `In`, `Bur` por `But`, `'The`.

### O que ficou de fora, e por quê

- `HybridOCRPipeline.read_line` continua sendo o contrato da camada de
  domínio, com o leitor de linha por faixa. O fluxo de livro não passou a
  chamá-lo: ele lê a faixa de cada linha, e o Tesseract por faixa custa uma
  chamada de processo por linha (F114: 138 ms/linha contra uma chamada por
  página). A regra que os dois compartilham — lance com a âncora, prosa com o
  motor, divergência registrada — está nos dois; o que a produção tem a mais
  é a fusão por palavra com as caixas do Tesseract.
- O cabeçalho que o Tesseract não leu na primeira passada é um problema do
  `--psm 3`, e não do roteamento; fica para a OCR-15 (layout especial), junto
  com a segunda passada sobre a trama, que nesta página só produziu lixo.

### Segunda passada, 2026-09-15: o pingo, o gancho e a faixa

Antes de partir para a OCR-14, uma medição sobre os 14 erros da cadeia no
lance: **de qual confiança eles são?** Se fossem de hesitação, o Tesseract
poderia entrar como segunda opinião gateada pela confiança (a OCR-13 em
produção); se fossem confiantes, só treino resolve. `_texto_da_linha` ganhou
o `marcador_confianca`, e a resposta veio clara: mediana 1,00 nos tokens
errados, igual à dos certos. A segunda opinião por confiança está descartada.

Mas o mesmo instrumento mostrou o padrão: `25.g4?` saía `25.g4.` com o `.` a
1,00 **e um box derrubado ao lado, um `'` a 0,21** — o gancho do `?`. O
segmentador partia o glifo em dois componentes, o gancho virava apóstrofo de
baixa confiança e caía; o mesmo com o `!`. E, olhando os vizinhos, o **pingo
do `i` também não fundia**: `.` em y 238–242 sobre a haste em 248–266, 6 px
numa altura mediana de 18 — 0,33 —, e `BoxService.FOLGA_DE_DIACRITICO` era
0,30. É daí que vinham `A1nazing]y`, `1n.ssed`, `b.s`, `on]y`: a haste solta
lida como `l` a 0,37, e derrubada.

A população da página, medida (pares curto-sobre-alto alinhados em x): 8 em
0,11, 5 em 0,16, 27 em 0,21, 7 em 0,26, **36 em 0,32** — o maior grupo, logo
acima da régua — e o próximo grupo só em 0,74 (pontuação da linha de cima). A
régua da F3.11 tinha sido medida nas 11 páginas rotuladas, onde o diacrítico
vai a 0,23 e o outro lado começa em 0,55; esta digitalização cai no vale, do
lado errado. **0,30 → 0,40**: nas 11 páginas rotuladas nada muda
(`medir_paginas.py`, F1 94,9 nas duas, precisão 93,7 → 93,6 por
arredondamento); na página 30 a cadeia sozinha vai de 31,6% para 27,3% de CER
na prosa e de 20,5% para 17,0% de WER na notação — os quatro `?`/`!` voltam.

E o cabeçalho que o Tesseract não leu (8 erros): a passada de página com
`--psm 3` pula linhas inteiras, e para essas a produção passa a ler **a faixa
da linha** (`OCRService.tesseract_faixa_detalhada_conf`, `--psm 7`,
`ler_faixa` em `extrair_pagina`), só para a linha sem registro compatível —
uma chamada de processo por faixa, nunca por página. O registro volta em
coordenadas da página e entra na mesma fusão.

| modo | CER prosa | WER prosa | CER notação | WER notação | CER total | s |
|---|---:|---:|---:|---:|---:|---:|
| `glifo` (só a cadeia) | 27,32% | 55,07% | 9,83% | 17,05% | 21,59% | 1,6 |
| `linha` (modo anterior) | 1,73% | 4,35% | 15,06% | 36,36% | 6,10% | 4,9 |
| `palavra` (novo, padrão) | **1,33%** | **2,90%** | **4,60%** | **11,36%** | **2,40%** | 2,9 |

A página está abaixo da meta inicial do roadmap (CER < 3%, WER < 8%). Dos 16
tokens que sobram: 10 são da cadeia no lance, com confiança — o ponto que se
funde ao vizinho (`25♖xc7!`, `26♕g5`, `57..`), `⩲` por `±`, `e`/`c`, o `gxh5`
lido como um box só (`a6`), `1–0` lido `1`; 3 são do Tesseract na prosa
(`[n`, `Bur`, `'The`); 2 são uma marca de digitalização na margem da linha
do cabeçalho; 1 é a vírgula depois de `58.♘xc4?`.

### A segunda página: Yusupov, «Chess Evolution 1», p. 34 (duas colunas)

`preview_ocr/referencia/yusupov_chess_evolution_1/p034.txt`, transcrita da
imagem em 2026-09-15: «Solutions» em duas colunas, cabeçalhos em negativo
(branco sobre preto), 127 tokens de prosa e 119 de notação. As referências
passaram a ficar numa pasta por livro (`--referencia`). A página foi
escolhida para ver se a régua do pingo e a semelhança de linha eram desta
digitalização ou gerais — e o que ela trouxe foi outra coisa: **a primeira
rodada deu 106% de CER**, porque as duas colunas saíram intercaladas.

O que a página exigiu, em ordem de descoberta:

1. **A calha apagada pela mobília.** O que a F70 deixou em aberto na letra —
   "o título de duas linhas sobre a calha ainda a apaga": aqui são o título
   «Solutions» em cima e o número da página centrado embaixo, duas linhas
   cruzando a calha contra uma tolerada. A linha de mobília — compacta
   (tinta em < 30% da largura) **e** centrada no texto — deixa de entrar na
   projeção (`BoxService._e_mobilia`). A primeira versão tirava toda linha
   curta e abriu calha falsa no sumário do «Calculation» (linhas de ponta a
   ponta com pouca tinta) e numa página do Seirawan (títulos à esquerda) —
   os dois são cobertos pela regra final. Medido em amostras de 12 páginas de
   8 livros: os de coluna única não mudam (Darcy Lima 0/13, Calculation
   0/13, Seirawan 2/12), os de duas colunas ganham (Chess Evolution 1 8 → 10
   de 11, Yusupov Complete 11 → 12 de 12), e nas 11 páginas rotuladas nada
   muda. A banda de `_linhas` é julgada pelo seu maior grupo de caixas
   (`_nucleo_da_banda`): a orelha girada do capítulo, na mesma altura do
   título e a 800 px dele, não o tira da mobília.
2. **O título centrado saía partido**: `Solu` no fim da coluna da esquerda,
   `tions` no começo da direita. A linha de mobília que cruza a calha é um
   elemento transversal de `sort_boxes_reading_order`: sai inteira, no lugar
   dela.
3. **O número de lance partido do lance**: `1 .♘f6!`, `1 ...♕xe2`,
   `1 1.♕g7`. O `1` em negrito deste livro tem a tinta estreita e o avanço
   largo, e o vão até o ponto (8–12 px) passa da régua do espaço (6–8 px).
   Lexicalmente não há dúvida: `_colar_numero_de_lance` tira o espaço nos
   quatro vetores (texto, pesos, lacunas, caixas). `201 2 .` não cola: o
   ponto precisa de lance depois.
4. **O cabeçalho em negativo**: o Tesseract lê a tarja como está e devolve
   `].Bolbochan` a 0,4 e `W.Steinit`. A linha com boxes `negativo` ignora o
   registro da página e vai para a faixa dela **invertida no miolo** (a
   margem que `faixa_da_linha` põe em volta fica branca — invertida, virava
   moldura preta). Sai `].Bolbochan — L.Pachman` a 0,82, `Em.Lasker —
   W.Steinitz` a 0,87.
5. **As lacunas do lance.** Os quatro erros de notação que sobravam eram o
   mesmo fenômeno: o `–` de `+–` a 0,40–0,44 (três vezes) e a ligadura `ex`
   de `exf4` a 0,43, derrubados por `CONF_MINIMA`. O box derrubado é a
   evidência de que há um glifo ali, e o Tesseract leu os quatro certos.
   `_preencher_lacunas_do_lance` alinha o lance à palavra do motor com a
   figurina e a lacuna como curingas de um ou dois caracteres
   (`_alinhar_lance`, programação dinâmica; no empate a letra vai para a
   figurina, não para a lacuna ao lado), aceita na lacuna só o alfabeto do
   lance — figurina não, lixo não — e só se o lance inteiro continuar com
   forma de lance (`26...g16` + `¢xh6` → `26...g1h6` é recusado). A linha só
   de notação, que não paga o motor, passa a usar o registro que a página
   já tem para isto, e só para isto (`so_lacunas`), quando tem box
   derrubado. O traço do motor vira o da cadeia (`–`).

| página | modo | CER prosa | WER prosa | CER notação | WER notação | CER total |
|---|---|---:|---:|---:|---:|---:|
| Aagaard p. 30 | `glifo` | 27,32% | 55,07% | 9,83% | 17,05% | 21,59% |
| | `linha` | 1,73% | 4,35% | 15,06% | 36,36% | 6,10% |
| | `palavra` | **1,33%** | **2,90%** | **4,60%** | **11,36%** | **2,40%** |
| Yusupov p. 34 | `glifo` | 7,30% | 18,11% | 2,56% | 12,61% | 4,81% |
| | `linha` | 1,99% | 3,15% | 4,06% | 14,29% | 3,08% |
| | `palavra` | **0,50%** | **2,36%** | **0,75%** | **4,20%** | **0,63%** |

A régua do pingo (0,40) e a semelhança de linha (0,5) valeram na segunda
página sem ajuste — a primeira rodada do Yusupov, ainda com as colunas
intercaladas, já tinha a fusão certa linha a linha. Dos 10 tokens que sobram
no Yusupov: 6 são a orelha girada do capítulo (lida como `♕ ♕ ♕ ⩲`) e o
número da página; 2 são a primeira letra em negrito lida pelo Tesseract
(`].Bolbochan`, `§.Tarrasch`); 2 são o `–` de `+–` que o motor também não
leu. No Aagaard nada mudou — os 16 de antes, com o cabeçalho e o `gxh5` da
cadeia.

### A terceira página: Nunn, «Secrets of Rook Endings», p. 237 do PDF (impressa 236) — a tabela

`preview_ocr/referencia/nunn_secrets_of_rook_endings/p237.txt`, transcrita
da imagem em 2026-09-15: o cabeçalho corrente, a legenda e a tabela de seis
filas da F72 ocupando a largura da página, e embaixo duas colunas de prosa
densa de notação, a da direita com um diagrama e duas linhas. 165 tokens de
prosa e 73 de notação. A primeira rodada deu **47% de CER**, e o que a página
exigiu, em ordem:

1. **A tabela apagava a calha.** As caixas de dentro da moldura (F71) eram
   treze linhas atravessando a calha na projeção, e as duas colunas de baixo
   saíam intercaladas. `detectar_colunas` deixa de contar as caixas
   `moldura`, e na ordem de leitura elas são um elemento só, no lugar da
   tabela. E **tudo que está dentro do retângulo da moldura é da moldura**
   (`_marcar_o_miolo_da_moldura`): `trama.glifos` só marca o componente com
   altura de caractere, e os dois pontos, as reticências e os pedaços das
   réguas ficavam sem a marca — saíam depois da tabela como linhas de
   `: : :`, e as células saíam `W Win(1 ♖e1!)`.
2. **O filete.** A régua dupla do topo da tabela saía como dois boxes de
   937×49 px: baixos, passavam pelo descarte de bloco, eram lidos como `T` e
   cruzavam a calha inteira. `FATOR_FILETE`: contorno mais largo que dez
   alturas de caractere não é texto, depois de `negativo` e `trama` terem
   aberto tarja e moldura. Nas 11 páginas rotuladas nada muda (F1 94,9).
3. **O cabeçalho corrente e a legenda da tabela**, de lado a lado sobre as
   colunas: duas linhas largas cruzando a calha. Não são compactas; são
   **centradas nas margens** do bloco de texto (12%, a mesma de
   `livro.MARGEM_DE_PAGINA`) e **isoladas** das vizinhas por mais de um
   passo e meio de linha — as duas últimas linhas de uma página de duas
   colunas também são uma banda larga e centrada na margem de baixo, mas
   estão a um passo da linha de cima, e são texto. A primeira versão tentou
   "a linha larga que é minoria é separador", e é insustentável: a banda que
   junta as duas colunas na mesma altura também é larga, e a calha do Nunn
   (3,3 larguras) fica abaixo do vão que separa grupos.
4. **O vão que é metade da calha não é calha.** Onde a coluna tem duas linhas,
   um espaço entre palavras alinhado nas duas passa pela tolerância e abria
   um terceiro corte de 13 px ao lado da calha de 100; `CALHA_FRACAO_DA_MAIOR`
   descarta o corte que não chega à metade do maior. Nas amostras dos 8
   livros isto só tirou faixas espúrias (Chess Evolution 1 p48 3 → 2, p92
   4 → 2, p114 3 → 2; Complete p438 4 → 2).
5. **A célula fechada.** Dentro da tabela cada célula é um retângulo fechado
   pelas réguas, e `trama.glifos` usava `RETR_EXTERNAL`: o que está dentro é
   contorno filho e não saía — a coluna do meio vinha vazia em quatro das seis
   filas, e as outras só saíam porque a régua delas estava partida na
   binarização. É a F71 uma moldura para dentro. Componentes conexos no
   lugar de contornos; a régua cai pela altura como o tabuleiro cai. E o
   piso de `ALTURA_GLIFO` desce de 0,35 para 0,15: a pontuação das células
   tem 5 px em 29 (0,17), e o ponto da trama tem 2. No painel de pontuação
   do Yusupov Complete (p. 20) o pingo do `i` passa a entrar (`p1nts` →
   `pints`); nas páginas 18 e 19 nada muda.

| página | modo | CER prosa | WER prosa | CER notação | WER notação | CER total |
|---|---|---:|---:|---:|---:|---:|
| Nunn p. 237 (primeira rodada) | `palavra` | 43,30% | 43,03% | 52,78% | 43,84% | 47,36% |
| Nunn p. 237 | `glifo` | 20,47% | 24,85% | 21,31% | 26,03% | 20,83% |
| | `linha` | 18,66% | 18,79% | 25,18% | 38,36% | 21,45% |
| | `palavra` | **16,49%** | **16,36%** | **19,85%** | **26,03%** | **17,93%** |
| Aagaard p. 30 | `palavra` | 1,33% | 2,90% | 4,60% | 11,36% | 2,40% |
| Yusupov p. 34 | `palavra` | 0,50% | 2,36% | 0,75% | 3,36% | 0,63% |

As duas primeiras páginas não mudaram. Dos 46 tokens que sobram no Nunn, 40
são da tabela — e a tabela é lida **só pela cadeia própria**, célula a
célula (`_tabela_da_pagina`), sem a fusão: `W:Win(1` por `W: Win (1` (a
régua do espaço numa célula de poucos boxes), `W:W1n` (o `i`), a fila de
cabeçalho `W♔d1 W♔c1 W♔b1`, que está num bloco à parte, baixo demais para
`trama.candidatos` (91 px contra o piso de 116), e os dois `*`, que a cadeia
não tem. Fora da tabela sobram 6: o `W` lido `w`, `1..♖b2?`, `♖e8 !` partido
e a marca `-see`.

### O que ficou de fora, e por quê

- **As células da tabela não passam pela fusão.** O Tesseract da página lê
  as células com as caixas das palavras; ligar `_tabela_da_pagina` ao mesmo
  laço de linha de `extrair_pagina` é o passo que tira a maior parte dos 40.
- **A fila de cabeçalho da tabela** está num bloco de 937×91 px que
  `trama.candidatos` recusa por baixo (piso de 4 escalas). Abrir blocos
  baixos e largos é o que a resolve — com a peneira do filete logo atrás.
- **As páginas de capítulo do Chess Evolution 1 (18, 46) saem como lixo**
  (`⯹⯹♖= . :. . .`, 912 «caracteres» na 18; 9 na 46, sem a prosa) — **e já
  saíam assim em HEAD**, conferido num worktree limpo com o mesmo modelo. O
  painel de conteúdo sobre a trama envenena a segmentação da página inteira;
  é o layout "prosa com diagrama do Yusupov" que o A/B ia ver a seguir, e é
  um defeito anterior a esta fase, do tamanho de uma fase.

### Próximo passo

Conferir as três referências contra o livro impresso. Depois, as páginas de
capítulo do Chess Evolution 1 (18, 46), e a medição já diz por onde: a
binária de segmentação da página 46 tem 5.724 componentes com **altura
mediana de 2 px** — os pontos do painel sobre a trama —, e a escala de texto
sai **6** (a prosa tem 30). Com a escala em 6 tudo que é letra vira bloco
para o descarte (`FATOR_NAO_TEXTO` × 6 = 24 px), e sobram 4 boxes antes do
descarte, 23 depois. Só na metade direita, sem o painel, Otsu dá 949
componentes: a prosa está lá. O passo é a estimativa de escala ignorar a
nuvem de pontos (é o que `preprocess.escala_de_texto` promete "pesando por
tinta", e aqui não entrega), medindo nas 11 páginas rotuladas antes de
mexer. Em paralelo, as células da tabela pela fusão. A orelha girada do
capítulo (`♕ ♕ ♕ ⩲`) é assunto da F8.1, e os erros confiantes da cadeia no
lance, da OCR-14.
