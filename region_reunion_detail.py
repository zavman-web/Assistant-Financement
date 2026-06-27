"""
Fetch de second niveau — récupération des échéances de dépôt pour les
appels à projets / AMI de la Région Réunion.

CONTEXTE IMPORTANT (vérifié sur deux fiches réelles le 24/06/2026) :

Sur regionreunion.com, la liste des appels à projets (/aides-services/appels-a-projets/)
ne contient PAS la date limite de dépôt — il faut ouvrir chaque fiche détaillée.

Sur la fiche détaillée elle-même, deux cas ont été observés :
  1. Cas "structuré" (ex. AAP FEDER-NDICI) : le texte contient littéralement
     "Date d'ouverture : <date>" et "Date limite de remise des propositions : <date>"
     en clair, juste après le chapô de l'article.
  2. Cas "non structuré" (ex. Guétali 2025/2026) : aucune date limite n'apparaît
     dans le texte de la page — elle est uniquement dans un PDF téléchargeable
     ("Télécharger l'AAP ..."), ce qui est hors de portée d'un parsing HTML/texte.

Ce module traite donc l'extraction de date comme un best-effort, PAS comme une
garantie. Quand le patron structuré n'est pas trouvé, le résultat le signale
explicitement (deadline=None, trouve=False) plutôt que de risquer un faux
négatif silencieux interprété comme "pas d'échéance".
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

import requests

logger = logging.getLogger("veille_fi.region_reunion_detail")

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
REQUEST_TIMEOUT_SECONDS = 20
DELAY_ENTRE_FICHES_SECONDS = 1.0

# Patrons observés sur de vraies fiches (Région Réunion ET Département 974,
# vérifiés le 24/06/2026). Volontairement permissifs sur les variantes de
# ponctuation/casse/format, car les sites ne sont pas garantis homogènes.
#
# Trois formats de date réels rencontrés :
#   - "28 novembre 2025"        (jour numérique + mois en lettres)
#   - "1er juin 2026"           (jour ordinal "1er" + mois en lettres)
#   - "12/05/2026"              (format numérique JJ/MM/AAAA)
#
# Le groupe capturant la date est commun aux trois regex ci-dessous via
# _PATRON_DATE_FR (texte) ou _PATRON_DATE_NUM (numérique), combinés dans
# chaque patron de contexte.
_PATRON_DATE_FR = r"(?:1er|[0-9]{1,2})\s+\w+\s+[0-9]{4}"
_PATRON_DATE_NUM = r"[0-9]{1,2}/[0-9]{1,2}/[0-9]{4}"
_PATRON_DATE_TOUTE_FORME = rf"({_PATRON_DATE_FR}|{_PATRON_DATE_NUM})"

PATRON_DATE_OUVERTURE = re.compile(
    rf"date\s+d.ouverture\s*:?\s*{_PATRON_DATE_TOUTE_FORME}",
    re.IGNORECASE,
)
PATRON_DATE_LIMITE = re.compile(
    rf"date\s+limite\s+de\s+(?:remise|d[ée]p[oô]t)[^:]*:?\s*{_PATRON_DATE_TOUTE_FORME}",
    re.IGNORECASE,
)
# Repli si la fiche dit juste "Date limite : ..." sans qualificatif complet
# (cas réel : Département 974, "Date limite : 1er juin 2026 à 23h59").
PATRON_DATE_LIMITE_GENERIQUE = re.compile(
    rf"date\s+limite\s*:?\s*{_PATRON_DATE_TOUTE_FORME}",
    re.IGNORECASE,
)
# Cas réel Département 974 : "Clôture de l'appel à projets : 12/05/2026 à 15h00"
PATRON_CLOTURE = re.compile(
    rf"cl[ôo]ture\s+de\s+l.appel[^:]*:?\s*{_PATRON_DATE_TOUTE_FORME}",
    re.IGNORECASE,
)
# Cas réel Département 974 : "Au plus tard le 23 janvier 2026"
PATRON_AU_PLUS_TARD = re.compile(
    rf"au\s+plus\s+tard\s+(?:le\s+)?{_PATRON_DATE_TOUTE_FORME}",
    re.IGNORECASE,
)
# Cas réel ADEME (flux RSS collectivités), format réel confirmé le 27/06/2026
# par lecture directe (repr()) du résumé RSS : "du JJ/MM/AAAA - HH:MM au
# JJ/MM/AAAA - HH:MM". Ajouté initialement le 27/06/2026 après constat
# qu'aucune échéance n'était jamais extraite pour les ~194 entrées ADEME
# d'un rapport réel, rendant le tri par urgence inopérant sur la majorité du
# rapport — une première tentative basée sur un format supposé à tort
# ("Ouvert jusqu'au [date]", jamais vérifié sur le vrai flux) avait échoué
# silencieusement ; voir le commentaire ci-dessous pour le détail.
# CORRECTION DU 27/06/2026 : le format initialement supposé ("Ouvert
# jusqu'au [date]") était une hypothèse FAUSSE, jamais vérifiée sur le vrai
# contenu du flux RSS — construite par erreur à partir d'un souvenir de la
# page web, pas du flux lui-même. Le vrai format, confirmé par Claude Code
# en conditions
# réelles (repr() du résumé RSS), est :
#   "du JJ/MM/AAAA - HH:MM au JJ/MM/AAAA - HH:MM" (parfois suivi de
#   "- Heure de Paris" et potentiellement coupé par des retours à la ligne
#   ou espaces non-classiques entre les éléments).
# C'est la DEUXIÈME date (après "au") qui est l'échéance — la première est
# la date d'ouverture du dispositif, pas la limite de dépôt.
# [\s\S]*? (non-greedy) plutôt que \s+ : tolère tout caractère (retours à
# ligne inclus, espaces insécables &nbsp;/\xa0) entre les deux dates, sans
# capter un texte démesurément long entre elles.
PATRON_OUVERT_JUSQU_AU = re.compile(
    rf"du\s+{_PATRON_DATE_NUM}[\s\S]*?au\s+({_PATRON_DATE_NUM})",
    re.IGNORECASE,
)

# Ordre de priorité des patrons : du plus spécifique/fiable au plus générique.
# Un patron plus spécifique (ex. "date limite de remise") est préféré à un
# générique (ex. "au plus tard") quand les deux matchent, car il est moins
# susceptible de capter une date qui n'a rien à voir avec le dépôt du dossier.
_PATRONS_DATE_LIMITE_PAR_PRIORITE = [
    ("structuree", PATRON_DATE_LIMITE),
    ("cloture", PATRON_CLOTURE),
    ("ouvert_jusqu_au", PATRON_OUVERT_JUSQU_AU),
    ("generique", PATRON_DATE_LIMITE_GENERIQUE),
    ("au_plus_tard", PATRON_AU_PLUS_TARD),
]

MOIS_FR = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5,
    "juin": 6, "juillet": 7, "août": 8, "aout": 8, "septembre": 9,
    "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
}


@dataclass
class EcheanceFiche:
    url: str
    date_ouverture_brute: str | None
    date_limite_brute: str | None
    date_limite_iso: str | None  # YYYY-MM-DD si parsing réussi, sinon None
    trouve: bool
    methode: str  # "structuree" | "generique" | "absente"


def _parser_date_fr_vers_iso(date_brute: str) -> str | None:
    """
    Convertit une date textuelle vers le format ISO YYYY-MM-DD.
    Gère trois formats réels rencontrés (vérifiés le 24/06/2026) :
      - "28 novembre 2025"  -> jour numérique + mois en lettres
      - "1er juin 2026"     -> jour ordinal "1er" + mois en lettres
      - "12/05/2026"        -> format numérique JJ/MM/AAAA
    Retourne None si aucun de ces formats ne correspond, plutôt que de
    deviner — un échec de parsing explicite est préférable à une date fausse.
    """
    date_brute = date_brute.strip()

    # Format numérique JJ/MM/AAAA
    if "/" in date_brute:
        try:
            jour_str, mois_str, annee_str = date_brute.split("/")
            return f"{int(annee_str):04d}-{int(mois_str):02d}-{int(jour_str):02d}"
        except (ValueError, AttributeError):
            return None

    # Format textuel "28 novembre 2025" ou "1er juin 2026"
    try:
        jour_str, mois_str, annee_str = date_brute.split()
        jour_str = jour_str.lower().removesuffix("er")  # "1er" -> "1"
        jour = int(jour_str)
        mois = MOIS_FR.get(mois_str.lower())
        annee = int(annee_str)
        if mois is None:
            return None
        return f"{annee:04d}-{mois:02d}-{jour:02d}"
    except (ValueError, AttributeError):
        return None


def extraire_echeance_depuis_texte(texte: str, url: str) -> EcheanceFiche:
    """
    Essaie chaque patron de date limite dans l'ordre de priorité défini par
    _PATRONS_DATE_LIMITE_PAR_PRIORITE, et retourne le premier qui matche.
    """
    match_ouverture = PATRON_DATE_OUVERTURE.search(texte)

    match_limite = None
    methode = "absente"
    for nom_methode, patron in _PATRONS_DATE_LIMITE_PAR_PRIORITE:
        match_limite = patron.search(texte)
        if match_limite:
            methode = nom_methode
            break

    if not match_limite:
        return EcheanceFiche(
            url=url,
            date_ouverture_brute=match_ouverture.group(1) if match_ouverture else None,
            date_limite_brute=None,
            date_limite_iso=None,
            trouve=False,
            methode="absente",
        )

    date_limite_brute = match_limite.group(1)
    date_limite_iso = _parser_date_fr_vers_iso(date_limite_brute)

    return EcheanceFiche(
        url=url,
        date_ouverture_brute=match_ouverture.group(1) if match_ouverture else None,
        date_limite_brute=date_limite_brute,
        date_limite_iso=date_limite_iso,
        trouve=True,
        methode=methode,
    )


def recuperer_echeance_fiche(url: str) -> EcheanceFiche:
    """Fait le GET de la fiche et tente l'extraction. Ne lève jamais d'exception :
    retourne toujours un EcheanceFiche, avec trouve=False en cas d'échec réseau."""
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Échec réseau sur la fiche %s : %s", url, exc)
        return EcheanceFiche(
            url=url, date_ouverture_brute=None, date_limite_brute=None,
            date_limite_iso=None, trouve=False, methode="echec_reseau",
        )

    # On travaille sur le texte brut de la réponse (déjà nettoyé en amont par
    # l'outil de fetch dans le cas de web_fetch ; ici avec requests, il faudra
    # que l'appelant passe par BeautifulSoup .get_text() avant si nécessaire).
    return extraire_echeance_depuis_texte(resp.text, url)


