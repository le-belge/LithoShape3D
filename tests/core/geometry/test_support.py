"""Pied/support d'impression (v0.3) : fusion manifold3d au modele compose."""

import numpy as np
import pytest

from lithoshape3d.core.geometry.heightmap import Heightmap
from lithoshape3d.core.geometry.mesh_builder import build_slab_mesh
from lithoshape3d.core.geometry.support import (
    attach_support,
    build_side_stabilizer_mesh,
    build_side_stabilizer_pair,
    build_support_mesh,
)
from lithoshape3d.core.scene.models import GeometryParameters, PrintSupport, SupportType
from lithoshape3d.core.validation.mesh_checks import validate_mesh

WIDTH_MM, HEIGHT_MM = 60.0, 40.0


@pytest.fixture
def panel_mesh():
    heightmap = Heightmap(values=np.full((60, 80), 0.5, dtype=np.float32))
    params = GeometryParameters(width_mm=WIDTH_MM, height_mm=HEIGHT_MM, resolution=0.75)
    return build_slab_mesh(heightmap, mask=None, params=params)


def test_support_none_returns_mesh_unchanged(panel_mesh):
    fused = attach_support(panel_mesh, PrintSupport(support_type=SupportType.NONE))

    assert fused is panel_mesh


def test_build_support_mesh_none_returns_none():
    assert build_support_mesh(0.0, WIDTH_MM, 0.0, PrintSupport(support_type=SupportType.NONE)) is None


@pytest.mark.parametrize("support_type", [SupportType.FLAT, SupportType.REINFORCED])
def test_support_fuses_into_single_manifold_body(panel_mesh, support_type):
    fused = attach_support(panel_mesh, PrintSupport(support_type=support_type))

    result = validate_mesh(fused)
    assert result.is_watertight
    assert result.is_winding_consistent
    assert result.manifold3d_compatible
    assert result.connected_components == 1
    assert not np.isnan(fused.vertices).any()
    assert not np.isinf(fused.vertices).any()


def test_support_does_not_float_below_the_panel(panel_mesh):
    """Le pied doit toucher/recouvrir le panneau, pas etre detache dans l'espace."""
    fused = attach_support(panel_mesh, PrintSupport(support_type=SupportType.FLAT))

    assert fused.bounds[0][1] < 0.0  # s'etend bien sous Y=0 (bord bas du panneau)
    assert validate_mesh(fused).connected_components == 1


def test_support_respects_overhang_and_height_params(panel_mesh):
    support = PrintSupport(
        support_type=SupportType.FLAT, height_mm=12.0, overhang_left_mm=3.0, overhang_right_mm=7.0
    )
    fused = attach_support(panel_mesh, support)

    assert fused.bounds[0][0] == pytest.approx(-3.0, abs=0.5)
    assert fused.bounds[1][0] == pytest.approx(WIDTH_MM + 7.0, abs=0.5)
    assert fused.bounds[0][1] == pytest.approx(-12.0, abs=0.5)


