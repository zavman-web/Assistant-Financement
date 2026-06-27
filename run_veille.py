"""
Point d'entrée principal de VEILLE-FI.

CONFORME À CAHIER_DES_CHARGES.md (version révisée le 27/06/2026 — diffusion
publique via GitHub Pages, voir Section 4 et 5). Toute modification de la
logique ci-dessous doit d'abord être reportée dans ce cahier des charges.

Orchestre :
1. Vérification de l'âge du dernier rapport (Section 5) — décide si une
   collecte est nécessaire ou si on affiche simplement le rapport existant.
   Ne s'applique qu'au mode local (--force/manuel) ; en exécution via
   GitHub Actions, la collecte est toujours lancée (le calendrier pilote
   la fréquence, pas cette règle de fraîcheur).
2. La collecte via l'API Aides-territoires (client_aides_territoires.py)
3. Le scraping HTML des autres sources (scraper_html.py)
4. Le fetch de second niveau pour les échéances Région Réunion, uniquement
   sur les nouveautés détectées (region_reunion_detail.py)
5. L'intégration dans le cache de déduplication (cache_dedup.py)
6. La catégorisation thématique SANS exclusion (categorisation.py)
7. La production de DEUX formats de sortie (Section 4) :
   - un rapport Markdown local (test/diagnostic), inchangé depuis le 24/06
   - une page HTML interactive (generer_html.py), destinée à la publication
     sur GitHub Pages — tableau filtrable, même tri par urgence, mêmes tags

Usage :
    python3 run_veille.py                # comportement normal : vérifie
                                           # l'âge, collecte si nécessaire,
                                           # affiche le chemin du rapport
    python3 run_veille.py --force         # force une collecte même si le
                                           # dernier rapport a moins de 7 jours
    python3 run_veille.py --diagnostic    # mode diagnostic sur les sources HTML

RAPPEL DES EXCLUSIONS (Section 6 du cahier des charges, révisée le
27/06/2026) : pas de base de données, pas de serveur dynamique (Flask/
Django), pas d'authentification utilisateur sur la page publiée, pas de
notification email/SMS, pas de généralisation à d'autres communes. Une
interface web STATIQUE (générée puis publiée, jamais un serveur qui répond
en temps réel) est désormais autorisée — voir Section 6 révisée.
"""

from __future__ import annotations

import logging
import sys
from datetime import date, datetime
from pathlib import Path

from ademe_rss import collecter_appels_ademe
from cache_dedup import (
    charger_cache,
    integrer_aides_api,
    integrer_items_html,
    sauvegarder_cache,
)
from categorisation import construire_entree, trier_par_urgence
from client_aides_territoires import collecter_aides_reunion
from generer_html import ecrire_page_html
from region_reunion_detail import enrichir_items_avec_echeances
from scraper_html import charger_sources, diagnostiquer_source, scraper_source

logger = logging.getLogger("veille_fi.run")

REPERTOIRE_MODULE = Path(__file__).parent
CHEMIN_SOURCES_JSON = REPERTOIRE_MODULE / "sources.json"
CHEMIN_CACHE = REPERTOIRE_MODULE / "cache" / "veille_fi_cache.json"
DOSSIER_RAPPORTS = REPERTOIRE_MODULE / "rapports"

# Page HTML publique (Section 4 révisée le 27/06/2026, diffusion GitHub
# Pages). Le nom "index.html" et le dossier "docs/" sont ceux attendus par
# défaut par GitHub Pages quand la source de publication est configurée sur
# "docs/" — voir CAHIER_DES_CHARGES.md Section 5 pour la configuration.
DOSSIER_PUBLIC = REPERTOIRE_MODULE / "docs"
CHEMIN_PAGE_HTML = DOSSIER_PUBLIC / "index.html"

# Section 5 du cahier des charges : seuil d'âge déclenchant une collecte
# automatique à l'ouverture de l'outil (mode local uniquement).
SEUIL_AGE_RAPPORT_JOURS = 7

# Décision validée par Xavier le 27/06/2026 : un dispositif dont l'échéance
# est dépassée depuis plus de ce nombre de jours disparaît de la page HTML
# publique (mais reste dans le cache local, jamais supprimé des données —
# seulement filtré à l'affichage, conformément au principe de non-exclusion
# du cahier des charges qui porte sur les données, pas sur la présentation).
SEUIL_EXCLUSION_HTML_JOURS = 60

