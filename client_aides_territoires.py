"""
Client API pour Aides-territoires (https://aides-territoires.beta.gouv.fr).

Source de vérité technique : api_aides_territoires.json (même répertoire que ce module).

Comportement :
- Appelle l'API REST documentée (lecture seule, sans authentification).
- Tente un filtrage côté serveur sur le périmètre géographique et le public visé.
- Si le filtrage serveur ne réduit pas significativement le volume de résultats
  (signe probable que le paramètre n'est pas pris en compte), bascule en mode
  "récupération complète + filtrage côté client" et le signale dans les logs.
- Pagine automatiquement en suivant le champ `next` jusqu'à épuisement.

Ce module ne fait AUCUNE hypothèse silencieuse : tout comportement de repli est loggé.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import requests

logger = logging.getLogger("veille_fi.aides_territoires")

API_BASE_URL = "https://aides-territoires.beta.gouv.fr/api/aids/"
API_VERSION = "1.4"  # Mis à jour le 24/06/2026 suite à un 401 Unauthorized
# constaté en conditions réelles avec version="1.1" (qui fonctionnait le
# 22/06/2026, cf. ancien commentaire). Le guide officiel des utilisateurs
# (fabrique-numerique.gitbook.io/aides-territoires-guide-des-utilisateurs)
# documente désormais l'exemple avec version=1.4 et indique que c'est la
# version actuelle de l'API. Hypothèse retenue : la version 1.1 a été
# dépréciée/désactivée côté serveur entre le 22/06 et le 24/06/2026, ce qui
# expliquerait un 401 plutôt qu'une erreur de paramètre ignoré. À CONFIRMER
# EN CONDITIONS RÉELLES avec ce nouveau numéro de version — si le 401
# persiste, le problème est probablement ailleurs (clé/authentification
# réellement requise désormais, changement de politique d'accès suite au
# recentrage de mars 2026 sur les seules collectivités). Voir
# api_aides_territoires.json pour le contexte complet.
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
REQUEST_TIMEOUT_SECONDS = 20
DELAY_BETWEEN_PAGES_SECONDS = 0.5  # Courtoisie : éviter de marteler l'API.
MAX_PAGES_HARD_LIMIT = 200  # Garde-fou anti-boucle infinie si `next` est mal formé.

# Termes utilisés pour le filtrage côté client sur le champ `perimeter`.
# À enrichir si on identifie d'autres libellés utilisés par Aides-territoires
# pour La Réunion (ex. nom exact de la CIREST tel qu'il apparaît dans leurs données).
TERMES_PERIMETRE_REUNION = [
    "réunion",
    "reunion",
    "974",
    "cirest",
    "saint-benoît",
    "saint-benoit",
    "outre-mer",
    "outremer",
    "drom",
    "rup",  # région ultrapériphérique
]

# Publics visés pertinents pour une commune.
PUBLICS_CIBLES_PERTINENTS = [
    "communes",
    "epci",
    "établissement public",
    "etablissement public",
]


@dataclass
class ResultatCollecte:
    """Résultat d'une collecte API, avec métadonnées sur la méthode effectivement utilisée."""

    aides: list[dict[str, Any]] = field(default_factory=list)
    nb_pages_recuperees: int = 0
    nb_total_annonce_par_api: int | None = None
    filtrage_serveur_utilise: bool = False
    filtrage_client_applique: bool = False
    erreurs: list[str] = field(default_factory=list)


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    return s


def _perimetre_concerne_reunion(perimeter: str | None) -> bool:
    if not perimeter:
        return False
    p = perimeter.lower()
    return any(terme in p for terme in TERMES_PERIMETRE_REUNION)


def _public_cible_pertinent(targeted_audiences: list[str] | None) -> bool:
    if not targeted_audiences:
        return False
    audiences = [a.lower() for a in targeted_audiences]
    return any(
        any(terme in a for terme in PUBLICS_CIBLES_PERTINENTS) for a in audiences
    )


