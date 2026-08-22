"""ColorStrategy (v0.4.1) : separe strictement geometrie/relief, materiau/
couleur, et strategie couleur. MATERIAL_ONLY doit garantir que la surface
exterieure deja composee ne change JAMAIS du seul fait d'assigner un
materiau a une zone -- regression du bug "la rose ressort en sur-relief"
(mission 0.4.1)."""

import numpy as np
import pytest
import trimesh
from PIL import Image

from lithoshape3d.core.geometry.composition import (
    ZoneSource,
    compose_scene_heightfield,
    compose_scene_mesh,
)
from lithoshape3d.core.geometry.materials import partition_mesh_by_material
from lithoshape3d.core.scene.models import (
    ColorStrategy,
    CompositionMode,
    GeometryParameters,
    ReliefMode,
    Zone,
)
from lithoshape3d.core.validation.mesh_checks import validate_mesh
from tests.fixtures.synthetic_images import make_uniform_image

ROWS, COLS = 40, 60
WIDTH_MM, HEIGHT_MM = 60.0, 40.0


def _params(**overrides) -> GeometryParameters:
    defaults = {
        "width_mm": WIDTH_MM,
        "height_mm": HEIGHT_MM,
        "min_thickness_mm": 0.8,
        "max_thickness_mm": 3.0,
        "resolution": WIDTH_MM / COLS,
    }
    defaults.update(overrides)
    return GeometryParameters(**defaults)


@pytest.fixture
def varied_image(tmp_path):
    """Degrade non uniforme : necessaire pour distinguer "la geometrie a
    change" de "elle n'a jamais change" -- une image uniforme produirait la
    meme epaisseur des deux cotes meme si le bug n'etait pas corrige."""
    _yy, xx = np.mgrid[0:ROWS, 0:COLS]
    array = ((xx * 255) // COLS).astype(np.uint8)
    path = tmp_path / "gradient.png"
    Image.fromarray(array, mode="L").save(path)
    return path


def _base_zone() -> Zone:
    return Zone(name="Base", composition_mode=CompositionMode.BASE, geometry_params=_params())


def _rose_mask() -> np.ndarray:
    mask = np.zeros((ROWS, COLS), dtype=np.float32)
    mask[10:25, 20:40] = 1.0
    return mask


@pytest.mark.parametrize("composition_mode", [CompositionMode.ADD, CompositionMode.REPLACE])
def test_material_only_zone_never_changes_the_composed_surface(varied_image, composition_mode):
    """Le coeur du bug 0.4.1 : une nouvelle zone (+Zone) a par defaut
    CompositionMode.ADD -- avant le correctif, assigner un materiau via
    cette zone AJOUTAIT sa propre contribution par-dessus la base. Teste
    explicitement ADD (le vrai defaut d'une nouvelle zone) ET REPLACE (l'
    ancien contournement manuel) : color_strategy doit neutraliser les deux."""
    base = _base_zone()
    rose_mask = _rose_mask()

    baseline_sources = [ZoneSource(zone=base, image_path=str(varied_image))]
    z_baseline, active_baseline, _w, _h = compose_scene_heightfield(baseline_sources)

    rose_zone = Zone(
        name="Rose",
        composition_mode=composition_mode,
        relief_mode=ReliefMode.SOLID,  # deliberement tres different du Base (LITHOPHANE)
        geometry_params=_params(min_thickness_mm=5.0, max_thickness_mm=5.0),  # deliberement enorme
        color_strategy=ColorStrategy.MATERIAL_ONLY,
    )
    colored_sources = [
        ZoneSource(zone=base, image_path=str(varied_image)),
        ZoneSource(zone=rose_zone, image_path=str(varied_image), mask=rose_mask),
    ]
    z_colored, active_colored, _w2, _h2 = compose_scene_heightfield(colored_sources)

    assert np.array_equal(z_baseline, z_colored)
    assert np.array_equal(active_baseline, active_colored)


def test_without_color_strategy_replace_still_changes_geometry_as_before(varied_image):
    """Garde-fou : color_strategy=None (comportement historique, defaut de
    tout projet migre) doit continuer a laisser REPLACE modifier la hauteur
    -- ne pas casser l'usage geometrique legitime de REPLACE (ex. gravure)."""
    base = _base_zone()
    rose_mask = _rose_mask()

    replace_zone = Zone(
        name="Gravure",
        composition_mode=CompositionMode.REPLACE,
        relief_mode=ReliefMode.SOLID,
        geometry_params=_params(min_thickness_mm=5.0, max_thickness_mm=5.0),
        color_strategy=None,
    )
    sources = [
        ZoneSource(zone=base, image_path=str(varied_image)),
        ZoneSource(zone=replace_zone, image_path=str(varied_image), mask=rose_mask),
    ]
    z_final, _active, _w, _h = compose_scene_heightfield(sources)

    inside = np.flipud(rose_mask) >= 0.5
    assert np.allclose(z_final[inside], 5.0, atol=1e-3)


def test_material_only_partition_reproduces_the_all_white_surface_exactly(varied_image):
    """Test A de la mission 0.4.1 : genere (1) une lithophanie entierement
    blanche et (2) la meme avec une rose MATERIAL_ONLY -- compare
    numeriquement la surface exterieure des DEUX corps materiaux au mesh
    tout-blanc de reference. Doit etre strictement identique ; seule la
    partition materiau change."""
    base = _base_zone()
    base.material.name = "Blanc"
    all_white_mesh = compose_scene_mesh([ZoneSource(zone=base, image_path=str(varied_image))])

    rose_zone = Zone(
        name="Rose",
        composition_mode=CompositionMode.ADD,
        color_strategy=ColorStrategy.MATERIAL_ONLY,
    )
    rose_zone.material.name = "Rose"
    colored_sources = [
        ZoneSource(zone=base, image_path=str(varied_image)),
        ZoneSource(zone=rose_zone, image_path=str(varied_image), mask=_rose_mask()),
    ]

    partition = partition_mesh_by_material(colored_sources)
    assert set(partition.keys()) == {"Blanc", "Rose"}
    for mesh in partition.values():
        assert validate_mesh(mesh).is_valid

    reunited = trimesh.util.concatenate(list(partition.values()))
    assert reunited.volume == pytest.approx(all_white_mesh.volume, rel=1e-6)
    # meme boite englobante -- aucune bosse, aucun retrait a la frontiere Blanc/Rose
    assert np.allclose(reunited.bounds, all_white_mesh.bounds, atol=1e-4)


def test_base_zone_color_strategy_is_never_skipped(tmp_path):
    """Garde-fou structurel : meme si `color_strategy` etait (a tort)
    positionne sur la zone BASE, elle doit continuer a fournir la geometrie
    -- c'est la fondation, l'exclure viderait tout le resultat."""
    image_path = make_uniform_image(tmp_path / "uniform.png", value=128, width=COLS, height=ROWS)
    base = Zone(
        name="Base",
        composition_mode=CompositionMode.BASE,
        geometry_params=_params(),
        color_strategy=ColorStrategy.MATERIAL_ONLY,
    )
    sources = [ZoneSource(zone=base, image_path=str(image_path))]

    z_final, active_final, _w, _h = compose_scene_heightfield(sources)

    assert active_final.any()
    assert z_final[active_final].min() > 0
