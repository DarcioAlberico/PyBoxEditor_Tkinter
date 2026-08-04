import os
import glob
import json
import random
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader, Subset, WeightedRandomSampler
import cv2
import numpy as np
from core.neural_model import SimpleCNN, get_device
from core.learner import folder_to_char
from core.avaliacao import (SEMENTE_PADRAO, avaliar, dividir_estratificado,
                            gravar_relatorio, salvar_amostras_erradas,
                            texto_do_relatorio)


# -------------------------------------------------------
# Data Augmentation Functions
# -------------------------------------------------------

def augment_rotate(img, max_angle=15):
    """Rotaciona a imagem aleatoriamente."""
    angle = random.uniform(-max_angle, max_angle)
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(img, M, (w, h), borderValue=255)

def augment_shift(img, max_shift=3):
    """Translada (desloca) a imagem em X e Y."""
    dx = random.randint(-max_shift, max_shift)
    dy = random.randint(-max_shift, max_shift)
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(img, M, (img.shape[1], img.shape[0]), borderValue=255)

def augment_noise(img, intensity=15):
    """Adiciona ruido gaussiano."""
    noise = np.random.normal(0, intensity, img.shape).astype(np.float32)
    noisy = img.astype(np.float32) + noise
    return np.clip(noisy, 0, 255).astype(np.uint8)

def augment_scale(img, scale_range=(0.8, 1.2)):
    """Redimensiona e recorta/padda de volta para o tamanho original."""
    h, w = img.shape[:2]
    scale = random.uniform(*scale_range)
    new_w, new_h = int(w * scale), int(h * scale)
    if new_w < 1 or new_h < 1:
        return img
    resized = cv2.resize(img, (new_w, new_h))
    
    # Pad ou crop de volta para (w, h)
    canvas = np.full((h, w), 255, dtype=np.uint8)
    
    # Centro
    cx = (w - new_w) // 2
    cy = (h - new_h) // 2
    
    # Calcular regioes de copia
    src_x1 = max(0, -cx)
    src_y1 = max(0, -cy)
    src_x2 = min(new_w, w - cx)
    src_y2 = min(new_h, h - cy)
    
    dst_x1 = max(0, cx)
    dst_y1 = max(0, cy)
    dst_x2 = dst_x1 + (src_x2 - src_x1)
    dst_y2 = dst_y1 + (src_y2 - src_y1)
    
    if dst_x2 > dst_x1 and dst_y2 > dst_y1:
        canvas[dst_y1:dst_y2, dst_x1:dst_x2] = resized[src_y1:src_y2, src_x1:src_x2]
    
    return canvas

def augment_erode_dilate(img):
    """Aplica erosao ou dilatacao aleatoria (engrossa ou afina tracos)."""
    kernel = np.ones((2, 2), np.uint8)
    if random.random() > 0.5:
        return cv2.erode(img, kernel, iterations=1)
    else:
        return cv2.dilate(img, kernel, iterations=1)

def augment_brightness(img, delta_range=(-30, 30)):
    """Altera brilho aleatoriamente."""
    delta = random.randint(*delta_range)
    return np.clip(img.astype(np.int16) + delta, 0, 255).astype(np.uint8)

def apply_random_augmentation(img):
    """Aplica uma combinacao aleatoria de augmentacoes."""
    result = img.copy()
    
    # Cada augmentacao tem uma probabilidade de ser aplicada
    if random.random() > 0.3:
        result = augment_rotate(result)
    if random.random() > 0.4:
        result = augment_shift(result)
    if random.random() > 0.5:
        result = augment_noise(result)
    if random.random() > 0.5:
        result = augment_scale(result)
    if random.random() > 0.6:
        result = augment_erode_dilate(result)
    if random.random() > 0.5:
        result = augment_brightness(result)
    
    return result


# -------------------------------------------------------
# Balanceamento
# -------------------------------------------------------

# Abaixo deste número a classe não é excluída — é apenas reportada. Excluir era
# a proposta original da SPEC §5.3, e conferindo quais classes cairiam ficou
# claro que não servia: nesta base as 33 classes com menos de 10 amostras
# incluem 'K' (6), 'Q' (5) e os símbolos de anotação de xadrez ± ∓ ∞ □ ■ △ ▼.
# São raras porque aparecem pouco no texto, não porque sejam lixo — e são
# justamente vocabulário do domínio.
MIN_AMOSTRAS_POR_CLASSE = 10

