"""Tests du dialogue "LightBox depuis image" pour la selection du connecteur
(USB-C / pogo pin / personnalise) -- retour utilisateur : "un emplacement
pour fixer un port usb c ou un connecteur pogo"."""

from __future__ import annotations

from lithoshape3d.ui.lightbox_image_dialog import LightboxImageDialog


def test_connector_default_is_none(qapp):
    dialog = LightboxImageDialog()
    assert dialog._connector_generation_kwargs() == {"connector_shape": None}
    assert dialog.connector_width_spin.isHidden()
    assert dialog.connector_pos_x_row.isHidden()


def test_connector_usb_c_preset_fills_expected_dimensions(qapp):
    dialog = LightboxImageDialog()
    dialog.connector_combo.setCurrentIndex(dialog.connector_combo.findData("rect_usb_c"))

    kwargs = dialog._connector_generation_kwargs()
    assert kwargs["connector_shape"] == "rect"
    assert kwargs["connector_width_mm"] == 9.5
    assert kwargs["connector_height_mm"] == 3.8
    assert not dialog.connector_width_spin.isHidden()
    assert not dialog.connector_height_spin.isHidden()


def test_connector_pogo_preset_fills_diameter_and_hides_height(qapp):
    dialog = LightboxImageDialog()
    dialog.connector_combo.setCurrentIndex(dialog.connector_combo.findData("circle_pogo"))

    kwargs = dialog._connector_generation_kwargs()
    assert kwargs["connector_shape"] == "circle"
    assert kwargs["connector_width_mm"] == 6.0
    assert kwargs["connector_height_mm"] is None
    assert dialog.connector_height_spin.isHidden()


def test_connector_position_fractions_come_from_percent_spins(qapp):
    dialog = LightboxImageDialog()
    dialog.connector_combo.setCurrentIndex(dialog.connector_combo.findData("circle_pogo"))
    dialog.connector_pos_x_spin.setValue(75.0)
    dialog.connector_pos_y_spin.setValue(20.0)

    kwargs = dialog._connector_generation_kwargs()
    assert kwargs["connector_position_x_fraction"] == 0.75
    assert kwargs["connector_position_y_fraction"] == 0.2
