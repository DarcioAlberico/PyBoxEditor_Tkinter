# Contexto de domínio — OCR editorial de livros de xadrez

Este arquivo registra somente o vocabulário e as invariantes do produto. Detalhes
de implementação pertencem às specs e aos ADRs.

## Glossário canônico

- **Documento-fonte**: PDF ou imagem original recebido pelo usuário. É a evidência
  imutável que não pode ser substituída por uma versão corrigida.
- **Página**: unidade física do documento-fonte, com imagem, dimensões, número
  físico e, quando existir, camada de texto original.
- **Camada tipográfica**: camada de texto que é o texto composto do livro — o
  PDF nascido digital, com fonte de texto, fonte de figurina e diagrama em fonte
  de xadrez —, e não o OCR de fábrica (texto invisível sobre a imagem, fonte
  sintetizada pelo ClearScan). Só ela é lida como texto; a página que não a tem
  vai ao OCR, e a régua que decide é por página.
- **Região**: área semântica da página, como prosa, título, cabeçalho, rodapé,
  legenda, notação, tabela ou diagrama.
- **Glifo**: símbolo visual individual reconhecido na página. Pode ser letra,
  pontuação, peça figurativa, marcador ou símbolo de avaliação.
- **Linha**: sequência visual de glifos alinhados na página.
- **Palavra**: grupo de glifos separado por espaço visual ou regra editorial.
- **Parágrafo**: unidade de leitura formada por uma ou mais linhas relacionadas.
- **Notação**: texto que representa lances, variantes, comentários e símbolos de
  uma partida; pode usar SAN, LAN, figurinas ou convenções do livro.
- **Diagrama**: representação visual de uma posição de xadrez, incluindo casas,
  peças, coordenadas, setas, destaques e legenda associada.
- **Evidência**: observação preservada do documento-fonte, incluindo recorte,
  coordenadas, camada de texto, hipótese de engine e confiança.
- **Hipótese**: uma leitura possível para uma região, linha, palavra, glifo ou
  posição, sempre identificada por sua origem.
- **Alinhamento**: correspondência auditável entre duas leituras, explicitando
  inserções, remoções, substituições e expansão de ligaduras.
- **Fusão**: decisão que compara hipóteses de fontes diferentes usando domínio,
  confiança, consenso e evidência textual/visual, sem eliminar as alternativas.
- **Sequência de notação**: conjunto estruturado de tokens de xadrez, variantes,
  comentários e anotações, mantendo a grafia original e a forma normalizada.
- **Orientação do diagrama**: informação sobre qual lado do tabuleiro está embaixo,
  confirmada por coordenadas ou explicitamente marcada; ausência de evidência é
  incerteza, não uma orientação padrão silenciosa.
- **Posição candidata**: conjunto de hipóteses top-k para as 64 casas de um
  diagrama, antes da decisão editorial do FEN.
- **Estado de revisão**: situação que informa se um diagrama foi aceito
  automaticamente, precisa de conferência, foi revisado ou permanece sem solução.
- **Anotação visual**: seta, destaque, coordenada ou legenda associada ao
  diagrama, preservada como metadado e não confundida com peça.
- **Decisão**: hipótese escolhida pelo pipeline ou pelo revisor, sem apagar as
  alternativas e a evidência anterior.
- **Suspeita**: decisão que precisa de revisão humana por baixa confiança,
  conflito, geometria anormal ou regra de domínio violada.
- **Correção editorial**: alteração explicitamente confirmada pelo revisor,
  vinculada à evidência e ao motivo da mudança.
- **Fila de revisão**: conjunto ordenado de suspeitas e decisões pendentes,
  navegável por página, região, tipo de erro e severidade.
- **Documento editorial**: representação estruturada do livro já reconstruído,
  independente do formato final de exportação.
- **Exportação**: transformação do documento editorial em PDF pesquisável, DOCX,
  EPUB ou HTML, preservando texto, layout, diagramas e proveniência quando o
  formato permitir.

## Termos adicionais da Fase 5 e 6

- **Evento de revisão**: registro append-only de uma decisão humana, com valor anterior, novo valor, motivo, usuário, data e origem.
- **Projeção editorial**: estado atual reconstruído aplicando eventos sobre o documento intermediário; o diário histórico permanece.
- **Modo de exportação**: `faithful`, `clean` ou `hybrid`, definindo a relação entre fidelidade visual, leitura e auditoria.
- **Correção de treino**: decisão editorial confirmada que pode ser reutilizada
  como dado supervisionado, mantendo sua origem, domínio e autor.
- **Amostra ativa**: caso escolhido para revisão ou treino pelo valor combinado
  de incerteza do modelo e impacto editorial, não por ordem de página.
- **Holdout real**: conjunto de documentos-fonte nunca usado para ajuste, separado
  de dados sintéticos e protegido contra vazamento por livro, editor, fonte ou layout.
- **Calibração por domínio**: ajuste da confiança para que sua escala tenha o
  mesmo significado em prosa, notação, diagramas e demais domínios.
- **Manifesto de pesos**: identidade verificável de um peso, incluindo checksum,
  schema, pipeline, configuração e domínios compatíveis.
- **Contrato de cache**: identidade de um resultado que inclui entrada, código,
  schema, modelo e configuração; mudar qualquer um invalida o resultado anterior.
- **Orçamento de recursos**: limite efetivo de memória e workers por engine, usado
  para evitar concorrência que exceda a máquina disponível.
- **Pacote de modelo**: conjunto distribuível de pesos e manifesto verificável,
  instalável sem depender de caminhos do ambiente de desenvolvimento.
- **Protocolo de benchmark**: conjunto imutável de corpus, idioma, resolução,
  pré-processamento e política de revisão que todos os engines devem compartilhar.

## Invariantes do domínio

1. A imagem e o texto original do documento-fonte nunca são destruídos.
2. Uma correção manual tem precedência até que o usuário peça reprocessamento.
3. Notação e diagramas são domínios de xadrez; não devem ser tratados como prosa
   genérica sem deixar a decisão explícita.
4. Toda saída editorial deve conseguir apontar de volta para página e região de
   origem.
5. Confiança é evidência para priorização, não autorização para corrigir
   silenciosamente.
6. A mesma decisão editorial deve alimentar todos os formatos de exportação.
7. Um classificador visual não pode criar uma peça ausente apenas para satisfazer
   a legalidade; legalidade filtra candidatos observados.
8. Todo diagrama materializado tem estado de revisão e referência à imagem de
   origem, mesmo quando aceito automaticamente.
9. Eventos de revisão não apagam decisões anteriores; desfazer também é evento.
10. Todos os formatos percorrem a mesma sequência ordenada de blocos editoriais.
11. Uma saída limpa pode ocultar a auditoria visualmente, mas nunca a destrói no
    documento editorial ou no diário de revisão.
12. Dados sintéticos não substituem holdout real nem podem contaminar sua medição.
13. Um split não separa amostras que compartilham livro, editor, fonte ou layout.
14. Peso sem checksum e compatibilidade declarados não pode ser promovido a produção.
15. Comparações entre engines usam a mesma entrada, resolução, idioma e política de saída.
16. Um release só é promovido depois de passar o smoke test e os gates de qualidade.