def enrichir_items_avec_echeances(
    items: list,  # list[ItemExtrait] du module scraper_html
    limite_items: int = 30,
) -> dict[str, EcheanceFiche]:
    """
    Pour une liste d'items scrapés (titre+lien), va chercher l'échéance de
    chacun en suivant son lien — UNIQUEMENT pour les `limite_items` premiers,
    par courtoisie réseau (chaque item = 1 requête HTTP supplémentaire).

    Retourne un dict {lien: EcheanceFiche}.

    À utiliser avec discernement : c'est le poste le plus coûteux en requêtes
    du pipeline VEILLE-FI (un fetch par appel à projets, contre un seul fetch
    pour toute la page de liste). Recommandation : n'appeler ceci que sur les
    items NOUVEAUX détectés par cache_dedup, pas sur l'ensemble à chaque passage.
    """
    resultats: dict[str, EcheanceFiche] = {}
    items_a_traiter = [i for i in items if i.lien][:limite_items]

    for i, item in enumerate(items_a_traiter):
        logger.info(
            "Récupération échéance %d/%d : %s", i + 1, len(items_a_traiter), item.titre[:60]
        )
        resultats[item.lien] = recuperer_echeance_fiche(item.lien)
        if i < len(items_a_traiter) - 1:
            time.sleep(DELAY_ENTRE_FICHES_SECONDS)

    nb_trouvees = sum(1 for e in resultats.values() if e.trouve)
    logger.info(
        "Échéances trouvées : %d/%d (les autres ont leur deadline uniquement "
        "dans un PDF ou une mise en page non standard — limite connue, voir "
        "docstring du module).",
        nb_trouvees, len(resultats),
    )

    return resultats


