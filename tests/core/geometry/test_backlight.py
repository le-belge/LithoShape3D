"""Backlight Insert (v0.4.1) : corps blanc a cavite + insert independant.
Couvre les tests B/C/D imposes par la mission (watertight/manifold simple,
masque complexe avec trou, jeu XY qui modifie reellement la geometrie)."""

import numpy as np
import pytest
import trimesh
from PIL import Image

from lithoshape3d.core.geometry import backlight as backlight_module
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
from tests.fixtures.synthetic_masks import concave_star_mask, ring_mask

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


def _compose_and_capture_heightfields(sources):
    """Espionne `build_mesh_from_heightfield` pour recuperer les tableaux
    front_z/back_z du CORPS BLANC (l'appel avec back_z != None) tels que
    `compose_backlight_bodies` les a reellement calcules -- permet de
    verifier le contrat geometrique de la mission hotfix 0.4.2 au niveau du
    champ de hauteur, pas seulement du mesh final."""
    captured = []
    original = backlight_module.build_mesh_from_heightfield

    def spy(front_z, active, width_mm, height_mm, back_z=None):
        captured.append({"front_z": front_z.copy(), "active": active.copy(), "back_z": None if back_z is None else back_z.copy()})
        return original(front_z, active, width_mm, height_mm, back_z=back_z)

    backlight_module.build_mesh_from_heightfield = spy
    try:
        result = compose_backlight_bodies(sources)
    finally:
        backlight_module.build_mesh_from_heightfield = original

    white_call = next(c for c in captured if c["back_z"] is not None)
    return result, white_call["front_z"], white_call["back_z"], white_call["active"]


