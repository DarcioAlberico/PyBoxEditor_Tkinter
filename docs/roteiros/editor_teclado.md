# Roteiro — o editor de livros inteiro pelo teclado (ED-13, AC-006, §13.2)

O que os testes conferem por comando (`tests/test_editor_ac_globais.py::test_ac006`,
`tests/test_editor_teclado.py`) é a metade que uma janela `withdraw`n permite: os
mnemônicos dos menus, cada item invocável, o mapa do tabuleiro, o anel de foco nos
controles, e — no teste `gui`, com a janela de verdade — o `F6`. Esta é a outra metade:
**uma pessoa, um teclado, sem mouse**, na janela de verdade. Abrir com
`.venv/Scripts/python.exe appy.py --editor <um EPUB>` e percorrer a tabela. Marcar cada
linha com a data e a máquina. **AAA só quando a coluna "Conferido" está preenchida por
alguém; o que só o teste cobre diz qual teste; o que não se pôde conferir fica dito, não
suposto.**

Convenções: `Alt+letra` abre o menu pelo mnemônico (**A**rquivo, **E**ditar, E**x**ibir,
**I**nserir, **F**ormatar, Xadre**z**, Ferra**m**entas, **L**ivro, Aj**u**da); `F6` /
`Shift+F6` percorrem os painéis na ordem da §7.1 (navegador, sumário, estilos, editor,
propriedades, xadrez, busca, resultados, mensagens, validação); `Shift+F10` ou a tecla de
menu abrem o contexto do controle focado; o foco visível é o `highlightthickness ≥ 2` dos
controles `tk` e o `AnelDeFoco` (um quadro azul de 2 px) em volta dos botões `ttk`.

| # | O que fazer | Como saber que está certo | Conferido |
|---|---|---|---|
| 1 | `Alt+A`, setas, `Enter` em "Abrir…" | O menu Arquivo abre com o A sublinhado; a caixa de arquivo abre; `Esc` fecha sem abrir nada | ✅ o sublinhado de cada menu é o mnemônico da spec e cada item habilitado é invocável (`test_ac006…`, 2026-09-21); abrir o menu com `Alt+A` na janela de verdade: — por conferir à mão |
| 2 | Abrir um EPUB e `F6` dez vezes | O foco anda navegador → sumário → estilos → editor → propriedades → xadrez → busca → resultados → mensagens → validação → navegador; em cada parada o controle focado tem o anel ou a borda de 2 px | ✅ `test_gui_f6_percorre_os_paineis_e_shift_f6_volta` (`event_generate` na janela com `deiconify`, 2026-09-21); o anel em cada parada: `test_ac006…` varre os controles focáveis |
| 3 | `Shift+F6` | Volta um painel | ✅ o mesmo teste `gui` |
| 4 | No texto, `Ctrl+B`, `Ctrl+I`, `Ctrl+U` com uma palavra selecionada (`Shift+Ctrl+→`) | O formato aparece na palavra; a barra de formatação mostra o estado; `Ctrl+Z` desfaz | ✅ os acordes chegam ao comando sem mexer no texto (`test_gui_ac3_os_acordes…`, ED-02); o formato pelo comando (`test_editor_texto_rico`); à mão: — por conferir |
| 5 | `F11` e `F11` | O capítulo vira código e volta ao texto; a barra de status diz o modo; nada muda no livro (título sem `•`) | ✅ `test_ac003_modo_texto_e_codigo_dez_vezes_sem_perda` (pelo comando); à mão: — por conferir |
| 6 | `Ctrl+Shift+D` | A caixa "Inserir diagrama" abre com o foco no FEN; `Tab` chega ao tabuleiro; setas movem a casa (anel de dois tons); `q` põe a dama branca, `Shift+Q` a preta, `Delete` esvazia, `F` gira; `Enter` confirma e o diagrama entra no texto | ✅ `test_o_editor_de_posicao_inteiro_pelo_teclado` e `test_editor_tabuleiro` (o mapa da §11.2 por eventos sintéticos, 2026-09-21); a caixa de verdade: — por conferir à mão |
| 7 | Setas até o diagrama e `Enter`; `Alt+Enter` | `Enter` abre "Editar posição"; `Alt+Enter` leva o foco ao painel Propriedades, com o botão "Editar posição…" alcançável por `Tab` | ✅ `Enter` = ação principal e o botão do painel (`test_editor_objetos`, `test_editor_xadrez_extras`); à mão: — por conferir |
| 8 | `Shift+F10` sobre um parágrafo | O menu de contexto abre no cursor; setas e `Enter` executam; `Esc` fecha | ✅ a tecla está na tabela e o comando existe (`test_toda_tecla_da_tabela…`); o menu aberto de verdade: — por conferir à mão |
| 9 | `Ctrl+F`, digitar, `Enter`, `Shift+Enter` | O painel Busca recebe o foco; `Enter` acha o próximo, `Shift+Enter` o anterior; `Esc` volta ao editor com a seleção no achado | ✅ pelo comando (`test_editor_painel_busca`, ED-06); à mão: — por conferir |
| 10 | `Ctrl+Shift+F` | O foco vai à paleta de figurinas; setas andam entre os botões (anel visível), `Enter` insere a figurina no texto, `Esc` volta ao editor | ✅ `test_editor_paleta` (as ligações e o `invoke`; a janela oculta não recebe tecla); à mão: — por conferir |
| 11 | `F7` | A ortografia percorre as palavras desconhecidas com a caixa; `Tab` entre "Ignorar", "Trocar", "Aprender" | ✅ pelo comando (`test_editor_ortografia`, ED-06); à mão: — por conferir |
| 12 | `Ctrl+S` com o livro sujo | Salva; o `•` do título some; a barra de status diz "Salvo" | ✅ pelo comando (`test_editor_janela`); à mão: — por conferir |
| 13 | `Alt+U`, "Atalhos de teclado…" | A lista dos acordes abre num texto percorrível por setas e `PgDn`; `Esc` fecha | ✅ o texto lista a tabela inteira (`test_toda_tecla_da_tabela…`); à mão: — por conferir |
| 14 | `Alt+F4` com o livro sujo | A guarda pergunta salvar / descartar / cancelar, com o foco em "Salvar"; `Esc` cancela | ✅ a guarda pelo `WM_DELETE_WINDOW` (`test_ac6_guarda_ao_fechar…`, ED-02); à mão: — por conferir |
| 15 | Leitor de tela (NVDA) sobre a barra de ferramentas | Cada botão é anunciado pelo `text`; a barra de status **não** é anunciada ao mudar — o painel Mensagens é o canal redundante (§15) | — não conferido (sem NVDA na máquina de referência); limite declarado na §15 |

O que ficou fora do teclado, e por quê: o arrastar do navegador (reordenar capítulos)
tem o par "Mover para cima/para baixo" no menu Livro; o `Ctrl+clique` em link tem
"Seguir link" no menu e no contexto; o zoom da superfície tem `Ctrl+=`/`Ctrl+-`/`Ctrl+0`.
