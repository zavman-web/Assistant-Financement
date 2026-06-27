"""
Génération de la page HTML interactive de VEILLE-FI, destinée à la
publication sur GitHub Pages — voir Section 4 ("Format de diffusion HTML
public") et Section 5 du cahier des charges.

Ce module ne collecte rien lui-même : il prend en entrée les mêmes données
déjà triées/catégorisées par run_veille.py (liste d'EntreeCategorisee) et
produit un unique fichier HTML autonome (CSS et JS inclus, pas de dépendance
externe au chargement — pas de CDN, pour que la page reste utilisable même
si une ressource externe devient indisponible).

Design : sobre et institutionnel plutôt que démonstratif — l'usage visé est
un outil de travail pour des élus, pas une page de présentation. Le tableau
filtrable est l'élément central, pas un argument de vente.
"""

from __future__ import annotations

import html
import json
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from categorisation import EntreeCategorisee


def _echappe(texte: str) -> str:
    """Échappe le texte pour insertion sûre dans du HTML."""
    return html.escape(texte, quote=True)


def _statut_urgence(jours_avant_echeance: int | None) -> str:
    """Retourne une classe CSS selon l'urgence, pour le badge visuel."""
    if jours_avant_echeance is None:
        return "neutre"
    if jours_avant_echeance < 0:
        return "depassee"
    if jours_avant_echeance <= 15:
        return "urgent"
    return "actif"


def _libelle_echeance(jours_avant_echeance: int | None) -> str:
    if jours_avant_echeance is None:
        return "Échéance inconnue"
    if jours_avant_echeance < 0:
        return "Échéance dépassée"
    if jours_avant_echeance == 0:
        return "Échéance aujourd'hui"
    if jours_avant_echeance == 1:
        return "Échéance demain"
    return f"Échéance dans {jours_avant_echeance} j"


def _construire_donnees_json(entrees: list["EntreeCategorisee"]) -> str:
    """
    Sérialise les entrées en JSON pour le JavaScript côté navigateur, qui
    s'en sert pour le filtrage/tri en direct sans aucun appel réseau après
    chargement initial de la page (tout se passe dans le navigateur de
    l'élu, conformément à la Section 4 : "pas de recherche serveur").

    SÉCURITÉ — CORRIGÉ LE 27/06/2026 après un test DOM réel (jsdom) ayant
    révélé une vraie vulnérabilité : si un titre d'AAP scrapé contient la
    séquence "</script>" (ex. injection malveillante depuis une source
    compromise, ou même un titre légitime qui mentionnerait cette chaîne
    par hasard), elle fermerait PRÉMATURÉMENT la balise <script> du document
    HTML lui-même — avant même que le JavaScript n'ait pu s'exécuter et
    appliquer son propre échappement (echapperHtml côté affichage). Ce n'est
    pas couvert par json.dumps() seul, qui échappe pour la syntaxe JS, pas
    pour le contexte HTML englobant. La séquence "</" est donc remplacée par
    "<\\/" après sérialisation JSON — un échappement JS valide qui empêche
    toute fermeture de balise tout en préservant le sens du JSON.
    """
    donnees = [
        {
            "titre": e.titre,
            "lien": e.lien or "",
            "source": e.source_id,
            "jours": e.jours_avant_echeance,
            "tags": e.thematiques,
        }
        for e in entrees
    ]
    json_brut = json.dumps(donnees, ensure_ascii=False)
    # Empêche toute fermeture prématurée de la balise <script> englobante
    # si un titre/lien contient la séquence "</" (voir docstring ci-dessus).
    return json_brut.replace("</", "<\\/")


