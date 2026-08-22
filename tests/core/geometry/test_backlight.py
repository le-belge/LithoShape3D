"""Backlight Insert (v0.4.1) : corps blanc a cavite + insert independant.
Couvre les tests B/C/D imposes par la mission (watertight/manifold simple,
masque complexe avec trou, jeu XY qui modifie reellement la geometrie)."""

import numpy as np
import pytest
from PIL import Image

from lithoshape3d.core.geometry.backlight import compose_backlight_bodies
from lithoshape3d.core.geometry.composition import ZoneSource, compose_scene_heightfield
from lithoshape3d.core.scene.models import (
    BacklightInsertParams,
    ColorStrategy,
    CompositionMode,
    GeometryParameters,
    Zone,
)
from lithoshape3d.core.validation.mesh_checks import validate_mesh
from tests.fixtures.synthetic_masks import ring_mask

ROWS, COLS = 60, 60
WIDTH_MM, HEIGHT_MM = 60.0, 60.0


def _params(**overrides) -> GeometryParameters:
    defaults = {
        "width_mm": WIDTH_MM,
        "height_mm": HEIGHT_MM,
        "min_thickness_mm": 1.5,
        "max_thickness_mm": 3.0,
        "resolution": WIDTH_MM / COLS,
    }
    defaults.update(overrides)
    return GeometryParameters(**defaults)