# Teto de repetição por amostra num epoch. É uma trava, não o mecanismo
# principal: no modo padrão ("sqrt") a amostra mais repetida da base real chega
# a 63 sorteios e o teto mal encosta nela. Ele existe para o modo "inverso", em
# que a única imagem de 'X' seria sorteada ~1.235 vezes por epoch — o modelo
# decoraria um PNG —, e para bases degeneradas de qualquer modo.
TETO_DE_REPETICAO = 50.0


def contar_por_classe(labels, num_classes: int) -> np.ndarray:
    return np.bincount(np.asarray(labels, dtype=np.int64), minlength=num_classes)


def pesos_de_amostragem(contagens, labels, modo: str = "sqrt",
                        teto: float = TETO_DE_REPETICAO) -> np.ndarray:
    """
    Peso de cada amostra para o `WeightedRandomSampler`.

    `modo`:
      - "inverso": 1/n — todas as classes com a mesma chance por epoch.
      - "sqrt":    1/sqrt(n) — compensa parcialmente. Padrão.
      - "nenhum":  peso igual, equivalente a `shuffle=True`.

    O teto limita quantas vezes, em média, uma amostra pode ser sorteada num
    epoch. É o que impede uma classe de 1 amostra de virar 1/103 do treino.
    """
    contagens = np.asarray(contagens, dtype=np.float64)
    labels = np.asarray(labels, dtype=np.int64)
    n = np.maximum(contagens, 1.0)

    if modo == "nenhum":
        por_classe = np.ones_like(n)
    elif modo == "inverso":
        por_classe = 1.0 / n
    elif modo == "sqrt":
        por_classe = 1.0 / np.sqrt(n)
    else:
        raise ValueError(f"modo de balanceamento desconhecido: {modo!r}")

    pesos = por_classe[labels]

    if teto and teto > 0 and len(pesos):
        # Repetições esperadas de uma amostra num epoch de len(labels) sorteios.
        # Baixar os pesos que estouram o teto reduz a soma, o que empurra todos
        # os outros para cima — inclusive os que acabaram de ser cortados. Por
        # isso o corte é iterado até estabilizar; uma passada só deixa o teto
        # efetivo bem acima do pedido (medido: 72 repetições para um teto de 50).
        for _ in range(50):
            excesso = (pesos / pesos.sum() * len(pesos)) / teto
            if excesso.max() <= 1.0 + 1e-9:
                break
            pesos = np.where(excesso > 1.0, pesos / excesso, pesos)

    return pesos


# -------------------------------------------------------
# Dataset with Augmentation
# -------------------------------------------------------

