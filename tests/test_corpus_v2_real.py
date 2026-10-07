from pathlib import Path

import pytest

from core.ocr_corpus import carregar_manifesto, executar_corpus
from core.ocr_holdout import selecionar_holdout


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "benchmarks" / "corpus_v2.json"

#: Os PDFs-fonte do corpus ficam fora do git — são livros com direito autoral, pela
#: mesma razão de `/PDF/` (ver `.gitignore`). O manifesto, as referências, as predições
#: e as quatro imagens de página estão no git, mas `require_files=True` e a rodada de
#: verdade pedem os PDFs: num clone novo e na CI estes dois testes pulam, como os que
#: dependem do `custom_model.pth`.
FONTES = [ROOT / "benchmarks" / "corpus_v2" / "source" / nome
          for nome in ("aagaard.pdf", "nunn.pdf", "yusupov.pdf")]
pytestmark = pytest.mark.skipif(
    not all(fonte.is_file() for fonte in FONTES),
    reason="os PDFs-fonte de benchmarks/corpus_v2/source/ ficam fora do git")


def test_corpus_real_v2_tem_hash_arquivos_e_holdout_isolado():
    manifesto = carregar_manifesto(MANIFEST, validate_paths=True, require_files=True)
    selecao = selecionar_holdout(MANIFEST)

    assert manifesto.corpus_sha256
    assert len(selecao.pages) == 4
    assert {documento.split for documento in manifesto.documents} == {"holdout"}
    assert all(page.image.is_file() and page.reference.is_file()
               for page in selecao.pages)


def test_corpus_real_v2_reproduz_a_baseline_de_texto():
    resultado = executar_corpus(MANIFEST, engine="current", split="holdout")

    assert resultado.pages == 4
    assert resultado.text.cer < 0.05
    assert resultado.words.cer < 0.05
