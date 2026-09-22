"""Treinamento CTC de OCR sequencial para linhas de texto.

O formato da base é ``rec_gt.txt`` com uma entrada por linha::

    images/linha_00001.png<TAB>1. e4 ♘f3

O modelo aprende a sequência inteira; não depende de um box por caractere.
"""

from __future__ import annotations

import json
import random
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, Tuple

import numpy as np
from PIL import Image


ALTURA = 48
# Limite evita que uma linha corrompida ou um scan panorâmico faça o collate
# reservar dezenas de megabytes para todos os itens do batch.
LARGURA_MAXIMA = 640

#: Acima deste CER de validação o modelo de linha **não entra em produção**:
#: nem a exportação de livro o oferece como fallback de faixa, nem o registro
#: de engines o inclui, nem o botão de preenchimento por linha o usa sem
#: avisar. A régua vem da fusão que já existe: na página de referência a
#: prosa sai a 1,3% de CER com a cadeia própria + Tesseract, e um leitor de
#: faixa acima de 15% só injeta ruído nela. O modelo treinado em 2026-09-17
#: estava em 96% — e era oferecido na exportação a um "Sim" de distância.
CER_MAXIMO_EM_PRODUCAO = 0.15


def cer_de_validacao(meta: dict) -> Optional[float]:
    """O CER de validação do peso gravado, lido dos metadados.

    `treinar` grava o peso da época de **menor perda de validação**, e é o
    CER dessa época que vale — não o da última, que pode ser pior. A chave
    `cer_validacao`, quando existe, é a medida direta (`avaliar`) e ganha do
    histórico. Sem nenhum dos dois não há como saber, e a resposta é `None`.
    """
    direto = meta.get("cer_validacao")
    if isinstance(direto, (int, float)):
        return float(direto)
    historico = [h for h in meta.get("historico") or ()
                 if isinstance(h, dict) and "cer" in h]
    if not historico:
        return None
    melhor = min(historico, key=lambda h: h.get("perda_validacao", float("inf")))
    try:
        return float(melhor["cer"])
    except (TypeError, ValueError):
        return None


def modelo_utilizavel(meta: str | Path = "text_line_model.json",
                      destino: str | Path = "text_line_model.pth",
                      cer_maximo: float = CER_MAXIMO_EM_PRODUCAO
                      ) -> Tuple[bool, str]:
    """`(True, resumo)` se o modelo de linha pode ler faixas em produção;
    `(False, motivo)` se não — peso ou metadados ausentes, sem medida de
    validação, ou CER acima de `cer_maximo`. É o portão que separa "existe
    um `.pth` no disco" de "ele lê melhor do que atrapalha"."""
    meta = Path(meta)
    destino = Path(destino)
    if not destino.exists() or not meta.exists():
        return False, "não há modelo de linha treinado (text_line_model.pth/.json)"
    try:
        dados = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, ValueError) as erro:
        return False, f"metadados do modelo de linha ilegíveis: {erro}"
    cer = cer_de_validacao(dados)
    if cer is None:
        return False, ("o modelo de linha não tem medida de validação nos "
                       "metadados; treine-o de novo ou rode a avaliação")
    if cer > cer_maximo:
        return False, (f"o modelo de linha erra {cer:.0%} dos caracteres na "
                       f"validação (limite para produção: {cer_maximo:.0%})")
    return True, f"modelo de linha com {cer:.1%} de CER na validação"


def validar_dataset(pasta: str | Path = "training_data_linhas") -> dict:
    """Valida imagens, manifesto e cobertura de caracteres antes do treino."""
    pasta = Path(pasta)
    manifesto = pasta / "rec_gt.txt"
    registros = _ler_manifesto(pasta)
    caracteres = sorted({c for _, texto in registros for c in texto})
    vazias = []
    ilegiveis = []
    for caminho, _texto in registros:
        try:
            with Image.open(caminho) as imagem:
                if imagem.width < 2 or imagem.height < 2:
                    vazias.append(str(caminho))
        except (OSError, ValueError):
            ilegiveis.append(str(caminho))
    ausentes = []
    malformadas = []
    if manifesto.exists():
        for bruto in manifesto.read_text(encoding="utf-8").splitlines():
            if not bruto.strip():
                continue
            if "\t" not in bruto:
                malformadas.append(bruto[:120])
                continue
            nome = bruto.split("\t", 1)[0]
            if not (pasta / nome).exists():
                ausentes.append(str(pasta / nome))
    return {"linhas": len(registros), "caracteres": len(caracteres),
            "alfabeto": "".join(caracteres), "vazias": vazias,
            "ilegiveis": ilegiveis, "ausentes": ausentes,
            "malformadas": malformadas}