class CharDataset(Dataset):
    """
    Amostras originais em uint8 32x32; a augmentation é aplicada sob demanda.

    Antes o construtor gerava 8 variantes de cada amostra e guardava tudo em
    float32. Na base real isso são 127.263 originais virando 1.145.367 arrays de
    4 KB: **4,7 GB de RAM** e ~9,5 min por epoch, numa máquina de 16 GB. Só o
    original em uint8 custa 124 MB, e augmentar na hora sai por 53 µs/amostra
    (7 s por epoch de 127 mil).

    A mudança não é só de memória, e é o que faz o balanceamento funcionar: com
    a augmentation congelada no construtor, o `WeightedRandomSampler` sorteia
    sempre as **mesmas 9 imagens** de uma classe rara, centenas de vezes. Sob
    demanda, cada sorteio produz uma variante nova.
    """

    def __init__(self, data_dir="training_data", augment=True):
        # `augment_factor` saiu junto com as cópias congeladas: quantas
        # variantes existem por amostra passou a ser função de quantas vezes o
        # sampler a sorteia, não de um número fixo no construtor.
        self.data = np.zeros((0, 32, 32), dtype=np.uint8)
        self.labels = []
        self.label_map = {}    # nome da pasta -> int
        self.idx_to_char = {}  # int -> caractere
        self.augment = augment
        self.contagens = np.zeros(0, dtype=np.int64)
        self.classes_raras = []    # [(pasta, caractere, n)] — reportadas, não excluídas
        self.classes_vazias = []   # pastas sem nenhuma amostra legível

        self.load_data(data_dir)

    def load_data(self, data_dir):
        if not os.path.exists(data_dir):
            return

        # Pastas com '_' na frente não são classes. A `_quarentena` do
        # dataset_check (F1.4) entrava como classe de índice 0 — antes de todas
        # as outras, na ordenação — e deslocava o mapa inteiro. Como ela só
        # nasce quando um PNG é posto em quarentena, o modelo seguinte sairia
        # errado sem nada aparecer.
        classes = sorted([d for d in os.listdir(data_dir)
                          if os.path.isdir(os.path.join(data_dir, d))
                          and not d.startswith("_")])

        amostras = []
        for char_name in classes:
            folder_path = os.path.join(data_dir, char_name)
            do_grupo = []
            for img_path in glob.glob(os.path.join(folder_path, "*.png")):
                try:
                    # open() + imdecode em vez de cv2.imread: no Windows o
                    # imread falha em caminho não-ASCII e devolve None, o mesmo
                    # que devolveria para um PNG corrompido (ver dataset_check).
                    with open(img_path, "rb") as f:
                        dados = f.read()
                    img = cv2.imdecode(np.frombuffer(dados, dtype=np.uint8),
                                       cv2.IMREAD_GRAYSCALE)
                    if img is None:
                        continue
                    do_grupo.append(cv2.resize(img, (32, 32)))
                except Exception as e:
                    print(f"Skipping {img_path}: {e}")

            # Pasta vazia não ganha índice. A `lower_ä` da base real ficou vazia
            # (o cv2.imwrite descartava as amostras em silêncio, F1.4) e mesmo
            # assim ocupava uma saída da rede: um neurônio que nunca podia estar
            # certo, competindo com os outros em toda predição.
            if not do_grupo:
                self.classes_vazias.append(char_name)
                continue

            idx = len(self.label_map)
            real_char = folder_to_char(char_name)
            self.label_map[char_name] = idx
            self.idx_to_char[idx] = real_char

            amostras.extend(do_grupo)
            self.labels.extend([idx] * len(do_grupo))

            if len(do_grupo) < MIN_AMOSTRAS_POR_CLASSE:
                self.classes_raras.append((char_name, real_char, len(do_grupo)))

        if amostras:
            self.data = np.stack(amostras)
        self.contagens = contar_por_classe(self.labels, len(self.label_map))

    def __len__(self):
        return len(self.data)

    # Fração dos sorteios que devolve a amostra intacta. O desenho antigo
    # guardava 1 original para cada 8 cópias aumentadas, então 1/9 do treino era
    # imagem limpa — e é imagem limpa que chega na hora de predizer. Augmentar
    # 100% dos sorteios trocaria um problema por outro: `apply_random_augmentation`
    # deixa passar intacto só 0,9% das vezes (é o produto das seis probabilidades).
    FRACAO_SEM_AUGMENTATION = 1.0 / 9.0

    def __getitem__(self, idx):
        img = self.data[idx]
        if self.augment and random.random() >= self.FRACAO_SEM_AUGMENTATION:
            img = apply_random_augmentation(img)
        tensor = torch.from_numpy(np.ascontiguousarray(img)).float().div_(255.0)
        return tensor.unsqueeze(0), self.labels[idx]


# -------------------------------------------------------
# Trainer with LR Scheduler
# -------------------------------------------------------

