"""Decouverte des polices grasses/epaisses installees sur la machine, pour
le selecteur de police de LightBox Letters (voir lightbox_letters_dialog.py).

Contexte (retour utilisateur reel) : un caisson lumineux tire ses parois du
contour de la lettre -- une police fine ne laisse pas assez de matiere, d'ou
le garde-fou `letter_wall_thickness_ok` (lightbox_letters_export.py). Ce
module ne fait AUCUNE hypothese sur les polices presentes : il scanne
reellement le disque et ne propose que des fichiers .ttf/.otf simples
(fontTools/`letter_glyph_extractor.py` charge un chemin de fichier direct
via `TTFont`, donc les collections `.ttc` et les polices variables sans
fichier de poids statique dedie sont exclues -- rien ne garantit qu'un poids
"Black" y soit selectionnable par simple chemin de fichier)."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("lithoshape3d.ui.fonts")

_FONT_DIRS = (
    Path("/System/Library/Fonts"),
    Path("/System/Library/Fonts/Supplemental"),
    Path("/Library/Fonts"),
)

# Mots-cles (dans le nom de fichier OU le nom interne de la police) qui
# indiquent un poids grasse/epaisse adapte aux parois fines d'un caisson
# lumineux -- pas de liste de chemins codee en dur, seulement des indices
# pour filtrer un scan reel du disque.
_BOLD_KEYWORDS = ("black", "heavy", "extrabold", "bold", "impact", "blk", "hv", "extra bold")
# Exclus explicitement : "bold italic" reste lisible mais l'italique n'aide
# pas l'epaisseur de paroi et complique le rendu -- on garde les variantes
# droites en priorite, sans les rejeter si aucune version droite n'existe.


def _is_bold_candidate(stem_lower: str) -> bool:
    return any(keyword in stem_lower for keyword in _BOLD_KEYWORDS)


def discover_bold_fonts(max_fonts: int = 20) -> list[tuple[str, str]]:
    """Scanne reellement les dossiers de polices macOS et retourne les
    polices grasses/epaisses valides pour le pipeline existant (fichier
    .ttf/.otf simple, chargeable par `fontTools.ttLib.TTFont`, meme
    mecanisme que `letter_glyph_extractor.extract_word_glyphs`).

    Retourne une liste `(nom_affiche, chemin)` triee (les variantes "black"/
    "heavy"/"impact" en priorite, puis "bold"), dedupliquee par chemin."""
    try:
        from fontTools.ttLib import TTFont
    except ImportError:  # pragma: no cover - dependance deja requise ailleurs
        return []

    candidates: list[Path] = []
    seen_paths: set[Path] = set()
    for directory in _FONT_DIRS:
        if not directory.is_dir():
            continue
        for pattern in ("*.ttf", "*.otf"):
            for path in directory.glob(pattern):
                if path in seen_paths:
                    continue
                seen_paths.add(path)
                if _is_bold_candidate(path.stem.lower()):
                    candidates.append(path)

    def priority(path: Path) -> int:
        stem = path.stem.lower()
        if "italic" in stem or "oblique" in stem:
            return 2
        if any(k in stem for k in ("black", "heavy", "impact", "blk", "extrabold", "extra bold", "hv")):
            return 0
        return 1

    results: list[tuple[str, str]] = []
    for path in sorted(candidates, key=lambda p: (priority(p), p.stem.lower())):
        try:
            tt_font = TTFont(str(path))
            display_name = tt_font["name"].getDebugName(1) or path.stem
            subfamily = tt_font["name"].getDebugName(2) or ""
        except Exception as exc:  # pragma: no cover - defensif, police corrompue
            logger.debug("Police ignoree (illisible) : %s (%s)", path, exc)
            continue
        label = f"{display_name} {subfamily}".strip() if subfamily and subfamily.lower() != "regular" else display_name
        results.append((label, str(path)))
        if len(results) >= max_fonts:
            break

    return results
