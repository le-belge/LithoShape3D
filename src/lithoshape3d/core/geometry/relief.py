"""Contribution de hauteur (mm) d'une Zone, selon son ReliefMode.

Une seule fonction par formule, reutilisee partout (moteur mono-zone
historique ET composition multi-zone Phase 2C) : source de verite unique.

Important : cette fonction calcule uniquement LA CONTRIBUTION propre a la
zone. Comment cette contribution s'integre au resultat deja compose
(remplacement, cumul...) est decide par CompositionMode, jamais ici -- les
deux concepts restent strictement separes.

Formules :

    LITHOPHANE
        Identique a core/geometry/thickness.compute_thickness_mm (formule
        Phase 1A, inchangee) : la luminosite du pixel determine l'epaisseur
        entre min_thickness_mm et max_thickness_mm.

    SOLID
        Valeur constante = max_thickness_mm partout ou le masque est actif.
        L'image n'intervient pas (texte, elements graves a hauteur fixe).

    RELIEF
        Meme formule mathematique que LITHOPHANE (meme mappage
        luminosite -> fraction). La distinction n'est pas dans le calcul
        mais dans l'INTENTION : min_thickness_mm/max_thickness_mm sont
        censes definir une AMPLITUDE de relief modeste (ex. 0.1-0.3mm) a
        additionner (CompositionMode.ADD) plutot qu'une epaisseur
        lithophanique absolue. Reutilise compute_thickness_mm tel quel.
"""

from __future__ import annotations

import numpy as np

from lithoshape3d.core.geometry.thickness import compute_thickness_mm
from lithoshape3d.core.scene.models import GeometryParameters, ReliefMode


def compute_zone_contribution_mm(
    values: np.ndarray, params: GeometryParameters, relief_mode: ReliefMode
) -> np.ndarray:
    if relief_mode in (ReliefMode.LITHOPHANE, ReliefMode.RELIEF):
        return compute_thickness_mm(values, params)

    if relief_mode == ReliefMode.SOLID:
        return np.full(values.shape, params.max_thickness_mm, dtype=np.float32)

    raise NotImplementedError(f"ReliefMode {relief_mode} non supporte")
