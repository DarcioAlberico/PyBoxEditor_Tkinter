"""A escrita atômica única (RG-03, R-01 da revisão geral 2).

Cada gravador gravava do seu jeito: `.tmp` de nome fixo — que a janela principal e o
`appy.py --editor`, processos diferentes, disputavam no mesmo `settings.json.tmp` —,
gravação direta no destino (um erro no meio zerava o `.box`), `mkstemp` sem `fsync`.
`core.escrita_atomica` é o lugar único: temporário único na mesma pasta, `fsync`,
`os.replace` com nova tentativa breve quando o Windows o recusa porque outro processo lê
o arquivo, LF no texto, modo do destino preservado, e o temporário apagado na falha.
"""

import os
import sys
import threading
from pathlib import Path

import pytest

from core import escrita_atomica as ea


def _sobras(pasta: Path, destino: Path) -> list[str]:
    return sorted(p.name for p in pasta.iterdir() if p != destino)


def test_grava_texto_com_lf_e_bytes(tmp_path):
    destino = tmp_path / "a.txt"
    ea.gravar_atomico(destino, "um\ndois\n")
    assert destino.read_bytes() == b"um\ndois\n"
    ea.gravar_atomico(destino, b"\x00\x01")
    assert destino.read_bytes() == b"\x00\x01"
    assert _sobras(tmp_path, destino) == []


def test_falha_no_meio_deixa_o_original_e_nenhum_temporario(tmp_path):
    destino = tmp_path / "livro.box"
    destino.write_text("original", encoding="utf-8")
    with pytest.raises(RuntimeError):
        with ea.escrita_atomica(destino) as f:
            f.write("meio arquivo")
            raise RuntimeError("queda no meio")
    assert destino.read_text(encoding="utf-8") == "original"
    assert _sobras(tmp_path, destino) == []


def test_falha_no_fsync_deixa_o_original(tmp_path, monkeypatch):
    destino = tmp_path / "settings.json"
    destino.write_text("{}", encoding="utf-8")

    def sem_disco(_fd):
        raise OSError("disco cheio")

    monkeypatch.setattr(ea.os, "fsync", sem_disco)
    with pytest.raises(OSError):
        ea.gravar_atomico(destino, '{"novo": 1}')
    assert destino.read_text(encoding="utf-8") == "{}"
    assert _sobras(tmp_path, destino) == []


def test_o_caminho_temporario_serve_a_quem_grava_por_nome(tmp_path):
    destino = tmp_path / "modelo.pth"
    destino.write_bytes(b"velho")
    with ea.caminho_temporario(destino) as tmp:
        assert Path(tmp).parent == tmp_path and Path(tmp) != destino
        Path(tmp).write_bytes(b"novo")            # como faria o torch.save(…, tmp)
        assert destino.read_bytes() == b"velho"   # nada publicado antes do fim
    assert destino.read_bytes() == b"novo"
    with pytest.raises(ValueError):
        with ea.caminho_temporario(destino) as tmp:
            Path(tmp).write_bytes(b"pela metade")
            raise ValueError("a biblioteca levantou")
    assert destino.read_bytes() == b"novo"
    assert _sobras(tmp_path, destino) == []


def test_sem_duravel_nao_paga_o_fsync(tmp_path, monkeypatch):
    chamadas = []
    monkeypatch.setattr(ea.os, "fsync", chamadas.append)
    ea.gravar_atomico(tmp_path / "cache.json", "{}", duravel=False)
    assert chamadas == []
    ea.gravar_atomico(tmp_path / "dado.json", "{}")
    assert len(chamadas) == 1


def test_replace_recusado_pelo_windows_tenta_de_novo(tmp_path, monkeypatch):
    original = os.replace
    recusas = []

    def ocupado(origem, destino):
        if len(recusas) < 2:
            recusas.append(destino)
            raise PermissionError(13, "o arquivo está aberto por outro processo")
        return original(origem, destino)

    monkeypatch.setattr(ea.os, "replace", ocupado)
    monkeypatch.setattr(ea, "_PAUSA", 0.001)
    destino = tmp_path / "settings.json"
    ea.gravar_atomico(destino, "{}")
    assert len(recusas) == 2 and destino.read_text(encoding="utf-8") == "{}"


def test_replace_sempre_recusado_desiste_e_limpa(tmp_path, monkeypatch):
    def ocupado(origem, destino):
        raise PermissionError(13, "aberto")

    monkeypatch.setattr(ea.os, "replace", ocupado)
    monkeypatch.setattr(ea, "_PAUSA", 0.001)
    destino = tmp_path / "x.json"
    with pytest.raises(PermissionError):
        ea.gravar_atomico(destino, "{}")
    assert list(tmp_path.iterdir()) == []


def test_dois_gravadores_ao_mesmo_tempo_nao_dividem_o_temporario(tmp_path):
    destino = tmp_path / "settings.json"
    vistos, barreira = [], threading.Barrier(2)

    def gravar(texto):
        with ea.caminho_temporario(destino) as tmp:
            vistos.append(tmp)
            barreira.wait(timeout=5)
            Path(tmp).write_text(texto, encoding="utf-8")

    ts = [threading.Thread(target=gravar, args=(t,)) for t in ("um", "dois")]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert len(set(vistos)) == 2
    assert destino.read_text(encoding="utf-8") in ("um", "dois")
    assert _sobras(tmp_path, destino) == []


def test_cria_a_pasta_do_destino(tmp_path):
    destino = tmp_path / "nova" / "pasta" / "a.json"
    ea.gravar_atomico(destino, "{}")
    assert destino.is_file()


@pytest.mark.skipif(sys.platform.startswith("win"), reason="o Windows só guarda o bit de leitura")
def test_o_modo_do_destino_e_preservado_e_o_novo_nao_sai_0600(tmp_path):
    existente = tmp_path / "a.json"
    existente.write_text("{}", encoding="utf-8")
    os.chmod(existente, 0o640)
    ea.gravar_atomico(existente, '{"a": 1}')
    assert existente.stat().st_mode & 0o777 == 0o640
    novo = tmp_path / "b.epub"
    ea.gravar_atomico(novo, b"zip")
    assert novo.stat().st_mode & 0o777 == 0o666 & ~ea._UMASK
