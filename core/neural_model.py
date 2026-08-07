import torch
import torch.nn as nn
import torch.nn.functional as F

class SimpleCNN(nn.Module):
    def __init__(self, num_classes):
        super(SimpleCNN, self).__init__()
        # Input: 1 channel (grayscale), 32x32 images
        
        # Conv 1: 1 -> 32
        self.conv1 = nn.Conv2d(1, 32, kernel_size=3, padding=1)
        self.pool1 = nn.MaxPool2d(2, 2) # 32x32 -> 16x16
        
        # Conv 2: 32 -> 64
        self.conv2 = nn.Conv2d(32, 64, kernel_size=3, padding=1)
        self.pool2 = nn.MaxPool2d(2, 2) # 16x16 -> 8x8
        
        # Conv 3: 64 -> 128 (Optional, but good for complex fonts)
        self.conv3 = nn.Conv2d(64, 128, kernel_size=3, padding=1)
        self.pool3 = nn.MaxPool2d(2, 2) # 8x8 -> 4x4
        
        # Fully Connected
        # Flatten: 128 * 4 * 4 = 2048
        self.fc1 = nn.Linear(128 * 4 * 4, 256)
        self.dropout = nn.Dropout(0.5)
        self.fc2 = nn.Linear(256, num_classes)
        
    def forward(self, x):
        # x shape: (Batch, 1, 32, 32)
        x = self.pool1(F.relu(self.conv1(x)))
        x = self.pool2(F.relu(self.conv2(x)))
        x = self.pool3(F.relu(self.conv3(x)))
        
        x = x.view(-1, 128 * 4 * 4) # Flatten
        x = F.relu(self.fc1(x))
        x = self.dropout(x)
        x = self.fc2(x)
        return x

class RedeDiagrama(nn.Module):
    """
    A rede que lê as peças do diagrama (F7.4). Entrada 1x32x32, 12 classes.

    **Não é a `SimpleCNN`, e a diferença foi medida.** São 12 classes de glifo
    impresso, não 126 de texto corrido: a camada densa de 2.048 para 256 daquela
    responde por 85% dos seus 620 mil parâmetros e não paga. Deixando um livro
    inteiro de fora do treino (ver `core/treino_diagrama.py`):

        rede                        parâmetros   arquivo   livro novo
        SimpleCNN (a de caracteres)   620.300    2.423 KB     97,8%
        esta                           35.820      140 KB     98,0%
        esta, com média global          24.300       95 KB     81,4%
        esta, com metade dos canais     12.156       47 KB     96,0%

    **O tamanho do arquivo não é vaidade: é o que decide se o modelo viaja no
    repositório.** O `.gitignore` manda `*.pth` para fora porque o modelo de
    caracteres tem 2,6 MB, e o banco de peças que este substitui tinha 231 KB e
    era versionado — um clone novo lia diagramas sem baixar nada. Com 140 KB
    essa propriedade se mantém.

    **A média global é a variante que ensina o porquê.** Trocar o achatamento
    por `mean((2,3))` economiza 11 mil parâmetros e derruba 16,6 pontos: onde a
    tinta está dentro da casa é informação, e a média joga fora exatamente isso.
    """

    def __init__(self, num_classes):
        super().__init__()
        self.conv1 = nn.Conv2d(1, 16, kernel_size=3, padding=1)
        self.norm1 = nn.BatchNorm2d(16)
        self.conv2 = nn.Conv2d(16, 32, kernel_size=3, padding=1)
        self.norm2 = nn.BatchNorm2d(32)
        self.conv3 = nn.Conv2d(32, 64, kernel_size=3, padding=1)
        self.norm3 = nn.BatchNorm2d(64)
        self.dropout = nn.Dropout(0.3)
        self.fc = nn.Linear(64 * 4 * 4, num_classes)

    def forward(self, x):
        x = F.max_pool2d(F.relu(self.norm1(self.conv1(x))), 2)   # 32 -> 16
        x = F.max_pool2d(F.relu(self.norm2(self.conv2(x))), 2)   # 16 -> 8
        x = F.max_pool2d(F.relu(self.norm3(self.conv3(x))), 2)   # 8 -> 4
        return self.fc(self.dropout(x.flatten(1)))


def get_device():
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")
