"""
Cache de déduplication pour VEILLE-FI.

Objectif : entre deux passages du scraper, ne signaler comme "nouveau" ou
"mis à jour" que ce qui a réellement changé, pour ne pas noyer Xavier sous
des dizaines de lignes déjà vues la semaine précédente.

Stockage : un simple fichier JSON local (pas de base de données, pas de
dépendance externe). Suffisant pour un volume de quelques centaines à
quelques milliers d'entrées.

Clé de déduplication :
- Pour les aides API (Aides-territoires) : l'id numérique de l'aide.
- Pour les items scrapés en HTML (pas d'id stable garanti) : un hash du
  couple (titre, lien), qui est la meilleure approximation disponible
  sans connaître la structure réelle de chaque source.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class EntreeCache:
    cle: str
    source_id: str
    titre: str
    lien: str | None
    date_premiere_vue: str
    date_derniere_vue: str
    date_updated_origine: str | None = None  # `date_updated` côté API si disponible
    submission_deadline: str | None = None


@dataclass
class RapportDiff:
    nouvelles_entrees: list[EntreeCache] = field(default_factory=list)
    entrees_mises_a_jour: list[EntreeCache] = field(default_factory=list)
    entrees_inchangees_count: int = 0


def _hash_titre_lien(titre: str, lien: str | None) -> str:
    base = f"{titre}|{lien or ''}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]


def cle_pour_aide_api(aide: dict[str, Any]) -> str:
    return f"api:{aide['id']}"


def cle_pour_item_html(source_id: str, titre: str, lien: str | None) -> str:
    """
    Clé de déduplication = hash(titre, lien) — voir _hash_titre_lien.

    POINT DE VIGILANCE DOCUMENTÉ (24/06/2026, vérifié par test réel suite à
    une question de Claude Code) : le flux RSS ADEME republie chaque année
    certains AAP récurrents avec un TITRE STRICTEMENT IDENTIQUE entre éditions
    (ex. un AAP "... en Pays de la Loire" publié en 2024 puis republié en 2025
    avec le même titre, seul le lien change via un suffixe numérique -0/-1).
    Le couple (titre, lien) discrimine correctement ces éditions distinctes
    tant que leurs liens diffèrent — vérifié par test : deux passages
    successifs simulant l'édition 2024 puis 2025 produisent bien 2 entrées
    cache distinctes, pas une fusion. Si une future source republie un AAP
    avec un titre ET un lien identiques d'une année sur l'autre (cas non
    rencontré à ce jour), la dédup le traiterait à tort comme "déjà vu" —
    à surveiller si ce cas apparaît un jour.
    """
    return f"html:{source_id}:{_hash_titre_lien(titre, lien)}"


def charger_cache(chemin_cache: Path) -> dict[str, EntreeCache]:
    if not chemin_cache.exists():
        return {}
    with open(chemin_cache, encoding="utf-8") as f:
        data = json.load(f)
    return {cle: EntreeCache(**valeurs) for cle, valeurs in data.items()}


def sauvegarder_cache(chemin_cache: Path, cache: dict[str, EntreeCache]) -> None:
    data = {cle: vars(entree) for cle, entree in cache.items()}
    chemin_cache.parent.mkdir(parents=True, exist_ok=True)
    with open(chemin_cache, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def integrer_aides_api(
    cache: dict[str, EntreeCache],
    aides: list[dict[str, Any]],
) -> RapportDiff:
    """
    Intègre une liste d'aides issues de l'API Aides-territoires dans le cache.

    Une aide est considérée "mise à jour" si son champ `date_updated` côté API
    a changé depuis le dernier passage — c'est plus fiable qu'un simple diff de
    contenu, puisque c'est l'éditeur lui-même qui certifie la date de mise à jour.
    """
    maintenant = datetime.now(timezone.utc).isoformat()
    rapport = RapportDiff()

    for aide in aides:
        cle = cle_pour_aide_api(aide)
        date_updated_origine = aide.get("date_updated")

        if cle not in cache:
            entree = EntreeCache(
                cle=cle,
                source_id="aides_territoires",
                titre=aide.get("name", "(sans titre)"),
                lien=aide.get("url"),
                date_premiere_vue=maintenant,
                date_derniere_vue=maintenant,
                date_updated_origine=date_updated_origine,
                submission_deadline=aide.get("submission_deadline"),
            )
            cache[cle] = entree
            rapport.nouvelles_entrees.append(entree)
            continue

        entree_existante = cache[cle]
        entree_existante.date_derniere_vue = maintenant

        if (
            date_updated_origine
            and entree_existante.date_updated_origine
            and date_updated_origine != entree_existante.date_updated_origine
        ):
            entree_existante.date_updated_origine = date_updated_origine
            entree_existante.submission_deadline = aide.get("submission_deadline")
            rapport.entrees_mises_a_jour.append(entree_existante)
        else:
            rapport.entrees_inchangees_count += 1

    return rapport


def integrer_items_html(
    cache: dict[str, EntreeCache],
    source_id: str,
    items: list[Any],  # list[ItemExtrait] du module scraper_html, non importé pour éviter le couplage circulaire
) -> RapportDiff:
    """
    Intègre une liste d'items scrapés en HTML.

    Sans `date_updated` fiable, on ne peut détecter que l'apparition de
    nouvelles entrées (titre+lien jamais vus), pas les mises à jour de
    contenu d'une fiche existante. C'est une limite assumée du scraping HTML
    par rapport à l'API — documentée dans README_sources.md.
    """
    maintenant = datetime.now(timezone.utc).isoformat()
    rapport = RapportDiff()

    for item in items:
        cle = cle_pour_item_html(source_id, item.titre, item.lien)

        if cle not in cache:
            entree = EntreeCache(
                cle=cle,
                source_id=source_id,
                titre=item.titre,
                lien=item.lien,
                date_premiere_vue=maintenant,
                date_derniere_vue=maintenant,
                # Réutilise le champ submission_deadline (déjà utilisé pour
                # l'API) pour stocker l'échéance extraite directement depuis
                # la page de liste HTML, quand le scraper a pu la détecter
                # (cf. _extraire_items_generique dans scraper_html.py).
                submission_deadline=getattr(item, "date_limite", None),
            )
            cache[cle] = entree
            rapport.nouvelles_entrees.append(entree)
        else:
            cache[cle].date_derniere_vue = maintenant
            rapport.entrees_inchangees_count += 1

    return rapport