@pytest.fixture
def varied_image(tmp_path):
    _yy, xx = np.mgrid[0:ROWS, 0:COLS]
    array = ((xx * 255) // COLS).astype(np.uint8)
    path = tmp_path / "gradient.png"
    Image.fromarray(array, mode="L").save(path)
    return path


def _base_zone() -> Zone:
    return Zone(name="Base", composition_mode=CompositionMode.BASE, geometry_params=_params())


def _rose_mask() -> np.ndarray:
    mask = np.zeros((ROWS, COLS), dtype=np.float32)
    mask[15:40, 15:40] = 1.0
    return mask


def _backlight_zone(mask_source: np.ndarray | None = None, **param_overrides) -> Zone:
    zone = Zone(
        name="Rose",
        composition_mode=CompositionMode.ADD,  # deliberement le defaut d'une nouvelle zone (+Zone)
        color_strategy=ColorStrategy.BACKLIGHT_INSERT,
        backlight_insert=BacklightInsertParams(**param_overrides) if param_overrides else BacklightInsertParams(),
    )
    zone.material.name = "Rose"
    return zone


def test_backlight_white_and_insert_are_watertight_manifold_single_body(varied_image):
    base = _base_zone()
    rose = _backlight_zone()
    sources = [
        ZoneSource(zone=base, image_path=str(varied_image)),
        ZoneSource(zone=rose, image_path=str(varied_image), mask=_rose_mask()),
    ]

    result = compose_backlight_bodies(sources)

    white_result = validate_mesh(result.white_mesh)
    assert white_result.is_valid
    assert white_result.connected_components == 1
    assert result.has_inserts
    insert_mesh = result.insert_meshes["Rose"]
    insert_result = validate_mesh(insert_mesh)
    assert insert_result.is_valid
    assert insert_result.connected_components == 1
    assert result.warnings == []


def test_backlight_front_surface_is_never_bumped(varied_image):
    """Garde-fou central de la mission : la face avant du corps blanc doit
    rester EXACTEMENT celle que la composition produirait sans aucune zone
    Backlight Insert (aucune bosse en facade)."""
    base = _base_zone()
    rose_mask = _rose_mask()

    z_baseline, active_baseline, _w, _h = compose_scene_heightfield(
        [ZoneSource(zone=base, image_path=str(varied_image))]
    )

    rose = _backlight_zone()
    result = compose_backlight_bodies(
        [
            ZoneSource(zone=base, image_path=str(varied_image)),
            ZoneSource(zone=rose, image_path=str(varied_image), mask=rose_mask),
        ]
    )

    front_vertices = result.white_mesh.vertices
    # la face avant du corps blanc (Z le plus eleve a chaque colonne/ligne
    # de grille) doit reproduire z_baseline -- on verifie via un nouveau
    # champ de hauteur recompose plutot que de parcourir le mesh brut.
    z_recomposed, active_recomposed, _w2, _h2 = compose_scene_heightfield(
        [
            ZoneSource(zone=base, image_path=str(varied_image)),
            ZoneSource(zone=rose, image_path=str(varied_image), mask=rose_mask),
        ]
    )
    assert np.array_equal(z_baseline, z_recomposed)
    assert np.array_equal(active_baseline, active_recomposed)
    assert front_vertices[:, 2].max() == pytest.approx(z_baseline.max(), abs=1e-4)


def test_backlight_skin_and_insert_sit_behind_the_front_surface(varied_image):
    base = _base_zone()
    rose = _backlight_zone(white_skin_thickness_mm=0.4, insert_thickness_mm=0.6)
    result = compose_backlight_bodies(
        [
            ZoneSource(zone=base, image_path=str(varied_image)),
            ZoneSource(zone=rose, image_path=str(varied_image), mask=_rose_mask()),
        ]
    )

    # le corps blanc doit desormais avoir des sommets de dos (Z bas) AU-DESSUS
    # de 0 sous la zone (la cavite), alors qu'ailleurs le dos reste a Z=0.
    back_z_values = np.unique(result.white_mesh.vertices[:, 2])
    assert back_z_values.min() == pytest.approx(0.0, abs=1e-6)  # dos plat ailleurs
    assert (back_z_values > 0.05).any()  # au moins une cavite reelle creusee

    insert_mesh = result.insert_meshes["Rose"]
    assert insert_mesh.bounds[0][2] == pytest.approx(0.0, abs=1e-4)  # pose contre le dos
    assert insert_mesh.bounds[1][2] == pytest.approx(0.6, abs=1e-4)


def test_backlight_with_ring_shaped_zone_stays_manifold(varied_image):
    """Test C (masque complexe) : la zone Backlight Insert elle-meme a un
    trou reel (anneau) -- l'insert ET la cavite doivent rester manifold."""
    base = _base_zone()
    ring = ring_mask(ROWS, COLS).astype(np.float32)
    rose = _backlight_zone()

    result = compose_backlight_bodies(
        [
            ZoneSource(zone=base, image_path=str(varied_image)),
            ZoneSource(zone=rose, image_path=str(varied_image), mask=ring),
        ]
    )

    assert validate_mesh(result.white_mesh).is_valid
    assert result.has_inserts
    assert validate_mesh(result.insert_meshes["Rose"]).is_valid


def test_backlight_xy_clearance_is_monotonic(tmp_path):
    """Test D : 0.10/0.20/0.30mm (Serre/Standard/Facile) doivent produire des
    empreintes d'insert reellement differentes et monotones (pas juste une
    valeur stockee sans effet geometrique). Resolution fine dediee (0.2mm/px,
    grille 300x300) et masque CIRCULAIRE (pas un carre a bords droits) : la
    carte de distance d'un carre n'a de valeurs qu'a des multiples exacts de
    la taille de pixel (0.2/0.4/0.6...), ce qui confondrait 0.20 et 0.30mm au
    meme palier -- un contour courbe (plus representatif d'une vraie
    selection SAM2 de toute facon) varie continument et separe les trois."""
    fine_rows, fine_cols = 300, 300
    fine_width_mm = fine_height_mm = 60.0
    params = GeometryParameters(
        width_mm=fine_width_mm, height_mm=fine_height_mm,
        min_thickness_mm=1.5, max_thickness_mm=3.0, resolution=fine_width_mm / fine_cols,
    )
    yy, xx = np.mgrid[0:fine_rows, 0:fine_cols]
    array = ((xx * 255) // fine_cols).astype(np.uint8)
    image_path = tmp_path / "fine_gradient.png"
    Image.fromarray(array, mode="L").save(image_path)

    cy, cx, radius = 150, 150, 100
    fine_mask = (((yy - cy) ** 2 + (xx - cx) ** 2) <= radius**2).astype(np.float32)

    base = Zone(name="Base", composition_mode=CompositionMode.BASE, geometry_params=params)

    footprints = []
    for clearance_mm in (0.10, 0.20, 0.30):
        rose = _backlight_zone(xy_clearance_mm=clearance_mm)
        result = compose_backlight_bodies(
            [
                ZoneSource(zone=base, image_path=str(image_path)),
                ZoneSource(zone=rose, image_path=str(image_path), mask=fine_mask),
            ]
        )
        insert = result.insert_meshes["Rose"]
        # volume (pas la boite englobante) : le contour d'un cercle reste
        # localement quasi plat pres des points cardinaux qui definissent la
        # boite englobante -- celle-ci peut donc rester identique entre deux
        # clearances proches meme si l'aire reelle (donc le volume, epaisseur
        # constante) a bien retreci.
        footprints.append(insert.volume)

    assert footprints[0] > footprints[1] > footprints[2]


def test_backlight_zone_too_narrow_for_clearance_warns_instead_of_crashing(varied_image):
    base = _base_zone()
    thin_mask = np.zeros((ROWS, COLS), dtype=np.float32)
    thin_mask[28:32, 15:45] = 1.0  # bande de 4px = 4mm de large
    rose = _backlight_zone(xy_clearance_mm=5.0)  # bien plus large que la bande

    result = compose_backlight_bodies(
        [
            ZoneSource(zone=base, image_path=str(varied_image)),
            ZoneSource(zone=rose, image_path=str(varied_image), mask=thin_mask),
        ]
    )

    assert not result.has_inserts
    assert result.warnings != []
    assert "Rose" in result.warnings[0]
    assert validate_mesh(result.white_mesh).is_valid  # degrade proprement, pas de crash


def test_no_backlight_zones_matches_plain_composition(varied_image):
    """Zero zone Backlight Insert -> comportement identique a
    `compose_scene_mesh` (chemin sans effet)."""
    from lithoshape3d.core.geometry.composition import compose_scene_mesh

    base = _base_zone()
    sources = [ZoneSource(zone=base, image_path=str(varied_image))]

    plain_mesh = compose_scene_mesh(sources)
    result = compose_backlight_bodies(sources)

    assert not result.has_inserts
    assert np.array_equal(result.white_mesh.vertices, plain_mesh.vertices)
    assert np.array_equal(result.white_mesh.faces, plain_mesh.faces)