class NeuralTrainer:
    def __init__(self, data_dir="training_data", model_path="custom_model.pth", meta_path="model_meta.json"):
        self.data_dir = data_dir
        self.model_path = model_path
        self.meta_path = meta_path
        self.device = get_device()
        
    def train(self, epochs=20, callback=None, should_stop=None,
              balanceamento="sqrt", paciencia=5, semente=SEMENTE_PADRAO,
              relatorio=True):
        """
        should_stop: callable sem argumentos consultado a cada época. Se devolver
        True, o treino para e o melhor modelo até ali fica salvo. Necessário para
        que a UI consiga cancelar (o treino chega a durar minutos).

        balanceamento: "sqrt" (padrão), "inverso" ou "nenhum". Ver
        `pesos_de_amostragem`. A base é 25.075:1 entre a classe mais comum e a
        mais rara. Medido com holdout de 20% por classe (8 epochs, mesma
        semente), o sorteio uniforme deixa o recall macro em 88,7% contra 96,6%
        de acurácia global, com 5 classes zeradas; com "sqrt" os dois números
        sobem, para 96,7% e 98,6%, e sobra uma classe zerada.

        paciencia: epochs sem melhora da perda de validação até parar. O modelo
        gravado é o da melhor epoch, não o da última.

        semente: fixa o split. Dois treinos da mesma base são comparáveis; se
        variasse, cada relatório mediria um conjunto diferente.
        """
        dataset = CharDataset(self.data_dir, augment=True)
        if len(dataset) == 0:
            if callback: callback("Nenhum dado encontrado para treinamento.")
            return False

        num_classes = len(dataset.label_map)
        rotulos = np.asarray(dataset.labels, dtype=np.int64)

        divisao = dividir_estratificado(rotulos, num_classes, semente=semente)
        idx_treino = divisao.treino
        rotulos_treino = rotulos[idx_treino]
        contagens_treino = contar_por_classe(rotulos_treino, num_classes)
        tem_validacao = len(divisao.validacao) > 0

        # A augmentation fica no subconjunto de treino; a validação é avaliada
        # direto sobre os originais, por `avaliacao.avaliar`. Medir sobre imagem
        # aumentada tornaria o número irreprodutível entre execuções.
        treino_ds = Subset(dataset, idx_treino.tolist())

        # Um epoch = uma passada de len(treino) sorteios. Com o sampler as
        # classes raras aparecem muitas vezes e as comuns poucas, mas o total
        # sorteado continua sendo o tamanho do conjunto de treino.
        if balanceamento == "nenhum":
            dataloader = DataLoader(treino_ds, batch_size=64, shuffle=True)
        else:
            # Os pesos vêm das contagens **do treino**, não da base inteira:
            # usar a base contaria amostras que o modelo não vai ver.
            pesos = pesos_de_amostragem(contagens_treino, rotulos_treino,
                                        modo=balanceamento)
            sampler = WeightedRandomSampler(torch.DoubleTensor(pesos),
                                            len(idx_treino), replacement=True)
            # shuffle é incompatível com sampler — o sorteio já é aleatório.
            dataloader = DataLoader(treino_ds, batch_size=64, sampler=sampler)

        model = SimpleCNN(num_classes).to(self.device)

        criterion = nn.CrossEntropyLoss()
        optimizer = optim.Adam(model.parameters(), lr=0.001)

        # Learning Rate Scheduler: reduz o LR ao longo do treinamento
        scheduler = optim.lr_scheduler.StepLR(optimizer, step_size=7, gamma=0.5)

        model.train()

        if callback:
            n = dataset.contagens
            maior, menor = int(n.max()), int(n[n > 0].min())
            callback(f"Treinando: {len(dataset)} amostras, {num_classes} classes "
                     f"(augmentation sob demanda, balanceamento={balanceamento})")
            callback(f"Divisão: {divisao}")
            if divisao.sem_validacao:
                # Dizer isto alto é metade do ponto da F1.3: uma acurácia de
                # validação que ignora um terço das classes em silêncio é o
                # mesmo defeito que esta fase veio corrigir.
                callback(f"{len(divisao.sem_validacao)} classes pequenas demais "
                         "para dividir vão inteiras para o treino — os números "
                         "de validação não dizem nada sobre elas")
            if not tem_validacao:
                callback("AVISO: base pequena demais para separar validação. O "
                         "melhor modelo volta a ser escolhido pela perda de "
                         "treino, que é o critério ruim que a F1.3 substituiu.")
            callback(f"Desbalanceamento da base: {maior}:{menor}")
            if dataset.classes_vazias:
                callback(f"Ignoradas {len(dataset.classes_vazias)} pasta(s) sem "
                         f"amostra: {', '.join(dataset.classes_vazias[:8])}")
            if dataset.classes_raras:
                # Reportar, não excluir: nesta base as classes minúsculas são
                # 'K', 'Q' e os símbolos de anotação — vocabulário do domínio.
                lista = ", ".join(f"{c!r}({q})" for _, c, q in
                                  sorted(dataset.classes_raras, key=lambda t: t[2])[:12])
                callback(f"{len(dataset.classes_raras)} classes com menos de "
                         f"{MIN_AMOSTRAS_POR_CLASSE} amostras: {lista}"
                         f"{' ...' if len(dataset.classes_raras) > 12 else ''}")
                callback("Elas entram no treino com repetição, mas colete mais "
                         "amostras: uma classe assim generaliza pouco.")

        def gravar_modelo(estado):
            torch.save(estado, self.model_path)
            meta = {
                "label_map": dataset.label_map,
                "idx_to_char": dataset.idx_to_char,
                "num_classes": num_classes,
                # Volta a 1,0 de propósito: a temperatura da F1.9 é ajustada
                # para UM modelo. Herdar a do modelo anterior aplicaria uma
                # correção medida sobre outros pesos — pior que não calibrar.
                # `python calibrar_modelo.py --gravar` reajusta.
                "temperatura": 1.0,
            }
            # Encoding explícito: sem ele o Python usa o do sistema (cp1252
            # no Windows) e o metadado, que é cheio de símbolos Unicode,
            # quebra na leitura. Funcionava por acaso porque o json.dump
            # padrão escapa tudo em ASCII.
            with open(self.meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False)

        melhor_perda = float("inf")
        melhor_epoch = 0
        melhor_estado = None
        sem_melhora = 0
        historico = []
        av_val = None
        cancelado = False

        for epoch in range(epochs):
            if should_stop is not None and should_stop():
                cancelado = True
                break

            running_loss = 0.0
            correct = 0
            total_samples = 0

            for inputs, labels in dataloader:
                inputs, labels = inputs.to(self.device), labels.to(self.device)

                optimizer.zero_grad()
                outputs = model(inputs)
                loss = criterion(outputs, labels)
                loss.backward()
                optimizer.step()

                running_loss += loss.item()

                _, predicted = torch.max(outputs, 1)
                correct += (predicted == labels).sum().item()
                total_samples += labels.size(0)

            scheduler.step()

            perda_treino = running_loss / len(dataloader)
            acc_treino = 100.0 * correct / total_samples
            lr = optimizer.param_groups[0]["lr"]

            if tem_validacao:
                av_val = avaliar(model, dataset.data, rotulos, divisao.validacao,
                                 num_classes, self.device)
                criterio_atual = av_val.perda
                linha = (f"Epoch {epoch+1}/{epochs} - val loss {av_val.perda:.4f} "
                         f"- val acc {av_val.acuracia:.2f}% "
                         f"- macro {av_val.recall_macro:.2f}% "
                         f"- treino loss {perda_treino:.4f}")
            else:
                criterio_atual = perda_treino
                linha = (f"Epoch {epoch+1}/{epochs} - Loss: {perda_treino:.4f} "
                         f"- Acc(treino): {acc_treino:.1f}% - LR: {lr:.6f}")

            historico.append({
                "epoch": epoch + 1,
                "perda_treino": perda_treino,
                "acuracia_treino": acc_treino,
                "perda_val": av_val.perda if av_val else float("nan"),
                "acuracia_val": av_val.acuracia if av_val else float("nan"),
                "macro_val": av_val.recall_macro if av_val else float("nan"),
                "lr": lr,
            })

            # O checkpoint é pela perda de VALIDAÇÃO. Pela perda de treino, o
            # "melhor modelo" era o do momento de maior overfitting — quanto
            # mais o modelo decorava, melhor parecia.
            if criterio_atual < melhor_perda:
                melhor_perda = criterio_atual
                melhor_epoch = epoch + 1
                melhor_estado = {k: v.detach().cpu().clone()
                                 for k, v in model.state_dict().items()}
                gravar_modelo(melhor_estado)
                sem_melhora = 0
            else:
                sem_melhora += 1

            if callback:
                callback(linha)

            if tem_validacao and sem_melhora >= paciencia:
                if callback:
                    callback(f"Early stopping: {paciencia} epochs sem melhora da "
                             f"validação. Vale a epoch {melhor_epoch}.")
                break

        epochs_rodadas = len(historico)
        if melhor_estado is None:
            # Cancelado antes de terminar a primeira epoch: nada foi treinado.
            if callback:
                callback("Treino cancelado antes da primeira epoch; nada foi gravado.")
            return False

        # O relatório descreve o modelo GRAVADO, não o da última epoch.
        model.load_state_dict(melhor_estado)

        if cancelado and callback:
            callback(f"Treino interrompido. Vale a epoch {melhor_epoch}, "
                     "que está gravada.")

        caminho_relatorio = None
        if relatorio and tem_validacao:
            av_val = avaliar(model, dataset.data, rotulos, divisao.validacao,
                             num_classes, self.device)
            av_teste = (avaliar(model, dataset.data, rotulos, divisao.teste,
                                num_classes, self.device)
                        if len(divisao.teste) else None)

            pasta = os.path.dirname(os.path.abspath(self.model_path))
            pasta_erros = os.path.join(pasta, "relatorio_treino_erros")
            gravados = salvar_amostras_erradas(pasta_erros, dataset.data, av_val,
                                               dataset.idx_to_char)
            texto = texto_do_relatorio(av_val, dataset.idx_to_char, divisao,
                                       epochs_rodadas, melhor_epoch, historico,
                                       av_teste,
                                       pasta_erros if gravados else None)
            caminho_relatorio = gravar_relatorio(
                os.path.join(pasta, "relatorio_treino.txt"), texto, av_val,
                dataset.idx_to_char, divisao, historico, av_teste)

            if callback:
                callback(f"Validação: {av_val.acuracia:.2f}% de acurácia, "
                         f"{av_val.recall_macro:.2f}% de recall macro, "
                         f"{av_val.classes_zeradas()} classe(s) zerada(s)")
                if av_teste is not None:
                    callback(f"Teste (nunca usado em decisão): "
                             f"{av_teste.acuracia:.2f}%")
                callback(f"Relatório em {caminho_relatorio}")
        elif callback:
            callback(f"Treinamento concluído na epoch {melhor_epoch}. Modelo salvo.")

        return True

