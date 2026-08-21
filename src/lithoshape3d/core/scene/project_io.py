"""Sauvegarde/chargement d'un bundle de projet `.l3dproj` (dossier).

Format du bundle (dossier, pas d'archive pour cette phase) :

    MonPortrait.l3dproj/
        project.json
        source/<image copiee>
        masks/<zone_id>.png

Tous les chemins ecrits dans `project.json` sont relatifs a la racine du
bundle : jamais de chemin absolu machine. C'est ce qui rend le bundle
deplacable/copiable tel quel (voir `tests/core/scene/test_project_io.py`
pour le test de portabilite).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np

from lithoshape3d.core.scene.mask_io import save_zone_mask
from lithoshape3d.core.scene.models import Project
from lithoshape3d.core.scene.serialization import project_from_dict, project_to_dict

PROJECT_FILENAME = "project.json"


def _relative_to_bundle(path: Path, bundle_dir: Path) -> str | None:
    try:
        return path.resolve().relative_to(bundle_dir.resolve()).as_posix()
    except ValueError:
        return None


def _ensure_file_in_bundle(external_path: Path, bundle_dir: Path, subdir: str) -> str:
    target_dir = bundle_dir / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / external_path.name
    if not target.exists() or target.resolve() != external_path.resolve():
        shutil.copy2(external_path, target)
    return f"{subdir}/{external_path.name}"


def _ensure_source_image_in_bundle(external_image_path: Path, bundle_dir: Path) -> str:
    return _ensure_file_in_bundle(external_image_path, bundle_dir, "source")


def save_project_bundle(
    project: Project,
    bundle_dir: str | Path,
    *,
    dirty_masks: dict[str, np.ndarray] | None = None,
) -> None:
    """Ecrit/actualise le bundle. Modifie `project` en place (chemins
    normalises en relatif) pour que l'appelant reste synchronise."""
    bundle_dir = Path(bundle_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    if project.scene.source_image_path:
        candidate = Path(project.scene.source_image_path)
        if not candidate.is_absolute():
            candidate = bundle_dir / candidate
        relative = _relative_to_bundle(candidate, bundle_dir)
        if relative is None:
            relative = _ensure_source_image_in_bundle(candidate, bundle_dir)
        project.scene.source_image_path = relative

    if project.scene.shape.source_image_path:
        candidate = Path(project.scene.shape.source_image_path)
        if not candidate.is_absolute():
            candidate = bundle_dir / candidate
        relative = _relative_to_bundle(candidate, bundle_dir)
        if relative is None:
            relative = _ensure_file_in_bundle(candidate, bundle_dir, "shapes")
        project.scene.shape.source_image_path = relative

    if project.scene.shape.font_path:
        candidate = Path(project.scene.shape.font_path)
        if not candidate.is_absolute():
            candidate = bundle_dir / candidate
        relative = _relative_to_bundle(candidate, bundle_dir)
        if relative is None and candidate.is_file():
            relative = _ensure_file_in_bundle(candidate, bundle_dir, "shapes")
            project.scene.shape.font_path = relative

    if dirty_masks:
        for zone in project.scene.zones:
            if zone.id in dirty_masks:
                zone.mask_path = save_zone_mask(bundle_dir, zone.id, dirty_masks[zone.id])

    data = project_to_dict(project)
    (bundle_dir / PROJECT_FILENAME).write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_project_bundle(bundle_dir: str | Path) -> Project:
    bundle_dir = Path(bundle_dir)
    data = json.loads((bundle_dir / PROJECT_FILENAME).read_text(encoding="utf-8"))
    return project_from_dict(data)


def resolve_bundle_path(bundle_dir: str | Path, relative_path: str) -> Path:
    return Path(bundle_dir) / relative_path