def _torch():
    import torch
    import torch.nn as nn
    return torch, nn


def _ler_manifesto(pasta: str | Path):
    pasta = Path(pasta)
    manifesto = pasta / "rec_gt.txt"
    if not manifesto.exists():
        raise FileNotFoundError(f"Manifesto não encontrado: {manifesto}")
    registros = []
    vistos = set()
    for bruto in manifesto.read_text(encoding="utf-8").splitlines():
        if not bruto.strip() or "\t" not in bruto:
            continue
        nome, texto = bruto.split("\t", 1)
        caminho = pasta / nome
        if not caminho.exists():
            continue
        chave = str(caminho.resolve()).casefold()
        if chave in vistos:
            continue
        vistos.add(chave)
        texto = texto.strip()
        if texto:
            registros.append((caminho, texto))
    if not registros:
        raise ValueError("O manifesto não contém linhas com imagem e texto.")
    return registros


def _imagem(caminho: Path):
    if isinstance(caminho, (str, Path)):
        imagem = Image.open(caminho).convert("L")
    elif isinstance(caminho, Image.Image):
        imagem = caminho.convert("L")
    else:
        matriz = np.asarray(caminho)
        if matriz.ndim == 3:
            matriz = matriz[..., :3].mean(axis=2)
        imagem = Image.fromarray(np.asarray(matriz, dtype=np.uint8)).convert("L")
    largura, altura = imagem.size
    largura_nova = max(16, round(largura * ALTURA / max(1, altura)))
    largura_nova = min(LARGURA_MAXIMA, largura_nova)
    imagem = imagem.resize((largura_nova, ALTURA), Image.Resampling.BILINEAR)
    # Tinta branca sobre fundo preto: a rede recebe o traço com valor alto.
    matriz = 1.0 - np.asarray(imagem, dtype=np.float32) / 255.0
    return matriz


class LinhaDataset:
    def __init__(self, registros, char_to_id, augment=False, semente: int = 42):
        self.registros = registros
        self.char_to_id = char_to_id
        self.augment = augment
        # A augmentação tem o próprio gerador, semeado: com `random`/`np.random`
        # globais duas rodadas com a mesma `semente` davam modelos diferentes,
        # e "medir antes e depois" não media o código, media a sorte.
        self._rng = random.Random(semente)
        self._ruido = np.random.default_rng(semente)

    def __len__(self):
        return len(self.registros)

    def __getitem__(self, indice):
        caminho, texto = self.registros[indice]
        matriz = _imagem(caminho)
        if self.augment:
            # Variações pequenas simulam scan com contraste e ruído diferentes
            # sem alterar a transcrição nem a ordem dos caracteres.
            if self._rng.random() < 0.5:
                matriz *= self._rng.uniform(0.88, 1.12)
            if self._rng.random() < 0.25:
                matriz += self._ruido.normal(0, 0.025, matriz.shape)
            matriz = np.clip(matriz, 0.0, 1.0)
        ids = [self.char_to_id[c] for c in texto]
        # A saída da CNN tem aproximadamente largura/4 passos. O CTC precisa
        # de pelo menos um passo por caractere, especialmente em frases longas.
        largura_minima = max(16, len(ids) * 4)
        if matriz.shape[1] < largura_minima:
            from cv2 import resize, INTER_LINEAR
            matriz = resize(matriz, (largura_minima, ALTURA), interpolation=INTER_LINEAR)
        return matriz, ids


def _batch_sampler(registros, batch_size: int, semente: int):
    """Agrupa imagens de largura parecida para evitar padding excessivo."""
    from torch.utils.data import Sampler

    class SamplerPorLargura(Sampler):
        def __init__(self):
            self.indices = list(range(len(registros)))
            self.indices.sort(key=lambda i: _imagem(registros[i][0]).shape[1])
            self.batches = [self.indices[i:i + batch_size]
                            for i in range(0, len(self.indices), batch_size)]
            random.Random(semente).shuffle(self.batches)

        def __iter__(self):
            return iter(self.batches)

        def __len__(self):
            return len(self.batches)

    return SamplerPorLargura()


