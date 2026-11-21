"""O editor não deixa `after` órfão nem vigia morta (RG-13, R-18).

- O painel de mensagens reagendava a cada 200 ms e nunca chamava `after_cancel`: fechar o
  editor embutido disparava `bgerror` (`invalid command name …esvaziar`); o original e a
  reconciliação do texto idem.
- A vigia de "Abrir com…" morria no primeiro `PermissionError` do `open`.
- A validação rodava `epub.escrever` e o epubcheck na thread do Tk, e deixava o cursor
  "watch" se `escrever` levantava; a pasta do `mkdtemp` nunca saía.
"""

import os
import time

import pytest

from tests.test_editor_janela import _Janela


def _orfaos(raiz):
    """Os `after` agendados cujo comando já não existe (é o que vira `bgerror`)."""
    orfaos = []
    for ident in raiz.tk.splitlist(raiz.tk.call("after", "info")):
        script = raiz.tk.splitlist(raiz.tk.call("after", "info", ident))[0]
        comando = raiz.tk.splitlist(script)[0] if script else ""
        if comando and not raiz.tk.call("info", "commands", comando):
            orfaos.append(script)
    return orfaos


def _esperar_tarefa(t, limite=20.0):
    fim = time.time() + limite
    t.raiz.update()
    while t.j.task.is_running() and time.time() < fim:
        t.raiz.update()
        time.sleep(0.01)
    t.raiz.update()


def test_abrir_e_fechar_o_editor_nao_deixa_after_orfao():
    with _Janela() as t:
        raiz = t.raiz
        # O `after info` é do interpretador inteiro: os órfãos que outro teste deixou (um
        # editor destruído sem `fechar`) saem antes, para medir só o que este fechamento deixa.
        for script in _orfaos(raiz):
            for ident in raiz.tk.splitlist(raiz.tk.call("after", "info")):
                if raiz.tk.splitlist(raiz.tk.call("after", "info", ident))[0] == script:
                    raiz.tk.call("after", "cancel", ident)
        erros = []
        # O `after` órfão dispara depois do fechamento e vira `bgerror` ("invalid command
        # name …esvaziar"), que o Tk só imprime: o teste o captura pelo próprio `bgerror`.
        raiz.tk.createcommand("bgerror", lambda *a: erros.append(a))
        try:
            t.j.aba_ativa().widget.inserir("x")
            t.caixas.pergunta_resposta = False                 # fecha sem salvar
            assert t.j.fechar() is True
            assert _orfaos(raiz) == [], "fechar o editor deixou after agendado para widget destruído"
            fim = time.time() + 1.0
            while time.time() < fim:
                raiz.update()
                time.sleep(0.02)
            assert erros == [], f"o fechamento deixou bgerror: {erros}"
        finally:
            raiz.tk.deletecommand("bgerror")


def test_a_vigia_sobrevive_a_um_permission_error(tmp_path, monkeypatch):
    import builtins

    with _Janela() as t:
        from core.editor import xhtml

        operacoes = t.j.operacoes
        caminho = str(tmp_path / "fora.xhtml")
        cap = t.j.projeto.livro.capitulos[0]
        open(caminho, "w", encoding="utf-8").write(xhtml.escrever(cap))
        href = cap.arquivo
        operacoes.vigiados[caminho] = (href, 0.0)               # mtime velho: "mudou"
        original = builtins.open

        def preso(arquivo, *a, **k):
            if os.fspath(arquivo) == caminho:
                raise PermissionError(13, "o programa de fora segura o arquivo", caminho)
            return original(arquivo, *a, **k)

        monkeypatch.setattr(builtins, "open", preso)
        operacoes._vigiar()                                    # não levanta
        assert caminho in operacoes.vigiados and operacoes._vigia_id is not None, "a vigia morreu"
        monkeypatch.setattr(builtins, "open", original)
        assert href in operacoes.verificar_vigiados(), "o arquivo não voltou quando o open deixou"
        operacoes.fechar()


def test_a_validacao_roda_em_tarefa_e_o_cursor_volta_quando_escrever_levanta(monkeypatch):
    from core.editor import epub

    with _Janela() as t:
        j = t.j

        def quebra(*a, **k):
            raise OSError("disco cheio")

        monkeypatch.setattr(epub, "escrever", quebra)
        j.operacoes.comando_do_epubcheck = lambda: None
        try:
            j.executar("validar_epub")
        except OSError:
            pytest.fail("a validação levantou na thread da interface")
        _esperar_tarefa(t)
        assert str(j.cget("cursor")) == "", "o cursor ficou 'watch' depois da falha"
        assert any("disco cheio" in str(c) for c in t.caixas.chamadas) or j.mensagens.contem("disco cheio")


def test_a_pasta_temporaria_sai_no_fechamento():
    with _Janela() as t:
        pasta = t.j.operacoes.pasta_temporaria()
        open(os.path.join(pasta, "validar.epub"), "wb").write(b"x")
        t.caixas.pergunta_resposta = False
        t.j.fechar()
        assert not os.path.exists(pasta), "a pasta do mkdtemp ficou no disco"
