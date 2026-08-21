"""Cadrage (Image Transform) : positionne une image source (deja en niveaux
de gris, resolution arbitraire) dans la grille canonique de la Scene.

Concept independant de la vue (zoom/pan d'affichage, jamais persiste) et de
la geometrie 3D (Transform de Zone) -- voir docstring de
`core.scene.models.ImageTransform`.

Convention "identite" (offset=0, scale=1.0, rotation=0) = "Ajuster" (Fit) :
mise a l'echelle ISOTROPE (meme facteur en X et en Y, jamais de distorsion)
qui rend l'image entiere visible, centree, quitte a laisser des bandes
vides (`fill_value`) si le ratio d'aspect de la Shape differe de celui de
la photo. `transform.scale` est un multiplicateur applique UNIFORMEMENT
par-dessus cette base isotrope -- jamais un facteur par-axe independant :
c'est ce qui permet aux boutons "Remplir"/"Ajuster" de rester sans
distorsion quel que soit le ratio d'aspect (une base anisotrope,
etirant independamment X et Y, ne peut PAS etre corrigee vers un rendu
isotrope par un simple multiplicateur scalaire).

Retro-compatibilite (migration v4->v5, cf.
`core.scene.serialization._migrate_v4_to_v5`) : un projet v4 migre
reproduit son comportement historique (image etiree pour remplir
exactement la grille, SANS passer par cette fonction) via le chemin de
repli `image_transform=None` de `core.geometry.composition` -- pas via un
cas particulier de cette fonction, qui reste reservee au nouveau cadrage
isotrope."""

from __future__ import annotations

import cv2
import numpy as np

from lithoshape3d.core.scene.models import ImageTransform


def fill_scale_relative_to_fit(src_w: int, src_h: int, width_px: int, height_px: int) -> float:
    """Multiplicateur de `ImageTransform.scale` (relatif a la base isotrope
    "Ajuster") qui produit le comportement "Remplir" (Fill/cover) : l'image
    couvre entierement la grille, sans distorsion, quitte a rogner le
    surplus. Utilise par le bouton "Remplir" du cadrage (ui/)."""
    if src_w <= 0 or src_h <= 0 or width_px <= 0 or height_px <= 0:
        return 1.0
    fit_scale = min(width_px / src_w, height_px / src_h)
    fill_scale = max(width_px / src_w, height_px / src_h)
    return fill_scale / fit_scale if fit_scale > 0 else 1.0


def apply_image_transform(
    source_array: np.ndarray,
    transform: ImageTransform,
    width_px: int,
    height_px: int,
    fill_value: float = 1.0,
) -> np.ndarray:
    """Retourne un tableau (height_px, width_px) : `source_array` place selon
    `transform` dans la grille canonique. Les zones hors de l'empreinte de
    l'image transformee recoivent `fill_value` (1.0 = blanc/fin par defaut :
    evite de creer une epaisseur inattendue dans les zones vides d'une
    Shape non rectangulaire cadree en mode "Ajuster")."""
    src_h, src_w = source_array.shape[:2]
    if src_w == 0 or src_h == 0 or width_px <= 0 or height_px <= 0:
        return np.full((height_px, width_px), fill_value, dtype=np.float32)

    base_scale = min(width_px / src_w, height_px / src_h)  # isotrope : "Ajuster"
    scale_x = base_scale * transform.scale
    scale_y = base_scale * transform.scale

    theta = np.radians(transform.rotation_deg)
    cos_t, sin_t = float(np.cos(theta)), float(np.sin(theta))

    a, b = cos_t * scale_x, -sin_t * scale_y
    c, d = sin_t * scale_x, cos_t * scale_y

    dst_center_x = width_px / 2.0 + transform.offset_x * width_px
    dst_center_y = height_px / 2.0 + transform.offset_y * height_px
    src_cx, src_cy = src_w / 2.0, src_h / 2.0
    # Convention "centre de pixel" (celle de cv2.resize/warpAffine par
    # defaut, INTER_LINEAR) : l'echantillon du pixel d'indice i est pris a
    # la position continue i+0.5, pas i -- sans cette correction, le cas
    # identite (offset=0/scale=1/rotation=0) ne reproduit PAS exactement
    # `resize_array` (ecart mesure jusqu'a 0.55 sur des pixels de bord),
    # ce qui casserait la garantie "un projet migre ne change pas
    # visuellement" (migration v4->v5).
    tx = dst_center_x - (a * src_cx + b * src_cy) + (a + b) * 0.5 - 0.5
    ty = dst_center_y - (c * src_cx + d * src_cy) + (c + d) * 0.5 - 0.5

    matrix = np.array([[a, b, tx], [c, d, ty]], dtype=np.float32)

    # BORDER_REPLICATE (pas BORDER_CONSTANT) pour l'echantillonnage lui-meme :
    # un depassement de quelques millipixels au bord (arrondi flottant, cas
    # identite) doit se clamper comme le ferait cv2.resize, pas se meler a
    # fill_value -- sinon le cas identite ne reproduit plus exactement
    # `resize_array` (necessaire pour la migration v4->v5, cf. tests). Les
    # zones VRAIMENT hors de l'empreinte source (crop/zoom) sont determinees
    # a part, analytiquement (matrice inverse), pas via un second warp.
    warped = cv2.warpAffine(
        source_array.astype(np.float32),
        matrix,
        (width_px, height_px),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )

    inverse = cv2.invertAffineTransform(matrix)
    dst_y, dst_x = np.mgrid[0:height_px, 0:width_px].astype(np.float32)
    src_x = inverse[0, 0] * dst_x + inverse[0, 1] * dst_y + inverse[0, 2]
    src_y = inverse[1, 0] * dst_x + inverse[1, 1] * dst_y + inverse[1, 2]
    eps = 1e-3
    inside = (
        (src_x >= -0.5 - eps)
        & (src_x <= src_w - 0.5 + eps)
        & (src_y >= -0.5 - eps)
        & (src_y <= src_h - 0.5 + eps)
    )

    result = np.where(inside, warped, np.float32(fill_value))
    return result.astype(np.float32)
