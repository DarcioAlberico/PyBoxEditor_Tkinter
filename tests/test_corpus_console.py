import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))


def test_a_rodada_configura_saida_utf8_para_o_console_do_windows():
    import rodada_do_corpus

    class Stream:
        def __init__(self):
            self.chamadas = []

        def reconfigure(self, **kwargs):
            self.chamadas.append(kwargs)

    stream = Stream()
    rodada_do_corpus.configurar_saida_terminal(stream)

    assert stream.chamadas == [{"encoding": "utf-8", "errors": "replace"}]
