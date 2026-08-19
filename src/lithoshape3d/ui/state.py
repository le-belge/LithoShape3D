"""Etats de l'application, geres explicitement par MainWindow.

    NO_IMAGE      -> aucune image chargee
    IMAGE_LOADED  -> image chargee, jamais encore generee (ou reinitialisee)
    PARAMS_DIRTY  -> un mesh existe mais ne correspond plus aux parametres
                     courants (perime) ; l'export doit rester impossible
    GENERATING    -> generation en cours dans le worker
    MESH_READY    -> le mesh affiche correspond exactement aux parametres
                     courants ; export autorise
    ERROR         -> derniere generation en echec
"""

from __future__ import annotations

from enum import Enum, auto


class AppState(Enum):
    NO_IMAGE = auto()
    IMAGE_LOADED = auto()
    PARAMS_DIRTY = auto()
    GENERATING = auto()
    MESH_READY = auto()
    ERROR = auto()
