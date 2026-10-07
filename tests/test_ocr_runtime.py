import time

import numpy as np
import pytest

from core.ocr_result import PageResult
from core.ocr_runtime import (
    BatchProcessor,
    CancellationToken,
    OCRCache,
    OCRCancelled,
    Profiler,
    RuntimeConfig,
    configuracao_cache,
    fingerprint,
    modelo_assinatura,
)


def _processor(item, token):
    token.raise_if_cancelled()
    return PageResult(str(item), text=f"page {item}")


def test_fingerprint_e_cache_sao_estaveis(tmp_path):
    a = np.zeros((4, 5), np.uint8)
    assert fingerprint(a) == fingerprint(a.copy())
    assert fingerprint(a) != fingerprint(np.ones((4, 5), np.uint8))
    cache = OCRCache(tmp_path)
    resultado = PageResult("p1", text="ok")
    chave = fingerprint(a)
    cache.save(chave, resultado)
    assert cache.load(chave).text == "ok"


def test_cache_poda_entradas_por_idade_e_retorna_relatorio(tmp_path):
    cache = OCRCache(tmp_path)
    velho = fingerprint("velho")
    novo = fingerprint("novo")
    cache.save(velho, PageResult("p-velho", text="old"))
    cache.save(novo, PageResult("p-novo", text="new"))
    (tmp_path / f"{velho}.json").touch()
    (tmp_path / f"{novo}.json").touch()
    import os
    os.utime(tmp_path / f"{velho}.json", (100.0, 100.0))
    os.utime(tmp_path / f"{novo}.json", (950.0, 950.0))

    relatorio = cache.prune(max_age_seconds=100, now=1000.0)

    assert not (tmp_path / f"{velho}.json").exists()
    assert (tmp_path / f"{novo}.json").exists()
    assert relatorio["removed"] == 1
    assert relatorio["remaining"] == 1


def test_cache_poda_por_tamanho_remove_mais_antigos_e_ignora_temporario(tmp_path):
    cache = OCRCache(tmp_path)
    chaves = [fingerprint(item) for item in ("a", "b", "c")]
    for indice, chave in enumerate(chaves):
        cache.save(chave, PageResult(f"p{indice}", text="x" * (indice + 1)))
        (tmp_path / f"{chave}.json").touch()
        import os
        os.utime(tmp_path / f"{chave}.json", (100 + indice, 100 + indice))
    temporario = tmp_path / "incompleto.tmp"
    temporario.write_text("nao apagar", encoding="utf-8")
    limite = (tmp_path / f"{chaves[-1]}.json").stat().st_size

    relatorio = cache.prune(max_bytes=limite)

    assert relatorio["remaining"] == 1
    assert (tmp_path / f"{chaves[-1]}.json").exists()
    assert temporario.exists()


def test_batch_aplica_poda_configurada_ao_inicializar(tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    chave = fingerprint("antigo")
    arquivo = cache_dir / f"{chave}.json"
    OCRCache(cache_dir).save(chave, PageResult("p-antigo", text="old"))
    import os
    os.utime(arquivo, (100.0, 100.0))

    batch = BatchProcessor(
        _processor,
        config=RuntimeConfig(cache_dir=cache_dir,
                             cache_prune_max_age_seconds=100),
    )

    assert not arquivo.exists()
    assert batch.cache_prune_report is not None
    assert batch.cache_prune_report["removed"] == 1


def test_batch_processa_em_ordem_e_reaproveita_cache(tmp_path):
    chamadas = []

    def processor(item, token):
        chamadas.append(item)
        return _processor(item, token)

    config = RuntimeConfig(cache_dir=tmp_path / "cache")
    batch = BatchProcessor(processor, config=config)
    primeiro = batch.process([1, 2, 3])
    segundo = batch.process([1, 2, 3])
    assert [item.page_id for item in primeiro.results] == ["1", "2", "3"]
    assert segundo.cached == 3
    assert chamadas == [1, 2, 3]


def test_batch_isola_erro_e_notifica_progresso():
    progresso = []

    def processor(item, token):
        if item == 2:
            raise RuntimeError("falha de página")
        return _processor(item, token)

    resultado = BatchProcessor(processor).process([1, 2, 3],
                                                  progress=lambda a, b: progresso.append((a, b)))
    assert [item.page_id for item in resultado.results] == ["1", "3"]
    assert "1" in resultado.errors
    assert progresso == [(1, 3), (2, 3)]


def test_cancelamento_cooperativo():
    token = CancellationToken()
    token.cancel()
    with pytest.raises(OCRCancelled):
        token.raise_if_cancelled()
    resultado = BatchProcessor(_processor).process([1, 2], token=token)
    assert resultado.cancelled is True


def test_workers_preservam_ordem():
    def lento(item, token):
        time.sleep(0.01 if item == 1 else 0)
        return _processor(item, token)
    resultado = BatchProcessor(lento, config=RuntimeConfig(workers=2)).process([1, 2, 3])
    assert [item.page_id for item in resultado.results] == ["1", "2", "3"]


def test_profiler_registra_tempo_e_memoria():
    profiler = Profiler()
    with profiler.stage("step"):
        _ = [0] * 1000
    dados = profiler.to_dict()
    assert dados["stages"][0]["name"] == "step"
    assert dados["stages"][0]["seconds"] >= 0


def test_configuracao_cache_inclui_modelo_idioma_dpi_e_variante(tmp_path):
    modelo = tmp_path / "modelo.pth"
    modelo.write_bytes(b"v1")
    config = configuracao_cache(engine="trained_line", idioma="pt", dpi=300,
                                preprocessamento="adaptive", variante="gray",
                                modelos=[modelo])
    assert config["idioma"] == "pt" and config["dpi"] == 300
    assert config["preprocessamento"] == "adaptive"
    assert config["modelos"][0]["size"] == 2
    chave1 = fingerprint(np.zeros((2, 2), np.uint8), config=config)
    modelo.write_bytes(b"v2-new")
    config2 = {**config, "modelos": [modelo_assinatura(modelo)]}
    assert chave1 != fingerprint(np.zeros((2, 2), np.uint8), config=config2)
