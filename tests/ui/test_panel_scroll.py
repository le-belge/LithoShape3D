"""Hotfix 0.3.1 : le panneau de parametres (droite) doit rester utilisable
sur un ecran plus petit que celui du developpeur -- avant ce correctif, les
derniers groupes (Support d'impression, Affichage) devenaient inaccessibles
sans aucun moyen de scroller."""

from PySide6.QtWidgets import QScrollArea


def test_params_panel_is_wrapped_in_a_scroll_area(main_window):
    assert isinstance(main_window.params_scroll_area, QScrollArea)
    assert main_window.params_scroll_area.widgetResizable() is True


def test_params_scroll_area_has_no_horizontal_scrollbar_policy(main_window):
    from PySide6.QtCore import Qt

    assert (
        main_window.params_scroll_area.horizontalScrollBarPolicy()
        == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )


def test_all_param_groups_are_descendants_of_the_scroll_area_content(main_window):
    content = main_window.params_scroll_area.widget()
    for widget in (
        main_window.relief_mode_combo,
        main_window.composition_mode_combo,
        main_window.material_name_edit,
        main_window.width_spin,
        main_window.invert_checkbox,
        main_window.support_type_combo,
        main_window.display_mode_combo,
        main_window.view_reset_button,
    ):
        assert content.isAncestorOf(widget), widget


def test_scroll_area_scrolls_when_window_is_short(qapp, main_window):
    """A une hauteur de fenetre reduite, le contenu du panneau doit depasser
    la zone visible (verticalScrollBar utile) -- sinon le bug original
    (derniers controles inaccessibles) n'est pas reproduit/corrige."""
    main_window.resize(1300, 500)
    main_window.show()
    for _ in range(5):
        qapp.processEvents()

    scroll_area = main_window.params_scroll_area
    scrollbar = scroll_area.verticalScrollBar()
    assert scrollbar.maximum() > 0

    scroll_area.ensureWidgetVisible(main_window.view_reset_button)
    for _ in range(3):
        qapp.processEvents()
    # ne doit pas lever ; le controle reste atteignable via scroll
    assert main_window.view_reset_button.isVisible()


def test_scroll_area_needs_less_scroll_on_a_taller_window(qapp, main_window):
    """La quantite de scroll necessaire doit diminuer avec la hauteur
    disponible (verifie que le scroll s'adapte reellement a l'espace, plutot
    que d'etre fixe/casse). Ne verifie pas un "zero scrollbar" absolu : sur
    un environnement de test avec un ecran virtuel reduit, le panneau
    (~1000px de contenu, 7 groupes) peut legitimement rester un peu plus
    grand que l'espace dispo meme fenetre maximisee -- ce que confirme cette
    meme situation, c'est que le scroll REND le dernier controle atteignable
    (voir test precedent), ce qui etait impossible avant le correctif."""
    main_window.resize(1300, 500)
    main_window.show()
    for _ in range(5):
        qapp.processEvents()
    short_max = main_window.params_scroll_area.verticalScrollBar().maximum()

    main_window.showMaximized()
    for _ in range(5):
        qapp.processEvents()
    tall_max = main_window.params_scroll_area.verticalScrollBar().maximum()

    assert tall_max < short_max
