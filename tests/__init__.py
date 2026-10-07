"""Testes do projeto, importáveis como pacote durante a suíte.

Parte da suíte histórica usa ``from conftest import ...``; o alias preserva
esse contrato quando os testes passam a ser resolvidos como ``tests.*``.
"""

import sys

from . import conftest as _conftest

sys.modules.setdefault("conftest", _conftest)
