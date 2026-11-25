"""Os testes que conferem a grafia do código (`inspect.getsource`) estão numa lista nominal
(RG-01b, R-39): são os do falso vermelho quando se edita com a suíte rodando. Teste novo mede
comportamento; o que sair da lista sai convertido (PD-26)."""

import ast
from pathlib import Path

TESTES = Path(__file__).resolve().parent

#: (arquivo, teste): quantas chamadas. A lista só encolhe.
NOMINAL = {
    ("test_detectar_e_preencher_neural.py", "test_as_duas_acoes_isentam_so_o_easyocr"): 2,
    ("test_detectar_e_preencher_neural.py", "test_o_trabalho_tambem_recusa_um_modelo_que_sumiu_no_caminho"): 1,
    ("test_detectar_e_preencher_neural.py", "test_a_altura_de_referencia_nao_e_lida_dentro_de_preparar"): 1,
    ("test_estado_da_janela.py", "test_o_appy_restaura_a_janela_ao_abrir"): 1,
    ("test_f117_mascara_na_cadeia.py", "test_as_duas_acoes_e_a_exportacao_passam_o_mesmo_idioma"): 4,
    ("test_f123_poda_na_janela.py", "test_so_a_acao_neural_passa_a_poda"): 3,
    ("test_f14_dataset.py", "test_metadado_e_lido_como_utf8"): 1,
    ("test_f15_preprocess.py", "test_descarte_acontece_depois_do_merge"): 2,
    ("test_f17_leitura_de_linha.py", "test_nenhum_caminho_de_producao_filtra_a_linha"): 2,
    ("test_f19_calibracao.py", "test_retreino_zera_a_temperatura_no_meta"): 1,
    ("test_f23_medir_cadeia.py", "test_o_instrumento_nao_copia_a_regra_da_fila"): 1,
    ("test_f43_navegacao.py", "test_selecao_nao_chama_mais_o_zoom"): 1,
    ("test_f43_navegacao.py", "test_ha_um_guard_so"): 1,
    ("test_f43_navegacao.py", "test_guard_sobrevive_a_focus_get_sem_foco"): 1,
    ("test_f43_navegacao.py", "test_f4_esta_ligado_ao_zoom"): 1,
    ("test_f71_diagrama.py", "test_ler_pagina_mede_a_escala_sozinha"): 1,
    ("test_f72_knn.py", "test_o_instrumento_varre_o_voto_de_verdade"): 1,
    ("test_f73_modelo.py", "test_o_treino_grava_os_campos_novos"): 1,
    ("test_f73_modelo.py", "test_todo_caminho_que_le_com_a_rede_confere_o_modelo"): 1,
}


def _achados():
    achados = {}
    for caminho in sorted(TESTES.glob("*.py")):
        for funcao in ast.walk(ast.parse(caminho.read_text(encoding="utf-8"))):
            if not isinstance(funcao, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            chamadas = sum(1 for no in ast.walk(funcao) if isinstance(no, ast.Call)
                           and ast.unparse(no.func).split(".")[-1] in ("getsource", "getsourcelines"))
            if chamadas:
                achados[caminho.name, funcao.name] = chamadas
    return achados


def test_a_grafia_so_se_confere_na_lista():
    assert _achados() == NOMINAL