def _collate(amostras):
    torch, _ = _torch()
    altura = max(x.shape[0] for x, _ in amostras)
    largura = max(x.shape[1] for x, _ in amostras)
    imagens = torch.zeros((len(amostras), 1, altura, largura), dtype=torch.float32)
    comprimentos = []
    alvos = []
    for pos, (imagem, ids) in enumerate(amostras):
        h, w = imagem.shape
        imagens[pos, 0, :h, :w] = torch.from_numpy(np.ascontiguousarray(imagem))
        comprimentos.append(max(1, w // 4))
        alvos.extend(ids)
    return imagens, torch.tensor(alvos, dtype=torch.long), torch.tensor(comprimentos), \
        torch.tensor([len(ids) for _, ids in amostras], dtype=torch.long)


def _modelo(num_classes):
    torch, nn = _torch()

    class CRNN(nn.Module):
        def __init__(self):
            super().__init__()
            self.extrator = nn.Sequential(
                nn.Conv2d(1, 64, 3, padding=1), nn.ReLU(),
                nn.MaxPool2d((2, 2)),
                nn.Conv2d(64, 128, 3, padding=1), nn.ReLU(),
                nn.MaxPool2d((2, 2)),
                nn.Conv2d(128, 256, 3, padding=1), nn.ReLU(),
            )
            self.rnn = nn.LSTM(256, 128, num_layers=2, bidirectional=True,
                               dropout=0.2, batch_first=True)
            self.classificador = nn.Linear(256, num_classes)

        def forward(self, entrada):
            x = self.extrator(entrada)
            x = x.mean(dim=2).transpose(1, 2)  # B, tempo, canais
            x, _ = self.rnn(x)
            return self.classificador(x).log_softmax(2)

    return CRNN


def _decodificar(ids, id_to_char):
    saida, anterior = [], 0
    for indice in ids:
        indice = int(indice)
        if indice and indice != anterior:
            saida.append(id_to_char.get(indice, ""))
        anterior = indice
    return "".join(saida)


def _distancia(a, b):
    linha = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        nova = [i]
        for j, cb in enumerate(b, 1):
            nova.append(min(nova[-1] + 1, linha[j] + 1,
                            linha[j - 1] + (ca != cb)))
        linha = nova
    return linha[-1]


def _beam_ctc(logits, id_to_char, largura=5):
    """Decodificação CTC por prefixos, sem depender de um idioma específico."""
    import math
    beams = {("", 0): 0.0}  # (prefixo, último token), log-probabilidade
    for passo in logits:
        novos = {}
        for (prefixo, ultimo), valor in beams.items():
            for token, prob in enumerate(passo):
                logp = math.log(max(float(prob), 1e-12))
                if token == 0:
                    chave = (prefixo, 0)
                elif token == ultimo:
                    chave = (prefixo, token)
                else:
                    chave = (prefixo + id_to_char.get(token, ""), token)
                novos[chave] = max(novos.get(chave, -float("inf")), valor + logp)
        beams = dict(sorted(novos.items(), key=lambda item: item[1], reverse=True)[:largura])
    return max(beams.items(), key=lambda item: item[1])[0][0]


def treinar(pasta: str = "training_data_linhas",
            destino: str = "text_line_model.pth",
            meta: str = "text_line_model.json",
            epocas: int = 20, batch_size: int = 8, paciencia: int = 6,
            semente: int = 42,
            taxa_aprendizado: float = 1e-3, dispositivo: str = "auto",
            callback: Optional[Callable[[str], None]] = None,
            should_stop: Optional[Callable[[], bool]] = None,
            retomar: bool = True,
            validacao: str | None = None,
            alfabeto_automatico: bool = True) -> bool:
    """Treina e grava o reconhecedor sequencial de linhas."""
    torch, nn = _torch()
    # A inicialização dos pesos também obedece à semente — sem isto a mesma
    # `semente` só governava o embaralhamento, e o modelo não se repetia.
    torch.manual_seed(semente)
    diagnostico = validar_dataset(pasta)
    if (diagnostico["vazias"] or diagnostico["ilegiveis"]
            or diagnostico["ausentes"] or diagnostico["malformadas"]):
        raise ValueError("Dataset inválido: existem imagens ausentes, vazias ou ilegíveis.")
    registros = _ler_manifesto(pasta)
    suporte_charset = []
    random.Random(semente).shuffle(registros)
    # Linhas da mesma página compartilham fonte, ruído e geometria. Quando há
    # mais de uma página, separar por página mede generalização de verdade.
    grupos = {}
    for registro in registros:
        grupo = registro[0].stem.split("_linha_", 1)[0]
        grupos.setdefault(grupo, []).append(registro)
    if validacao is not None:
        validacao_diagnostico = validar_dataset(validacao)
        if (validacao_diagnostico["vazias"] or validacao_diagnostico["ilegiveis"]
                or validacao_diagnostico.get("ausentes")
                or validacao_diagnostico.get("malformadas")):
            raise ValueError("Dataset de validação inválido.")
        treino = registros
        validacao = _ler_manifesto(validacao)
        caracteres_validacao = {c for _, texto in validacao for c in texto}
        desconhecidos = caracteres_validacao - {c for _, texto in treino for c in texto}
        if desconhecidos:
            if not alfabeto_automatico:
                raise ValueError("Validação contém caracteres ausentes no treino: "
                                 + "".join(sorted(desconhecidos)))
            from core.linha_sintetica import gerar_caracteres_faltantes
            suporte_charset = gerar_caracteres_faltantes(
                desconhecidos, Path(pasta) / ".charset_sintetico", semente=semente)
            treino = treino + suporte_charset
            if callback:
                callback("Classes ausentes na validação receberam suporte "
                         f"sintético: {''.join(sorted(desconhecidos))}")
    elif len(grupos) > 1:
        nomes = list(grupos)
        random.Random(semente).shuffle(nomes)
        n_validacao = max(1, round(len(nomes) * 0.1))
        nomes_val = set(nomes[:n_validacao])
        treino = [r for r in registros if r[0].stem.split("_linha_", 1)[0] not in nomes_val]
        validacao = [r for r in registros if r[0].stem.split("_linha_", 1)[0] in nomes_val]
    else:
        corte = max(1, int(len(registros) * 0.9))
        treino, validacao = registros[:corte], registros[corte:]
    caracteres = sorted({c for _, texto in treino for c in texto}
                        | {c for _, texto in validacao for c in texto})
    char_to_id = {c: i + 1 for i, c in enumerate(caracteres)}  # 0 = blank CTC
    id_to_char = {v: k for k, v in char_to_id.items()}
    Dataset = LinhaDataset
    treino_ds = Dataset(treino, char_to_id, augment=True, semente=semente)
    val_ds = Dataset(validacao or treino[:1], char_to_id, augment=False)
    from torch.utils.data import DataLoader
    loader = DataLoader(treino_ds, batch_sampler=_batch_sampler(
        treino, batch_size, semente), collate_fn=_collate, num_workers=0)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False,
                            collate_fn=_collate, num_workers=0)
    if dispositivo == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA foi solicitado, mas não está disponível.")
    device = torch.device("cuda" if dispositivo == "cuda" or
                          (dispositivo == "auto" and torch.cuda.is_available()) else "cpu")
    modelo = _modelo(len(char_to_id) + 1)().to(device)
    otimizador = torch.optim.Adam(modelo.parameters(), lr=float(taxa_aprendizado))
    criterio = nn.CTCLoss(blank=0, zero_infinity=True)
    melhor = float("inf")
    sem_melhora = 0
    paciencia = max(1, int(paciencia))
    historico = []
    destino = Path(destino)
    meta = Path(meta)
    checkpoint_ultimo = destino.with_name(
        f"{destino.stem}_ultimo{destino.suffix}")
    retomado = False
    if retomar and (destino.exists() or checkpoint_ultimo.exists()) and meta.exists():
        try:
            meta_anterior = json.loads(meta.read_text(encoding="utf-8"))
            if meta_anterior.get("char_to_id") == char_to_id:
                checkpoint = checkpoint_ultimo if checkpoint_ultimo.exists() else destino
                modelo.load_state_dict(torch.load(checkpoint, map_location=device,
                                                  weights_only=True))
                retomado = True
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError):
            # Um checkpoint incompatível não impede um treino novo.
            retomado = False
    if callback:
        callback(f"Treino sequencial: {len(treino)} linhas, "
                 f"validação {len(validacao)} linhas, "
                 f"{len(caracteres)} caracteres, dispositivo={device}")
        callback("Checkpoint anterior retomado." if retomado else
                 "Treino iniciado do zero (alfabeto novo ou checkpoint ausente).")

    for epoca in range(1, epocas + 1):
        inicio_epoca = time.perf_counter()
        modelo.train()
        perda_treino = 0.0
        for imagens, alvos, entradas, tamanhos in loader:
            if should_stop and should_stop():
                return False
            imagens, alvos = imagens.to(device), alvos.to(device)
            saida = modelo(imagens).transpose(0, 1)
            entrada = torch.full((imagens.shape[0],), saida.shape[0], dtype=torch.long)
            # Cada imagem pode ter largura diferente; o padding não participa.
            entrada = torch.clamp(entradas, max=saida.shape[0])
            perda = criterio(saida, alvos, entrada.to(device), tamanhos.to(device))
            otimizador.zero_grad()
            perda.backward()
            torch.nn.utils.clip_grad_norm_(modelo.parameters(), 5.0)
            otimizador.step()
            perda_treino += float(perda.detach().cpu())

        modelo.eval()
        perda_val = 0.0
        linhas_exatas = 0
        erros, total_chars = 0, 0
        with torch.no_grad():
            for imagens, alvos, entradas, tamanhos in val_loader:
                offset = 0
                saida = modelo(imagens.to(device)).transpose(0, 1)
                entrada = torch.clamp(entradas, max=saida.shape[0])
                perda_val += float(criterio(saida, alvos.to(device),
                                            entrada.to(device), tamanhos.to(device)).cpu())
                previstos = saida.argmax(2).transpose(0, 1).cpu().tolist()
                alvos_cpu = alvos.tolist()
                for pos, tamanho in enumerate(tamanhos.tolist()):
                    esperado = _decodificar(alvos_cpu[offset:offset + tamanho], id_to_char)
                    previsto = _decodificar(previstos[pos][:int(entrada[pos])], id_to_char)
                    linhas_exatas += previsto == esperado
                    erros += _distancia(previsto, esperado)
                    total_chars += len(esperado)
                    offset += tamanho
        perda_treino /= max(1, len(loader))
        perda_val /= max(1, len(val_loader))
        if callback:
            callback(f"Época {epoca}/{epocas} — perda treino {perda_treino:.4f}, validação {perda_val:.4f}")
        historico.append({"epoca": epoca, "perda_treino": perda_treino,
                          "perda_validacao": perda_val,
                          "linhas_exatas": linhas_exatas,
                          "cer": erros / max(1, total_chars),
                          "segundos": time.perf_counter() - inicio_epoca})
        # O checkpoint de trabalho é separado do melhor modelo. Assim um
        # cancelamento/fechamento da UI pode continuar da última época sem
        # substituir o peso que já foi validado como melhor.
        checkpoint_ultimo.parent.mkdir(parents=True, exist_ok=True)
        temporario_ultimo = checkpoint_ultimo.with_suffix(
            checkpoint_ultimo.suffix + ".tmp")
        torch.save(modelo.state_dict(), temporario_ultimo)
        os.replace(temporario_ultimo, checkpoint_ultimo)
        if callback:
            callback(f"Validação — linhas exatas {linhas_exatas}/{len(val_ds)}, "
                     f"CER {erros / max(1, total_chars):.2%}, "
                     f"tempo {historico[-1]['segundos']:.1f}s")
        if perda_val < melhor:
            melhor = perda_val
            sem_melhora = 0
            destino.parent.mkdir(parents=True, exist_ok=True)
            temporario = destino.with_suffix(destino.suffix + ".tmp")
            torch.save(modelo.state_dict(), temporario)
            os.replace(temporario, destino)
        else:
            sem_melhora += 1
            if sem_melhora >= paciencia:
                if callback:
                    callback(f"Parada antecipada após {paciencia} epochs sem melhora.")
                break

    # O CER que vale é o da época cujo peso ficou gravado — a de menor perda
    # de validação —, e é ele que `modelo_utilizavel` lê para decidir se o
    # modelo entra em produção.
    cer_do_melhor = cer_de_validacao({"historico": historico})
    meta.write_text(json.dumps({"altura": ALTURA, "char_to_id": char_to_id,
                                "blank": 0, "arquitetura": "crnn_ctc_v1",
                                "historico": historico, "melhor_validacao": melhor,
                                "cer_validacao": cer_do_melhor,
                                "modelo": "CRNN", "versao": 1,
                                "checkpoint_ultimo": str(checkpoint_ultimo),
                                "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                "alfabeto_automatico": alfabeto_automatico,
                                "classes_suporte_sintetico": [c for _, c in suporte_charset]},
                               ensure_ascii=False, indent=2), encoding="utf-8")
    Path("text_line_training_report.json").write_text(
        json.dumps({"linhas_treino": len(treino), "linhas_validacao": len(validacao),
                    "caracteres": len(caracteres), "historico": historico,
                    "melhor_validacao": melhor}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    Path("text_line_training_report.txt").write_text(
        "Treinamento OCR sequencial\n"
        f"Linhas de treino: {len(treino)}\n"
        f"Linhas de validação: {len(validacao)}\n"
        f"Caracteres: {len(caracteres)}\n"
        f"Melhor perda de validação: {melhor:.6f}\n"
        f"Última CER: {historico[-1]['cer']:.2%}\n",
        encoding="utf-8")
    return True


def _confianca_dos_caracteres(probabilidades) -> float:
    """A confiança média **dos caracteres emitidos**, e não de todo passo do
    CTC: os passos de blank (a maioria, numa faixa larga) são quase sempre
    confiantes, e a média sobre todos eles dava 0,9 a uma leitura de lixo.
    Sem nenhum passo não-blank a confiança é zero — a linha não leu nada."""
    if not len(probabilidades):
        return 0.0
    ids = np.argmax(probabilidades, axis=1)
    emitidos = ids != 0
    if not emitidos.any():
        return 0.0
    return float(np.max(probabilidades[emitidos], axis=1).mean())


class LinhaPredictor:
    """Carrega o modelo treinado e decodifica uma linha por greedy CTC."""

    def __init__(self, destino="text_line_model.pth", meta="text_line_model.json"):
        torch, _ = _torch()
        self.torch = torch
        self.meta = json.loads(Path(meta).read_text(encoding="utf-8"))
        self.id_to_char = {int(v): k for k, v in self.meta["char_to_id"].items()}
        self.modelo = _modelo(len(self.id_to_char) + 1)()
        if self.meta.get("modelo", "CRNN") != "CRNN" or self.meta.get("versao", 1) != 1:
            raise ValueError("Metadados incompatíveis com o treinador de linhas.")
        # `weights_only=True` é o carregamento seguro, como em `core.diagrama`:
        # um `.pth` é um pickle, e sem isso abrir um arquivo de terceiro
        # executa o que estiver dentro.
        self.modelo.load_state_dict(torch.load(destino, map_location="cpu",
                                               weights_only=True))
        self.modelo.eval()

    def predict(self, imagem):
        matriz = _imagem(imagem)
        entrada = self.torch.from_numpy(np.ascontiguousarray(matriz)).float()[None, None]
        with self.torch.no_grad():
            probabilidades = self.modelo(entrada).softmax(2)[0].cpu().numpy()
            return _beam_ctc(probabilidades, self.id_to_char)

    def predict_conf(self, imagem):
        """Retorna ``(texto, confiança média dos caracteres)``."""
        matriz = _imagem(imagem)
        entrada = self.torch.from_numpy(np.ascontiguousarray(matriz)).float()[None, None]
        with self.torch.no_grad():
            probabilidades = self.modelo(entrada).softmax(2)[0].cpu().numpy()
        texto = _beam_ctc(probabilidades, self.id_to_char)
        return texto, _confianca_dos_caracteres(probabilidades)

    def predict_detalhado(self, imagem):
        """Retorna texto e confianças dos caracteres emitidos pelo CTC.

        A confiança de cada caractere é a probabilidade do token no passo em
        que ele foi emitido; blanks e repetições CTC não viram caracteres.
        """
        matriz = _imagem(imagem)
        entrada = self.torch.from_numpy(np.ascontiguousarray(matriz)).float()[None, None]
        with self.torch.no_grad():
            probabilidades = self.modelo(entrada).softmax(2)[0].cpu().numpy()
        ids = probabilidades.argmax(axis=1) if len(probabilidades) else []
        chars, confiancas, anterior = [], [], 0
        for passo, indice in enumerate(ids):
            indice = int(indice)
            if indice and indice != anterior:
                chars.append(self.id_to_char.get(indice, ""))
                confiancas.append(float(probabilidades[passo, indice]))
            anterior = indice
        texto_greedy = "".join(chars)
        texto = _beam_ctc(probabilidades, self.id_to_char)
        # Transfere confiança apenas para caracteres realmente corroborados
        # pelo caminho greedy. Inserções/alterações do beam permanecem 0.0 e
        # entram naturalmente na fila de revisão.
        from difflib import SequenceMatcher
        resultado = []
        for operacao, a1, a2, b1, b2 in SequenceMatcher(
                None, texto_greedy, texto, autojunk=False).get_opcodes():
            if operacao == "equal":
                resultado.extend(confiancas[a1:a2])
            else:
                resultado.extend([0.0] * (b2 - b1))
        return texto, resultado


def avaliar(destino: str = "text_line_model.pth",
            meta: str = "text_line_model.json",
            pasta: str = "training_data_linhas") -> dict:
    """Mede CER/WER e acerto exato do modelo nas linhas anotadas."""
    registros = _ler_manifesto(pasta)
    predictor = LinhaPredictor(destino, meta)
    total_edicoes = total_chars = total_words = total_word_errors = exatas = 0
    piores = []
    grupos = {}
    for caminho, esperado in registros:
        previsto, confianca = predictor.predict_conf(caminho)
        palavras_esperadas, palavras_previstas = esperado.split(), previsto.split()
        distancia = _distancia(previsto, esperado)
        erro_palavras = _distancia(palavras_previstas, palavras_esperadas)
        grupo = caminho.stem.split("_linha_", 1)[0]
        item = grupos.setdefault(grupo, {"linhas": 0, "exatas": 0,
                                         "edicoes": 0, "caracteres": 0,
                                         "palavras": 0, "erros_palavras": 0,
                                         "confianca_media": 0.0})
        item["linhas"] += 1
        item["exatas"] += int(previsto == esperado)
        item["edicoes"] += distancia
        item["caracteres"] += len(esperado)
        item["palavras"] += len(palavras_esperadas)
        item["erros_palavras"] += erro_palavras
        item["confianca_media"] += confianca
        exatas += int(previsto == esperado)
        total_edicoes += distancia
        total_chars += len(esperado)
        total_words += len(palavras_esperadas)
        total_word_errors += erro_palavras
        piores.append({"imagem": str(caminho), "grupo": grupo,
                       "esperado": esperado, "previsto": previsto,
                       "distancia": distancia, "cer": distancia / max(1, len(esperado)),
                       "confianca": confianca})
    piores.sort(key=lambda item: (item["distancia"], item["cer"]), reverse=True)
    for item in grupos.values():
        item["cer"] = item["edicoes"] / max(1, item["caracteres"])
        item["wer"] = item["erros_palavras"] / max(1, item["palavras"])
        item["exatas_percentual"] = item["exatas"] / max(1, item["linhas"])
        item["confianca_media"] /= max(1, item["linhas"])
    modelo_path, meta_path = Path(destino), Path(meta)
    return {"modelo": str(modelo_path), "meta": str(meta_path),
            "modelo_bytes": modelo_path.stat().st_size if modelo_path.exists() else None,
            "modelo_mtime_ns": modelo_path.stat().st_mtime_ns if modelo_path.exists() else None,
            "dataset": str(Path(pasta) / "rec_gt.txt"),
            "dataset_mtime_ns": ((Path(pasta) / "rec_gt.txt").stat().st_mtime_ns
                                  if (Path(pasta) / "rec_gt.txt").exists() else None),
            "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "linhas": len(registros),
            "exatas": exatas, "exatas_percentual": exatas / max(1, len(registros)),
            "cer": total_edicoes / max(1, total_chars),
            "wer": total_word_errors / max(1, total_words),
            "caracteres": total_chars, "palavras": total_words, "grupos": grupos,
            "piores": piores[:20]}


def salvar_avaliacao(resultado: dict, destino: str = "text_line_evaluation.json") -> Path:
    """Persiste o benchmark e a fila de amostras prioritárias para revisão."""
    caminho = Path(destino)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
    return caminho
