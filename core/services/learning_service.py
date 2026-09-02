import os
import cv2
import numpy as np
import uuid
import glob
from typing import List, Tuple, Optional, Callable
from PIL import Image

from core import alfabeto, proporcao, vertical
from core.box_model import BoxEntry
from core.learner import CharacterLearner, char_to_folder
from core.neural_trainer import NeuralTrainer, NeuralPredictor


class DatasetInvalido(RuntimeError):
    """A base de treino tem problemas que invalidariam o modelo."""

    def __init__(self, problemas):
        self.problemas = problemas
        linhas = "\n".join(f"  - {p}" for p in problemas[:12])
        extra = (f"\n  ... e mais {len(problemas) - 12}"
                 if len(problemas) > 12 else "")
        super().__init__(
            f"A base de treino tem {len(problemas)} problema(s) que "
            f"invalidariam o modelo:\n\n{linhas}{extra}\n\n"
            "Use 'Verificar base de treino' no menu Ferramentas para o "
            "diagnóstico completo."
        )


class LearningService:
    """
    Serviço puro que encapsula:
      - Aprendizado interativo (k-NN / CharacterLearner)
      - Treinamento e predição da Rede Neural
      - Processamento em lote (extração + classificação)
    """

    def __init__(
        self,
        data_dir: str = "training_data",
        model_path: str = "custom_model.pth",
        meta_path: str = "model_meta.json",
    ):
        self.data_dir = data_dir
        self.model_path = model_path
        self.meta_path = meta_path

        self._learner: Optional[CharacterLearner] = None
        self._predictor: Optional[NeuralPredictor] = None

    # ------------------------------------------------------------------
    # Learner (k-NN)
    # ------------------------------------------------------------------
    def _get_learner(self) -> CharacterLearner:
        if self._learner is None:
            self._learner = CharacterLearner(self.data_dir)
        return self._learner

    def learn_from_boxes(self, image: Image.Image, boxes: List[BoxEntry]) -> int:
        """
        Adiciona todos os boxes que têm caractere definido à base de conhecimento.
        Retorna quantidade de amostras adicionadas.

        Box de texto girado entra **de pé** (F8.1). A base de referência é de
        glifo em pé, e guardar um 'A' deitado sob o rótulo 'A' envenenaria a
        vizinhança do k-NN para todo mundo.
        """
        learner = self._get_learner()
        count = 0
        pagina = np.asarray(image)

        for b in boxes:
            if not b.char:
                continue

            crop_np = vertical.recorte_de_pe(pagina, b)

            learner.learn(crop_np, b.char)
            count += 1

        # Uma gravação por lote, não por amostra: refazer a impressão digital
        # custa 0,2 s, e por amostra isso somaria minutos numa página cheia.
        # Sem isto o cache ficaria velho e a sessão seguinte releria 151 mil
        # PNGs — os 141 s que a otimização existe para eliminar.
        if count:
            learner.salvar_cache()

        return count

    def predict_learner(self, crop_np: np.ndarray) -> Tuple[str, float]:
        """Predição via k-NN."""
        learner = self._get_learner()
        return learner.predict(crop_np)

    # ------------------------------------------------------------------
    # Neural Network
    # ------------------------------------------------------------------
    def load_predictor(self) -> bool:
        """Carrega o modelo neural (lazy). Retorna True se conseguiu."""
        if self._predictor is None:
            self._predictor = NeuralPredictor(self.model_path, self.meta_path)
        if getattr(self._predictor, "loaded", False):
            return True
        return self._predictor.load()

    def aviso_do_modelo(self) -> str:
        """
        A ressalva de um modelo que **carregou**, ou string vazia.

        Irmã de `motivo_do_modelo`, que é para quando a carga falha. O canal de
        aviso existia desde a F7.3 e **não tinha leitor nenhum** — o que o
        tornava equivalente a não existir. Foi por isso que um modelo sem
        calibração passou um dia em produção sem ninguém notar (F26).
        """
        if not self.load_predictor():
            return ""
        return getattr(self._predictor, "aviso", "")

    def motivo_do_modelo(self) -> str:
        """
        Por que a carga do modelo falhou, na linguagem de quem vai ler.

        Sem isto, um par `.pth`/`.json` trocado é reportado como "modelo não
        encontrado" — que manda o usuário procurar um arquivo que está lá.
        """
        motivo = getattr(self._predictor, "erro", "") if self._predictor else ""
        if motivo:
            return motivo
        if not os.path.exists(self.model_path):
            return (f"{os.path.basename(self.model_path)} não existe.\n"
                    "Treine a rede primeiro (Ferramentas → Treinar Rede Neural).")
        if not os.path.exists(self.meta_path):
            return (f"{os.path.basename(self.meta_path)} não existe — é ele que "
                    "traduz a saída do modelo em caracteres.\nTreine a rede "
                    "novamente para regravá-lo.")
        return ("Não foi possível carregar o modelo neural. Veja o console para "
                "o erro exato.")

    def predict_neural(self, crop_np: np.ndarray) -> Tuple[str, float]:
        """Predição via CNN. Retorna ('?', 0.0) se modelo não carregado."""
        if not self.load_predictor():
            return "?", 0.0
        return self._predictor.predict(crop_np)

    def ler_texto(self, crop_np: np.ndarray,
                  referencia: Optional[float] = None,
                  idioma: Optional[str] = None) -> Tuple[str, float]:
        """
        `predict_neural` com o veto geométrico da F106 e a máscara de alfabeto
        da F109 — para quem lê **texto**.

        Mesmo contrato `(recorte) -> (char, confiança)`, então entra no lugar do
        outro sem nenhuma outra mudança; a proporção que o veto usa é a do
        próprio recorte, e não precisa ser passada de fora.

        `idioma` é o do livro (`"en"`, `"pt"`), e liga a máscara: a letra
        acentuada que o idioma não escreve é vetada como o travessão fora de
        proporção é — a rede dá as candidatas seguintes e a primeira que cabe
        nos dois crivos sai. Sem idioma a máscara não opina, que é o de antes.
        O que ela pega está medido em `core.alfabeto`; quem lê um livro inteiro
        prende o idioma uma vez com `leitor_de_texto`.

        **Não é o classificador de tudo, e a separação é o assunto.** A rede crua
        continua respondendo onde a pergunta não é "que caractere é este":
        o árbitro da segmentação (F1.5b), que compara confiança entre cortes; e a
        peça do diagrama (F7.4), que é desenho de xadrez e não letra. O envelope
        fala de tipografia, e ali não há tipografia sobre o que falar.

        Sem `referencia` — a mediana da altura dos boxes da página —, o veto roda
        só pela proporção, e o par `.`/`■` fica como estava. Quem lê um PDF
        inteiro caractere a caractere não tem a página à mão nesse contrato.
        """
        char, conf = self.predict_neural(crop_np)
        largura, altura = proporcao.lados(crop_np)
        if (alfabeto.permitido(char, idioma)
                and proporcao.cabe(char, largura, altura, referencia)):
            return char, conf

        # Segunda passada pela rede, e só aqui: medido, o veto pega 2 leituras
        # em 10.641 numa página normal. O caminho de sempre não paga nada.
        # **A máscara filtra antes da geometria escolher**, e os dois crivos
        # valem juntos: a candidata que o idioma admite ainda precisa caber no
        # recorte. Sem candidata que passe nos dois, fica a leitura que havia —
        # inventar uma classe que a rede não ofereceu seria o voto que a F19
        # mediu e descartou.
        escolhida = proporcao.escolher(
            alfabeto.filtrar(self.candidatas(crop_np, k=proporcao.CANDIDATAS),
                             idioma),
            largura, altura, referencia)
        return escolhida if escolhida is not None else (char, conf)

    def leitor_de_texto(self, idioma: Optional[str] = None) -> Callable:
        """
        `ler_texto` com o idioma do livro preso (F109).

        `livro.extrair` chama o classificador com o recorte só, e é o contrato
        certo — ele não tem por que saber de idioma. Quem sabe é quem abriu o
        livro, e prende aqui, uma vez, o que vale para todas as páginas.
        """
        def ler(crop_np: np.ndarray, referencia: Optional[float] = None
                ) -> Tuple[str, float]:
            return self.ler_texto(crop_np, referencia, idioma=idioma)
        return ler

    def probabilidade_de(self, crop_np: np.ndarray, char: str) -> float:
        """Quanto a rede dá a **esta** classe neste recorte (F69). 0,0 sem modelo."""
        if not self.load_predictor():
            return 0.0
        return self._predictor.probabilidade_de(crop_np, char)

    def candidatas(self, crop_np: np.ndarray, k: int = 3):
        """
        As `k` classes mais prováveis, `[(char, prob), ...]`. Vazio sem modelo.

        Passagem para `NeuralPredictor.predict_topk`, que a UI não deve alcançar
        por dentro. Quem a usa hoje é a coleta (F93): a segunda candidata vai
        para o índice da revisão, e é ela que diz **para onde ia** o recorte que
        caiu na pasta errada.
        """
        if not self.load_predictor():
            return []
        return self._predictor.predict_topk(crop_np, k=k)

    def validar_dados(self, checar_pngs: bool = False):
        """Problemas na base de treino. Lista vazia = pode treinar."""
        from core.dataset_check import validar_dataset
        return validar_dataset(self.data_dir, checar_pngs=checar_pngs)

    def sanear_dados(self, checar_pngs: bool = False,
                     callback: Optional[Callable[[str], None]] = None) -> List[str]:
        """
        Corrige o que `validar_dados` acusa: renomeia, mescla e quarentena.

        `checar_pngs` acompanha o da validação que achou o problema — o caminho
        rápido não lê arquivo nenhum, e então não há PNG ilegível a mover.

        O k-NN em memória é descartado: ele foi montado com os nomes de pasta
        antigos, e as amostras mescladas ainda não estão na matriz dele.
        """
        from core.dataset_check import sanear_dataset
        registro = sanear_dataset(self.data_dir, checar_pngs=checar_pngs,
                                  log=callback)
        if registro:
            self._learner = None
        return registro

    def caminho_relatorio(self) -> str:
        """Onde o último treino gravou o relatório (pode não existir ainda)."""
        pasta = os.path.dirname(os.path.abspath(self.model_path))
        return os.path.join(pasta, "relatorio_treino.txt")

    def train_neural(self, epochs: int = 20,
                     callback: Optional[Callable[[str], None]] = None,
                     should_stop: Optional[Callable[[], bool]] = None,
                     validar: bool = True,
                     balanceamento: str = "sqrt",
                     calibrar: bool = True,
                     corrigir: bool = False) -> bool:
        """
        Treina a rede neural com os dados atuais.

        `balanceamento` controla o sorteio das amostras (ver
        `core.neural_trainer.pesos_de_amostragem`). O padrão compensa o
        desbalanceamento de 25.075:1 da base.

        `corrigir=True` sanea a base antes de desistir, em vez de só levantar
        `DatasetInvalido`. Continua sendo decisão de quem chama, e não o
        padrão: a correção mexe nas pastas do usuário, e o pedido de treino
        sozinho não autoriza isso.
        """
        if not os.path.exists(self.data_dir) or not os.listdir(self.data_dir):
            if callback:
                callback("Nenhum dado de treinamento encontrado.")
            return False

        if validar:
            # Falhar alto antes do treino, em vez de deixar o problema virar
            # ruído no modelo. Foi assim que 127 amostras de "f7" passaram
            # meses treinando a classe "?" sem ninguém notar.
            graves = [p for p in self.validar_dados() if p.grave]
            if graves and corrigir:
                if callback:
                    callback(f"{len(graves)} problema(s) na base; corrigindo...")
                for linha in self.sanear_dados(callback=callback):
                    if callback:
                        callback(linha)
                # Revalidar, e não confiar no registro: o que importa é a base
                # ter ficado treinável, não a migração ter dito que fez algo.
                graves = [p for p in self.validar_dados() if p.grave]
            if graves:
                raise DatasetInvalido(graves)

        trainer = NeuralTrainer(self.data_dir, self.model_path, self.meta_path)
        ok = trainer.train(epochs=epochs, callback=callback,
                           should_stop=should_stop,
                           balanceamento=balanceamento,
                           calibrar=calibrar)
        if ok:
            # O preditor em memória é o do modelo ANTERIOR, e `load_predictor`
            # devolve `True` sem reler quando já há um carregado. Sem isto a
            # sessão seguiria usando os pesos velhos, e a ressalva da F26 seria
            # a do arquivo que acabou de ser substituído.
            self._predictor = None
        return ok

    # ------------------------------------------------------------------
    # Batch processing (extract + classify)
    # ------------------------------------------------------------------
    def batch_extract_and_classify(
        self,
        images: List[Tuple[str, Image.Image]],
        output_dir: str,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> int:
        """
        Recebe uma lista de (nome, PIL.Image), detecta boxes, classifica via neural
        e salva os recortes em subpastas de output_dir.
        Retorna total de recortes salvos.
        """
        from core.services.box_service import BoxService

        if not self.load_predictor():
            raise RuntimeError("Modelo neural não encontrado. Treine a rede primeiro.")

        total_crops = 0
        predictor = self._predictor

        for i, (source_name, pil_img) in enumerate(images):
            if progress_callback:
                progress_callback(source_name, i + 1, len(images))

            pil_gray = pil_img.convert("L")
            img_cv = np.array(pil_gray)

            # Threshold + contornos
            _, th = cv2.threshold(img_cv, 180, 255, cv2.THRESH_BINARY_INV)
            contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            page_boxes = []
            for c in contours:
                x, y, w, h = cv2.boundingRect(c)
                if w < 5 or h < 5:
                    continue
                if w > 150 or h > 150:
                    continue  # ignorar diagramas grandes
                page_boxes.append(BoxEntry("", x, y, x + w, y + h))

            page_boxes.sort(key=lambda b: (b.y1, b.x1))
            page_boxes = BoxService.merge_vertical_boxes(page_boxes)
            page_boxes = BoxService.sort_boxes_reading_order(page_boxes)

            for b in page_boxes:
                crop = pil_gray.crop((b.x1, b.y1, b.x2, b.y2))
                crop_np = np.array(crop)

                char, _ = predictor.predict(crop_np)
                if not char:
                    char = "unknown"

                safe_folder = char_to_folder(char)
                save_path = os.path.join(output_dir, safe_folder)
                os.makedirs(save_path, exist_ok=True)

                if len(crop_np.shape) == 3:
                    img_gray = cv2.cvtColor(crop_np, cv2.COLOR_RGB2GRAY)
                else:
                    img_gray = crop_np

                img_resized = cv2.resize(img_gray, (32, 32))
                fname = f"{uuid.uuid4()}.png"
                cv2.imwrite(os.path.join(save_path, fname), img_resized)
                total_crops += 1

        return total_crops

    # ------------------------------------------------------------------
    # Importação de dados externos
    # ------------------------------------------------------------------
    @staticmethod
    def import_character_images(src_dir: str, dest_dir: str = "training_data") -> int:
        """
        Importa imagens de uma pasta externa (organizada por caracteres)
        para a pasta oficial de treinamento.
        """
        import shutil

        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir)

        count = 0
        for subdir in os.listdir(src_dir):
            src_sub = os.path.join(src_dir, subdir)
            if not os.path.isdir(src_sub):
                continue

            dest_sub = os.path.join(dest_dir, subdir)
            os.makedirs(dest_sub, exist_ok=True)

            for f in glob.glob(os.path.join(src_sub, "*.png")):
                new_name = f"{uuid.uuid4()}.png"
                shutil.copy2(f, os.path.join(dest_sub, new_name))
                count += 1

        return count
