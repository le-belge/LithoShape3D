"""Export multi-materiau (v0.3) : 3MF standard multi-objets + repli STL."""

import pytest
import trimesh

from lithoshape3d.core.export.multi_material_export import (
    export_multi_material_3mf,
    export_stl_per_material,
)


def _box(extents, offset=(0.0, 0.0, 0.0)) -> trimesh.Trimesh:
    mesh = trimesh.creation.box(extents=extents)
    mesh.apply_translation(offset)
    return mesh


def test_export_3mf_roundtrips_all_bodies_aligned(tmp_path):
    material_meshes = {
        "Blanc": _box([40, 30, 3], offset=(20, 15, 1.5)),
        "Rose": _box([10, 10, 2], offset=(20, 15, 1.0)),
    }
    output_path = tmp_path / "demo.3mf"

    export_multi_material_3mf(material_meshes, output_path)

    assert output_path.exists()
    reloaded = trimesh.load(output_path)
    assert hasattr(reloaded, "geometry")
    assert set(reloaded.geometry.keys()) == {"Blanc", "Rose"}

    # les deux corps doivent rester dans le meme repere qu'a l'origine (le
    # 3MF conserve les transforms de scene -- pas de recadrage independant).
    original_white_bounds = material_meshes["Blanc"].bounds
    combined_scene_bounds = reloaded.bounds
    assert combined_scene_bounds[0] == pytest.approx(original_white_bounds[0], abs=0.5)


def test_export_stl_per_material_writes_explicit_named_files(tmp_path):
    material_meshes = {
        "Blanc": _box([40, 30, 3]),
        "Rose vif": _box([10, 10, 2]),
    }

    written = export_stl_per_material(material_meshes, tmp_path, base_name="portrait")

    names = {p.name for p in written}
    assert "portrait_BLANC.stl" in names
    assert "portrait_ROSE_VIF.stl" in names
    for p in written:
        assert p.exists()
        reloaded = trimesh.load(p, process=True)
        assert reloaded.is_watertight


def test_export_stl_per_material_bodies_share_coordinate_system(tmp_path):
    """Deux corps issus du meme decoupage doivent rester alignes une fois
    relus depuis le disque -- pas de decalage/recadrage independant."""
    material_meshes = {
        "Blanc": _box([40, 30, 3], offset=(20, 15, 1.5)),
        "Rose": _box([10, 10, 2], offset=(20, 15, 1.0)),
    }

    written = export_stl_per_material(material_meshes, tmp_path, base_name="portrait")
    reloaded = {p.stem.split("_")[-1]: trimesh.load(p, process=True) for p in written}

    assert reloaded["BLANC"].bounds[0] == pytest.approx(material_meshes["Blanc"].bounds[0], abs=0.5)
    assert reloaded["ROSE"].bounds[0] == pytest.approx(material_meshes["Rose"].bounds[0], abs=0.5)