class NeuralPredictor:
    def __init__(self, model_path="custom_model.pth", meta_path="model_meta.json"):
        self.model_path = model_path
        self.meta_path = meta_path
        self.model = None
        self.idx_to_char = {}
        self.device = get_device()
        self.loaded = False
        # 1.0 = softmax cru. Modelo gravado antes da F1.9 não tem o campo, e
        # neutro é o único padrão seguro: uma temperatura chutada mexeria em
        # todo número que a UI mostra.
        self.temperatura = 1.0

    def load(self):
        if not os.path.exists(self.model_path) or not os.path.exists(self.meta_path):
            return False

        try:
            with open(self.meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)

            self.idx_to_char = {int(k): v for k, v in meta["idx_to_char"].items()}
            num_classes = meta["num_classes"]

            try:
                t = float(meta.get("temperatura", 1.0))
                self.temperatura = t if t > 0 else 1.0
            except (TypeError, ValueError):
                self.temperatura = 1.0

            self.model = SimpleCNN(num_classes).to(self.device)
            self.model.load_state_dict(torch.load(self.model_path, map_location=self.device))
            self.model.eval()
            self.loaded = True
            return True
        except Exception as e:
            print(f"Erro ao carregar modelo: {e}")
            return False
            
    def predict(self, img_np):
        if not self.loaded:
            return "?", 0.0
            
        # Preprocess
        if len(img_np.shape) == 3:
            img_gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
        else:
            img_gray = img_np
            
        img = cv2.resize(img_gray, (32, 32))
        img = img.astype(np.float32) / 255.0
        img = np.expand_dims(img, axis=0) # (1, 32, 32)
        img = np.expand_dims(img, axis=0) # (1, 1, 32, 32)
        
        tensor = torch.tensor(img).to(self.device)

        with torch.no_grad():
            outputs = self.model(tensor)
            # Temperatura (F1.9): divide os logits antes do softmax. Não muda
            # qual classe vence — só a confiança —, então nenhuma leitura muda
            # de caractere por causa dela.
            probs = F.softmax(outputs / self.temperatura, dim=1)

            conf, predicted = torch.max(probs, 1)
            
            idx = predicted.item()
            confidence = conf.item()
            
            char = self.idx_to_char.get(idx, "?")
            
            return char, confidence
