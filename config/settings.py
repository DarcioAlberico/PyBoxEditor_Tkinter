import copy
import json
import shutil
from pathlib import Path

from config.paths import settings_path
from core.log import logger

log = logger(__name__)

#: Marca da chave que a instância não tinha visto (distinta de `None`, que é valor).
_AUSENTE = object()


class _NaoSeLeu(Exception):
    """O arquivo existe e não abriu (`OSError`): não há o que mesclar, e gravar perderia tudo."""


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
    as chaves que esta instância mudou. Na mesma chave vale a última gravação,
    salvo quando o disco e o valor novo são dicionários: aí a mescla desce um
    nível (RG-05, R-02) — as preferências do editor são uma chave só, `editor`,
    e dois editores abertos regravavam-na inteira, cada um com a sua cópia.

    O arquivo que existe e não abre (`OSError`) não é regravado: sem o que
    mesclar, a gravação trocaria todas as preferências pelo que esta instância
    sabe. O que não se lê como JSON, esse sim, é trocado, e a cópia fica ao lado
    (`settings.json.corrompido`).
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
        try:
            lido = self._ler()
        except _NaoSeLeu as erro:
            log.warning("as preferências não se leram (%s): o programa segue com as de fábrica, "
                        "e o arquivo não é regravado enquanto não abrir", erro)
            lido = {}
        if lido is None:
            log.warning("%s não é um JSON de preferências: vale o de fábrica, e o arquivo vai "
                        "para %s na primeira gravação", self.path, self._corrompido().name)
            lido = {}
        self.data = lido
        self._visto = copy.deepcopy(self.data)

    def save(self):
        try:
            no_disco = self._ler()
        except _NaoSeLeu as erro:
            log.warning("preferências não gravadas: o arquivo não se leu (%s), e gravá-lo "
                        "agora trocaria as outras pelo que esta janela sabe", erro)
            return
        if no_disco is None:
            # Não se lê como JSON: não há o que preservar dele, e vai o que esta
            # instância sabe, como antes da mescla — com a cópia guardada ao lado.
            self._guardar_corrompido()
            no_disco = dict(self.data)
        for chave, valor in self.data.items():
            anterior = self._visto.get(chave, _AUSENTE)
            if anterior is not _AUSENTE and anterior == valor:
                continue
            atual = no_disco.get(chave, _AUSENTE)
            if isinstance(valor, dict) and isinstance(atual, dict):
                no_disco[chave] = _mesclar(atual, anterior if isinstance(anterior, dict) else {}, valor)
            else:
                no_disco[chave] = valor
        for chave in self._visto.keys() - self.data.keys():
            no_disco.pop(chave, None)
        # Temporário único: a janela principal e o `appy.py --editor` gravavam o mesmo
        # `settings.json.tmp`, um por cima do outro (RG-03).
        from core.escrita_atomica import gravar_atomico
        gravar_atomico(self.path, json.dumps(no_disco, indent=2, ensure_ascii=False) + "\n")
        self.data = no_disco
        self._visto = copy.deepcopy(no_disco)

    def _ler(self) -> dict | None:
        """O arquivo agora: `{}` se ele não existe, `None` se não se lê como objeto JSON.

        Levanta `_NaoSeLeu` quando ele existe e não abre: a falta de permissão não é
        JSON quebrado (RG-05, R-02).
        """
        if not self.path.is_file():
            return {}
        try:
            texto = self.path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return None
        except OSError as erro:
            raise _NaoSeLeu(erro) from erro
        try:
            dados = json.loads(texto)
        except ValueError:
            return None
        return dados if isinstance(dados, dict) else None

    def _corrompido(self) -> Path:
        return self.path.with_name(self.path.name + ".corrompido")

    def _guardar_corrompido(self) -> None:
        try:
            shutil.copyfile(self.path, self._corrompido())
        except OSError as erro:
            log.warning("o %s ilegível não foi copiado para %s antes de regravado: %s",
                        self.path.name, self._corrompido().name, erro)
        else:
            log.warning("%s não era JSON; a cópia ficou em %s", self.path.name, self._corrompido())

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def set(self, key: str, value):
        self.data[key] = value


def _mesclar(no_disco: dict, visto: dict, novo: dict) -> dict:
    """Um nível abaixo: do `novo`, só as subchaves que mudaram desde o `visto`; o resto, do disco."""
    mesclado = dict(no_disco)
    for sub, valor in novo.items():
        if sub not in visto or visto[sub] != valor:
            mesclado[sub] = valor
    for sub in visto.keys() - novo.keys():
        mesclado.pop(sub, None)
    return mesclado
