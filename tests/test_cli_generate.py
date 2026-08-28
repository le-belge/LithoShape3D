import numpy as np
import pytest
from PIL import Image

from lithoshape3d.cli import main
from lithoshape3d.core.export.stl_export import load_stl
from lithoshape3d.core.validation.mesh_checks import validate_mesh
from tests.fixtures.synthetic_images import make_gradient_image, make_uniform_image


def test_generate_command_produces_a_valid_stl(tmp_path, capsys):
    image_path = make_gradient_image(tmp_path / "gradient.png", width=48, height=32)
    output_path = tmp_path / "output.stl"

    exit_code = main(
        [
            "generate",
            str(image_path),
            str(output_path),
            "--width",
            "60",
            "--min-thickness",
            "0.8",
            "--max-thickness",
            "3.0",
            "--resolution",
            "2.0",
        ]
    )

    assert exit_code == 0
    assert output_path.exists()

    captured = capsys.readouterr()
    assert "OK" in captured.out

    mesh = load_stl(output_path)
    result = validate_mesh(mesh)
    assert result.is_valid


def test_generate_command_deduces_height_from_aspect_ratio(tmp_path):
    image_path = make_gradient_image(tmp_path / "gradient.png", width=80, height=40)
    output_path = tmp_path / "output.stl"

    exit_code = main(
        ["generate", str(image_path), str(output_path), "--width", "80", "--resolution", "4.0"]
    )

    assert exit_code == 0
    mesh = load_stl(output_path)
    # ratio 80x40 -> largeur 80mm => hauteur attendue 40mm
    assert abs(mesh.bounds[1][1] - 40.0) < 1.0


def test_lightbox_text_command_exports_body_with_integrated_back_and_face(tmp_path, capsys):
    image_path = make_uniform_image(tmp_path / "photo.png", value=160, width=64, height=32)
    output_dir = tmp_path / "lightbox"

    exit_code = main(
        [
            "lightbox-text",
            str(image_path),
            str(output_dir),
            "--text",
            "O",
            "--width",
            "70",
            "--height",
            "45",
            "--depth",
            "25",
            "--wall-thickness",
            "5",
            "--resolution",
            "2.5",
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "OK:" in captured.out

    expected = [
        output_dir / "lightbox_body.stl",
        output_dir / "lightbox_face.stl",
    ]
    for path in expected:
        assert path.exists()
        assert validate_mesh(load_stl(path)).is_valid
    assert not (output_dir / "lightbox_back_panel.stl").exists()


def test_lightbox_shape_command_exports_body_with_integrated_back_and_flat_cap(tmp_path, capsys):
    silhouette = np.zeros((48, 64), dtype=np.uint8)
    silhouette[8:40, 10:54] = 255
    silhouette[20:30, 26:38] = 0
    shape_path = tmp_path / "logo.png"
    Image.fromarray(silhouette, mode="L").save(shape_path)
    output_dir = tmp_path / "shape_lightbox"

    exit_code = main(
        [
            "lightbox-shape",
            str(shape_path),
            str(output_dir),
            "--width",
            "80",
            "--height",
            "50",
            "--depth",
            "25",
            "--wall-thickness",
            "5",
            "--resolution",
            "2.5",
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "OK:" in captured.out

    expected = [
        output_dir / "lightbox_body.stl",
        output_dir / "lightbox_face.stl",
    ]
    for path in expected:
        assert path.exists()
        assert validate_mesh(load_stl(path)).is_valid
    assert not (output_dir / "lightbox_back_panel.stl").exists()


def test_lightbox_shape_lithophane_face_requires_image(tmp_path, capsys):
    shape_path = make_uniform_image(tmp_path / "shape.png", value=255, width=32, height=32)

    exit_code = main(
        [
            "lightbox-shape",
            str(shape_path),
            str(tmp_path / "out"),
            "--width",
            "40",
            "--height",
            "40",
            "--face",
            "lithophane",
        ]
    )

    assert exit_code == 1
    assert "--lithophane-image est requis" in capsys.readouterr().out


def test_lightbox_shape_command_accepts_svg_when_qtsvg_is_available(tmp_path, capsys):
    pytest.importorskip("PySide6.QtSvg")
    svg_path = tmp_path / "logo.svg"
    svg_path.write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 60'>"
        "<path d='M10 10 H90 V50 H10 Z M40 25 H60 V35 H40 Z' fill='black'/>"
        "</svg>",
        encoding="utf-8",
    )
    output_dir = tmp_path / "svg_lightbox"

    exit_code = main(
        [
            "lightbox-shape",
            str(svg_path),
            str(output_dir),
            "--width",
            "80",
            "--height",
            "50",
            "--depth",
            "25",
            "--wall-thickness",
            "5",
            "--resolution",
            "2.5",
        ]
    )

    assert exit_code == 0
    assert "OK:" in capsys.readouterr().out
    assert validate_mesh(load_stl(output_dir / "lightbox_body.stl")).is_valid
