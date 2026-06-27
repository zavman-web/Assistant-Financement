"""
Client RSS pour ADEME — flux officiel des appels à projets collectivités.

CONTEXTE : découvert et vérifié le 24/06/2026. Contrairement aux autres
sources HTML de ce projet, ADEME expose un vrai flux RSS dédié, mis à jour
quotidiennement selon la documentation officielle :
    https://agirpourlatransition.ademe.fr/collectivites/rss/appels-a-projet

Un flux RSS est structurellement plus fiable qu'un scraping HTML (format XML
standardisé par la spécification RSS, pas de risque de changement de mise en
page CSS). C'est la seule source de ce projet, avec Aides-territoires (API),
à ne pas dépendre d'une extraction HTML fragile.

DÉPENDANCE : ce module nécessite la librairie `feedparser`
(pip install feedparser --break-system-packages). Si elle n'est pas
disponible dans l'environnement de production, installer avant utilisation.

LIMITE CONNUE (non encore vérifiée à ce stade) : le contenu exact des entrées
RSS (quels champs sont remplis — résumé, date, catégorie/région) n'a pas pu
être inspecté depuis cet environnement, le fetch ayant renvoyé du XML binaire
non interprété par l'outil de récupération disponible. La structure ci-dessous
est donc écrite de façon défensive : elle utilise les champs RSS standards
(title, link, summary, published) qui existent dans presque tous les flux
RSS/Atom, mais le mode diagnostic doit être lancé en conditions réelles avant
de faire confiance à l'extraction de la région/échéance depuis le résumé.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import requests

from region_reunion_detail import extraire_echeance_depuis_texte

logger = logging.getLogger("veille_fi.ademe_rss")

URL_FLUX_RSS_COLLECTIVITES = "https://agirpourlatransition.ademe.fr/collectivites/rss/appels-a-projet"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
REQUEST_TIMEOUT_SECONDS = 20

# Termes utilisés pour filtrer la pertinence géographique côté client, sur le
# même principe que client_aides_territoires.py — au cas où le flux RSS ne
# permettrait pas de filtrer par région nativement (à vérifier en conditions
# réelles : le site web, lui, accepte bien un paramètre ?localisation[La
# Réunion], mais rien ne garantit que ce même filtre s'applique à l'URL RSS).
TERMES_PERIMETRE_REUNION = [
    "réunion", "reunion", "974", "outre-mer", "outremer", "drom", "rup",
    "toutes les régions", "toutes les regions",  # items nationaux, pertinents partout
]


@dataclass
class AppelAProjetADEME:
    titre: str
    lien: str
    resume: str | None
    date_publication: str | None  # format brut RSS, non normalisé
    date_limite_iso: str | None = None  # échéance extraite du résumé, format YYYY-MM-DD
    source_id: str = "ademe"


@dataclass
class ResultatCollecteADEME:
    appels: list[AppelAProjetADEME] = field(default_factory=list)
    nb_total_flux: int = 0
    erreurs: list[str] = field(default_factory=list)


# Liste des autres régions/territoires métropolitains et DROM-COM qui, si
# mentionnés SEULS (sans Réunion ni mention nationale), signalent qu'un AAP
# est probablement à exclure. Cette liste sert à la détection d'exclusivité
# géographique (cf. _perimetre_concerne_reunion ci-dessous), pas à filtrer
# directement.
AUTRES_TERRITOIRES_EXCLUSIFS = [
    "auvergne-rhône-alpes", "bourgogne-franche-comté", "bretagne",
    "centre-val de loire", "corse", "grand est", "guadeloupe", "guyane",
    "hauts-de-france", "île-de-france", "ile-de-france", "martinique",
    "mayotte", "normandie", "nouvelle-aquitaine", "nouvelle-calédonie",
    "occitanie", "pays de la loire", "polynésie française",
    "provence-alpes-côte d'azur", "paca", "saint-barthélemy", "saint-martin",
    "saint-pierre-et-miquelon", "wallis et futuna",
]
# DÉCISION DE DESIGN (24/06/2026, suite vérification Claude Code) : un AAP
# explicitement réservé à un autre DROM nommé (ex. "Martinique", "Guadeloupe")
# est ICI VOLONTAIREMENT EXCLU, alors qu'un AAP mentionnant "Outre-mer" de
# façon générique est inclus (cf. TERMES_PERIMETRE_REUNION). Cette asymétrie
# est intentionnelle, pas un oubli : le cahier des charges (Section 1) précise
# que l'outil doit aider les services à identifier ce qui sert LEURS PROPRES
# dossiers, pas faire de la veille stratégique générale sur les politiques
# DROM. Un AAP fermé aux candidatures réunionnaises (ex. "Martinique
# uniquement") n'aide aucun service à monter un dossier réel — l'inclure
# ajouterait du bruit non actionnable dans un rapport déjà dense, à l'inverse
# du principe de praticité pour les lecteurs (Xavier, DGS, DGF). Si ce choix
# doit changer (ex. veille de tendance transposable entre DROM), il faut
# d'abord le documenter dans CAHIER_DES_CHARGES.md avant de modifier ce code.


def _perimetre_concerne_reunion(texte: str | None) -> bool:
    """
    Détermine si un AAP est pertinent pour La Réunion, à partir du texte
    disponible (titre + résumé RSS).

    LOGIQUE CORRIGÉE LE 24/06/2026 suite à une remarque de Claude Code en
    diagnostic réel : l'ancienne version excluait par défaut tout AAP sans
    mention explicite de "Réunion"/"Outre-mer"/"Toutes les Régions" — ce qui
    excluait à tort les AAP nationaux génériques dont le résumé RSS ne liste
    pas spécifiquement les régions (ex. programmes nationaux sans restriction
    géographique mentionnée dans le résumé court du flux).

    Nouvelle règle, plus sûre par défaut :
    1. Si le texte mentionne explicitement Réunion/974/Outre-mer/DROM/RUP ou
       "Toutes les Régions" → pertinent (inclus).
    2. Si le texte mentionne EXCLUSIVEMENT d'autres régions précises (ex.
       "Nouvelle-Aquitaine uniquement", ou une liste de régions qui exclut
       La Réunion) sans mentionner Réunion → non pertinent (exclu).
    3. Si le texte ne mentionne AUCUNE région du tout (cas par défaut,
       probablement un AAP national générique ou un résumé RSS tronqué) →
       pertinent par défaut (inclus), pour ne pas rater une opportunité
       éligible faute d'information suffisante. Mieux vaut un faux positif
       (un AAP non pertinent visible dans le rapport, facile à ignorer en
       lecture) qu'un faux négatif (un AAP éligible jamais montré à personne).
    """
    if not texte:
        return True  # Règle 3 : absence totale de texte -> inclusion par défaut

    texte_lower = texte.lower()

    if any(terme in texte_lower for terme in TERMES_PERIMETRE_REUNION):
        return True  # Règle 1

    autres_territoires_mentionnes = [
        t for t in AUTRES_TERRITOIRES_EXCLUSIFS if t in texte_lower
    ]
    if autres_territoires_mentionnes:
        return False  # Règle 2 : mention exclusive d'autres régions

    return True  # Règle 3 : aucune mention géographique -> inclusion par défaut


def collecter_appels_ademe() -> ResultatCollecteADEME:
    """
    Récupère et parse le flux RSS ADEME collectivités, filtre côté client
    sur la pertinence géographique (Réunion/Outre-mer/national), et retourne
    le résultat. Ne lève jamais d'exception : les erreurs sont collectées
    dans le champ `erreurs` du résultat.
    """
    resultat = ResultatCollecteADEME()

    try:
        import feedparser
    except ImportError:
        resultat.erreurs.append(
            "Librairie 'feedparser' non installée. Installer avec : "
            "pip install feedparser --break-system-packages"
        )
        return resultat

    try:
        resp = requests.get(
            URL_FLUX_RSS_COLLECTIVITES,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        resultat.erreurs.append(f"Échec réseau sur le flux RSS ADEME : {exc}")
        return resultat

    flux = feedparser.parse(resp.content)
    resultat.nb_total_flux = len(flux.entries)

    if flux.bozo:
        # `bozo` signale un flux mal formé — on continue malgré tout (feedparser
        # est tolérant), mais on logue pour visibilité, conformément au principe
        # de ce projet de ne jamais échouer silencieusement.
        logger.warning(
            "Le flux RSS ADEME semble mal formé (bozo=1) : %s. "
            "Les entrées extraites peuvent être incomplètes.",
            getattr(flux, "bozo_exception", "raison inconnue"),
        )

    for entree in flux.entries:
        titre = getattr(entree, "title", "(sans titre)")
        lien = getattr(entree, "link", "")
        resume = getattr(entree, "summary", None)
        date_pub = getattr(entree, "published", None)

        # Filtrage de pertinence géographique : on regarde le titre ET le
        # résumé, car on ne sait pas encore lequel des deux champs contient
        # la mention de région (à confirmer par diagnostic réel).
        texte_a_filtrer = f"{titre} {resume or ''}"
        if not _perimetre_concerne_reunion(texte_a_filtrer):
            continue

        # Extraction de l'échéance depuis le résumé RSS (patron "Ouvert
        # jusqu'au [date]", cf. region_reunion_detail.py). Ajouté le
        # 27/06/2026 : auparavant, AUCUNE échéance n'était jamais extraite
        # pour cette source, ce qui rendait le tri par urgence du rapport
        # final inopérant sur la totalité des entrées ADEME (la source la
        # plus volumineuse du pipeline, ~194 entrées sur un rapport réel).
        echeance = extraire_echeance_depuis_texte(resume or "", lien)
        date_limite_iso = echeance.date_limite_iso if echeance.trouve else None

        resultat.appels.append(AppelAProjetADEME(
            titre=titre, lien=lien, resume=resume, date_publication=date_pub,
            date_limite_iso=date_limite_iso,
        ))

    logger.info(
        "Flux RSS ADEME : %d entrées totales, %d retenues après filtrage Réunion/national.",
        resultat.nb_total_flux, len(resultat.appels),
    )

    return resultat


def diagnostiquer_flux_rss() -> None:
    """
    Mode diagnostic : affiche un échantillon brut des entrées du flux RSS,
    pour permettre de vérifier en conditions réelles quels champs sont
    effectivement remplis (résumé, région, date) avant de faire confiance
    au filtrage automatique.
    """
    try:
        import feedparser
    except ImportError:
        print("ERREUR : la librairie 'feedparser' n'est pas installée.")
        print("Installer avec : pip install feedparser --break-system-packages")
        return

    print(f"\n=== DIAGNOSTIC : flux RSS ADEME ({URL_FLUX_RSS_COLLECTIVITES}) ===")
    try:
        resp = requests.get(
            URL_FLUX_RSS_COLLECTIVITES,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"ÉCHEC RÉSEAU : {exc}")
        return

    flux = feedparser.parse(resp.content)
    print(f"Statut HTTP : {resp.status_code}")
    print(f"Nombre d'entrées dans le flux : {len(flux.entries)}")
    print(f"Flux bien formé : {not flux.bozo}")

    print("\n--- Échantillon des 5 premières entrées (tous champs disponibles) ---")
    for i, entree in enumerate(flux.entries[:5], start=1):
        print(f"\n[{i}] {getattr(entree, 'title', '(sans titre)')}")
        print(f"    lien      : {getattr(entree, 'link', 'absent')}")
        print(f"    résumé    : {getattr(entree, 'summary', 'absent')[:200] if getattr(entree, 'summary', None) else 'absent'}")
        print(f"    publié    : {getattr(entree, 'published', 'absent')}")
        print(f"    tags      : {getattr(entree, 'tags', 'absent')}")

    print(
        "\n>>> Vérifier ci-dessus si la région (Réunion) apparaît dans le titre, "
        "le résumé, ou les tags — ajuster _perimetre_concerne_reunion() dans "
        "ademe_rss.py si le filtrage ne fonctionne pas comme attendu.\n"
    )


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if len(sys.argv) > 1 and sys.argv[1] == "--diagnostic":
        diagnostiquer_flux_rss()
    elif len(sys.argv) > 1 and sys.argv[1] == "--test":
        # Test de la logique de filtrage sur un flux RSS simulé, sans réseau.
        from unittest.mock import MagicMock, patch

        flux_simule = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item>
  <title>Systèmes performants de production de froid en Outre-mer et Corse</title>
  <link>https://example.org/aap-froid</link>
  <description>du 01/06/2026 - 00:00 au 15/10/2026 - 00:00 - Heure de Paris - 11 régions dont La Réunion</description>
  <pubDate>Mon, 01 Jun 2026 10:00:00 GMT</pubDate>
</item>
<item>
  <title>Appel à projets régional Nouvelle-Aquitaine sur la rénovation thermique</title>
  <link>https://example.org/aap-na</link>
  <description>du 01/06/2026 - 00:00 au 30/09/2026 - 00:00 - Heure de Paris - Nouvelle-Aquitaine uniquement</description>
  <pubDate>Tue, 02 Jun 2026 10:00:00 GMT</pubDate>
</item>
<item>
  <title>Mobilogs - Co-construction de connaissances pour des mobilités soutenables</title>
  <link>https://example.org/aap-mobilogs</link>
  <description>du 01/06/2026 - 00:00 au 22/06/2026 - 00:00 - Heure de Paris - Toutes les Régions</description>
  <pubDate>Wed, 03 Jun 2026 10:00:00 GMT</pubDate>
</item>
<item>
  <title>Aide nationale à la rénovation énergétique des bâtiments publics</title>
  <link>https://example.org/aap-national-sans-region</link>
  <description>du 01/06/2026 - 00:00 au 30/11/2026 - 00:00 - Heure de Paris - dispositif national</description>
  <pubDate>Thu, 04 Jun 2026 10:00:00 GMT</pubDate>
</item>
</channel></rss>"""

        resp_mock = MagicMock()
        resp_mock.raise_for_status = MagicMock()
        resp_mock.content = flux_simule.encode("utf-8")

        with patch("requests.get", return_value=resp_mock):
            resultat = collecter_appels_ademe()

        assert resultat.nb_total_flux == 4
        assert len(resultat.appels) == 3, (
            f"Attendu 3 entrées pertinentes (Réunion + Toutes les Régions + "
            f"national sans mention de région), obtenu {len(resultat.appels)}"
        )
        titres_retenus = {a.titre for a in resultat.appels}
        assert "Systèmes performants de production de froid en Outre-mer et Corse" in titres_retenus
        assert "Mobilogs - Co-construction de connaissances pour des mobilités soutenables" in titres_retenus
        assert "Aide nationale à la rénovation énergétique des bâtiments publics" in titres_retenus, (
            "RÉGRESSION : un AAP national sans mention de région explicite doit "
            "être inclus par défaut (correction du 24/06/2026 suite remarque "
            "Claude Code), pas exclu."
        )
        assert "Appel à projets régional Nouvelle-Aquitaine sur la rénovation thermique" not in titres_retenus

        print("OK : filtrage géographique RSS fonctionne correctement sur flux simulé.")

        # Test ajouté le 27/06/2026, corrigé le même jour pour utiliser le
        # VRAI format du résumé RSS ("du JJ/MM/AAAA - HH:MM au JJ/MM/AAAA -
        # HH:MM"), confirmé en conditions réelles après qu'une première
        # version basée sur un format supposé à tort ("Ouvert jusqu'au
        # [date]") se soit révélée inopérante en production malgré des
        # tests qui passaient (le flux RSS simulé reproduisait la même
        # hypothèse fausse que le code testé — d'où l'importance d'avoir
        # confirmé le vrai format via repr() du résumé réel avant de corriger).
        appels_par_titre = {a.titre: a for a in resultat.appels}
        assert appels_par_titre["Systèmes performants de production de froid en Outre-mer et Corse"].date_limite_iso == "2026-10-15", (
            "RÉGRESSION : l'échéance du format réel 'du ... au 15/10/2026 ...' doit être extraite."
        )
        assert appels_par_titre["Mobilogs - Co-construction de connaissances pour des mobilités soutenables"].date_limite_iso == "2026-06-22"
        assert appels_par_titre["Aide nationale à la rénovation énergétique des bâtiments publics"].date_limite_iso == "2026-11-30"
        print("OK : extraction d'échéance depuis le résumé RSS fonctionne (3/3 entrées avec date).")

        # Test de la décision de design du 24/06/2026 (cf. commentaire au-dessus
        # de AUTRES_TERRITOIRES_EXCLUSIFS) : un AAP réservé à un autre DROM
        # nommé explicitement (Martinique, Guadeloupe, Mayotte...) doit être
        # exclu, par asymétrie volontaire avec les mentions génériques
        # "Outre-mer". Cas réel rencontré en diagnostic : AAP "Alimentation
        # Durable" réservé à la Martinique.
        texte_martinique = (
            "améliorer l'offre durable alimentaire en Martinique et à "
            "rapprocher les Martiniquais de leur alimentation"
        )
        assert _perimetre_concerne_reunion(texte_martinique) is False, (
            "RÉGRESSION : un AAP explicitement réservé à un autre DROM nommé "
            "(ex. Martinique) doit être exclu — décision de design du "
            "24/06/2026, voir commentaire sur AUTRES_TERRITOIRES_EXCLUSIFS."
        )
        print("OK : asymétrie Outre-mer générique vs DROM nommé individuellement respectée.")
        print(f"  Total flux : {resultat.nb_total_flux}, retenus : {len(resultat.appels)}")
    else:
        resultat = collecter_appels_ademe()
        print(f"Entrées totales dans le flux : {resultat.nb_total_flux}")
        print(f"Entrées retenues (Réunion/national) : {len(resultat.appels)}")
        for appel in resultat.appels[:10]:
            print(f"  - {appel.titre[:70]!r}")
        if resultat.erreurs:
            print("Erreurs :")
            for e in resultat.erreurs:
                print(f"  - {e}")