def generer_page_html(
    entrees: list["EntreeCategorisee"],
    sections_techniques_texte: str,
) -> str:
    """
    Construit la page HTML complète (un seul fichier, CSS/JS inclus).
    `sections_techniques_texte` est le même texte que celui inséré dans le
    rapport Markdown (statuts par source) — affiché ici dans un panneau
    repliable, pour ne pas distraire l'élu du contenu utile par défaut.
    """
    aujourdhui = date.today().strftime("%d/%m/%Y")
    donnees_json = _construire_donnees_json(entrees)
    nb_entrees = len(entrees)

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>VEILLE-FI — Saint-Benoît</title>
<style>
  :root {{
    --fond: #FAFAF7;
    --fond-carte: #FFFFFF;
    --encre: #1C1E21;
    --encre-douce: #5A6472;
    --accent: #1B3A5C;
    --accent-clair: #E8EEF3;
    --urgent: #C0392B;
    --urgent-clair: #FBEAE8;
    --actif: #1E7B4D;
    --actif-clair: #E7F3EC;
    --depassee: #9AA1AB;
    --bordure: #DDE1E6;
  }}

  * {{ box-sizing: border-box; }}

  body {{
    margin: 0;
    background: var(--fond);
    color: var(--encre);
    font-family: "Source Sans Pro", "Segoe UI", system-ui, -apple-system, sans-serif;
    line-height: 1.5;
  }}

  header {{
    background: var(--accent);
    color: #FFFFFF;
    padding: 2rem 1.5rem 1.75rem;
  }}

  .entete-contenu {{
    max-width: 960px;
    margin: 0 auto;
  }}

  h1 {{
    font-family: "Georgia", "Iowan Old Style", serif;
    font-size: 1.8rem;
    font-weight: 600;
    margin: 0 0 0.35rem;
    letter-spacing: 0.01em;
  }}

  .sous-titre {{
    color: #C9D6E3;
    font-size: 0.95rem;
    margin: 0;
  }}

  main {{
    max-width: 960px;
    margin: 0 auto;
    padding: 1.5rem;
  }}

  .barre-controles {{
    display: flex;
    gap: 0.75rem;
    flex-wrap: wrap;
    margin-bottom: 1rem;
    align-items: center;
  }}

  #recherche {{
    flex: 1;
    min-width: 220px;
    padding: 0.65rem 0.9rem;
    border: 1px solid var(--bordure);
    border-radius: 6px;
    font-size: 0.95rem;
    background: var(--fond-carte);
    color: var(--encre);
  }}

  #recherche:focus {{
    outline: 2px solid var(--accent);
    outline-offset: 1px;
  }}

  .compteur {{
    font-size: 0.85rem;
    color: var(--encre-douce);
    white-space: nowrap;
  }}

  .tableau-conteneur {{
    background: var(--fond-carte);
    border: 1px solid var(--bordure);
    border-radius: 8px;
    overflow: hidden;
  }}

  table {{
    width: 100%;
    border-collapse: collapse;
  }}

  thead th {{
    text-align: left;
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--encre-douce);
    padding: 0.7rem 0.9rem;
    border-bottom: 2px solid var(--bordure);
    cursor: pointer;
    user-select: none;
    white-space: nowrap;
  }}

  thead th:hover {{
    color: var(--accent);
  }}

  thead th:focus-visible {{
    outline: 2px solid var(--accent);
  }}

  tbody tr {{
    border-bottom: 1px solid var(--bordure);
  }}

  tbody tr:last-child {{
    border-bottom: none;
  }}

  tbody tr:hover {{
    background: var(--accent-clair);
  }}

  td {{
    padding: 0.75rem 0.9rem;
    vertical-align: top;
    font-size: 0.92rem;
  }}

  .titre-cell a {{
    color: var(--accent);
    text-decoration: none;
    font-weight: 600;
  }}

  .titre-cell a:hover {{
    text-decoration: underline;
  }}

  .tags {{
    margin-top: 0.3rem;
    font-size: 0.8rem;
    color: var(--encre-douce);
  }}

  .source-badge {{
    display: inline-block;
    font-size: 0.75rem;
    color: var(--encre-douce);
    background: var(--fond);
    border: 1px solid var(--bordure);
    border-radius: 4px;
    padding: 0.1rem 0.4rem;
  }}

  .echeance-badge {{
    display: inline-block;
    font-size: 0.78rem;
    font-weight: 600;
    border-radius: 4px;
    padding: 0.25rem 0.55rem;
    white-space: nowrap;
  }}

  .echeance-badge.urgent {{
    background: var(--urgent-clair);
    color: var(--urgent);
  }}

  .echeance-badge.actif {{
    background: var(--actif-clair);
    color: var(--actif);
  }}

  .echeance-badge.depassee {{
    background: var(--fond);
    color: var(--depassee);
  }}

  .echeance-badge.neutre {{
    background: var(--fond);
    color: var(--encre-douce);
  }}

  .aucun-resultat {{
    padding: 2rem;
    text-align: center;
    color: var(--encre-douce);
  }}

  details {{
    margin-top: 1.5rem;
    font-size: 0.88rem;
  }}

  details summary {{
    cursor: pointer;
    color: var(--encre-douce);
    padding: 0.5rem 0;
  }}

  details pre {{
    background: var(--fond-carte);
    border: 1px solid var(--bordure);
    border-radius: 6px;
    padding: 1rem;
    overflow-x: auto;
    white-space: pre-wrap;
    font-size: 0.82rem;
    color: var(--encre-douce);
  }}

  footer {{
    max-width: 960px;
    margin: 0 auto;
    padding: 1rem 1.5rem 2.5rem;
    font-size: 0.8rem;
    color: var(--encre-douce);
  }}

  @media (max-width: 640px) {{
    .tags, .source-badge {{ display: block; margin-top: 0.25rem; }}
    thead {{ display: none; }}
    tbody tr {{ display: block; padding: 0.5rem 0; }}
    td {{ display: block; padding: 0.2rem 0.9rem; }}
  }}

  @media (prefers-reduced-motion: reduce) {{
    * {{ transition: none !important; }}
  }}
