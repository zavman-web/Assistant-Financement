"""
Catégorisation thématique pour VEILLE-FI — conforme à la Section 3 du
CAHIER_DES_CHARGES.md.

PRINCIPE DIRECTEUR (différent de l'ancien scoring.py, archivé) :
Ce module n'EXCLUT rien et ne hiérarchise pas une thématique au-dessus d'une
autre. Son seul rôle est d'étiqueter chaque nouveauté avec une ou plusieurs
des 7 thématiques génériques définies dans le cahier des charges, pour que
chaque service de la mairie puisse scanner la section qui le concerne.

Le seul tri qui subsiste est par URGENCE D'ÉCHÉANCE (section 4 du cahier des
charges) — pas par pertinence politique. Une entrée sans échéance connue
n'est pas pénalisée : elle est simplement classée après celles qui ont une
échéance, dans l'ordre où elle a été détectée.

Si une entrée ne correspond à aucun mot-clé reconnu, elle est explicitement
étiquetée "Autre / Non catégorisé" — elle n'est jamais supprimée du rapport.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

# Les 8 thématiques de la Section 3 du cahier des charges, dans l'ordre où
# elles doivent apparaître dans le rapport. NE PAS modifier cette liste sans
# mettre à jour CAHIER_DES_CHARGES.md en premier.
#
# "Agriculture / Ruralité" ajoutée le 24/06/2026 (validée par Xavier) : avant
# cette date, les AAP agricoles (apiculture, MAEC, conseil agricole) étaient
# fusionnés dans "Environnement / Transition écologique" faute de case
# dédiée — voir l'historique correspondant dans CAHIER_DES_CHARGES.md.
THEMATIQUES = [
    "Voirie / Aménagement / Écarts ruraux",
    "Environnement / Transition écologique",
    "Agriculture / Ruralité",
    "Action sociale / Petite enfance / Parentalité",
    "Culture / Sport / Jeunesse",
    "Affaires financières / Ingénierie",
    "Europe / Coopération régionale",
    "Autre / Non catégorisé",
]

# Mots-clés déclenchant chaque thématique. Volontairement large : mieux vaut
# qu'une entrée apparaisse dans deux thématiques pertinentes plutôt qu'aucune.
# Ces listes sont amenées à être enrichies au fil des passages réels — c'est
# la partie la plus susceptible d'ajustement continu de tout le pipeline.
#
# IMPORTANT (corrigé le 24/06/2026 suite à un bug réel constaté en
# production) : ces mots-clés sont matchés par MOT ENTIER (limites \b), pas
# par sous-chaîne brute. L'ancienne approche par sous-chaîne faisait que
# "culture" matchait dans "agriCULTUre" et "sport" dans tranSPORT, classant
# à tort des AAP de transport maritime ou d'apiculture dans "Culture / Sport
# / Jeunesse". Voir _categoriser_par_mots_entiers ci-dessous.
MOTS_CLES_PAR_THEMATIQUE: dict[str, list[str]] = {
    "Voirie / Aménagement / Écarts ruraux": [
        "voirie", "désenclavement", "desenclavement",
        "écarts", "ecarts", "les hauts", "aménagement", "amenagement",
        "aire de jeux", "aires de jeux", "équipements de jeux", "equipements de jeux",
        "équipement sportif", "equipement sportif",
        "city stade", "street workout", "urbanisme", "espace public",
    ],
    "Environnement / Transition écologique": [
        "fonds vert", "transition écologique", "transition ecologique",
        "énergie", "energie", "déchets", "dechets", "biodiversité", "biodiversite",
        "ressource en eau", "climat", "rénovation énergétique", "renovation energetique",
        # Enrichissement du 24/06/2026, mots-clés manquants identifiés sur un
        # vrai rapport (AAP ADEME massivement classés "Autre" alors que leurs
        # titres étaient sans ambiguïté thématique) :
        "économie circulaire", "economie circulaire", "réemploi", "reemploi",
        "écoconception", "ecoconception", "qualité de l'air", "qualite de l'air",
        "décarbonation", "decarbonation", "renouvelable", "renouvelables",
        "biomasse", "géothermie", "geothermie", "chaleur renouvelable",
        # "feader", "agricole", "agriculture", "forestier", "sols",
        # "apiculture", "maec", "gaspillage alimentaire", "alimentation
        # durable" déplacés vers "Agriculture / Ruralité" le 24/06/2026.
    ],
    "Agriculture / Ruralité": [
        # Catégorie créée le 24/06/2026 (validée par Xavier) suite à un vrai
        # rapport montrant des AAP agricoles sans ambiguïté (apiculture,
        # MAEC, conseil agricole) fusionnés à tort dans "Environnement".
        "agricole", "agricoles", "agriculture", "feader", "maec",
        "apiculture", "élevage", "elevage", "exploitation agricole",
        "route agricole", "chemin rural", "forestier", "forestiers",
        "filière agricole", "filiere agricole", "circuits courts",
        "gaspillage alimentaire", "alimentation durable", "pêche", "peche",
        "aquaculture", "agroalimentaire", "agro-alimentaire",
        "monde agricole", "exploitants agricoles", "chambre d'agriculture",
    ],
    "Action sociale / Petite enfance / Parentalité": [
        "petite enfance", "parentalité", "parentalite", "crèche", "creche",
        "clas", "accompagnement scolaire", "action sociale", "solidarité",
        "solidarite", "famille", "insertion", "logement social",
        "perte d'autonomie", "personnes âgées", "personnes agees",
    ],
    "Culture / Sport / Jeunesse": [
        "culturel", "culturelle", "sportif", "sportive", "jeunesse", "jeune",
        "spectacle vivant", "arts visuels", "patrimoine", "festival",
        "éducation artistique", "education artistique", "associatif",
        "associations",
        # "culture" et "sport" en tant que mots seuls ont été retirés
        # (cf. bug ci-dessus) : "culturel/sportif" couvrent l'essentiel des
        # cas réels sans matcher "agriculture"/"transport".
    ],
    "Affaires financières / Ingénierie": [
        "ingénierie financière", "ingenierie financiere", "contrôle de gestion",
        "controle de gestion", "prospective financière", "prospective financiere",
        "prêt", "pret", "investissement local", "ingénierie technique",
        "ingenierie technique",
    ],
    "Europe / Coopération régionale": [
        "feder", "fse", "interreg", "ndici", "feampa", "océan indien",
        "ocean indien", "coopération régionale", "cooperation regionale",
        "union européenne", "union europeenne",
    ],
}

# Mots-clés transverses (transport/mobilité, textile, logistique,
# équipements de chantier) qui ne rentrent pas naturellement dans les 8
# thématiques métier mais qui sont des cas réels rencontrés sur le flux
# ADEME — rattachés à "Environnement / Transition écologique" car la
# quasi-totalité des AAP ADEME sur ces sujets relèvent de la transition
# écologique (mobilité décarbonée, logistique durable, etc.), plutôt que de
# les laisser systématiquement dans "Autre".
MOTS_CLES_PAR_THEMATIQUE["Environnement / Transition écologique"] += [
    "transport", "transports", "maritime", "maritimes", "mobilité", "mobilite",
    "mobilités", "mobilites", "logistique", "textile", "engins de chantier",
    "véhicules électriques", "vehicules electriques", "covoiturage",
]


def _construire_pattern_mot_entier(expression: str) -> re.Pattern:
    """
    Construit un pattern regex qui matche `expression` comme un mot/une
    expression ENTIÈRE, pas comme sous-chaîne brute.

    Pour un mot simple (ex. "sport") : \\bsport\\b — ne matche pas "transport".
    Pour une expression multi-mots (ex. "petite enfance") : la limite de mot
    s'applique au début du premier mot et à la fin du dernier, ce qui reste
    sûr car les espaces internes ne créent pas de risque de sous-chaîne.

    re.escape() protège les expressions contenant des caractères spéciaux
    regex (ex. apostrophes typographiques, parenthèses).
    """
    return re.compile(rf"\b{re.escape(expression)}\b", re.IGNORECASE)


# Pré-compilation des patterns une seule fois au chargement du module, par
# thématique, pour éviter de recompiler à chaque appel de categoriser().
_PATTERNS_PAR_THEMATIQUE: dict[str, list[re.Pattern]] = {
    thematique: [_construire_pattern_mot_entier(mot) for mot in mots_cles]
    for thematique, mots_cles in MOTS_CLES_PAR_THEMATIQUE.items()
}


@dataclass
class EntreeCategorisee:
    titre: str
    lien: str | None
    source_id: str
    thematiques: list[str]  # toujours au moins une (jamais vide grâce au repli)
    echeance_iso: str | None
    jours_avant_echeance: int | None
    statut_dedup: str = "nouvelle"  # "nouvelle" | "mise_a_jour"


def _texte_recherchable(titre: str, description: str | None = None) -> str:
    return f"{titre} {description or ''}".lower()


def categoriser(titre: str, description: str | None = None) -> list[str]:
    """
    Retourne la liste des thématiques correspondantes. Ne renvoie JAMAIS une
    liste vide : si aucun mot-clé ne correspond, retourne explicitement
    ["Autre / Non catégorisé"] — c'est le comportement attendu, pas un échec.

    Utilise un matching par MOT ENTIER (cf. _PATTERNS_PAR_THEMATIQUE), pas
    par sous-chaîne brute — voir le commentaire au-dessus de
    MOTS_CLES_PAR_THEMATIQUE pour le contexte du bug que ça corrige.
    """
    texte = _texte_recherchable(titre, description)
    matches = [
        thematique
        for thematique, patterns in _PATTERNS_PAR_THEMATIQUE.items()
        if any(pattern.search(texte) for pattern in patterns)
    ]
    return matches if matches else ["Autre / Non catégorisé"]


def _jours_avant_echeance(echeance_iso: str | None) -> int | None:
    if not echeance_iso:
        return None
    try:
        d = datetime.strptime(echeance_iso, "%Y-%m-%d").date()
    except ValueError:
        return None
    return (d - date.today()).days


def construire_entree(
    titre: str,
    lien: str | None,
    source_id: str,
    description: str | None = None,
    echeance_iso: str | None = None,
    statut_dedup: str = "nouvelle",
) -> EntreeCategorisee:
    return EntreeCategorisee(
        titre=titre,
        lien=lien,
        source_id=source_id,
        thematiques=categoriser(titre, description),
        echeance_iso=echeance_iso,
        jours_avant_echeance=_jours_avant_echeance(echeance_iso),
        statut_dedup=statut_dedup,
    )


def trier_par_urgence(entrees: list[EntreeCategorisee]) -> list[EntreeCategorisee]:
    """
    Trie par échéance la plus proche en premier, en EXCLUANT les échéances
    déjà dépassées du haut de la liste.

    BUG CORRIGÉ LE 24/06/2026 (constaté en conditions réelles : des AAP
    clôturés avec échéance dépassée depuis des mois apparaissaient en tête
    du rapport, avant des AAP réellement actifs). La cause : un tri croissant
    naïf sur `jours_avant_echeance` traite une valeur très négative (ex. -400,
    une échéance dépassée depuis 400 jours) comme "plus urgente" qu'une valeur
    positive proche de zéro (ex. +5, une échéance dans 5 jours) — alors que
    c'est l'inverse qui est utile à un lecteur.

    Ordre de priorité corrigé, du plus important au moins important :
    1. Échéances actives, triées de la plus proche à la plus lointaine
       (jours_avant_echeance >= 0, croissant)
    2. Entrées sans échéance connue (jours_avant_echeance is None), dans
       leur ordre d'arrivée d'origine — ni pénalisées ni mises en avant
    3. Échéances déjà dépassées (jours_avant_echeance < 0), en dernier —
       elles restent visibles dans le rapport (principe de non-exclusion,
       Section 1 du cahier des charges) mais ne doivent jamais polluer le
       haut de la liste destinée à attirer l'attention sur l'urgent.
    """
    actives = [e for e in entrees if e.jours_avant_echeance is not None and e.jours_avant_echeance >= 0]
    sans_echeance = [e for e in entrees if e.jours_avant_echeance is None]
    depassees = [e for e in entrees if e.jours_avant_echeance is not None and e.jours_avant_echeance < 0]

    actives_triees = sorted(actives, key=lambda e: e.jours_avant_echeance)
    return actives_triees + sans_echeance + depassees


def regrouper_par_thematique(
    entrees: list[EntreeCategorisee],
) -> dict[str, list[EntreeCategorisee]]:
    """
    Retourne un dict {thematique: [entrées]} couvrant TOUJOURS toutes les
    thématiques de THEMATIQUES, même avec une liste vide — c'est ce qui
    permet au rapport d'afficher explicitement "rien de nouveau" plutôt que
    de faire disparaître une catégorie silencieusement (Section 4 du cahier
    des charges).
    """
    regroupement: dict[str, list[EntreeCategorisee]] = {t: [] for t in THEMATIQUES}
    for entree in entrees:
        for thematique in entree.thematiques:
            regroupement[thematique].append(entree)
    return regroupement


if __name__ == "__main__":
    # Auto-test : vérifie que rien n'est jamais exclu, même hors mots-clés,
    # et que le tri par urgence respecte le principe de neutralité décrit.
    exemples = [
        construire_entree(
            "Subvention équipements de jeux pour enfants en milieu rural",
            "https://x.org/a", "region_reunion_aap",
            echeance_iso=date.today().isoformat(),
        ),
        construire_entree(
            "Appel à projets petite enfance et parentalité",
            "https://x.org/b", "caf_reunion",
        ),
        construire_entree(
            "Dispositif sans rapport apparent avec nos thématiques connues",
            "https://x.org/c", "ademe",
        ),
    ]

    print("Catégorisation :")
    for e in exemples:
        print(f"  {e.titre[:55]!r:60s} -> {e.thematiques}")

    # Vérifie qu'aucune entrée n'est orpheline de thématique
    assert all(len(e.thematiques) >= 1 for e in exemples)
    # Vérifie que l'entrée "sans rapport apparent" tombe bien dans Autre
    assert "Autre / Non catégorisé" in exemples[2].thematiques

    triees = trier_par_urgence(exemples)
    print("\nTri par urgence :")
    for e in triees:
        print(f"  jours_avant_echeance={e.jours_avant_echeance}  {e.titre[:50]!r}")
    assert triees[0].titre.startswith("Subvention équipements de jeux")  # a une échéance aujourd'hui

    # Test de non-régression : un cas réel en conditions réelles a révélé que
    # des AAP CLÔTURÉS (échéance très dépassée) apparaissaient en tête du
    # rapport, avant des AAP réellement actifs — un tri croissant naïf
    # traitait une échéance très négative comme "plus urgente". Ce test
    # garantit que les échéances dépassées sont toujours reléguées en fin de
    # liste, après les actives ET après les entrées sans échéance connue.
    exemples_avec_depassees = [
        construire_entree(
            "AAP clôturé depuis longtemps", "https://x.org/clos", "departement_974",
            echeance_iso=(date.today() - timedelta(days=400)).isoformat(),
        ),
        construire_entree(
            "AAP urgent dans 5 jours", "https://x.org/urgent", "region_reunion_aap",
            echeance_iso=(date.today() + timedelta(days=5)).isoformat(),
        ),
        construire_entree(
            "AAP sans échéance connue", "https://x.org/inconnu", "ademe",
        ),
    ]
    triees_2 = trier_par_urgence(exemples_avec_depassees)
    assert triees_2[0].titre == "AAP urgent dans 5 jours", (
        "RÉGRESSION : l'AAP actif et urgent doit être en première position, "
        "pas un AAP clôturé."
    )
    assert triees_2[-1].titre == "AAP clôturé depuis longtemps", (
        "RÉGRESSION : un AAP clôturé (échéance dépassée) doit être en "
        "dernière position, jamais en tête de rapport."
    )
    print("\nOK : les échéances dépassées ne polluent plus le haut du classement.")

    regroupement = regrouper_par_thematique(exemples)
    print(f"\nRegroupement par thématique ({len(THEMATIQUES)} catégories, même vides) :")
    for thematique in THEMATIQUES:
        nb = len(regroupement[thematique])
        print(f"  {thematique:55s} : {nb} entrée(s)")
    assert len(regroupement) == len(THEMATIQUES)  # toutes les thématiques présentes, même à 0

    # Test de non-régression : un cas réel a révélé un chevauchement entre
    # "Voirie" et "Environnement" via le mot-clé générique "rural"/"eau".
    # Ce test garantit qu'un texte parlant d'équipements de jeux en zone rurale
    # tombe bien dans Voirie/Aménagement, pas dans Environnement.
    cas_chevauchement = categoriser("Subvention équipements de jeux pour enfants en milieu rural")
    assert "Voirie / Aménagement / Écarts ruraux" in cas_chevauchement
    assert "Environnement / Transition écologique" not in cas_chevauchement

    # Tests de non-régression sur des cas réels constatés dans un rapport
    # généré le 24/06/2026 : "culture"/"sport" en sous-chaîne classaient à
    # tort des AAP de transport maritime et d'apiculture dans "Culture /
    # Sport / Jeunesse" (agriCULTUre, tranSPORT). Le matching par mot entier
    # (cf. _construire_pattern_mot_entier) doit empêcher ce type d'erreur.
    cas_transport_maritime = categoriser(
        "Aides à l'investissement pour la décarbonation du transport et des services maritimes"
    )
    assert "Culture / Sport / Jeunesse" not in cas_transport_maritime, (
        "RÉGRESSION : 'transport' ne doit pas matcher 'sport' par sous-chaîne."
    )
    assert "Environnement / Transition écologique" in cas_transport_maritime

    cas_apiculture = categoriser("Appel à projets : dispositif 70.291_MAEC - Apiculture - 2026")
    assert "Culture / Sport / Jeunesse" not in cas_apiculture, (
        "RÉGRESSION : 'MAEC - Apiculture' ne doit pas matcher 'culture' par sous-chaîne."
    )
    assert "Agriculture / Ruralité" in cas_apiculture, (
        "RÉGRESSION : depuis la création de la catégorie Agriculture / Ruralité "
        "(24/06/2026), un AAP MAEC-Apiculture doit y être rattaché, plus à "
        "Environnement."
    )

    print("OK : matching par mot entier — plus de faux positifs transport/sport ou apiculture/culture.")

    print("\nOK : aucune exclusion, toutes les thématiques représentées, tri par urgence neutre.")