# Sources HTML pour lesquelles le fetch de second niveau (échéances) a été
# vérifié comme pertinent — cf. region_reunion_detail.py. Depuis le 24/06/2026,
# l'extraction directe depuis la page de liste (scraper_html.py) couvre déjà
# la plupart des cas pour departement_974, donc le fetch de second niveau ne
# sera déclenché que pour les éventuelles entrées sans échéance détectée.
SOURCES_AVEC_FETCH_SECOND_NIVEAU = {"region_reunion_aap", "region_reunion_feder", "departement_974", "prefecture_reunion"}


def _dernier_rapport_existant() -> Path | None:
    if not DOSSIER_RAPPORTS.exists():
        return None
    rapports = sorted(DOSSIER_RAPPORTS.glob("rapport_*.md"), reverse=True)
    return rapports[0] if rapports else None


def _age_en_jours(chemin_rapport: Path) -> int:
    # On se base sur la date dans le nom de fichier (rapport_AAAA-MM-JJ.md)
    # plutôt que sur le mtime du fichier, pour rester correct même si le
    # fichier a été copié/déplacé et a perdu son horodatage système.
    nom = chemin_rapport.stem  # "rapport_2026-06-24"
    date_str = nom.removeprefix("rapport_")
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        # Repli sur le mtime si le nom de fichier ne suit pas le format attendu.
        d = datetime.fromtimestamp(chemin_rapport.stat().st_mtime).date()
    return (date.today() - d).days


def _faut_il_collecter(force: bool) -> tuple[bool, str]:
    """
    Implémente la règle de la Section 5 : collecte si le dernier rapport
    n'existe pas ou a plus de SEUIL_AGE_RAPPORT_JOURS jours.
    Retourne (faut_il_collecter, raison_lisible).
    """
    if force:
        return True, "Collecte forcée via --force."

    dernier = _dernier_rapport_existant()
    if dernier is None:
        return True, "Aucun rapport existant — première collecte."

    age = _age_en_jours(dernier)
    if age > SEUIL_AGE_RAPPORT_JOURS:
        return True, f"Dernier rapport vieux de {age} jours (seuil : {SEUIL_AGE_RAPPORT_JOURS})."

    return False, f"Dernier rapport vieux de {age} jour(s) — pas de collecte nécessaire."


