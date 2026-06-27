"""
Tests rapides, hors réseau, pour valider la logique interne avant livraison.
Ne teste PAS la connectivité réelle aux sites cibles (impossible depuis cet
environnement) — teste uniquement que le code fait ce qu'il est censé faire
sur des données simulées.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from cache_dedup import (
    charger_cache,
    integrer_aides_api,
    integrer_items_html,
    sauvegarder_cache,
)
from scraper_html import ItemExtrait, _extraire_items_generique


def test_extraction_generique_basique():
    html = """
    <html><body>
    <nav><a href="/accueil">Accueil</a></nav>
    <article>
        <a href="/aides/aide-voirie-rurale">Aide à la rénovation de voirie rurale 2026</a>
    </article>
    <li><a href="/aides/aide-jeux">Subvention équipements de jeux pour enfants</a></li>
    <div><a href="#">x</a></div>
    </body></html>
    """
    items = _extraire_items_generique(html, "https://example.org", "test_source")
    titres = [i.titre for i in items]
    assert "Aide à la rénovation de voirie rurale 2026" in titres
    assert "Subvention équipements de jeux pour enfants" in titres
    assert "Accueil" not in titres
    assert "x" not in titres
    print("OK: test_extraction_generique_basique")


def test_filtre_structurel_nav_header_footer():
    """
    Reproduit le type de bruit constaté en diagnostic réel sur Département 974
    (87 candidats) et CEREMA (157 candidats) : un menu de navigation imbriqué
    dans des <li><div><a>...</a></div></li>, qui matchait l'ancienne version
    de l'extraction générique car ces balises sont aussi celles utilisées pour
    le vrai contenu. Le filtre structurel (suppression de <nav>/<header>/
    <footer> avant extraction) doit éliminer ce bruit sans toucher au contenu
    utile situé ailleurs sur la page.
    """
    html = """
    <html><body>
    <header>
        <nav>
            <li><div><a href="/menu/item1">Domaines d'activités</a></div></li>
            <li><div><a href="/menu/item2">Publications et ressources</a></div></li>
            <li><div><a href="/menu/item3">Actions territoriales en région</a></div></li>
        </nav>
    </header>
    <main>
        <article>
            <a href="/actualites/aap-culture-sante-2026">Appel à projets Culture et Santé 2026</a>
        </article>
    </main>
    <footer>
        <li><a href="/footer/mentions">Mentions légales et CGU du site</a></li>
        <li><a href="/footer/contact">Contactez notre équipe ici</a></li>
    </footer>
    </body></html>
    """
    items = _extraire_items_generique(html, "https://example.org", "test_source")
    titres = [i.titre for i in items]

    assert "Appel à projets Culture et Santé 2026" in titres, (
        "Le contenu utile dans <main> doit être conservé"
    )
    assert "Domaines d'activités" not in titres, "Le menu dans <nav> doit être éliminé"
    assert "Publications et ressources" not in titres, "Le menu dans <nav> doit être éliminé"
    assert "Mentions légales et CGU du site" not in titres, "Le footer doit être éliminé"
    assert len(items) == 1, (
        f"Un seul item utile attendu après filtrage structurel, {len(items)} trouvé(s) : {titres}"
    )
    print("OK: test_filtre_structurel_nav_header_footer")


def test_filtre_boutons_action_ui_et_liens_javascript():
    """
    Reproduit le bruit constaté dans un rapport réel généré le 24/06/2026 :
    un bouton de pagination ("Afficher plus de contenus", remonté à tort
    comme un faux AAP en position 5 de la vue d'ensemble) et des liens de
    partage social qui faisaient perdre du temps au fetch de second niveau
    avec des erreurs réseau (400 sur facebook.com/sharer, "No connection
    adapters" sur javascript:;).
    """
    html = """
    <html><body>
    <main>
    <article>
      <a href="/actualite/aap-culture-sante-2026">Appel à projets : Culture et Santé - 2026</a>
    </article>
    <li><a href="/avis-appels-projets-enquetes-publiques">Afficher plus de contenus</a></li>
    <li><a href="https://facebook.com/sharer?u=x">Partager sur Facebook</a></li>
    <li><a href="https://x.com/intent/tweet">Partager sur X (anciennement Twitter)</a></li>
    <li><a href="javascript:;">Redirection en cours ...</a></li>
    </main>
    </body></html>
    """
    items = _extraire_items_generique(html, "https://www.departement974.fr", "departement_974")
    titres = [i.titre for i in items]

    assert "Appel à projets : Culture et Santé - 2026" in titres, (
        "Le contenu utile doit être conservé"
    )
    assert len(items) == 1, (
        f"Un seul item utile attendu après filtrage des boutons d'action UI "
        f"et liens javascript:, {len(items)} trouvé(s) : {titres}"
    )
    print("OK: test_filtre_boutons_action_ui_et_liens_javascript")


def test_dedup_titre_resume_meme_url():
    """
    Reproduit un cas réel constaté le 24/06/2026 sur Département 974 : sur
    certaines cartes d'actualité, le site pose un <a> distinct sur le titre
    ET sur les premiers mots du résumé, les deux pointant vers la MÊME URL.
    L'extraction générique doit les fusionner en un seul item (le titre, le
    plus court des deux), quel que soit l'ordre d'apparition dans le HTML.
    """
    html_ordre_normal = """
    <html><body><main>
    <article>
      <a href="/aap/ananas-victoria">Soutien au développement de la filière Ananas Victoria 2026</a>
      <a href="/aap/ananas-victoria">Cette aide vise a soutenir durablement la filiere locale d ananas Victoria face aux defis climatiques et economiques du territoire</a>
    </article>
    </main></body></html>
    """
    items = _extraire_items_generique(html_ordre_normal, "https://www.departement974.fr", "departement_974")
    assert len(items) == 1, f"Attendu 1 item fusionné, obtenu {len(items)} : {[i.titre for i in items]}"
    assert items[0].titre == "Soutien au développement de la filière Ananas Victoria 2026"

    # Même cas mais avec l'ordre résumé-puis-titre inversé dans le HTML —
    # doit donner le même résultat (le texte le plus court gagne, peu importe
    # l'ordre d'apparition dans le document).
    html_ordre_inverse = """
    <html><body><main>
    <article>
      <a href="/aap/test-inverse">Ce dispositif vise a soutenir tres largement les projets locaux</a>
      <a href="/aap/test-inverse">Appel a projets Test Inverse 2026</a>
    </article>
    </main></body></html>
    """
    items_inverse = _extraire_items_generique(html_ordre_inverse, "https://www.departement974.fr", "departement_974")
    assert len(items_inverse) == 1, (
        f"Attendu 1 item fusionné même avec ordre inversé, obtenu "
        f"{len(items_inverse)} : {[i.titre for i in items_inverse]}"
    )
    assert items_inverse[0].titre == "Appel a projets Test Inverse 2026", (
        "RÉGRESSION : doit garder le texte le plus court (le titre), "
        "indépendamment de l'ordre titre/résumé dans le HTML."
    )
    print("OK: test_dedup_titre_resume_meme_url")




def test_dedup_html_detecte_nouveaute_puis_stabilite():
    with tempfile.TemporaryDirectory() as tmp:
        chemin_cache = Path(tmp) / "cache.json"
        cache = charger_cache(chemin_cache)
        assert cache == {}

        items_passage_1 = [
            ItemExtrait(titre="Aide A", lien="https://x.org/a", source_id="src1"),
            ItemExtrait(titre="Aide B", lien="https://x.org/b", source_id="src1"),
        ]
        rapport_1 = integrer_items_html(cache, "src1", items_passage_1)
        assert len(rapport_1.nouvelles_entrees) == 2
        assert rapport_1.entrees_inchangees_count == 0

        sauvegarder_cache(chemin_cache, cache)
        cache_relu = charger_cache(chemin_cache)
        assert len(cache_relu) == 2

        items_passage_2 = [
            ItemExtrait(titre="Aide A", lien="https://x.org/a", source_id="src1"),  # déjà vue
            ItemExtrait(titre="Aide C", lien="https://x.org/c", source_id="src1"),  # nouvelle
        ]
        rapport_2 = integrer_items_html(cache_relu, "src1", items_passage_2)
        assert len(rapport_2.nouvelles_entrees) == 1
        assert rapport_2.nouvelles_entrees[0].titre == "Aide C"
        assert rapport_2.entrees_inchangees_count == 1
        print("OK: test_dedup_html_detecte_nouveaute_puis_stabilite")


def test_dedup_api_detecte_mise_a_jour_via_date_updated():
    with tempfile.TemporaryDirectory() as tmp:
        chemin_cache = Path(tmp) / "cache.json"
        cache = charger_cache(chemin_cache)

        aide_v1 = {
            "id": 12345,
            "name": "Aide test FEDER",
            "url": "/aides/abcd-aide-test-feder/",
            "submission_deadline": "2026-12-31",
            "date_updated": "2026-01-01T10:00:00+01:00",
        }
        rapport_1 = integrer_aides_api(cache, [aide_v1])
        assert len(rapport_1.nouvelles_entrees) == 1

        # Même passage exact -> rien de nouveau, rien de mis à jour
        rapport_2 = integrer_aides_api(cache, [aide_v1])
        assert len(rapport_2.nouvelles_entrees) == 0
        assert len(rapport_2.entrees_mises_a_jour) == 0
        assert rapport_2.entrees_inchangees_count == 1

        # date_updated change -> doit être détecté comme mise à jour
        aide_v2 = {**aide_v1, "date_updated": "2026-06-15T10:00:00+01:00", "submission_deadline": "2027-01-31"}
        rapport_3 = integrer_aides_api(cache, [aide_v2])
        assert len(rapport_3.entrees_mises_a_jour) == 1
        assert cache["api:12345"].submission_deadline == "2027-01-31"
        print("OK: test_dedup_api_detecte_mise_a_jour_via_date_updated")


if __name__ == "__main__":
    test_extraction_generique_basique()
    test_filtre_structurel_nav_header_footer()
    test_filtre_boutons_action_ui_et_liens_javascript()
    test_dedup_titre_resume_meme_url()
    test_dedup_html_detecte_nouveaute_puis_stabilite()
    test_dedup_api_detecte_mise_a_jour_via_date_updated()
    print("\nTous les tests sont passés.")