</style>
</head>
<body>

<header>
  <div class="entete-contenu">
    <h1>VEILLE-FI</h1>
    <p class="sous-titre">Financements et appels à projets pour les élus de Saint-Benoît — mis à jour le {aujourdhui}</p>
  </div>
</header>

<main>
  <div class="barre-controles">
    <input type="search" id="recherche" placeholder="Rechercher un mot-clé (ex. voirie, agriculture, ADEME...)" aria-label="Rechercher dans les dispositifs">
    <span class="compteur" id="compteur">{nb_entrees} dispositif(s)</span>
  </div>

  <div class="tableau-conteneur">
    <table>
      <thead>
        <tr>
          <th data-tri="titre" tabindex="0">Dispositif</th>
          <th data-tri="jours" tabindex="0">Échéance</th>
          <th data-tri="source" tabindex="0">Source</th>
        </tr>
      </thead>
      <tbody id="corps-tableau"></tbody>
    </table>
    <p class="aucun-resultat" id="aucun-resultat" style="display:none;">Aucun dispositif ne correspond à cette recherche.</p>
  </div>

  <details>
    <summary>Détail technique par source (statuts de collecte)</summary>
    <pre>{_echappe(sections_techniques_texte)}</pre>
  </details>
</main>

<footer>
  VEILLE-FI — outil interne de veille des financements publics pour Saint-Benoît. Document généré automatiquement, à vérifier auprès des organismes financeurs avant toute démarche.
</footer>