def test_support_does_not_alter_panel_content_above_the_seam(panel_mesh):
    """Le pied ne doit pas modifier le contenu lithophanique au-dessus de la
    zone de raccord : les sommets du panneau loin de Y=0 restent inchanges."""
    fused = attach_support(panel_mesh, PrintSupport(support_type=SupportType.FLAT))

    far_from_seam = panel_mesh.vertices[panel_mesh.vertices[:, 1] > HEIGHT_MM * 0.5]
    for vertex in far_from_seam[:: max(1, len(far_from_seam) // 20)]:
        assert np.any(np.linalg.norm(fused.vertices - vertex, axis=1) < 1e-4)


def test_reinforced_uses_more_material_than_flat(panel_mesh):
    flat = attach_support(panel_mesh, PrintSupport(support_type=SupportType.FLAT))
    reinforced = attach_support(panel_mesh, PrintSupport(support_type=SupportType.REINFORCED))

    assert reinforced.volume > flat.volume


@pytest.mark.parametrize("support_type", [SupportType.FLAT, SupportType.REINFORCED])
def test_support_fuses_with_a_shape_whose_lowest_point_is_above_y_zero(support_type, tmp_path):
    """Regression (2.13) : un Coeur (ShapeMask) inscrit avec marge dans la
    grille canonique a son point le plus bas nettement au-dessus de Y=0
    (verifie empiriquement ~10mm sur une grille 100x100mm/2mm-px) -- pas un
    bord bas rectangulaire droit touchant Y=0. Le pied doit se caler sur ce
    point reel (`y_top`), sinon il reste flottant sous le modele et l'union
    manifold3d rend deux composantes disjointes au lieu d'un seul corps
    imprimable."""
    from PIL import Image

    from lithoshape3d.core.geometry.composition import ZoneSource, compose_scene_mesh
    from lithoshape3d.core.geometry.shape import build_shape_mask
    from lithoshape3d.core.scene.models import (
        CompositionMode,
        ReliefMode,
        ShapeParams,
        ShapeType,
        Zone,
    )
    from lithoshape3d.core.validation.mesh_checks import validate_mesh

    image_path = tmp_path / "uniform.png"
    Image.fromarray(np.full((300, 300), 150, dtype=np.uint8), mode="L").save(image_path)

    params = GeometryParameters(width_mm=100.0, height_mm=100.0, resolution=2.0)
    zone = Zone(name="base", composition_mode=CompositionMode.BASE, relief_mode=ReliefMode.LITHOPHANE, geometry_params=params)
    heart = build_shape_mask(ShapeParams(shape_type=ShapeType.HEART), 50, 50)
    panel = compose_scene_mesh([ZoneSource(zone=zone, image_path=str(image_path))], shape_mask=heart)
    assert panel.bounds[0][1] > 5.0  # confirme que le point le plus bas n'est PAS pres de Y=0

    fused = attach_support(panel, PrintSupport(support_type=support_type, height_mm=6.0))
    result = validate_mesh(fused)

    assert result.is_valid
    assert result.connected_components == 1


# --------------------------------------------------------------------- #
# Stabilisateurs lateraux (aide a l'impression, jamais fusionnes)
# --------------------------------------------------------------------- #


def _contact_point_at_height(mesh, y: float, *, x_max: bool):
    """Coupe transversale a la hauteur `y` : point de contact le plus
    proche du panneau (max en X pour le stabilisateur gauche, min pour
    le droit -- apres rotation du gabarit, ce sont les DENTS, pas le dos
    plat, qui atteignent cette valeur, periodiquement le long de Y --
    voir docstring de module). Retourne (x, z) du point trouve, ou None
    si aucune section a cette hauteur."""
    section = mesh.section(plane_origin=[0, y, 0], plane_normal=[0, 1, 0])
    if section is None:
        return None
    pts = section.vertices
    idx = int(np.argmax(pts[:, 0]) if x_max else np.argmin(pts[:, 0]))
    return float(pts[idx, 0]), float(pts[idx, 2])


def test_side_stabilizer_pair_are_watertight_and_never_fused():
    left, right = build_side_stabilizer_pair(
        panel_width_mm=100.0, y_bottom=0.0, y_top=140.0, panel_thickness_mm=2.65
    )

    for mesh in (left, right):
        result = validate_mesh(mesh)
        assert result.is_valid
        assert result.connected_components == 1


def test_side_stabilizer_teeth_touch_the_panel_edges_periodically_never_beyond():
    """Apres rotation du gabarit (dents en contact, pas la face large du
    coin -- retour terrain utilisateur), verifie sur plusieurs hauteurs :
    les dents affleurent EXACTEMENT X=0 (gauche) / X=panel_width_mm
    (droite) a certaines hauteurs (motif periodique), et le corps ne
    depasse JAMAIS ce bord (jamais de chevauchement dans le panneau)."""
    panel_width = 100.0
    left, right = build_side_stabilizer_pair(
        panel_width_mm=panel_width, y_bottom=0.0, y_top=140.0, panel_thickness_mm=2.65
    )

    # Depuis l'ajout du recouvrement volontaire (retour terrain : une
    # simple tangence peut ne pas etre vue comme un contact reel par le
    # slicer, cf. `_STABILIZER_CONTACT_OVERLAP_MM`), les dents penetrent
    # legerement DANS le panneau plutot que d'affleurer exactement X=0 /
    # X=panel_width_mm.
    overlap = 0.12

    left_contacts = [
        _contact_point_at_height(left, y, x_max=True) for y in np.linspace(2.0, 138.0, 12)
    ]
    left_x = [x for x, _z in left_contacts]
    assert any(x == pytest.approx(overlap, abs=1e-3) for x in left_x), (
        "Aucune dent ne touche a la profondeur de recouvrement attendue sur le stabilisateur gauche."
    )
    assert all(x <= overlap + 1e-6 for x in left_x), "Le stabilisateur gauche deborde trop dans le panneau."

    right_contacts = [
        _contact_point_at_height(right, y, x_max=False) for y in np.linspace(2.0, 138.0, 12)
    ]
    right_x = [x for x, _z in right_contacts]
    assert any(x == pytest.approx(panel_width - overlap, abs=1e-3) for x in right_x), (
        "Aucune dent ne touche a la profondeur de recouvrement attendue sur le stabilisateur droit."
    )
    assert all(x >= panel_width - overlap - 1e-6 for x in right_x), (
        "Le stabilisateur droit deborde trop dans le panneau."
    )


def test_side_stabilizer_contact_ridge_is_aligned_with_panel_thickness_in_depth():
    """Regression du bug reel signale par l'utilisateur (mesure au regle
    du slicer sur un export reel : ~13mm d'ecart en profondeur/Y, alors
    que X touchait deja parfaitement) : la nervure de contact du gabarit
    est nativement centree a 15mm de profondeur (moitie de sa largeur
    native 30mm), SANS AUCUN RAPPORT avec l'epaisseur du panneau -- sans
    recalage explicite, les dents "touchent" X=0/panel_width_mm en
    projection plate, mais a une profondeur Z totalement hors de la ou
    le panneau existe reellement (Z=[0, panel_thickness_mm]), donc sans
    contact reel en 3D. Verifie que le point de contact (X) trouve a
    chaque hauteur testee a aussi un Z a l'INTERIEUR de l'epaisseur
    reelle du panneau."""
    panel_thickness = 2.65
    left, _right = build_side_stabilizer_pair(
        panel_width_mm=100.0, y_bottom=0.0, y_top=140.0, panel_thickness_mm=panel_thickness
    )

    overlap = 0.12
    contacts = [_contact_point_at_height(left, y, x_max=True) for y in np.linspace(2.0, 138.0, 12)]
    touching_zs = [z for x, z in contacts if x == pytest.approx(overlap, abs=1e-3)]
    assert touching_zs, "Aucun point de contact trouve -- verifier le motif periodique."
    for z in touching_zs:
        assert -1e-6 <= z <= panel_thickness + 1e-6, (
            f"Nervure de contact a Z={z:.2f}mm, hors de l'epaisseur du panneau "
            f"[0, {panel_thickness}]mm -- pas de contact 3D reel malgre un X correct."
        )


def test_side_stabilizer_spans_the_full_panel_height():
    y_bottom, y_top = 5.0, 145.0
    left, _right = build_side_stabilizer_pair(
        panel_width_mm=100.0, y_bottom=y_bottom, y_top=y_top, panel_thickness_mm=2.65
    )

    # Tolerance non-triviale : le gabarit source a lui-meme un residu
    # sub-micrometrique sur ses propres bornes (STL tel que fourni, avant
    # toute transformation) -- voir bounds natifs mesures dans le module.
    assert left.bounds[0][1] == pytest.approx(y_bottom, abs=1e-3)
    assert left.bounds[1][1] == pytest.approx(y_top, abs=1e-3)


def test_side_stabilizer_depth_extent_matches_the_original_template_regardless_of_panel():
    """Le gabarit reel a sa propre etendue de profondeur fixe (30mm,
    ancien axe largeur du coin avant rotation) -- contrairement a
    l'ancienne approximation, elle ne suit JAMAIS l'epaisseur du panneau
    (une lithophanie fine de 0.8mm n'a pas besoin d'un stabilisateur
    aussi fin et fragile). Seule la POSITION (pas l'etendue) de cette
    plage de 30mm change avec panel_thickness_mm, pour recentrer la
    nervure -- voir test dedie ci-dessus."""
    thin_panel = build_side_stabilizer_mesh(0.0, 100.0, side="left", panel_thickness_mm=0.8)
    depth_extent = thin_panel.bounds[1][2] - thin_panel.bounds[0][2]
    assert depth_extent == pytest.approx(30.0, abs=1e-3)


def test_side_stabilizer_rejects_invalid_side():
    with pytest.raises(ValueError, match="side"):
        build_side_stabilizer_mesh(0.0, 100.0, side="top", panel_thickness_mm=2.65)


def test_side_stabilizer_teeth_overlap_the_panel_edge_not_merely_tangent():
    """Retour terrain (ChatGPT) : une simple tangence (0.000mm) peut ne
    pas etre vue comme un vrai contact par le slicer (arrondi flottant a
    l'export, notamment introduit par le miroir du cote droit). Les dents
    doivent penetrer legerement DANS le panneau, pas seulement l'effleurer."""
    panel_width = 100.0
    left, right = build_side_stabilizer_pair(
        panel_width_mm=panel_width, y_bottom=0.0, y_top=140.0, panel_thickness_mm=2.65
    )
    assert left.bounds[1][0] > 1e-6, "Le stabilisateur gauche ne recouvre pas le panneau (simple tangence)."
    assert right.bounds[0][0] < panel_width - 1e-6, (
        "Le stabilisateur droit ne recouvre pas le panneau (simple tangence)."
    )


def test_real_edge_profile_uses_actual_vertices_not_global_bbox():
    """`real_edge_profile` doit caler la nervure sur la matiere REELLEMENT
    presente pres du bord concerne -- pas sur la bbox globale, qui peut
    ne pas etre representative d'un panneau non rectangulaire (bord
    incline, aminci localement)."""
    import trimesh

    from lithoshape3d.core.geometry.support import real_edge_profile

    mesh = trimesh.creation.box(extents=[100.0, 140.0, 2.65])
    mesh.apply_translation([50.0, 70.0, 1.325])

    y_bottom, y_top, z_bottom, z_top = real_edge_profile([mesh], "left")
    assert y_bottom == pytest.approx(0.0, abs=1e-3)
    assert y_top == pytest.approx(140.0, abs=1e-3)
    assert z_bottom == pytest.approx(0.0, abs=1e-3)
    assert z_top == pytest.approx(2.65, abs=1e-3)


def test_real_edge_profile_rejects_empty_meshes():
    from lithoshape3d.core.geometry.support import real_edge_profile

    with pytest.raises(ValueError):
        real_edge_profile([], "left")


def test_side_stabilizer_pair_accepts_independent_ridge_centers_per_side():
    """Retour terrain : rien ne garantit que le bord gauche et le bord
    droit d'un panneau non rectangulaire soient symetriques -- chaque
    cote doit pouvoir etre recale independamment sur SA PROPRE epaisseur
    reelle (cf. `real_edge_profile` + `left_ridge_center_z_mm` /
    `right_ridge_center_z_mm`)."""
    left, right = build_side_stabilizer_pair(
        panel_width_mm=100.0,
        y_bottom=0.0,
        y_top=140.0,
        panel_thickness_mm=2.65,
        left_ridge_center_z_mm=1.0,
        right_ridge_center_z_mm=5.0,
    )
    # Un override de centre par cote doit deplacer la plage Z ENTIERE de
    # ce cote de exactement (override - centre par defaut) -- gauche et
    # droite peuvent donc finir a des profondeurs differentes l'un de
    # l'autre, chacun cale sur SA PROPRE geometrie reelle.
    assert float(left.bounds[:, 2].mean()) == pytest.approx(1.0, abs=1e-3)
    assert float(right.bounds[:, 2].mean()) == pytest.approx(5.0, abs=1e-3)
    assert float(left.bounds[:, 2].mean()) != pytest.approx(
        float(right.bounds[:, 2].mean()), abs=1e-3
    )
