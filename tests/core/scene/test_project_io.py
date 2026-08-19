import shutil

import numpy as np
import pytest

from lithoshape3d.core.scene.models import GeometryParameters, Project, Scene, Zone
from lithoshape3d.core.scene.project_io import load_project_bundle, save_project_bundle
from tests.fixtures.synthetic_images import make_gradient_image


def _make_project_with_zone() -> Project:
    zone = Zone(name="Lithophanie", geometry_params=GeometryParameters(100.0, 80.0))
    return Project(name="mon-portrait", scene=Scene(zones=[zone], active_zone_id=zone.id))


def test_save_creates_bundle_structure(tmp_path):
    source_image = make_gradient_image(tmp_path / "external" / "photo.png", width=40, height=30)
    project = _make_project_with_zone()
    project.scene.source_image_path = str(source_image)

    bundle_dir = tmp_path / "MonPortrait.l3dproj"
    save_project_bundle(project, bundle_dir)

    assert (bundle_dir / "project.json").exists()
    assert (bundle_dir / "source" / "photo.png").exists()


def test_save_normalizes_source_image_path_to_relative(tmp_path):
    source_image = make_gradient_image(tmp_path / "external" / "photo.png", width=40, height=30)
    project = _make_project_with_zone()
    project.scene.source_image_path = str(source_image)

    bundle_dir = tmp_path / "MonPortrait.l3dproj"
    save_project_bundle(project, bundle_dir)

    assert project.scene.source_image_path == "source/photo.png"
    from pathlib import Path

    assert not Path(project.scene.source_image_path).is_absolute()


def test_save_writes_dirty_masks_and_sets_relative_mask_path(tmp_path):
    source_image = make_gradient_image(tmp_path / "photo.png", width=40, height=30)
    project = _make_project_with_zone()
    project.scene.source_image_path = str(source_image)
    zone_id = project.scene.zones[0].id
    mask = np.zeros((30, 40), dtype=np.float32)
    mask[:, 20:] = 1.0

    bundle_dir = tmp_path / "MonPortrait.l3dproj"
    save_project_bundle(project, bundle_dir, dirty_masks={zone_id: mask})

    assert project.scene.zones[0].mask_path == f"masks/{zone_id}.png"
    assert (bundle_dir / "masks" / f"{zone_id}.png").exists()


def test_roundtrip_load_matches_saved_project(tmp_path):
    source_image = make_gradient_image(tmp_path / "photo.png", width=40, height=30)
    project = _make_project_with_zone()
    project.scene.source_image_path = str(source_image)
    zone_id = project.scene.zones[0].id
    mask = np.ones((30, 40), dtype=np.float32)

    bundle_dir = tmp_path / "MonPortrait.l3dproj"
    save_project_bundle(project, bundle_dir, dirty_masks={zone_id: mask})

    reloaded = load_project_bundle(bundle_dir)

    assert reloaded.name == project.name
    assert reloaded.scene.source_image_path == "source/photo.png"
    assert reloaded.scene.zones[0].mask_path == f"masks/{zone_id}.png"
    assert reloaded.scene.active_zone_id == zone_id


def test_bundle_is_portable_after_move(tmp_path):
    """Test de portabilite explicitement demande : creer, enregistrer,
    deplacer le bundle, rendre l'original inaccessible, recharger."""
    source_image = make_gradient_image(tmp_path / "originals" / "photo.png", width=32, height=24)
    project = _make_project_with_zone()
    project.scene.source_image_path = str(source_image)
    zone_id = project.scene.zones[0].id
    mask = np.zeros((24, 32), dtype=np.float32)
    mask[:12, :] = 1.0

    original_bundle = tmp_path / "originals" / "MonPortrait.l3dproj"
    save_project_bundle(project, original_bundle, dirty_masks={zone_id: mask})

    moved_bundle = tmp_path / "elsewhere" / "MonPortrait.l3dproj"
    moved_bundle.parent.mkdir(parents=True)
    shutil.move(str(original_bundle), str(moved_bundle))
    shutil.rmtree(tmp_path / "originals")  # emplacement d'origine rendu inaccessible

    reloaded = load_project_bundle(moved_bundle)

    from lithoshape3d.core.scene.mask_io import load_zone_mask

    image_path = moved_bundle / reloaded.scene.source_image_path
    assert image_path.exists()

    reloaded_mask = load_zone_mask(moved_bundle, reloaded.scene.zones[0], shape=(24, 32))
    assert np.array_equal(reloaded_mask, mask)


def test_bundle_json_contains_no_absolute_paths(tmp_path):
    source_image = make_gradient_image(tmp_path / "photo.png", width=20, height=20)
    project = _make_project_with_zone()
    project.scene.source_image_path = str(source_image)
    zone_id = project.scene.zones[0].id
    mask = np.ones((20, 20), dtype=np.float32)

    bundle_dir = tmp_path / "Projet.l3dproj"
    save_project_bundle(project, bundle_dir, dirty_masks={zone_id: mask})

    raw_json = (bundle_dir / "project.json").read_text(encoding="utf-8")
    assert str(tmp_path) not in raw_json
    assert not raw_json.count('"/')  # aucune chaine de chemin commencant par /


def test_load_missing_bundle_raises():
    with pytest.raises(FileNotFoundError):
        load_project_bundle("/chemin/inexistant.l3dproj")