<script>
  const donnees = {donnees_json};
  let triActuel = {{ colonne: "jours", sens: 1 }};

  function libelleEcheance(jours) {{
    if (jours === null) return "Échéance inconnue";
    if (jours < 0) return "Échéance dépassée";
    if (jours === 0) return "Échéance aujourd'hui";
    if (jours === 1) return "Échéance demain";
    return "Dans " + jours + " j";
  }}

  function classeEcheance(jours) {{
    if (jours === null) return "neutre";
    if (jours < 0) return "depassee";
    if (jours <= 15) return "urgent";
    return "actif";
  }}

  function echapperHtml(texte) {{
    // CORRIGÉ LE 27/06/2026 après un test DOM réel (jsdom) ayant révélé
    // une vraie vulnérabilité : l'ancienne implémentation (textContent
    // puis innerHTML) échappe correctement < > & pour du CONTENU texte
    // entre balises, mais NE protège PAS contre l'évasion d'un attribut
    // HTML (le guillemet " n'est pas échappé par ce mécanisme). Comme
    // cette fonction est aussi utilisée pour la valeur de l'attribut
    // href, un lien malveillant contenant un guillemet pouvait fermer
    // prématurément l'attribut et injecter un gestionnaire d'événement
    // exécutable (ex. onmouseover="..."). Échappement explicite et
    // complet ici, sûr aussi bien en contenu texte qu'en attribut.
    return String(texte)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }}

  function trierDonnees(liste) {{
    const copie = liste.slice();
    copie.sort((a, b) => {{
      let va = a[triActuel.colonne];
      let vb = b[triActuel.colonne];
      if (triActuel.colonne === "jours") {{
        // Les échéances inconnues (null) et dépassées vont en fin de liste,
        // conformément à la règle de tri du rapport Markdown (cahier des
        // charges, Section 4) : actives croissantes, puis inconnues, puis
        // dépassées en tout dernier.
        const rang = v => v === null ? 1e8 : (v < 0 ? 1e9 + Math.abs(v) : v);
        va = rang(va); vb = rang(vb);
      }} else {{
        va = (va || "").toLowerCase();
        vb = (vb || "").toLowerCase();
      }}
      if (va < vb) return -1 * triActuel.sens;
      if (va > vb) return 1 * triActuel.sens;
      return 0;
    }});
    return copie;
  }}

  function filtrerDonnees(texteRecherche) {{
    if (!texteRecherche) return donnees;
    const q = texteRecherche.toLowerCase();
    return donnees.filter(d =>
      d.titre.toLowerCase().includes(q) ||
      d.source.toLowerCase().includes(q) ||
      d.tags.some(t => t.toLowerCase().includes(q))
    );
  }}

  function rendre() {{
    const texteRecherche = document.getElementById("recherche").value;
    const filtre = filtrerDonnees(texteRecherche);
    const trie = trierDonnees(filtre);
    const corps = document.getElementById("corps-tableau");
    const aucunResultat = document.getElementById("aucun-resultat");
    const compteur = document.getElementById("compteur");

    compteur.textContent = trie.length + " dispositif(s)" + (texteRecherche ? " trouvé(s)" : "");

    if (trie.length === 0) {{
      corps.innerHTML = "";
      aucunResultat.style.display = "block";
      return;
    }}
    aucunResultat.style.display = "none";

    corps.innerHTML = trie.map(d => {{
      const lien = d.lien ? `<a href="${{echapperHtml(d.lien)}}" target="_blank" rel="noopener">${{echapperHtml(d.titre)}}</a>` : echapperHtml(d.titre);
      const tags = d.tags.map(t => echapperHtml(t)).join(" · ");
      return `<tr>
        <td class="titre-cell">${{lien}}<div class="tags">${{tags}}</div></td>
        <td><span class="echeance-badge ${{classeEcheance(d.jours)}}">${{libelleEcheance(d.jours)}}</span></td>
        <td><span class="source-badge">${{echapperHtml(d.source)}}</span></td>
      </tr>`;
    }}).join("");
  }}

  document.getElementById("recherche").addEventListener("input", rendre);

  document.querySelectorAll("th[data-tri]").forEach(th => {{
    const declencher = () => {{
      const colonne = th.getAttribute("data-tri");
      if (triActuel.colonne === colonne) {{
        triActuel.sens *= -1;
      }} else {{
        triActuel = {{ colonne, sens: 1 }};
      }}
      rendre();
    }};
    th.addEventListener("click", declencher);
    th.addEventListener("keydown", e => {{
      if (e.key === "Enter" || e.key === " ") {{ e.preventDefault(); declencher(); }}
    }});
  }});

  rendre();
</script>

</body>
</html>"""


def ecrire_page_html(
    entrees: list["EntreeCategorisee"],
    sections_techniques_texte: str,
    chemin_sortie: Path,
) -> Path:
    """Génère et écrit la page HTML sur disque. Retourne le chemin écrit."""
    contenu = generer_page_html(entrees, sections_techniques_texte)
    chemin_sortie.parent.mkdir(parents=True, exist_ok=True)
    chemin_sortie.write_text(contenu, encoding="utf-8")
    return chemin_sortie
