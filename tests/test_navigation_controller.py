import pytest

from core.services.navigation_controller import NavigationController


def test_reset_e_limites_de_navegacao():
    navigation = NavigationController()
    navigation.reset(3)
    assert navigation.current_page == 0
    assert not navigation.can_previous
    assert navigation.can_next

    navigation.next()
    assert navigation.current_page == 1
    navigation.previous()
    assert navigation.current_page == 0


def test_navegacao_rejeita_fora_dos_limites():
    navigation = NavigationController()
    navigation.reset(2)
    with pytest.raises(IndexError):
        navigation.go_to(2)
    with pytest.raises(IndexError):
        navigation.previous()


def test_documento_vazio_nao_tem_alvo():
    navigation = NavigationController()
    navigation.reset(0)
    assert navigation.current_page == -1
    assert not navigation.can_previous
    assert not navigation.can_next
    with pytest.raises(IndexError):
        navigation.next()

