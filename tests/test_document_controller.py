from core.box_model import BoxEntry
from core.services.document_controller import DocumentController


def box(char):
    return BoxEntry(char, 0, 0, 8, 12)


def test_abertura_cria_sessao_e_historico_isolado():
    controller = DocumentController()
    session = controller.open("livro.pdf", num_pages=3, is_pdf=True)

    assert controller.session is session
    assert controller.page == 0
    assert controller.boxes == []
    assert not controller.can_undo


def test_commit_marca_pagina_suja_e_undo_redo_preserva_selecao():
    controller = DocumentController()
    controller.open("imagem.png")
    controller.boxes.append(box("a"))
    controller.selected_index = 0
    controller.commit()
    controller.boxes.append(box("b"))
    controller.selected_index = 1
    controller.commit()

    assert controller.session.is_dirty()
    assert controller.can_undo
    assert controller.undo()
    assert [item.char for item in controller.boxes] == ["a"]
    assert controller.selected_index == 0
    assert controller.redo()
    assert [item.char for item in controller.boxes] == ["a", "b"]
    assert controller.selected_index == 1


def test_troca_de_pagina_persiste_boxes_sem_vazar_historico():
    controller = DocumentController()
    controller.open("livro.pdf", num_pages=2, is_pdf=True)
    controller.boxes.append(box("a"))
    controller.commit()

    controller.load_page(1)
    assert controller.boxes == []
    assert not controller.can_undo

    controller.boxes.append(box("b"))
    controller.commit()
    controller.load_page(0)
    assert [item.char for item in controller.boxes] == ["a"]

