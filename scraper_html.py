"""
Scraper HTML générique pour VEILLE-FI.

Lit sources.json et, pour chaque source de type "scraping_html", récupère la page
et tente d'en extraire une liste d'items (titre, lien, le cas échéant thème/date).

IMPORTANT — limite assumée de cette implémentation :
Les sélecteurs CSS précis (classes, balises exactes) n'ont PAS pu être vérifiés sur
le DOM réel depuis l'environnement où ce module a été écrit (accès réseau restreint
à une liste blanche de domaines ne couvrant pas regionreunion.com, departement974.fr,
la-reunion.gouv.fr). Ce module fournit donc :
  - une mécanique robuste de fetch + logging d'erreurs (réseau vs parsing),
  - une PREMIÈRE PASSE de sélecteurs construits sur des hypothèses raisonnables
    (liens dans des balises <a>, regroupement par blocs <article>/<li>/<div>),
  - un mode "diagnostic" qui imprime un échantillon du HTML brut pour permettre
    d'ajuster rapidement les sélecteurs réels au premier run en conditions réelles.

Quiconque reprend ce module (Claude Code, ou Xavier) doit lancer le mode diagnostic
sur chaque source avant de faire confiance aux résultats de la première passe.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from region_reunion_detail import extraire_echeance_depuis_texte

logger = logging.getLogger("veille_fi.scraper_html")

# User-Agent de navigateur standard (Chrome/Windows récent), plutôt qu'un
# identifiant explicite de bot. Changement effectué le 24/06/2026 suite à un
# blocage HTTP 403 constaté sur Région Réunion avec l'ancien User-Agent
# "VEILLE-FI/1.0 (...)". Limite assumée : certaines protections anti-bot se
# basent sur d'autres signaux (fréquence des requêtes, fingerprint TLS,
# nécessité d'exécuter du JavaScript) qu'un simple changement d'en-tête ne
# résout pas — si le 403 persiste après ce changement, il faudra creuser plus
# (espacer davantage les requêtes, vérifier robots.txt, ou accepter que cette
# source ne soit pas accessible par scraping simple).
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
REQUEST_TIMEOUT_SECONDS = 20
DELAY_ENTRE_SOURCES_SECONDS = 1.0


@dataclass
class ItemExtrait:
    titre: str
    lien: str | None
    source_id: str
    thematique: str | None = None
    date_limite: str | None = None


@dataclass
class ResultatSource:
    source_id: str
    statut: str  # "succes" | "echec_reseau" | "echec_parsing" | "vide"
    items: list[ItemExtrait] = field(default_factory=list)
    detail_erreur: str | None = None


def charger_sources(chemin_sources_json: Path) -> list[dict[str, Any]]:
    with open(chemin_sources_json, encoding="utf-8") as f:
        data = json.load(f)
    return [s for s in data["sources"] if s.get("type_acces") == "scraping_html"]


def _fetch(url: str) -> requests.Response | None:
    try:
        resp = requests.get(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        return resp
    except requests.RequestException as exc:
        logger.error("Échec réseau pour %s : %s", url, exc)
        return None


def _extraire_items_generique(html: str, url_base: str, source_id: str) -> list[ItemExtrait]:
    """
    Stratégie générique de première passe :
    cherche des blocs <article>, <li>, ou <div> contenant un lien <a> avec du texte,
    en excluant les liens de navigation manifestement génériques (trop courts,
    situés dans un bloc structurel de navigation, ou correspondant à des
    libellés de menu connus).

    Cette fonction est volontairement permissive : mieux vaut remonter trop de
    candidats (à filtrer ensuite par mot-clé thématique) que d'en manquer en étant
    trop strict sur une structure HTML qui n'a pas été vérifiée à l'avance.

    AJUSTEMENT DU 24/06/2026 (suite au diagnostic réel sur Département 974 et
    CEREMA, qui retournaient respectivement 87 et 157 candidats très bruités) :
    suppression préalable des blocs <nav>, <header>, <footer> avant extraction
    — la plupart du bruit de menu provient structurellement de ces zones, pas
    seulement de leur libellé textuel. Seuil de longueur minimale du texte
    relevé à 15 caractères (au lieu de 8) pour écarter davantage de libellés
    courts type "En savoir plus" / "Découvrir".
    """
    soup = BeautifulSoup(html, "html.parser")

    # Retrait préalable des zones structurelles de navigation, avant toute
    # extraction — réduit mécaniquement le bruit sans avoir à deviner les
    # libellés précis utilisés par chaque site.
    for balise_structurelle in soup.find_all(["nav", "header", "footer"]):
        balise_structurelle.decompose()

    LIBELLES_NAVIGATION_A_EXCLURE = {
        "accueil", "contact", "mentions légales", "plan du site",
        "connexion", "rechercher", "menu", "newsletter", "accessibilité",
        "en savoir plus", "découvrir", "lire la suite", "lire l'article",
        "voir toutes les actualités", "toutes les actualités",
        "s'abonner", "partager", "imprimer",
    }

    # Motifs d'action UI génériques (boutons, pagination, partage social),
    # plutôt qu'une liste figée de libellés exacts. Ajouté le 24/06/2026
    # suite à un rapport réel où "Afficher plus de contenus" (bouton de
    # pagination Département 974) était remonté comme un faux AAP, et où le
    # fetch de second niveau perdait du temps sur des liens "Partager sur
    # Facebook/X/LinkedIn". Le filtre s'applique au TEXTE du lien (insensible
    # à la casse) : mieux vaut un motif un peu large qui élimine ces actions
    # UI de façon générique que de devoir lister chaque variante par site.
    MOTIFS_ACTION_UI_A_EXCLURE = re.compile(
        r"afficher plus|voir plus|charger plus|partager sur|"
        r"je me désabonne|me désabonner|voir tous mes favoris|"
        r"ajouter aux favoris|redirection en cours|imprimer cette page|"
        # Ajouté le 24/06/2026 suite à un cas réel constaté (Préfecture) :
        # "X (anciennement Twitter)" comme libellé de lien social SANS le
        # préfixe "Partager sur" déjà couvert ci-dessus. Plutôt que de
        # chasser chaque variante de formulation, ce motif reconnaît le nom
        # du réseau social lui-même : un libellé de lien qui ne contient que
        # ça (souvent accompagné de sa mention "anciennement ...") n'est
        # jamais un titre d'AAP.
        r"^x \(anciennement twitter\)$|^twitter$|^facebook$|^linkedin$|^instagram$",
        re.IGNORECASE,
    )

    conteneurs = soup.find_all(["article", "li", "div"])
    vus: set[str] = set()
    candidats: list[ItemExtrait] = []

    for conteneur in conteneurs:
        liens_tags = conteneur.find_all("a", href=True)
        # CORRECTIF du 24/06/2026 : `find()` (singulier) ne retournait que le
        # PREMIER lien du conteneur. Sur les cartes d'actualité où le résumé
        # est listé avant le titre dans le DOM (cas réel possible, même si
        # l'ordre titre-puis-résumé est plus courant), le titre n'était alors
        # jamais capturé du tout — la dédup "garder le plus court" ne peut
        # choisir qu'entre des candidats effectivement collectés. `find_all()`
        # capture tous les liens du conteneur, laissant la dédup par URL
        # (plus bas) choisir le bon parmi tous les candidats réels.
        if not liens_tags:
            continue

        for lien_tag in liens_tags:
            texte = lien_tag.get_text(strip=True)
            if not texte or len(texte) < 15:
                continue
            if texte.lower() in LIBELLES_NAVIGATION_A_EXCLURE:
                continue
            if MOTIFS_ACTION_UI_A_EXCLURE.search(texte):
                continue
            href = lien_tag["href"]
            if href.strip().lower().startswith("javascript:"):
                # Cas réel rencontré : liens "javascript:;" qui faisaient échouer
                # le fetch de second niveau avec une erreur "No connection
                # adapters" — ce ne sont jamais de vrais liens de contenu.
                continue

            url_absolue = urljoin(url_base, href)

            cle_dedup = f"{texte}|{url_absolue}"
            if cle_dedup in vus:
                continue
            vus.add(cle_dedup)

            # Tentative d'extraction de l'échéance directement depuis le texte du
            # bloc englobant (pas seulement le lien) — utile pour les sources où
            # la date limite est déjà visible dans la page de liste, sans avoir
            # besoin d'un fetch de second niveau coûteux. Vérifié fonctionnel sur
            # Département 974 le 24/06/2026 (patrons "Date limite :", "Clôture
            # de l'appel :", "Au plus tard le"). Reste un best-effort : si rien
            # n'est trouvé ici, le fetch de second niveau (region_reunion_detail.py)
            # reste la solution de repli pour les sources qui le justifient.
            texte_bloc = conteneur.get_text(separator=" ", strip=True)
            echeance = extraire_echeance_depuis_texte(texte_bloc, url_absolue)
            date_limite = echeance.date_limite_iso if echeance.trouve else None

            candidats.append(ItemExtrait(
                titre=texte, lien=url_absolue, source_id=source_id, date_limite=date_limite,
            ))

    # Déduplication par URL SEULE (passe finale, après la collecte) — corrige
    # un cas réel constaté le 24/06/2026 sur Département 974 : certaines
    # cartes d'actualité posent un <a> distinct sur le titre ET sur les
    # premiers mots du résumé, les deux pointant vers la même URL. La dédup
    # par (texte, url) ci-dessus ne les fusionne pas puisque les textes
    # diffèrent. Ici, entre deux candidats de même URL, on garde celui dont
    # le texte est le PLUS COURT — un titre est presque toujours plus court
    # qu'un extrait de résumé, et ce choix ne dépend pas de l'ordre
    # d'apparition dans le HTML (plus robuste qu'un simple "garder le premier
    # rencontré", qui supposerait que le titre précède toujours le résumé
    # dans le document — non garanti sur tous les sites).
    meilleur_candidat_par_url: dict[str, ItemExtrait] = {}
    for candidat in candidats:
        existant = meilleur_candidat_par_url.get(candidat.lien)
        if existant is None or len(candidat.titre) < len(existant.titre):
            meilleur_candidat_par_url[candidat.lien] = candidat

    return list(meilleur_candidat_par_url.values())


def diagnostiquer_source(source: dict[str, Any], taille_echantillon: int = 3000) -> None:
    """
    Mode diagnostic : récupère la page et imprime un échantillon du HTML brut,
    ainsi que le nombre de candidats trouvés par l'extraction générique.
    À lancer manuellement avant de faire confiance à une source en production.
    """
    url = source["url_a_scraper"]
    print(f"\n=== DIAGNOSTIC : {source['nom']} ({url}) ===")
    resp = _fetch(url)
    if resp is None:
        print("ÉCHEC RÉSEAU — voir logs.")
        return

    print(f"Statut HTTP : {resp.status_code}")
    print(f"Taille de la réponse : {len(resp.text)} caractères")
    print(f"\n--- Échantillon HTML brut (premiers {taille_echantillon} caractères) ---")
    print(resp.text[:taille_echantillon])

    items = _extraire_items_generique(resp.text, url, source["id"])
    print(f"\n--- Extraction générique : {len(items)} candidats trouvés ---")
    for item in items[:10]:
        print(f"  - {item.titre[:80]!r} -> {item.lien}")
    if len(items) > 10:
        print(f"  ... et {len(items) - 10} autres.")

    print(
        "\n>>> Si ce nombre semble trop élevé (bruit de navigation) ou trop bas "
        "(structure non capturée), ajuster _extraire_items_generique ou écrire "
        "un extracteur dédié à cette source avant mise en production.\n"
    )


def scraper_source(source: dict[str, Any]) -> ResultatSource:
    url = source["url_a_scraper"]
    resp = _fetch(url)

    if resp is None:
        return ResultatSource(
            source_id=source["id"],
            statut="echec_reseau",
            detail_erreur=f"Impossible de récupérer {url}",
        )

    try:
        items = _extraire_items_generique(resp.text, url, source["id"])
    except Exception as exc:  # noqa: BLE001 — on veut capturer tout échec de parsing ici
        logger.error("Échec de parsing pour %s : %s", source["id"], exc)
        return ResultatSource(
            source_id=source["id"],
            statut="echec_parsing",
            detail_erreur=str(exc),
        )

    if not items:
        logger.warning(
            "Aucun item extrait pour %s — la page a été récupérée mais l'extraction "
            "générique n'a rien trouvé. Probable signe que la structure HTML réelle "
            "ne correspond pas aux hypothèses de _extraire_items_generique. "
            "Lancer diagnostiquer_source() pour investiguer.",
            source["id"],
        )
        return ResultatSource(source_id=source["id"], statut="vide")

    return ResultatSource(source_id=source["id"], statut="succes", items=items)


def scraper_toutes_les_sources_html(chemin_sources_json: Path) -> list[ResultatSource]:
    sources = charger_sources(chemin_sources_json)
    resultats = []
    for i, source in enumerate(sources):
        logger.info("Scraping de la source %s (%d/%d)...", source["id"], i + 1, len(sources))
        resultats.append(scraper_source(source))
        if i < len(sources) - 1:
            time.sleep(DELAY_ENTRE_SOURCES_SECONDS)
    return resultats


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    chemin = Path(__file__).parent / "sources.json"
    sources = charger_sources(chemin)

    if len(sys.argv) > 1 and sys.argv[1] == "--diagnostic":
        for source in sources:
            diagnostiquer_source(source)
    else:
        resultats = scraper_toutes_les_sources_html(chemin)
        for r in resultats:
            print(f"{r.source_id:25s} statut={r.statut:15s} items={len(r.items)}")
            if r.detail_erreur:
                print(f"  -> {r.detail_erreur}")