def _diagnostiquer_acces_api(session: requests.Session) -> str | None:
    """
    Teste l'accès de base à l'API avant toute autre opération, pour détecter
    spécifiquement le cas d'un accès devenu authentifié (HTTP 401 avec le
    message "JWT Token not found").

    CONTEXTE (confirmé le 24/06/2026 par test direct avec curl, avec et sans
    User-Agent personnalisé — le 401 est identique dans les deux cas) :
    Aides-territoires a basculé d'un accès API libre à un accès nécessitant
    un token JWT. Ce n'est PAS un problème de code (version d'API, headers,
    User-Agent) — c'est un changement de politique d'accès côté plateforme,
    probablement lié au recentrage de mars 2026 sur les seules collectivités
    et établissements publics (cf. annonce officielle sur le site).

    Retourne un message d'erreur explicite et actionnable si le problème est
    détecté, ou None si l'accès semble fonctionner normalement.
    """
    try:
        resp = session.get(API_BASE_URL, params={"version": API_VERSION}, timeout=REQUEST_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        return f"Échec réseau lors du diagnostic d'accès : {exc}"

    if resp.status_code == 401:
        corps = resp.text[:200] if resp.text else ""
        if "jwt" in corps.lower() or "token" in corps.lower():
            return (
                "L'API Aides-territoires exige désormais une authentification par "
                "token JWT (HTTP 401, message contenant 'JWT Token not found'). "
                "Ce n'est pas un bug du code — c'est un changement de politique "
                "d'accès côté plateforme. ACTION REQUISE (hors code) : créer un "
                "compte sur https://aides-territoires.beta.gouv.fr, faire une "
                "demande d'accès API en tant que réutilisateur de données, "
                "récupérer un token JWT, puis l'intégrer dans les en-têtes de "
                "ce module (Authorization: Bearer <token>). Voir "
                "CAHIER_DES_CHARGES.md pour le détail de la démarche."
            )
        return f"HTTP 401 reçu mais sans mention explicite de JWT/token (corps : {corps!r})."

    return None


def _tenter_filtre_serveur(session: requests.Session) -> tuple[dict | None, str | None]:
    """
    Teste un appel avec un paramètre de filtre de périmètre/public.

    Retourne (json_reponse, nom_du_parametre_qui_a_fonctionne) ou (None, None) si rien
    n'a fonctionné de façon probante.

    Heuristique de validation : on considère le filtre comme "actif" si le `count`
    retourné est strictement inférieur au count sans filtre. Ce n'est qu'une heuristique
    car un filtre légitime mais sans résultat (count=0) serait aussi inférieur ;
    on traite ce cas séparément en loggant un avertissement.
    """
    candidats = [
        {"targeted_audiences": "communes"},
        {"perimeter": "reunion"},
        {"perimeter": "974"},
        {"text": "reunion"},
    ]

    try:
        resp_sans_filtre = session.get(
            API_BASE_URL,
            params={"version": API_VERSION},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        resp_sans_filtre.raise_for_status()
        count_sans_filtre = resp_sans_filtre.json().get("count")
    except (requests.RequestException, ValueError) as exc:
        logger.error("Échec de l'appel de référence sans filtre : %s", exc)
        return None, None

    for params_filtre in candidats:
        params = {"version": API_VERSION, **params_filtre}
        try:
            resp = session.get(API_BASE_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as exc:
            logger.warning("Échec du test de filtre %s : %s", params_filtre, exc)
            continue

        count_filtre = data.get("count")
        if count_filtre is None:
            continue

        if 0 < count_filtre < count_sans_filtre:
            nom_param = list(params_filtre.keys())[0]
            logger.info(
                "Filtre serveur '%s' semble fonctionner : count %s -> %s",
                nom_param, count_sans_filtre, count_filtre,
            )
            return data, nom_param

        if count_filtre == 0:
            logger.warning(
                "Filtre %s retourne 0 résultat — soit le filtre fonctionne et "
                "aucune aide active ne correspond, soit le paramètre est ignoré "
                "et la combinaison est simplement absente. Traité comme NON CONCLUANT.",
                params_filtre,
            )

    return None, None


def _paginer_integralite(
    session: requests.Session,
    url_depart: str,
    params_initiaux: dict | None = None,
) -> tuple[list[dict], int, int | None, list[str]]:
    """Récupère toutes les pages en suivant `next`. Retourne (aides, nb_pages, count_annonce, erreurs)."""
    aides: list[dict] = []
    erreurs: list[str] = []
    url = url_depart
    params = params_initiaux
    nb_pages = 0
    count_annonce: int | None = None

    while url and nb_pages < MAX_PAGES_HARD_LIMIT:
        try:
            resp = session.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as exc:
            erreurs.append(f"Échec page {nb_pages + 1} ({url}) : {exc}")
            break

        if count_annonce is None:
            count_annonce = data.get("count")

        aides.extend(data.get("results", []))
        url = data.get("next")
        params = None  # `next` contient déjà tous les paramètres encodés dans l'URL.
        nb_pages += 1
        if url:
            time.sleep(DELAY_BETWEEN_PAGES_SECONDS)

    if nb_pages >= MAX_PAGES_HARD_LIMIT:
        erreurs.append(
            f"Garde-fou MAX_PAGES_HARD_LIMIT={MAX_PAGES_HARD_LIMIT} atteint — "
            "pagination interrompue par précaution, possible boucle ou volume inattendu."
        )

    return aides, nb_pages, count_annonce, erreurs


def collecter_aides_reunion() -> ResultatCollecte:
    """
    Point d'entrée principal du module.

    Stratégie :
    1. Teste un filtrage côté serveur (cf. _tenter_filtre_serveur).
    2. Si un filtre serveur probant est trouvé, pagine ce résultat filtré,
       PUIS applique quand même le filtrage côté client sur `perimeter`
       en filet de sécurité (le filtre serveur trouvé n'est peut-être que
       partiel, ex. filtré par public mais pas par géographie).
    3. Si aucun filtre serveur n'est concluant, récupère l'intégralité des
       aides actives et filtre entièrement côté client.
    """
    session = _session()
    resultat = ResultatCollecte()

    diagnostic = _diagnostiquer_acces_api(session)
    if diagnostic is not None:
        logger.error(diagnostic)
        resultat.erreurs.append(diagnostic)
        return resultat

    data_filtree, param_qui_fonctionne = _tenter_filtre_serveur(session)

    if data_filtree is not None:
        resultat.filtrage_serveur_utilise = True
        aides, nb_pages, count_annonce, erreurs = _paginer_integralite(
            session, data_filtree.get("next") or API_BASE_URL,
            params_initiaux=None if data_filtree.get("next") else {"version": API_VERSION},
        )
        aides = data_filtree.get("results", []) + aides
        nb_pages += 1
        resultat.erreurs.extend(erreurs)
    else:
        logger.info(
            "Aucun filtre serveur concluant — récupération intégrale puis "
            "filtrage côté client (cf. README_sources.md section 5)."
        )
        aides, nb_pages, count_annonce, erreurs = _paginer_integralite(
            session, API_BASE_URL, params_initiaux={"version": API_VERSION}
        )
        resultat.erreurs.extend(erreurs)

    resultat.nb_pages_recuperees = nb_pages
    resultat.nb_total_annonce_par_api = count_annonce

    # Filtrage côté client systématique, qu'il y ait eu filtrage serveur ou non
    # (filet de sécurité — voir docstring de collecter_aides_reunion).
    avant = len(aides)
    aides_filtrees = [
        a for a in aides
        if _perimetre_concerne_reunion(a.get("perimeter"))
        or _public_cible_pertinent(a.get("targeted_audiences"))
    ]
    resultat.filtrage_client_applique = True
    logger.info(
        "Filtrage client : %d aides avant -> %d aides retenues (pertinentes Réunion/commune).",
        avant, len(aides_filtrees),
    )

    resultat.aides = aides_filtrees
    return resultat


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        # Test du diagnostic 401 JWT, sur le cas réel confirmé le 24/06/2026
        # par test direct (curl, avec et sans User-Agent personnalisé).
        from unittest.mock import MagicMock, patch

        resp_mock = MagicMock()
        resp_mock.status_code = 401
        resp_mock.text = '{"detail":"JWT Token not found"}'

        def _session_get_mock_401(self, url, params=None, timeout=None):
            return resp_mock

        with patch("requests.Session.get", new=_session_get_mock_401):
            resultat_test = collecter_aides_reunion()

        assert len(resultat_test.erreurs) == 1, (
            "Le diagnostic doit produire exactement un message d'erreur."
        )
        assert "JWT" in resultat_test.erreurs[0], (
            "Le message d'erreur doit mentionner explicitement JWT."
        )
        assert "ACTION REQUISE" in resultat_test.erreurs[0], (
            "Le message doit indiquer une action concrète à mener (hors code)."
        )
        assert len(resultat_test.aides) == 0, (
            "Aucune aide ne doit être retournée quand l'accès API échoue."
        )
        print("OK : diagnostic du 401 JWT fonctionne correctement (cas réel reproduit).")
    else:
        res = collecter_aides_reunion()
        print(f"Pages récupérées : {res.nb_pages_recuperees}")
        print(f"Total annoncé par l'API (avant filtrage) : {res.nb_total_annonce_par_api}")
        print(f"Filtrage serveur utilisé : {res.filtrage_serveur_utilise}")
        print(f"Aides retenues après filtrage : {len(res.aides)}")
        if res.erreurs:
            print("Erreurs rencontrées :")
            for e in res.erreurs:
                print(f"  - {e}")