if __name__ == "__main__":
    # Test de la logique d'extraction sur les deux cas réels observés,
    # reproduits ici en texte brut (pas de requête réseau dans ce bloc de test).
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    texte_cas_structure = """
    # Appel à projets FEDER-NDICI
    Date d'ouverture : 28 août 2025
    Date limite de remise des propositions : 28 novembre 2025 à 12h00 (heure locale)
    """
    resultat_1 = extraire_echeance_depuis_texte(texte_cas_structure, "https://example.org/aap-feder-ndici")
    print(f"Cas structuré : trouve={resultat_1.trouve}, deadline_iso={resultat_1.date_limite_iso}, "
          f"methode={resultat_1.methode}")
    assert resultat_1.trouve is True
    assert resultat_1.date_limite_iso == "2025-11-28"

    texte_cas_absent = """
    # Appel à projets - Guétali 2025 / 2026
    Télécharger l'AAP Arts Visuels
    Télécharger l'AAP Spectacle Vivant
    """
    resultat_2 = extraire_echeance_depuis_texte(texte_cas_absent, "https://example.org/guetali")
    print(f"Cas absent : trouve={resultat_2.trouve}, methode={resultat_2.methode}")
    assert resultat_2.trouve is False
    assert resultat_2.methode == "absente"

    # Cas réels Département 974 (vérifiés le 24/06/2026 sur
    # /avis-appels-projets-enquetes-publiques) : trois formats de date
    # différents qui doivent tous être reconnus.
    texte_cas_1er_du_mois = "Date limite : 1er juin 2026 à 23h59 (heure de Paris)."
    resultat_3 = extraire_echeance_depuis_texte(texte_cas_1er_du_mois, "https://example.org/culture-sante")
    print(f"Cas '1er juin 2026' : trouve={resultat_3.trouve}, deadline_iso={resultat_3.date_limite_iso}")
    assert resultat_3.trouve is True
    assert resultat_3.date_limite_iso == "2026-06-01"

    texte_cas_cloture_numerique = (
        "Ouverture de l'appel à projets : 05/01/2026* "
        "Clôture de l'appel à projets : 12/05/2026 à 15h00**"
    )
    resultat_4 = extraire_echeance_depuis_texte(texte_cas_cloture_numerique, "https://example.org/apiculture")
    print(f"Cas 'Clôture : 12/05/2026' : trouve={resultat_4.trouve}, deadline_iso={resultat_4.date_limite_iso}")
    assert resultat_4.trouve is True
    assert resultat_4.date_limite_iso == "2026-05-12"

    texte_cas_au_plus_tard = "Au plus tard le 23 janvier 2026 Toutes les modalités de candidature"
    resultat_5 = extraire_echeance_depuis_texte(texte_cas_au_plus_tard, "https://example.org/autonomie")
    print(f"Cas 'Au plus tard le 23 janvier 2026' : trouve={resultat_5.trouve}, deadline_iso={resultat_5.date_limite_iso}")
    assert resultat_5.trouve is True
    assert resultat_5.date_limite_iso == "2026-01-23"

    # Cas réel ADEME (flux RSS collectivités), ajouté le 27/06/2026 suite au
    # constat qu'aucune échéance n'était extraite pour ~194 entrées ADEME
    # d'un rapport réel, rendant le tri par urgence largement inopérant.
    # CORRECTION DU 27/06/2026 : le premier essai de patron supposait le
    # format "Ouvert jusqu'au [date texte]" — une hypothèse JAMAIS vérifiée
    # sur le vrai contenu du flux, qui s'est révélée fausse en conditions
    # réelles (confirmé par Claude Code via repr() du résumé RSS réel). Le
    # vrai format est "du JJ/MM/AAAA - HH:MM au JJ/MM/AAAA - HH:MM", où
    # c'est la DEUXIÈME date qui est l'échéance (la première est la date
    # d'ouverture). Les 3 cas ci-dessous reproduisent exactement les 3
    # résumés réels remontés en diagnostic.
    cas_reels_ademe = [
        ("du 30/06/2026 - 00:00 au 31/12/2026 - 00:00 - Heure de Paris", "2026-12-31"),
        ("du 22/06/2026 - 12:00 au 12/10/2026 - 12:00 - Heure de Paris", "2026-10-12"),
        ("du 08/06/2026 - 14:00 au 01/09/2026 - 12:00 - Heure de Paris", "2026-09-01"),
    ]
    for texte_cas, attendu_iso in cas_reels_ademe:
        resultat_n = extraire_echeance_depuis_texte(texte_cas, "https://example.org/ademe-reel")
        print(f"Cas réel ADEME {texte_cas!r} : trouve={resultat_n.trouve}, deadline_iso={resultat_n.date_limite_iso}")
        assert resultat_n.trouve is True
        assert resultat_n.date_limite_iso == attendu_iso, (
            f"Attendu {attendu_iso}, obtenu {resultat_n.date_limite_iso} pour {texte_cas!r}"
        )

    # Robustesse : doit aussi fonctionner avec un retour à ligne ou un
    # espace insécable (&nbsp;) entre les deux dates, cas plausibles dans un
    # flux RSS réel selon l'hypothèse initiale de Claude Code.
    texte_saut_ligne = "du 30/06/2026 - 00:00\nau 31/12/2026 - 00:00 - Heure de Paris"
    resultat_saut = extraire_echeance_depuis_texte(texte_saut_ligne, "https://example.org/test-saut-ligne")
    assert resultat_saut.trouve is True and resultat_saut.date_limite_iso == "2026-12-31", (
        "RÉGRESSION : le patron doit tolérer un retour à ligne entre les deux dates."
    )

    print("\nTests de logique passés (sur données reproduites, pas en conditions réseau réelles).")
