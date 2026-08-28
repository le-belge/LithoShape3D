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


def test_lightbox_text_command_exports_separate_stl_parts(tmp_path, capsys):
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
        output_dir / "lightbox_back_panel.stl",
    ]
    for path in expected:
        assert path.exists()
        assert validate_mesh(load_stl(path)).is_valid
