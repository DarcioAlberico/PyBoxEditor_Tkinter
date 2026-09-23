import copy
import json
from pathlib import Path

from config.paths import settings_path


class Settings:
    """
    Configuração simples persistida em JSON.
    Ex.: tesseract_path, último diretório, etc.

    **Mais de uma instância grava o mesmo arquivo:** a janela principal e o
    editor de livros têm cada uma a sua, e o `appy.py --editor` é outro
    processo. Por isso `save()` não despeja `data` inteiro — isso devolvia ao
    disco a foto lida na construção e desfazia o que a outra instância tinha
    gravado no meio-tempo: os recentes do editor sumiam quando a principal
    guardava o último diretório, e o layout do editor, gravado ao fechar,
    trazia de volta o diretório velho. Ele relê o arquivo e aplica por cima só
    as chaves que esta instância mudou. Na mesma chave vale a última gravação
    — e as preferências do editor são uma chave só, `editor`.
    """
    def __init__(self, path: str | None = None):
        if path is None:
            self.path = settings_path()
        else:
            self.path = Path(path)

        self.data: dict = {}
        #: O que esta instância viu no disco pela última vez, lendo ou gravando.
        #: É contra ele que `save()` sabe o que mudou aqui — inclusive o que se
        #: mexeu por dentro do dict que `get` devolve, sem passar por `set`.
        self._visto: dict = {}
        self.load()

    def load(self):
        lido = self._ler()
        self.data = lido if lido is not None else {}
        self._visto = copy.deepcopy(self.data)

    def save(self):
        no_disco = self._ler()
        if no_disco is None:
            # O arquivo existe e não se lê: não há o que preservar dele, e vai
            # o que esta instância sabe, como antes da mescla.
            no_disco = dict(self.data)
        for chave, valor in self.data.items():
            if chave not in self._visto or self._visto[chave] != valor:
                no_disco[chave] = valor
        for chave in self._visto.keys() - self.data.keys():
            no_disco.pop(chave, None)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporario = self.path.with_name(self.path.name + ".tmp")
        temporario.write_text(
            json.dumps(no_disco, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporario.replace(self.path)
        self.data = no_disco
        self._visto = copy.deepcopy(no_disco)

    def _ler(self) -> dict | None:
        """O arquivo agora: `{}` se ele não existe, `None` se não se lê como objeto JSON."""
        if not self.path.is_file():
            return {}
        try:
            dados = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return dados if isinstance(dados, dict) else None

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def set(self, key: str, value):
        self.data[key] = value
