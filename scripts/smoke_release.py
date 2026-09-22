"""Smoke test estático do wheel de release — e, com `--editor`, o editor de livros de ponta a ponta.

    python scripts/smoke_release.py dist/pyboxeditor-0.1.0-py3-none-any.whl [--install] [--editor]

`--editor` (ED-13, AC-ED13-4) é um passo **a mais** sobre o wheel posicional: escreve um
livro sintético (`tests/editor_livros.livro_completo`) num EPUB temporário e roda
`appy.py --editor <livro> --fechar-apos 1 --diagnostico-modulos` em subprocesso, com
`timeout=30`, exigindo código 0 — o editor abre, desenha o capítulo e fecha sozinho, sem
carregar o OCR (DEC-07: `torch`, `easyocr`, `cv2`, `numpy`, `fitz`, `ui.main_window`
fora). A saída diz o que carregou.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PESADOS_PROIBIDOS = ("torch", "easyocr", "cv2", "numpy", "fitz", "ui.main_window")


def smoke_editor(timeout: float = 30.0, python: str = sys.executable) -> dict:
    """Roda o editor num subprocesso sobre um EPUB sintético; devolve `{"ok", "codigo", "modulos", "saida"}`."""
    sys.path.insert(0, RAIZ)
    sys.path.insert(0, os.path.join(RAIZ, "tests"))
    import editor_livros
    from core.editor import epub

    pasta = tempfile.mkdtemp(prefix="pbe-smoke-editor-")
    caminho = os.path.join(pasta, "smoke.epub")
    epub.escrever(editor_livros.livro_completo(), caminho)
    ambiente = dict(os.environ, PYBOXEDITOR_SETTINGS=os.path.join(pasta, "settings.json"))
    try:
        processo = subprocess.run([python, "appy.py", "--editor", caminho, "--fechar-apos", "1",
                                   "--diagnostico-modulos"], capture_output=True, text=True, cwd=RAIZ,
                                  timeout=timeout, env=ambiente, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired as erro:
        return {"ok": False, "codigo": None, "modulos": [], "saida": f"o editor não fechou em {timeout:g} s: {erro}"}
    linha = next((li for li in (processo.stdout or "").splitlines() if li.startswith("modulos pesados carregados:")),
                 "")
    modulos = [m for m in PESADOS_PROIBIDOS if f"'{m}'" in linha]
    ok = processo.returncode == 0 and not modulos
    return {"ok": ok, "codigo": processo.returncode, "modulos": modulos,
            "saida": (processo.stdout or "")[-2000:] + (processo.stderr or "")[-2000:]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Valida conteúdo mínimo de um wheel")
    parser.add_argument("wheel")
    parser.add_argument("--install", action="store_true",
                        help="instala em venv temporário e importa os módulos")
    parser.add_argument("--editor", action="store_true",
                        help="roda também o editor de livros (appy.py --editor) sobre um livro sintético")
    args = parser.parse_args(argv)
    from core.ocr_phase8 import smoke_test_installation, smoke_test_wheel

    smoke = smoke_test_installation if args.install else smoke_test_wheel
    report = smoke(args.wheel, required_modules=(
        "core.editorial_model", "core.ocr_phase7", "core.ocr_phase8",
    ))
    resultado = {"valid": report.valid, "errors": list(report.errors)}
    if args.editor:
        editor = smoke_editor()
        resultado["editor"] = {"ok": editor["ok"], "codigo": editor["codigo"], "modulos_pesados": editor["modulos"]}
        if not editor["ok"]:
            resultado["errors"].append("editor: " + (editor["saida"][-500:] or f"código {editor['codigo']}"))
        resultado["valid"] = resultado["valid"] and editor["ok"]
    print(json.dumps(resultado, ensure_ascii=False))
    return 0 if resultado["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