def executer_collecte() -> Path:
    """Exécute le pipeline complet de collecte et écrit un nouveau rapport.
    Retourne le chemin du rapport créé."""
    logger.info("=== Démarrage de la collecte VEILLE-FI ===")

    cache = charger_cache(CHEMIN_CACHE)
    logger.info("Cache chargé : %d entrées existantes.", len(cache))

    entrees_categorisees = []
    sections_techniques: list[str] = []

    # --- 1. Aides-territoires (API) ---
    logger.info("Collecte Aides-territoires (API)...")
    resultat_api = collecter_aides_reunion()
    rapport_api = integrer_aides_api(cache, resultat_api.aides)

    sections_techniques += [
        "## Aides-territoires (API)",
        "",
        f"- Aides pertinentes Réunion/commune retenues ce passage : {len(resultat_api.aides)}",
        f"- Filtrage serveur utilisé : {resultat_api.filtrage_serveur_utilise}",
        f"- Nouvelles aides détectées : {len(rapport_api.nouvelles_entrees)}",
        f"- Aides mises à jour depuis le dernier passage : {len(rapport_api.entrees_mises_a_jour)}",
        "",
    ]
    if resultat_api.erreurs:
        sections_techniques.append("**Erreurs rencontrées :**")
        for e in resultat_api.erreurs:
            sections_techniques.append(f"- {e}")
        sections_techniques.append("")

    for entree_cache in rapport_api.nouvelles_entrees:
        lien_complet = (
            f"https://aides-territoires.beta.gouv.fr{entree_cache.lien}"
            if entree_cache.lien else None
        )
        entrees_categorisees.append(construire_entree(
            titre=entree_cache.titre, lien=lien_complet, source_id="aides_territoires",
            echeance_iso=entree_cache.submission_deadline, statut_dedup="nouvelle",
        ))
    for entree_cache in rapport_api.entrees_mises_a_jour:
        lien_complet = (
            f"https://aides-territoires.beta.gouv.fr{entree_cache.lien}"
            if entree_cache.lien else None
        )
        entrees_categorisees.append(construire_entree(
            titre=entree_cache.titre, lien=lien_complet, source_id="aides_territoires",
            echeance_iso=entree_cache.submission_deadline, statut_dedup="mise_a_jour",
        ))

    # --- 1bis. ADEME (flux RSS) ---
    # Découvert le 24/06/2026 : un vrai flux RSS dédié existe pour cette
    # source (cf. ademe_rss.py), plus fiable qu'un scraping HTML classique.
    logger.info("Collecte ADEME (flux RSS)...")
    resultat_ademe = collecter_appels_ademe()

    sections_techniques += [
        "## ADEME (flux RSS)",
        "",
        f"- Entrées totales dans le flux : {resultat_ademe.nb_total_flux}",
        f"- Entrées pertinentes Réunion/national retenues : {len(resultat_ademe.appels)}",
        "",
    ]
    if resultat_ademe.erreurs:
        sections_techniques.append("**Erreurs rencontrées :**")
        for e in resultat_ademe.erreurs:
            sections_techniques.append(f"- {e}")
        sections_techniques.append("")

    class _ItemCompatADEME:
        """Adaptateur minimal pour réutiliser integrer_items_html, qui attend
        un objet avec .titre, .lien, et .date_limite (interface compatible
        avec ItemExtrait — voir cache_dedup.integrer_items_html, qui lit
        getattr(item, "date_limite", None))."""
        def __init__(self, titre, lien, date_limite):
            self.titre = titre
            self.lien = lien
            self.date_limite = date_limite

    items_ademe_compat = [
        _ItemCompatADEME(a.titre, a.lien, a.date_limite_iso) for a in resultat_ademe.appels
    ]
    rapport_ademe = integrer_items_html(cache, "ademe", items_ademe_compat)

    for entree_cache in rapport_ademe.nouvelles_entrees:
        entrees_categorisees.append(construire_entree(
            titre=entree_cache.titre, lien=entree_cache.lien, source_id="ademe",
            echeance_iso=entree_cache.submission_deadline,
            statut_dedup="nouvelle",
        ))

    # --- 2. Sources en scraping HTML ---
    sources_html = charger_sources(CHEMIN_SOURCES_JSON)
    sections_techniques += ["## Sources en scraping HTML", ""]
    toutes_nouveautes_html: list[tuple[str, list]] = []

    for source in sources_html:
        logger.info("Scraping %s...", source["id"])
        resultat = scraper_source(source)

        sections_techniques.append(f"### {source['nom']}")
        sections_techniques.append(f"- Statut : `{resultat.statut}`")

        if resultat.statut == "echec_reseau":
            sections_techniques.append(f"- ⚠️ Échec réseau : {resultat.detail_erreur}")
            sections_techniques.append("")
            continue
        if resultat.statut == "echec_parsing":
            sections_techniques.append(
                f"- ⚠️ Échec de PARSING (structure non reconnue) : {resultat.detail_erreur}. "
                f"La structure HTML de cette source a probablement changé."
            )
            sections_techniques.append("")
            continue
        if resultat.statut == "vide":
            sections_techniques.append(
                "- ⚠️ Page récupérée mais aucun item extrait — structure non reconnue. "
                "Lancer `python3 run_veille.py --diagnostic` sur cette source."
            )
            sections_techniques.append("")
            continue

        rapport_html = integrer_items_html(cache, source["id"], resultat.items)
        sections_techniques.append(f"- Items trouvés ce passage : {len(resultat.items)}")
        sections_techniques.append(f"- Nouveaux items : {len(rapport_html.nouvelles_entrees)}")
        sections_techniques.append("")

        if rapport_html.nouvelles_entrees:
            toutes_nouveautes_html.append((source["id"], rapport_html.nouvelles_entrees))

    # --- 3. Fetch de second niveau (échéances) ---
    # N'est appelé QUE pour les entrées dont l'échéance n'a pas déjà été
    # détectée directement dans la page de liste (cf. _extraire_items_generique
    # dans scraper_html.py, qui sait maintenant lire la date depuis le bloc
    # englobant pour des sources comme Département 974). Ça réduit le nombre
    # de requêtes réseau : un fetch de fiche détaillée par item coûte cher,
    # autant ne le faire que quand c'est vraiment nécessaire.
    echeances_par_lien: dict[str, str | None] = {}
    for source_id, nouvelles_entrees_cache in toutes_nouveautes_html:
        if source_id not in SOURCES_AVEC_FETCH_SECOND_NIVEAU:
            continue

        entrees_sans_echeance = [
            e for e in nouvelles_entrees_cache if not e.submission_deadline
        ]
        if not entrees_sans_echeance:
            logger.info(
                "Toutes les nouveautés de %s ont déjà une échéance détectée "
                "depuis la liste — pas de fetch de second niveau nécessaire.",
                source_id,
            )
            continue

        logger.info(
            "Fetch de second niveau pour les échéances de %s (%d nouveautés sans échéance connue)...",
            source_id, len(entrees_sans_echeance),
        )

        class _ItemCompat:
            def __init__(self, titre, lien):
                self.titre = titre
                self.lien = lien

        items_compat = [_ItemCompat(e.titre, e.lien) for e in entrees_sans_echeance]
        echeances = enrichir_items_avec_echeances(items_compat)
        for lien, echeance_fiche in echeances.items():
            echeances_par_lien[lien] = echeance_fiche.date_limite_iso

    # --- 4. Catégorisation des entrées HTML, dédupliquées par lien ---
    vus_par_lien: dict[str, bool] = {}
    for source_id, nouvelles_entrees_cache in toutes_nouveautes_html:
        for entree_cache in nouvelles_entrees_cache:
            cle_dedup = entree_cache.lien or entree_cache.titre
            if cle_dedup in vus_par_lien:
                continue  # deux entrées sources.json pointant sur la même URL (region_reunion_aap/feder)
            vus_par_lien[cle_dedup] = True
            # Priorité à l'échéance déjà détectée depuis la liste
            # (entree_cache.submission_deadline) ; sinon, on retombe sur le
            # résultat du fetch de second niveau s'il y en a eu un.
            echeance_finale = (
                entree_cache.submission_deadline
                or echeances_par_lien.get(entree_cache.lien)
            )
            entrees_categorisees.append(construire_entree(
                titre=entree_cache.titre, lien=entree_cache.lien, source_id=source_id,
                echeance_iso=echeance_finale, statut_dedup="nouvelle",
            ))

    # --- 5. Tri par urgence (neutre, pas de hiérarchie thématique) ---
    # RÉVISION DU 24/06/2026 : plus de regroupement par thématique en
    # sections fixes (cf. Section 3 et 4 du cahier des charges, révisées
    # suite au recentrage de l'outil sur les élus). Les tags restent
    # affichés en clair sur chaque ligne de la liste unique ci-dessous,
    # pour rester cherchables au Ctrl+F.
    entrees_triees = trier_par_urgence(entrees_categorisees)
    logger.info("Catégorisation effectuée sur %d entrées.", len(entrees_categorisees))

    # --- 6. Construction du rapport (Section 4 du cahier des charges) ---
    aujourdhui = date.today().isoformat()
    lignes: list[str] = [
        f"# Rapport VEILLE-FI — {aujourdhui}",
        "",
        f"Dernière mise à jour : aujourd'hui ({aujourdhui}). "
        f"Prochaine collecte automatique si ce rapport dépasse {SEUIL_AGE_RAPPORT_JOURS} jours.",
        "",
        f"**{len(entrees_triees)} aides/appels à projets nouveaux ou mis à jour** ce passage. "
        f"Document cherchable au Ctrl+F (thématique, nom de dispositif, source...).",
        "",
        "---",
        "",
        "## Nouveautés (triées par urgence d'échéance)",
        "",
    ]

    if not entrees_triees:
        lignes.append("_Aucune nouveauté ni mise à jour détectée ce passage._")
        lignes.append("")
    else:
        for i, e in enumerate(entrees_triees, start=1):
            marqueurs = []
            if e.jours_avant_echeance is not None:
                if e.jours_avant_echeance < 0:
                    marqueurs.append("échéance dépassée")
                elif e.jours_avant_echeance <= 15:
                    marqueurs.append(f"⚠️ échéance dans {e.jours_avant_echeance} j")
                else:
                    marqueurs.append(f"échéance dans {e.jours_avant_echeance} j")
            marqueurs.append("tags : " + ", ".join(e.thematiques))
            suffixe = f" _({' · '.join(marqueurs)})_"
            lignes.append(f"{i}. **{e.titre}**{suffixe}")
            if e.lien:
                lignes.append(f"   {e.lien}")
            lignes.append(f"   (source : `{e.source_id}`)")
            lignes.append("")

    lignes += ["---", "", "## Détail technique par source", ""]
    lignes.extend(sections_techniques)

    # --- Sauvegarde ---
    sauvegarder_cache(CHEMIN_CACHE, cache)
    logger.info("Cache mis à jour : %d entrées au total.", len(cache))

    DOSSIER_RAPPORTS.mkdir(parents=True, exist_ok=True)
    chemin_rapport = DOSSIER_RAPPORTS / f"rapport_{aujourdhui}.md"
    chemin_rapport.write_text("\n".join(lignes), encoding="utf-8")
    logger.info("Rapport écrit dans %s", chemin_rapport)

    # --- 7. Page HTML publique (Section 4 révisée le 27/06/2026) ---
    # Contrairement au Markdown ci-dessus (qui ne liste que les NOUVEAUTÉS
    # de ce passage), la page HTML est une vraie page de référence : elle
    # reconstruit l'intégralité du cache connu, pas seulement les nouveautés
    # de la semaine — décision validée par Xavier le 27/06/2026. Les
    # dispositifs dont l'échéance est dépassée depuis plus de
    # SEUIL_EXCLUSION_HTML_JOURS jours sont exclus (sinon la page grossirait
    # indéfiniment avec des AAP clos depuis des mois) ; ceux sans échéance
    # connue ou avec une échéance dépassée plus récemment restent visibles,
    # conformément au principe de non-exclusion du cahier des charges
    # (Section 1) — on filtre par ancienneté constatée, pas par pertinence.
    toutes_entrees_categorisees = [
        construire_entree(
            titre=ec.titre, lien=ec.lien, source_id=ec.source_id,
            echeance_iso=ec.submission_deadline,
        )
        for ec in cache.values()
    ]
    entrees_html = [
        e for e in toutes_entrees_categorisees
        if e.jours_avant_echeance is None or e.jours_avant_echeance >= -SEUIL_EXCLUSION_HTML_JOURS
    ]
    entrees_html_triees = trier_par_urgence(entrees_html)
    logger.info(
        "Page HTML : %d entrées du cache retenues (sur %d au total ; "
        "%d exclues car échéance dépassée depuis plus de %d jours).",
        len(entrees_html_triees), len(toutes_entrees_categorisees),
        len(toutes_entrees_categorisees) - len(entrees_html_triees),
        SEUIL_EXCLUSION_HTML_JOURS,
    )

    texte_sections_techniques = "\n".join(sections_techniques)
    chemin_html = ecrire_page_html(
        entrees_html_triees, texte_sections_techniques, CHEMIN_PAGE_HTML,
    )
    logger.info("Page HTML publique écrite dans %s", chemin_html)

    return chemin_rapport


def executer() -> None:
    """Point d'entrée pour un usage normal (sans --diagnostic) : implémente
    la règle de déclenchement de la Section 5 du cahier des charges."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    force = "--force" in sys.argv
    faut_collecter, raison = _faut_il_collecter(force)
    logger.info(raison)

    if faut_collecter:
        chemin_rapport = executer_collecte()
    else:
        chemin_rapport = _dernier_rapport_existant()

    # Conforme à la Section 4 : le terminal n'affiche QUE le chemin, il
    # n'ouvre aucune application.
    print(f"\n{chemin_rapport}")


def executer_diagnostic_html() -> None:
    sources_html = charger_sources(CHEMIN_SOURCES_JSON)
    for source in sources_html:
        diagnostiquer_source(source)


if __name__ == "__main__":
    if "--diagnostic" in sys.argv:
        executer_diagnostic_html()
    else:
        executer()