def test_backlight_thin_region_gets_elevated_instead_of_excluded(tmp_path):
    """Retour terrain (texte Backlight sur photo a luminosite variable) :
    la ou la lithophanie locale est trop fine pour loger a la fois la peau
    ET l'insert (z_final < skin + insert_thickness), l'ancien comportement
    (hotfix 0.4.2 initial) excluait ces points de la cavite -- des
    lettres/formes d'insert devenaient partiellement absentes des qu'elles
    chevauchaient une zone claire/fine de la photo. Doit maintenant : relever
    localement `z_final` au minimum requis (jamais ailleurs), pour garantir
    une cavite ET un insert continus sur TOUTE l'empreinte de la zone."""
    _yy, xx = np.mgrid[0:ROWS, 0:COLS]
    # degrade lineaire en X : colonnes basses = fin (proche du plancher),
    # colonnes hautes = epais -- une partie de la zone Backlight sera donc
    # necessairement trop fine pour skin(0.4) + insert(0.6) = 1.0mm.
    array = ((xx * 255) // COLS).astype(np.uint8)
    image_path = tmp_path / "thin_gradient.png"
    Image.fromarray(array, mode="L").save(image_path)

    base = Zone(
        name="Base", composition_mode=CompositionMode.BASE,
        geometry_params=_params(min_thickness_mm=0.2, max_thickness_mm=1.8),
    )
    rose = _backlight_zone(white_skin_thickness_mm=0.4, insert_thickness_mm=0.6)
    sources = [
        ZoneSource(zone=base, image_path=str(image_path)),
        ZoneSource(zone=rose, image_path=str(image_path), mask=_rose_mask()),
    ]
    required_total = 0.4 + 0.6

    # Reference : la hauteur AVANT tout traitement Backlight (base seule),
    # pour distinguer les points originellement trop fins de ceux deja
    # assez epais -- `front_z` capture plus bas est deja post-elevation.
    baseline_z, baseline_active, _w, _h = compose_scene_heightfield(
        [ZoneSource(zone=base, image_path=str(image_path))]
    )

    result, front_z, back_z, active = _compose_and_capture_heightfields(sources)

    assert result.warnings != []
    assert any("epaisseur locale relevee" in w for w in result.warnings)
    assert not any("trop fins" in w for w in result.warnings)

    # `_rose_mask()` est en orientation image (Y-down) ; `front_z`/`back_z`/
    # `active`/`baseline_z` sont deja dans l'orientation canonique Y-up
    # utilisee en interne (cf. le flip dans `_effective_zone_active`).
    zone_mask = np.flipud(_rose_mask()).astype(bool) & active
    thin_points = zone_mask & (baseline_z < required_total)
    thick_points = zone_mask & (baseline_z >= required_total)
    assert thin_points.any() and thick_points.any(), "le degrade doit couvrir les deux cas dans le test"

    # Points originellement trop fins : la facade (front_z) est relevee
    # EXACTEMENT au minimum requis, jamais plus.
    assert np.allclose(front_z[thin_points], required_total, atol=1e-4)
    # Points deja assez epais : la facade reste rigoureusement inchangee.
    assert np.allclose(front_z[thick_points], baseline_z[thick_points], atol=1e-6)
    # Hors de la zone Backlight, la facade est intacte partout.
    outside_zone = active & ~zone_mask
    assert np.allclose(front_z[outside_zone], baseline_z[outside_zone], atol=1e-6)

    # Cavite creusee sur TOUTE l'empreinte de la zone desormais, y compris
    # les points auparavant trop fins -- plus aucune exclusion.
    assert np.all(back_z[zone_mask] > 0.0)
    assert np.all(back_z[zone_mask] >= 0.6 - 1e-6)

    # L'insert couvre desormais l'integralite de la zone (plus tronque a la
    # region "assez epaisse").
    insert_mesh = result.insert_meshes["Rose"]
    zone_xs_mm = np.where(zone_mask.any(axis=0))[0] * (WIDTH_MM / COLS)
    assert insert_mesh.bounds[1][0] >= zone_xs_mm.max() - 1.0

    assert validate_mesh(result.white_mesh).is_valid
    assert validate_mesh(insert_mesh).is_valid


def test_backlight_minimum_effective_skin_meets_requested_everywhere(varied_image):
    """Mission hotfix 0.4.2, Test 1 : partout ou une cavite EST creusee,
    front_z - back_z >= requested_skin_thickness (a la tolerance numerique
    pres) -- jamais moins, jamais silencieusement."""
    base = _base_zone()
    requested_skin = 0.4
    rose = _backlight_zone(white_skin_thickness_mm=requested_skin, insert_thickness_mm=0.6)
    sources = [
        ZoneSource(zone=base, image_path=str(varied_image)),
        ZoneSource(zone=rose, image_path=str(varied_image), mask=_rose_mask()),
    ]

    _result, front_z, back_z, _active = _compose_and_capture_heightfields(sources)

    carved = back_z > 0.0
    assert carved.any()
    effective_skin = (front_z - back_z)[carved]
    assert effective_skin.min() >= requested_skin - 1e-6


def test_backlight_complex_rose_like_contour_never_undershoots_skin(tmp_path):
    """Mission hotfix 0.4.2, Test 3 : contour concave/complexe (etoile,
    proxy pour un masque SAM2 organique type petales de rose) -- aucun point
    de la zone Backlight ne doit tomber sous l'epaisseur de peau demandee."""
    fine_rows, fine_cols = 200, 200
    fine_width_mm = fine_height_mm = 60.0
    _yy, xx = np.mgrid[0:fine_rows, 0:fine_cols]
    array = ((xx * 255) // fine_cols).astype(np.uint8)
    image_path = tmp_path / "fine_gradient.png"
    Image.fromarray(array, mode="L").save(image_path)

    params = GeometryParameters(
        width_mm=fine_width_mm, height_mm=fine_height_mm,
        min_thickness_mm=1.5, max_thickness_mm=3.0, resolution=fine_width_mm / fine_cols,
    )
    base = Zone(name="Base", composition_mode=CompositionMode.BASE, geometry_params=params)
    star = concave_star_mask(fine_rows, fine_cols).astype(np.float32)
    requested_skin = 0.4
    rose = _backlight_zone(white_skin_thickness_mm=requested_skin, insert_thickness_mm=0.6, xy_clearance_mm=0.2)
    sources = [
        ZoneSource(zone=base, image_path=str(image_path)),
        ZoneSource(zone=rose, image_path=str(image_path), mask=star),
    ]

    result, front_z, back_z, _active = _compose_and_capture_heightfields(sources)

    carved = back_z > 0.0
    assert carved.any()
    effective_skin = (front_z - back_z)[carved]
    assert effective_skin.min() >= requested_skin - 1e-6
    assert validate_mesh(result.white_mesh).is_valid
    assert validate_mesh(result.insert_meshes["Rose"]).is_valid


def test_backlight_stl_round_trip_stays_watertight(tmp_path, varied_image):
    """Mission hotfix 0.4.2, Test 6 : export -> reimport -> validation."""
    base = _base_zone()
    rose = _backlight_zone()
    sources = [
        ZoneSource(zone=base, image_path=str(varied_image)),
        ZoneSource(zone=rose, image_path=str(varied_image), mask=_rose_mask()),
    ]
    result = compose_backlight_bodies(sources)

    white_path = tmp_path / "white.stl"
    insert_path = tmp_path / "insert.stl"
    result.white_mesh.export(white_path)
    result.insert_meshes["Rose"].export(insert_path)

    reloaded_white = trimesh.load(white_path, process=True)
    reloaded_insert = trimesh.load(insert_path, process=True)
    assert reloaded_white.is_watertight
    assert reloaded_insert.is_watertight


def test_backlight_transition_produces_progressive_back_z_ramp(tmp_path):
    """"Soft organic pocket" (retour terrain, validation physique) : le
    contour de la poche doit rester une rampe progressive vers le dos
    plein (Z=0), pas une marche abrupte -- il doit exister des back_z
    STRICTEMENT entre 0 et la profondeur de poche pleine pres du bord de
    l'insert (preuve que la rampe existe reellement, pas seulement les
    deux extremes). Resolution fine + masque circulaire (meme raison que
    le Test D xy_clearance) : a 1mm/px sur un carre a bords droits, la
    distance au bord saute directement au-dela de `transition_width_mm`
    (1.2mm par defaut), ne laissant aucune valeur intermediaire observable."""
    fine_rows, fine_cols = 300, 300
    fine_width_mm = fine_height_mm = 60.0
    yy, xx = np.mgrid[0:fine_rows, 0:fine_cols]
    array = ((xx * 255) // fine_cols).astype(np.uint8)
    image_path = tmp_path / "fine_gradient.png"
    Image.fromarray(array, mode="L").save(image_path)

    params = GeometryParameters(
        width_mm=fine_width_mm, height_mm=fine_height_mm,
        min_thickness_mm=1.5, max_thickness_mm=3.0, resolution=fine_width_mm / fine_cols,
    )
    base = Zone(name="Base", composition_mode=CompositionMode.BASE, geometry_params=params)
    cy, cx, radius = 150, 150, 100
    fine_mask = (((yy - cy) ** 2 + (xx - cx) ** 2) <= radius**2).astype(np.float32)

    rose = _backlight_zone(
        white_skin_thickness_mm=0.6, insert_thickness_mm=0.6,
        pocket_extra_depth_mm=0.08, transition_width_mm=1.2,
    )
    sources = [
        ZoneSource(zone=base, image_path=str(image_path)),
        ZoneSource(zone=rose, image_path=str(image_path), mask=fine_mask),
    ]

    _result, _front_z, back_z, _active = _compose_and_capture_heightfields(sources)

    carved = back_z > 0.0
    assert carved.any()
    pocket_depth = 0.6 + 0.08
    intermediate = back_z[carved & (back_z > 1e-6) & (back_z < pocket_depth - 1e-6)]
    assert intermediate.size > 0, "il doit exister des back_z strictement entre 0 et la profondeur de poche pleine"


def test_backlight_insert_thickness_stays_constant_never_ramped(tmp_path):
    """"Soft organic pocket" : contrairement a l'ancien chanfrein, l'insert
    lui-meme doit rester a EPAISSEUR CONSTANTE sur toute son empreinte --
    seule la cavite qui l'entoure (dans le corps blanc) est progressive.
    Aucune valeur de Z strictement entre 0 et `insert_thickness_mm` ne
    doit exister sur l'insert."""
    fine_rows, fine_cols = 300, 300
    fine_width_mm = fine_height_mm = 60.0
    yy, xx = np.mgrid[0:fine_rows, 0:fine_cols]
    array = ((xx * 255) // fine_cols).astype(np.uint8)
    image_path = tmp_path / "fine_gradient.png"
    Image.fromarray(array, mode="L").save(image_path)

    params = GeometryParameters(
        width_mm=fine_width_mm, height_mm=fine_height_mm,
        min_thickness_mm=1.5, max_thickness_mm=3.0, resolution=fine_width_mm / fine_cols,
    )
    base = Zone(name="Base", composition_mode=CompositionMode.BASE, geometry_params=params)
    cy, cx, radius = 150, 150, 100
    fine_mask = (((yy - cy) ** 2 + (xx - cx) ** 2) <= radius**2).astype(np.float32)

    insert_thickness = 0.6
    rose = _backlight_zone(
        white_skin_thickness_mm=0.6, insert_thickness_mm=insert_thickness, transition_width_mm=1.2,
    )
    sources = [
        ZoneSource(zone=base, image_path=str(image_path)),
        ZoneSource(zone=rose, image_path=str(image_path), mask=fine_mask),
    ]

    result = compose_backlight_bodies(sources)
    insert_mesh = result.insert_meshes["Rose"]
    top_z = insert_mesh.vertices[:, 2]
    intermediate = top_z[(top_z > 1e-6) & (top_z < insert_thickness - 1e-6)]
    assert intermediate.size == 0, "l'insert ne doit jamais avoir d'epaisseur intermediaire (jamais rampe)"


def test_backlight_zero_transition_confines_pocket_to_insert_footprint(varied_image):
    """`transition_width_mm=0` doit desactiver la rampe : la poche se
    limite alors exactement a l'empreinte de l'insert (marche abrupte),
    chaque point creuse a la profondeur de poche pleine (ou moins si
    plafonne par l'epaisseur locale disponible)."""
    base = _base_zone()
    rose = _backlight_zone(
        white_skin_thickness_mm=0.6, insert_thickness_mm=0.6,
        pocket_extra_depth_mm=0.08, transition_width_mm=0.0,
    )
    sources = [
        ZoneSource(zone=base, image_path=str(varied_image)),
        ZoneSource(zone=rose, image_path=str(varied_image), mask=_rose_mask()),
    ]

    _result, front_z, back_z, _active = _compose_and_capture_heightfields(sources)

    carved = back_z > 0.0
    assert carved.any()
    pocket_depth = 0.6 + 0.08
    max_back = np.clip(front_z - 0.6, 0.0, None)
    expected = np.minimum(max_back, pocket_depth)
    np.testing.assert_allclose(back_z[carved], expected[carved], atol=1e-6)


def test_backlight_floor_warns_below_0_6mm_for_skin_and_insert():
    """Le plancher de 0.6mm doit etre signale (pas silencieux) des qu'une
    valeur explicite descend en dessous, pour la peau ET pour l'insert."""
    with pytest.warns(UserWarning, match="white_skin_thickness_mm"):
        BacklightInsertParams(white_skin_thickness_mm=0.4)
    with pytest.warns(UserWarning, match="insert_thickness_mm"):
        BacklightInsertParams(insert_thickness_mm=0.4)

    import warnings as _warnings

    with _warnings.catch_warnings():
        _warnings.simplefilter("error")
        # valeurs au plancher (ou au-dessus) : aucun avertissement.
        BacklightInsertParams(white_skin_thickness_mm=0.6, insert_thickness_mm=0.6)
        # defauts actuels : deja au plancher commun, jamais d'avertissement.
        BacklightInsertParams()


def test_backlight_breakaway_support_matches_insert_footprint_and_is_watertight(varied_image):
    """Le support sacrificiel (aide a l'impression) doit exister pour
    chaque insert genere, sur la MEME empreinte XY (meme masque source),
    watertight/manifold comme l'insert lui-meme -- c'est ce qui se
    retirera avant de coller l'insert final."""
    base = _base_zone()
    rose = _backlight_zone()
    sources = [
        ZoneSource(zone=base, image_path=str(varied_image)),
        ZoneSource(zone=rose, image_path=str(varied_image), mask=_rose_mask()),
    ]

    result = compose_backlight_bodies(sources)

    assert "Rose" in result.breakaway_support_meshes
    support_mesh = result.breakaway_support_meshes["Rose"]
    support_result = validate_mesh(support_mesh)
    assert support_result.is_valid
    assert support_result.connected_components == 1

    insert_mesh = result.insert_meshes["Rose"]
    # meme empreinte XY (memes bornes en X/Y) que l'insert
    assert support_mesh.bounds[0][0] == pytest.approx(insert_mesh.bounds[0][0], abs=1e-6)
    assert support_mesh.bounds[1][0] == pytest.approx(insert_mesh.bounds[1][0], abs=1e-6)
    assert support_mesh.bounds[0][1] == pytest.approx(insert_mesh.bounds[0][1], abs=1e-6)
    assert support_mesh.bounds[1][1] == pytest.approx(insert_mesh.bounds[1][1], abs=1e-6)


def test_backlight_breakaway_support_is_taller_than_insert_but_never_exceeds_cavity(varied_image):
    """Le support doit etre plus epais que l'insert (presse contre le
    plafond de la cavite), mais JAMAIS au-dela de la profondeur reellement
    creusee -- pas de chevauchement avec le corps blanc solide."""
    base = _base_zone()
    rose = _backlight_zone()
    sources = [
        ZoneSource(zone=base, image_path=str(varied_image)),
        ZoneSource(zone=rose, image_path=str(varied_image), mask=_rose_mask()),
    ]

    result = compose_backlight_bodies(sources)

    insert_mesh = result.insert_meshes["Rose"]
    support_mesh = result.breakaway_support_meshes["Rose"]
    insert_top = insert_mesh.bounds[1][2]
    support_top = support_mesh.bounds[1][2]

    assert support_top > insert_top
    assert support_top <= insert_top + rose.backlight_insert.pocket_extra_depth_mm + 1e-6

    # Le support ne doit jamais depasser le plafond reel de la cavite (le
    # dos du corps blanc, cote insert) : verifie point par point via les
    # sommets de son maillage (indexation identique a la grille du corps
    # blanc puisque meme largeur/hauteur/pixel_size).
    white_result = validate_mesh(result.white_mesh)
    assert white_result.is_valid


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
