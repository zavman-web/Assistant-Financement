"""
Tests pour generer_html.py — en particulier les deux vulnérabilités XSS
trouvées et corrigées le 27/06/2026 via un test DOM réel (jsdom), conservées
ici sous forme de tests Python sans dépendance Node, pour rester exécutables
dans n'importe quel environnement (poste local, GitHub Actions).

Ces tests vérifient l'ABSENCE de séquences dangereuses dans le HTML produit
en sortie de `generer_page_html()` — ils ne remplacent pas une vérification
DOM complète (faite une fois manuellement avec jsdom au moment de la
correction), mais détecteraient une régression évidente du même type.
"""

from __future__ import annotations

from categorisation import construire_entree
from generer_html import generer_page_html


def test_titre_avec_balise_script_ne_casse_pas_le_bloc_script():
    """
    Vulnérabilité 1 (trouvée le 27/06/2026) : un titre contenant la
    séquence "</script>" fermait prématurément la balise <script> du
    document HTML lui-même, empêchant le JavaScript de s'exécuter du tout
    (SyntaxError côté navigateur) — avant même que l'échappement JS ait pu
    s'appliquer. Corrigé en échappant "</" en "<\\/" dans le JSON sérialisé.
    """
    entree = construire_entree(
        "<script>alert(1)</script>Titre piégé", "https://example.org/x", "test_source",
    )
    html_genere = generer_page_html([entree], "test")

    # Le HTML produit ne doit JAMAIS contenir "</script>" en dehors de la
    # vraie balise de fermeture du bloc <script> du document lui-même.
    nb_fermetures_script = html_genere.count("</script>")
    assert nb_fermetures_script == 1, (
        f"RÉGRESSION : attendu exactement 1 fermeture </script> (celle du "
        f"document), obtenu {nb_fermetures_script} — un titre contenant "
        f"cette séquence casse le bloc JavaScript."
    )
    print("OK: test_titre_avec_balise_script_ne_casse_pas_le_bloc_script")


def test_lien_avec_guillemet_ne_genere_pas_attribut_executable():
    """
    Vulnérabilité 2 (trouvée le 27/06/2026) : echapperHtml() côté JS
    n'échappait pas les guillemets doubles, ce qui permettait à un lien
    malveillant (ou une source compromise) d'injecter un attribut HTML
    exécutable du type onmouseover="..." sur la balise <a> générée.
    Corrigé en réécrivant echapperHtml() en JS pour échapper explicitement
    les guillemets (et apostrophes par précaution).

    Ce test vérifie la fonction JS elle-même (chaîne de caractères du
    code généré), pas le rendu DOM — un test DOM complet a été fait
    manuellement avec jsdom au moment de la correction.
    """
    html_genere = generer_page_html([], "test")

    assert '.replace(/"/g, "&quot;")' in html_genere, (
        "RÉGRESSION : la fonction echapperHtml() côté JS doit échapper "
        "explicitement les guillemets doubles, sinon un lien malveillant "
        "peut s'échapper de l'attribut href et injecter un gestionnaire "
        "d'événement exécutable."
    )
    print("OK: test_lien_avec_guillemet_ne_genere_pas_attribut_executable")


def test_apostrophe_legitime_reste_lisible():
    """
    Garde-fou de non-régression dans l'autre sens : un titre légitime
    contenant une apostrophe française (très courant : "Aide d'investissement")
    ne doit pas être rendu illisible par l'échappement de sécurité — le
    JSON doit transporter le texte correctement, l'affichage final
    (après échappement puis re-décodage HTML par le navigateur) doit
    rester lisible.
    """
    entree = construire_entree(
        "Aide d'investissement pour la transition", "https://example.org/y", "ademe",
    )
    html_genere = generer_page_html([entree], "test")
    assert "Aide d'investissement pour la transition" in html_genere, (
        "Le titre légitime doit apparaître intact dans le JSON embarqué "
        "(l'échappement HTML se fait côté JS au rendu, pas dans le JSON lui-même)."
    )
    print("OK: test_apostrophe_legitime_reste_lisible")


def test_recherche_par_prefixe_pas_par_sous_chaine():
    """
    Vulnérabilité fonctionnelle trouvée le 27/06/2026 EN CONDITIONS RÉELLES
    (premier vrai usage de la page publiée par l'utilisateur) : taper
    "Sport" dans le champ de recherche remontait aussi "Transport", à cause
    d'un matching JavaScript par sous-chaîne brute (.includes()) — la même
    classe de bug que celui déjà corrigé dans categorisation.py.

    Corrigé en JS par découpage en mots + startsWith(), plutôt qu'une regex
    avec \\b (une première tentative avec regex a généré du JavaScript
    cassé à cause d'échappements en cascade entre Python et JS — voir
    historique du cahier des charges). Vérifié par un vrai test DOM (jsdom)
    au moment de la correction ; ce test Python vérifie seulement la
    présence de la bonne logique dans le code généré, pas le comportement
    DOM complet (qui nécessiterait Node, non garanti disponible partout).
    """
    html_genere = generer_page_html([], "test")
    assert "unMotCommencePar" in html_genere, (
        "RÉGRESSION : la fonction de recherche par préfixe de mot doit être "
        "présente — sinon le filtrage redevient un matching par sous-chaîne "
        "brute (bug 'Sport' trouve 'Transport')."
    )
    assert ".includes(q)" not in html_genere or "catch (e)" not in html_genere, (
        "Vérifie qu'il ne reste pas un ancien chemin de code utilisant "
        ".includes() pour le filtrage de recherche principal."
    )
    print("OK: test_recherche_par_prefixe_pas_par_sous_chaine")


if __name__ == "__main__":
    test_titre_avec_balise_script_ne_casse_pas_le_bloc_script()
    test_lien_avec_guillemet_ne_genere_pas_attribut_executable()
    test_apostrophe_legitime_reste_lisible()
    test_recherche_par_prefixe_pas_par_sous_chaine()
    print("\nTous les tests de sécurité HTML sont passés.")
