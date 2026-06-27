"""
Test d'intégration de bout en bout pour run_veille.py — version conforme à
CAHIER_DES_CHARGES.md (24/06/2026, incluant la révision de fin de session
recentrant l'outil sur les élus avec un format cherchable par tags plutôt
que des sections thématiques fixes).

Vérifie en particulier :
1. Le pipeline complet s'exécute sans erreur (collecte, catégorisation, rapport)
2. Le rapport affiche les tags thématiques en clair sur chaque ligne (format
   "tags : ..."), SANS section de classement fixe ("Détail par thématique"
   a été retiré le 24/06/2026 — voir Section 3 et 4 du cahier des charges)
3. La règle de déclenchement par âge (Section 5) fonctionne : pas de collecte
   si le dernier rapport a moins de 7 jours, collecte si plus de 7 jours ou absent
4. Aucune entrée n'est jamais exclue du rapport (principe directeur de la
   Section 1 — l'outil n'est pas un filtre)

Tous les appels réseau sont mockés.
"""

from __future__ import annotations

import shutil
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import run_veille


def _reponse_mock(json_data=None, text_data=None, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    if json_data is not None:
        resp.json.return_value = json_data
    if text_data is not None:
        resp.text = text_data
    return resp


def _fausse_reponse_api(count_total: int = 2):
    return {
        "count": count_total,
        "next": None,
        "previous": None,
        "results": [
            {
                "id": 1,
                "name": "Aide test voirie rurale Saint-Benoît",
                "url": "/aides/test-voirie/",
                "perimeter": "Saint-Benoît (Commune – 97470)",
                "targeted_audiences": ["Communes"],
                "submission_deadline": "2026-08-15",
                "date_updated": "2026-06-01T10:00:00+02:00",
            },
            {
                "id": 2,
                "name": "Aide test hors-périmètre Paris",
                "url": "/aides/test-paris/",
                "perimeter": "Paris (Commune – 75001)",
                "targeted_audiences": ["Particuliers"],
                "submission_deadline": None,
                "date_updated": "2026-06-01T10:00:00+02:00",
            },
        ],
    }


HTML_LISTE_REGION_REUNION = """
<html><body>
<article><a href="/aides-services/appels-a-projets/article/aap-petite-enfance-test">
Appel à projets - Soutien à la petite enfance et parentalité 2026</a></article>
</body></html>
"""

HTML_FICHE_DETAIL = """
<html><body>
<h1>Appel à projets - Soutien à la petite enfance et parentalité 2026</h1>
Date d'ouverture : 1 juin 2026
Date limite de remise des propositions : 30 septembre 2026 à 12h00
</body></html>
"""

HTML_VIDE = """<html><body><nav><a href="/accueil">Accueil</a></nav></body></html>"""

FLUX_RSS_ADEME_SIMULE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item>
  <title>Aide test ADEME transition écologique La Réunion</title>
  <link>https://agirpourlatransition.ademe.fr/aap-test-reunion</link>
  <description>du 01/06/2026 - 00:00 au 30/09/2026 - 00:00 - Heure de Paris - La Réunion</description>
  <pubDate>Mon, 01 Jun 2026 10:00:00 GMT</pubDate>
</item>
</channel></rss>"""


def _route_get_mock(url, headers=None, params=None, timeout=None):
    if "api/aids" in url:
        return _reponse_mock(json_data=_fausse_reponse_api())
    if "rss/appels-a-projet" in url:
        resp = _reponse_mock()
        resp.content = FLUX_RSS_ADEME_SIMULE.encode("utf-8")
        return resp
    if "aap-petite-enfance-test" in url:
        return _reponse_mock(text_data=HTML_FICHE_DETAIL)
    if "regionreunion.com" in url or "region_reunion" in url:
        return _reponse_mock(text_data=HTML_LISTE_REGION_REUNION)
    return _reponse_mock(text_data=HTML_VIDE)


def _session_get_mock(self, url, headers=None, params=None, timeout=None):
    return _route_get_mock(url, headers=headers, params=params, timeout=timeout)


def test_pipeline_complet_et_conformite_cahier_des_charges():
    repertoire_test = Path(tempfile.mkdtemp())
    try:
        run_veille.CHEMIN_CACHE = repertoire_test / "cache" / "veille_fi_cache.json"
        run_veille.DOSSIER_RAPPORTS = repertoire_test / "rapports"
        # Redirection ajoutée le 27/06/2026 lors de l'introduction de la page
        # HTML publique — sans ça, chaque exécution du test polluait le
        # vrai dossier docs/ du projet plutôt que d'écrire dans un répertoire
        # temporaire jetable comme les autres sorties du test.
        run_veille.DOSSIER_PUBLIC = repertoire_test / "docs"
        run_veille.CHEMIN_PAGE_HTML = run_veille.DOSSIER_PUBLIC / "index.html"

        with patch("requests.get", side_effect=_route_get_mock), \
             patch("requests.Session.get", new=_session_get_mock):
            chemin_rapport = run_veille.executer_collecte()

        assert chemin_rapport.exists(), "Le rapport doit être créé"
        contenu = chemin_rapport.read_text(encoding="utf-8")

        # --- RÉVISION DU 24/06/2026 : plus de sections thématiques fixes ---
        # Le rapport ne contient plus "## Voirie...", "## Culture..." etc.
        # comme titres de section. Les tags thématiques apparaissent
        # désormais en clair sur chaque ligne (ex. "tags : Voirie /
        # Aménagement..."), pour rester cherchables au Ctrl+F sans
        # imposer un classement fixe au lecteur (élu de la majorité).
        assert "tags :" in contenu, (
            "Les tags thématiques doivent apparaître en clair sur les lignes "
            "du rapport, format 'tags : ...'"
        )

        # --- Test ajouté le 27/06/2026 : l'échéance ADEME doit apparaître ---
        # Avant cette correction, AUCUNE échéance n'était jamais extraite
        # pour la source ADEME, rendant le tri par urgence inopérant sur la
        # source la plus volumineuse du pipeline (~194 entrées sur un rapport
        # réel). Le mock FLUX_RSS_ADEME_SIMULE utilise le VRAI format du
        # résumé RSS ("du JJ/MM/AAAA - HH:MM au JJ/MM/AAAA - HH:MM"), confirmé
        # en conditions réelles le 27/06/2026 après qu'une première version
        # basée sur un format supposé à tort se soit révélée inopérante en
        # production. Ce texte doit se traduire par un marqueur "échéance
        # dans X j" sur la ligne correspondante du rapport.
        assert "échéance dans" in contenu and "Aide test ADEME" in contenu, (
            "L'entrée ADEME du mock doit afficher une échéance dans le rapport."
        )
        ligne_ademe = next(
            (l for l in contenu.splitlines() if "Aide test ADEME" in l), ""
        )
        assert "échéance dans" in ligne_ademe, (
            "RÉGRESSION : l'échéance extraite du résumé RSS ADEME ('Ouvert "
            "jusqu'au 30 septembre 2026') doit apparaître sur la ligne de "
            "cette entrée — sinon le tri par urgence redevient inopérant "
            "pour toute la source ADEME, comme constaté sur un rapport réel "
            "le 27/06/2026."
        )

        # --- Vérification principe directeur Section 1 : rien n'est filtré/exclu ---
        # Les deux entrées qu'on a injectées (voirie + petite enfance) doivent
        # apparaître quelque part dans le rapport, quelle que soit leur thématique.
        assert "voirie rurale Saint-Benoît" in contenu or "Voirie" in contenu
        assert "petite enfance et parentalité" in contenu

        # --- Vérification Section 4 : structure de l'en-tête ---
        assert "Rapport VEILLE-FI" in contenu
        assert "Nouveautés" in contenu
        assert "Détail technique par source" in contenu
        # Le rapport ne doit PLUS contenir l'ancienne section de classement fixe.
        assert "Détail par thématique" not in contenu, (
            "RÉGRESSION : la section 'Détail par thématique' (classement fixe "
            "en 8 sections) a été retirée le 24/06/2026 — ne doit plus apparaître."
        )

        print("Extrait du rapport généré :\n")
        print(contenu[:1500])
        print("\nOK : pipeline complet conforme au cahier des charges (test 1/3).")

        # --- Vérification de la page HTML publique (Section 4 révisée le 27/06/2026) ---
        assert run_veille.CHEMIN_PAGE_HTML.exists(), (
            "La page HTML publique doit être créée en complément du rapport Markdown."
        )
        contenu_html = run_veille.CHEMIN_PAGE_HTML.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in contenu_html
        assert "VEILLE-FI" in contenu_html
        assert "id=\"recherche\"" in contenu_html, "Le champ de recherche filtrant doit être présent."
        # Les mêmes entrées injectées dans le mock doivent apparaître dans le
        # JSON embarqué de la page HTML (reconstruites depuis le cache,
        # pas seulement les nouveautés de ce passage — décision du 27/06/2026).
        assert "voirie rurale Saint-Benoît" in contenu_html or "Voirie" in contenu_html
        print("OK : page HTML publique générée avec le contenu attendu.")

        # --- Test 2/3 : règle de déclenchement Section 5 — pas de collecte si récent ---
        faut_collecter, raison = run_veille._faut_il_collecter(force=False)
        assert faut_collecter is False, (
            f"Un rapport vient d'être créé aujourd'hui — aucune collecte ne devrait "
            f"être déclenchée. Raison reçue : {raison}"
        )
        print(f"OK : règle de non-collecte respectée ({raison}) (test 2/3).")

        # --- Test 3/3 : simulation d'un rapport vieux de 10 jours -> collecte attendue ---
        ancien_nom = f"rapport_{(date.today() - timedelta(days=10)).isoformat()}.md"
        for f in run_veille.DOSSIER_RAPPORTS.glob("rapport_*.md"):
            f.unlink()
        (run_veille.DOSSIER_RAPPORTS / ancien_nom).write_text("ancien rapport simulé", encoding="utf-8")

        faut_collecter, raison = run_veille._faut_il_collecter(force=False)
        assert faut_collecter is True, (
            f"Un rapport de 10 jours dépasse le seuil de {run_veille.SEUIL_AGE_RAPPORT_JOURS} "
            f"jours — une collecte devrait être déclenchée. Raison reçue : {raison}"
        )
        print(f"OK : règle de collecte sur rapport ancien respectée ({raison}) (test 3/3).")

    finally:
        shutil.rmtree(repertoire_test, ignore_errors=True)


def test_page_html_filtre_echeances_trop_anciennes():
    """
    Vérifie la décision validée par Xavier le 27/06/2026 : la page HTML
    reconstruit l'intégralité du cache (pas seulement les nouveautés), mais
    exclut les dispositifs dont l'échéance est dépassée depuis plus de
    SEUIL_EXCLUSION_HTML_JOURS (60) jours. Ceux dépassés plus récemment, ou
    sans échéance connue, restent visibles.
    """
    import json as json_module
    from datetime import date, timedelta

    repertoire_test = Path(tempfile.mkdtemp())
    try:
        run_veille.CHEMIN_CACHE = repertoire_test / "cache" / "veille_fi_cache.json"
        run_veille.DOSSIER_PUBLIC = repertoire_test / "docs"
        run_veille.CHEMIN_PAGE_HTML = run_veille.DOSSIER_PUBLIC / "index.html"
        run_veille.DOSSIER_RAPPORTS = repertoire_test / "rapports"

        maintenant = "2026-06-27T10:00:00+00:00"
        cache_simule = {
            "html:src:tres_ancien": {
                "cle": "html:src:tres_ancien", "source_id": "test", "titre": "AAP très ancien (100j dépassé)",
                "lien": "https://example.org/tres-ancien",
                "date_premiere_vue": maintenant, "date_derniere_vue": maintenant,
                "date_updated_origine": None,
                "submission_deadline": (date.today() - timedelta(days=100)).isoformat(),
            },
            "html:src:recent_depasse": {
                "cle": "html:src:recent_depasse", "source_id": "test", "titre": "AAP récemment dépassé (10j)",
                "lien": "https://example.org/recent-depasse",
                "date_premiere_vue": maintenant, "date_derniere_vue": maintenant,
                "date_updated_origine": None,
                "submission_deadline": (date.today() - timedelta(days=10)).isoformat(),
            },
            "html:src:actif": {
                "cle": "html:src:actif", "source_id": "test", "titre": "AAP actif (30j restants)",
                "lien": "https://example.org/actif",
                "date_premiere_vue": maintenant, "date_derniere_vue": maintenant,
                "date_updated_origine": None,
                "submission_deadline": (date.today() + timedelta(days=30)).isoformat(),
            },
            "html:src:sans_echeance": {
                "cle": "html:src:sans_echeance", "source_id": "test", "titre": "AAP sans échéance connue",
                "lien": "https://example.org/inconnu",
                "date_premiere_vue": maintenant, "date_derniere_vue": maintenant,
                "date_updated_origine": None, "submission_deadline": None,
            },
        }
        run_veille.CHEMIN_CACHE.parent.mkdir(parents=True, exist_ok=True)
        run_veille.CHEMIN_CACHE.write_text(json_module.dumps(cache_simule), encoding="utf-8")

        with patch("requests.get", side_effect=_route_get_mock), \
             patch("requests.Session.get", new=_session_get_mock):
            run_veille.executer_collecte()

        contenu_html = run_veille.CHEMIN_PAGE_HTML.read_text(encoding="utf-8")

        assert "AAP actif (30j restants)" in contenu_html, "Un dispositif actif doit apparaître."
        assert "AAP sans échéance connue" in contenu_html, "Un dispositif sans échéance doit apparaître."
        assert "AAP récemment dépassé (10j)" in contenu_html, (
            "Un dispositif dépassé depuis moins de 60 jours doit encore apparaître."
        )
        assert "AAP très ancien (100j dépassé)" not in contenu_html, (
            "RÉGRESSION : un dispositif dépassé depuis plus de 60 jours "
            "(SEUIL_EXCLUSION_HTML_JOURS) ne doit plus apparaître sur la page HTML."
        )
        print("OK : test_page_html_filtre_echeances_trop_anciennes")

    finally:
        shutil.rmtree(repertoire_test, ignore_errors=True)


if __name__ == "__main__":
    test_pipeline_complet_et_conformite_cahier_des_charges()
    test_page_html_filtre_echeances_trop_anciennes()
    print("\nTous les tests de conformité au cahier des charges sont passés.")
