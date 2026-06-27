# VEILLE-FI — Référentiel des sources officielles de financement

**⚠️ Document de référence prioritaire : `CAHIER_DES_CHARGES.md`**
Ce README documente la partie technique (sources, structure des fichiers).
Pour le périmètre fonctionnel, les règles de catégorisation, le format de
sortie, l'automatisation et les exclusions explicites du projet, voir
`CAHIER_DES_CHARGES.md` — c'est le document qui prime en cas de divergence.

**Fichier source de vérité des sources :** `sources.json` (même répertoire)
**Fiche technique complémentaire :** `api_aides_territoires.json` (même répertoire)
**Dernière mise à jour manuelle :** 24/06/2026
**Mode de collecte retenu :** scraping HTML direct pour la majorité des sources ; **API REST publique pour Aides-territoires**, dont l'existence a été confirmée et documentée (voir section 5).

---

## 1. Objectif du module

Ce référentiel liste les sites officiels où sont publiées les aides publiques mobilisables par la Commune de Saint-Benoît (et, par extension, la CIREST et la SPL Estival), tous échelons confondus : État, Europe, Région Réunion, Département de La Réunion, organismes nationaux, et désormais organismes de protection sociale (CAF).

**Rappel du principe directeur (Section 1 du cahier des charges, révisée le 24/06/2026)** : l'outil sert les élus de la majorité (adjoints + conseillers délégués) dans une logique de recherche active — identifier les cofinancements mobilisables pour un projet qu'ils portent, puis orienter les services administratifs vers les bons dispositifs à instruire. Le document reste cherchable librement (Ctrl+F) plutôt que classé en sections fixes par service.

Il est conçu pour être **consommé automatiquement** par un script de scraping dans VEILLE-FI, qui doit lire `sources.json`, itérer sur chaque entrée, récupérer la page, en extraire les dispositifs/appels à projets pertinents, les catégoriser sans en exclure aucun, et produire un rapport.

VEILLE-FI reste un outil **indépendant de PROFS v2** — ce référentiel ne doit pas être fusionné avec les fichiers de simulation financière.

---

## 2. Structure du fichier `sources.json`

Chaque source comporte :

| Champ | Rôle |
|---|---|
| `id` | identifiant stable, utilisé comme clé dans les logs/rapports VEILLE-FI |
| `echelon` | État, Europe, Région, Département, organisme |
| `url_a_scraper` | URL de départ pour le scraper |
| `type_acces` | `scraping_html` pour toutes les sources actuellement |
| `frequence_veille_recommandee` | cadence de passage du scraper |
| `thematiques_prioritaires` | mots-clés pour filtrer/scorer la pertinence pour Saint-Benoît |
| `structure_page_constatee` | notes sur le DOM observé manuellement — **à vérifier et corriger au premier run**, car non garanti stable |
| `priorite` | 1 = à scraper en premier (chaque passage), 4 = veille de fond ponctuelle |

⚠️ **Important — limite de cette livraison :** je n'ai pas pu inspecter le DOM brut (classes CSS, balises exactes) des sites cibles ; je n'ai eu accès qu'au texte nettoyé des pages. Le champ `structure_page_constatee` donne donc une description fonctionnelle, pas des sélecteurs CSS prêts à l'emploi. **La première tâche de Claude Code sur ce module doit être d'inspecter le HTML réel de chaque `url_a_scraper`** (via `requests.get()` + impression du HTML brut, ou `httpx`) avant d'écrire les sélecteurs `BeautifulSoup`.

---

## 3. Liste des sources (vue lisible)

### Multi-financeurs
- **Aides-territoires** — API REST : https://aides-territoires.beta.gouv.fr/api/aids/?version=1.1
  Plateforme pivot (ANCT) agrégeant État + Europe + organismes + collectivités, ~3000 dispositifs de ~600 porteurs. **Une API REST publique existe, en lecture seule, sans authentification, sous Licence Ouverte v2.0 (Etalab).** Voir `api_aides_territoires.json` pour le détail complet : champs disponibles, stratégie de filtrage, limites. C'est désormais le mode de collecte retenu pour cette source, le scraping de `/programmes/` ne servant plus que de repli en cas d'indisponibilité de l'API.

### État
- **Préfecture de La Réunion** — https://www.la-reunion.gouv.fr (DETR, DSIL, fonds vert)

### Europe
- **Europe en France** — https://www.europe-en-france.gouv.fr/fr/appels-a-projets (FEDER, FEADER, FSE+, Interreg — niveau national)

### Région Réunion
- **Appels à projets Région** — https://regionreunion.com/aides-services/appels-a-projets/
  C'est aussi via cette même page que transitent les AAP/AMI du programme FEDER-FSE+ Réunion 2021-2027 dont la Région est autorité de gestion.

### Département de La Réunion
- https://www.departement974.fr — rubrique précise à confirmer au premier run

### Organismes nationaux (priorité secondaire)
- **ADEME** — aides-financieres collectivités (transition écologique)
- **Banque des Territoires** — ingénierie et prêts
- **CEREMA** — normes techniques (utile pour le dossier aires de jeux CE/EN 1176, pas pour la veille de financement)

---

## 4. Recommandations d'implémentation pour Claude Code

1. **Respect des sites** : un seul GET par page par passage, `User-Agent` identifiable, pas de parallélisation agressive sur un même domaine, respecter un éventuel `robots.txt`.
2. **Robustesse** : chaque source doit logguer trois états distincts — `succès` / `échec réseau` / `échec parsing (sélecteur introuvable)`. Le troisième cas signale que la structure du site a changé et doit déclencher une alerte visible pour Xavier plutôt qu'un échec silencieux.
3. **Déduplication** : conserver un hash ou identifiant (titre + URL fiche) des dispositifs déjà vus pour ne signaler que les nouveautés ou échéances approchantes.
4. **Scoring de pertinence** : utiliser `thematiques_prioritaires` pour prioriser l'affichage (ex. aires de jeux/équipements, voirie rurale Hauts, ingénierie financière, FEADER), sans exclure le reste.
5. **Échéances** : pour Région Réunion notamment, la date limite de dépôt est dans la fiche détaillée, pas dans la liste — prévoir un second niveau de fetch par appel à projets retenu.
6. **Évolutivité** : ce fichier `sources.json` est conçu pour être complété au fil du temps (ajout d'une source = ajout d'un objet dans le tableau `sources`), sans toucher au code du scraper si celui-ci est bien écrit de façon générique.

---

## 5. Zoom — API Aides-territoires (mode de collecte retenu pour cette source)

Contrairement aux autres sources de ce référentiel, **Aides-territoires expose une API REST publique** que j'ai pu confirmer directement :

- **Endpoint :** `https://aides-territoires.beta.gouv.fr/api/aids/?version=1.1`
- **Format :** JSON paginé standard (`count`, `next`, `previous`, `results`)
- **Auth :** aucune authentification nécessaire pour une lecture simple
- **Licence :** Licence Ouverte v2.0 (Etalab) — réutilisation libre sous réserve de mention de paternité et de date de mise à jour
- **Champs clés pour VEILLE-FI :** `perimeter` (périmètre géographique), `targeted_audiences` (public visé, ex. Communes/EPCI), `submission_deadline` (échéance), `date_updated` (pour la déduplication entre deux passages)

**Ce qui reste à vérifier au premier run du script** (je n'ai pas pu le confirmer avec certitude depuis cet environnement) : les paramètres de filtrage acceptés directement par l'endpoint (par périmètre géographique notamment). L'interface de recherche web utilise des paramètres comme `?targeted_audiences=epci`, qui correspondent aux noms de champs JSON — c'est une piste forte, mais Claude Code doit la tester en conditions réelles avant de s'y fier pour la production. À défaut, la stratégie de repli documentée dans `api_aides_territoires.json` consiste à paginer l'ensemble des résultats et filtrer côté client sur les champs `perimeter` et `targeted_audiences`.

**Important — complémentarité, pas remplacement :** cette API ne couvre que ce qui est référencé sur Aides-territoires. Les appels à projets très récents ou très locaux de la Région Réunion ou du Département 974 peuvent apparaître sur leur site source avant (ou sans jamais) être repris sur Aides-territoires. Le scraping direct de ces sites reste donc nécessaire en complément.

---

## 6. Fichiers de code livrés

**Conformité : tous ces fichiers implémentent CAHIER_DES_CHARGES.md (24/06/2026).**

| Fichier | Rôle |
|---|---|
| `client_aides_territoires.py` | Client de l'API REST Aides-territoires : pagination, tentative de filtrage serveur, filet de sécurité de filtrage côté client sur `perimeter`/`targeted_audiences`. |
| `ademe_rss.py` | **Client du flux RSS ADEME** (découvert le 24/06/2026, voir section 7quater) : parse `collectivites/rss/appels-a-projet`, filtre côté client sur la pertinence Réunion/national. Nécessite la librairie `feedparser`. Inclut son propre mode diagnostic (`python3 ademe_rss.py --diagnostic`) pour vérifier en conditions réelles quels champs RSS contiennent la mention de région. |
| `scraper_html.py` | Scraper générique pour les sources HTML listées dans `sources.json`. Inclut un **mode diagnostic** (`--diagnostic`) à lancer en premier sur chaque source pour vérifier que l'extraction générique correspond à la structure réelle. |
| `region_reunion_detail.py` | **Fetch de second niveau** : ouvre chaque fiche détaillée d'appel à projets Région Réunion pour en extraire la date limite de dépôt. **Limite vérifiée sur deux fiches réelles** : fonctionne quand la date est écrite en clair dans le texte, mais reste vide quand la deadline n'existe que dans un PDF téléchargeable (cas réel observé : Guétali 2025/2026). N'est appelé que sur les nouveautés détectées, pas systématiquement, par courtoisie réseau. Contient aussi `PATRON_OUVERT_JUSQU_AU`, réutilisé par `ademe_rss.py`. |
| `generer_html.py` | **Génération de la page HTML publique** (ajouté le 27/06/2026, diffusion via GitHub Pages — voir Section 4/5 du cahier des charges). Page autonome (CSS/JS inclus), tableau filtrable/triable côté navigateur, reconstruit l'intégralité du cache (pas seulement les nouveautés). Deux vulnérabilités XSS trouvées et corrigées via test DOM réel (jsdom) — voir `test_generer_html.py` et l'historique du cahier des charges. |
| `test_generer_html.py` | Tests Python (sans dépendance Node) couvrant les deux vulnérabilités XSS corrigées dans `generer_html.py`. |
| `.github/workflows/veille-hebdomadaire.yml` | **Workflow GitHub Actions** : exécute `run_veille.py --force` chaque lundi, committe `docs/`/`cache/`/`rapports/`, ce qui déclenche la publication GitHub Pages. Configuration manuelle requise une fois dans les paramètres du dépôt (Settings → Pages → dossier `/docs`). |
| `categorisation.py` | **Module de catégorisation thématique** (remplace l'ancien `scoring.py`, retiré du périmètre suite à la révision du cahier des charges). N'EXCLUT JAMAIS rien — étiquette chaque entrée avec une ou plusieurs des 8 thématiques de la Section 3 (dont "Agriculture / Ruralité", ajoutée le 24/06/2026), avec repli explicite vers "Autre / Non catégorisé". Le seul tri qui subsiste est par urgence d'échéance, pas par pertinence politique. Matching par mot entier (pas sous-chaîne) depuis la correction du 24/06/2026. |
| `cache_dedup.py` | Cache JSON local + logique de déduplication entre deux passages (par `id` pour l'API, par hash titre+lien pour le HTML). Détecte aussi les mises à jour de contenu via `date_updated` côté API. |
| `run_veille.py` | **Point d'entrée principal** — implémente la règle de déclenchement par âge (Section 5 : collecte automatique si le dernier rapport a plus de 7 jours), orchestre les collectes, déclenche le fetch de second niveau ciblé, catégorise sans filtrer, écrit un rapport Markdown conforme au format de la Section 4. |
| `test_logique_interne.py` | Tests hors réseau validant la logique de dédup et d'extraction sur des données simulées. |
| `test_integration_complete.py` | **Test de bout en bout** avec mocks réseau complets, validant la conformité au cahier des charges : présence de toutes les thématiques même vides, absence d'exclusion, règle de déclenchement par âge (rapport récent → pas de collecte ; rapport ancien → collecte). |

### Fichiers archivés (non livrés, conservés en traçabilité interne uniquement)

Suite à la révision du périmètre (Section 1 du cahier des charges — l'outil doit servir tous les services, pas filtrer pour Xavier), les fichiers suivants de la version précédente ont été retirés du périmètre livré : l'ancien `scoring.py` (logique de score/filtre remplacée par `categorisation.py`) et l'ancien `run_veille.py` (format de rapport non conforme à la Section 4 actuelle). Ne pas les réintégrer sans relecture — ils ne correspondent plus au cahier des charges validé.

### Limite assumée et explicite de cette livraison

Je n'ai pas pu exécuter ce code contre les vrais sites depuis cet environnement : mon accès réseau pour l'exécution de code est restreint à une liste blanche de domaines (PyPI, npm, GitHub...) qui ne couvre pas `aides-territoires.beta.gouv.fr`, `regionreunion.com`, `caf.fr`, etc. J'ai donc :
- testé la logique pure (dédup, cache, extraction générique, catégorisation, parsing d'échéance, règle de déclenchement par âge) sur des données simulées et sur de vrais extraits de pages récupérés via l'outil de recherche web — ces tests passent ;
- testé le pipeline complet de bout en bout avec des appels réseau entièrement mockés, ce qui a permis de détecter et corriger un vrai bug de chevauchement de mots-clés (une entrée parlant d'équipements de jeux en "milieu rural" tombait à tort dans "Environnement" au lieu de "Voirie/Aménagement" à cause du mot-clé générique "rural" partagé entre les deux catégories) ;
- **mais pas** vérifié la connectivité réelle ni la structure HTML réelle des pages Préfecture / ADEME / Banque des Territoires / CAF Réunion — pour celles-ci, aucune fiche n'a pu être inspectée. **Département 974 a en revanche été vérifié et corrigé le 24/06/2026** (voir section 7bis) : l'URL initiale était imprécise (page d'accueil au lieu de la page réelle des appels à projets), et les patrons de date ont été élargis pour couvrir 3 formats réels rencontrés (jour ordinal "1er", format JJ/MM/AAAA, mention "Au plus tard le").

**Première action à mener par Claude Code (ou toi) en conditions réelles :**
```bash
python3 run_veille.py --diagnostic
```
Ce mode imprime un échantillon du HTML brut de chaque source HTML et le nombre de candidats trouvés par l'extraction générique, pour permettre d'ajuster rapidement si besoin avant tout passage en production.

---

## 7. Découverte importante : les échéances ne sont pas toujours dans le texte de la page

En récupérant deux vraies fiches Région Réunion pour construire le fetch de second niveau, j'ai constaté que **le site n'est pas homogène** :

- Sur l'AAP FEDER-NDICI, la date limite est écrite en clair : *« Date limite de remise des propositions : 28 novembre 2025 à 12h00 »* — extractible de façon fiable.
- Sur l'AAP Guétali 2025/2026, **aucune date limite n'apparaît dans le texte de la page** — elle n'existe que dans les PDF téléchargeables ("Télécharger l'AAP Arts Visuels"), hors de portée d'un parsing texte/HTML.

`region_reunion_detail.py` traite donc cette extraction comme un **best-effort explicite** : quand le patron structuré est absent, le résultat retourne `trouve=False` plutôt qu'une fausse certitude. Le rapport final reflète cette incertitude plutôt que de la masquer.

---

## 7bis. Département 974 — vérifié et corrigé le 24/06/2026

**L'URL initiale était fausse** (pointait sur la page d'accueil du site). La bonne URL, identifiée via le menu réel du site, est :

```
https://www.departement974.fr/avis-appels-projets-enquetes-publiques
```

Cette page a été inspectée directement (fetch réel) : flux actif (items datés mars-juin 2026 au moment de la vérification), site Drupal 9, structure en liste d'articles avec vignette + tag thématique + date + titre + court résumé. **Point clé** : le résumé contient souvent la date limite en clair, ce qui permet de l'extraire directement depuis la page de liste, sans avoir besoin d'ouvrir chaque fiche détaillée (contrairement à Région Réunion).

Trois formats de date réels ont été identifiés et sont maintenant gérés par `region_reunion_detail.py` (utilisé aussi par `scraper_html.py` pour l'extraction depuis la liste) :
- `"Date limite : 1er juin 2026 à 23h59"` — jour ordinal "1er"
- `"Clôture de l'appel à projets : 12/05/2026 à 15h00"` — format numérique JJ/MM/AAAA
- `"Au plus tard le 23 janvier 2026"` — formulation alternative

**Signal de fiabilité supplémentaire observé** : les appels déjà clos sont explicitement préfixés `(Clôturer)` ou `(Clôturé)` dans leur titre.

**Page écartée du périmètre de scraping** : `/aide-aux-communes` a aussi été inspectée mais ne contient que des articles d'actualité 2018-2019 sur les signatures historiques du Pacte de Solidarité Territoriale — utile pour comprendre le dispositif, mais pas un flux à surveiller en continu.

---

## 7ter. Préfecture de La Réunion — vérifiée et corrigée le 24/06/2026

**Le domaine initial était faux** : `la-reunion.gouv.fr` n'est pas le bon domaine. Le bon domaine est :

```
https://www.reunion.gouv.fr
```

La bonne page à scraper est `/Publications/Appels-a-projets` (identifiée via le menu réel du site). Vérifiée par fetch direct : flux actif (dernier item publié le 01/06/2026 au moment de la vérification), site sous Design System de l'État (DSFR), structure propre en liste d'articles avec pagination par offset numérique classique.

**Différence importante avec Département 974** : ici, la page de liste contient la date de **publication** de l'article, mais PAS la date limite de dépôt — celle-ci n'apparaît que dans la fiche détaillée (comme pour Région Réunion). Le fetch de second niveau (`region_reunion_detail.py`) reste donc nécessaire pour cette source ; il a été ajouté à `SOURCES_AVEC_FETCH_SECOND_NIVEAU` dans `run_veille.py`.

Le patron `"au plus tard le 13 mars 2026"` rencontré sur une fiche DSIL réelle est déjà couvert par le patron `au_plus_tard` ajouté pour Département 974 — aucune modification de code supplémentaire n'a été nécessaire.

**Ressource complémentaire repérée mais pas encore intégrée** : la page liste un article "Calendrier des appels à projets de l'État à La Réunion en 2026", potentiellement une vue de synthèse utile — à vérifier manuellement pour l'instant.

**Bonus découvert en vérifiant la page DETR/DSIL** : il existe un lien de dépôt spécifique à l'arrondissement de Saint-Benoît (`demarche.numerique.gouv.fr/commencer/demande-de-subvention-detr-dsil-saint-benoit`) — pertinent à connaître même s'il ne s'agit pas d'une source à scraper en tant que telle (formulaire de dépôt, pas un flux d'actualité).

---

## 7quater. ADEME, Banque des Territoires, CAF Réunion — vérifiées le 24/06/2026

Les 3 dernières sources non vérifiées ont été inspectées par fetch réel. Résultats très différents les uns des autres — c'est précisément l'intérêt de vérifier plutôt que de supposer.

### ADEME — meilleure découverte de toute la session de vérification

L'URL initiale (`/collectivites/aides-financieres`) menait à une page d'introduction, pas à la liste. La vraie page catalogue (`/collectivites/aides-financieres/catalogue`) est excellente : 60 dispositifs au moment de la vérification, **filtre géographique natif par URL** (`?localisation[La Réunion]=La Réunion` — confirmé fonctionnel, contrairement à Aides-territoires où ce filtre n'a jamais pu être confirmé), statut et date limite en clair pour chaque item (`"Ouvert jusqu'au JJ mois AAAA"`).

Mais surtout : **un vrai flux RSS officiel et dédié existe**, mis à jour quotidiennement selon la documentation du site :
```
https://agirpourlatransition.ademe.fr/collectivites/rss/appels-a-projet
```
C'est la seule source de ce projet, avec l'API Aides-territoires, à ne pas dépendre d'un scraping HTML fragile. Un nouveau module `ademe_rss.py` a été créé pour l'exploiter (nécessite la librairie `feedparser`, ajoutée à `demarrer.sh`). Limite assumée : le contenu exact des champs RSS (où se trouve la mention de région — titre, résumé, tags ?) n'a pas pu être inspecté en détail depuis cet environnement, le fetch ayant renvoyé du XML que l'outil de récupération ne pouvait afficher en texte. Le mode `python3 ademe_rss.py --diagnostic` doit être lancé en conditions réelles pour le confirmer.

### Banque des Territoires — corrigée mais moins prometteuse que prévu

L'URL initiale (`/nos-offres`) était imprécise. La vraie page (`/france-2030/appels-projets-en-cours`) est une vraie liste avec statuts explicites, mais **aucune date limite n'apparaît dans la liste** et **aucun item visible dans l'échantillon vérifié n'était spécifique à La Réunion** (vus : Auvergne-Rhône-Alpes, Bretagne, Martinique, Mayotte, Polynésie française...). Un flux RSS existe (`/flux-rss`) mais c'est le fil d'actualité Localtis (presse territoriale généraliste), pas un flux d'appels à projets — à ne pas confondre avec la découverte ADEME. Priorité abaissée de 3 à 4 en conséquence.

### CAF Réunion — constat structurel important, source repensée

Contrairement à l'hypothèse initiale, **il n'existe pas de page-liste centralisée avec dates** pour les appels à projets CAF Réunion. La page `/partenaires-locaux` est un menu de navigation thématique vers des fiches statiques individuelles. La page nationale `/dispositifs-partenaires` est un catalogue permanent de dispositifs stables (Centre social, Assistant maternel...), pas des appels à projets datés — à ne surtout pas confondre avec un flux de nouveautés malgré son apparence de liste paginée. La vraie source de nouveauté semble être les **Lettres aux partenaires**, publiées en PDF tous les 2-3 mois. La source a été repensée pour scraper `/partenaires-locaux/actualites-partenaires` (détection de sortie d'une nouvelle lettre) plutôt qu'un flux d'appels à projets qui n'existe pas sous cette forme. Fréquence abaissée à mensuelle, priorité à 3.

---

## 7quinquies. Premier diagnostic en conditions réelles côté Claude Code

Après remplacement d'un fichier `sources.json` périmé sur le disque (cause d'un faux diagnostic initial), le vrai test en conditions réseau réelles a confirmé : Préfecture, Département 974, Banque des Territoires, CAF Réunion fonctionnels (HTTP 200), et le flux RSS ADEME actif avec 209 entrées. Trois ajustements ont suivi ce diagnostic :

- **Europe en France** : URL corrigée vers `/fr/appels-projets`. Limite découverte : le contenu de la liste se charge en JavaScript côté client, un simple `requests.get()` ne récupère que le squelette de la page. À traiter plus tard (rendu JS ou recherche d'une API/flux alternatif) si cette source s'avère nécessaire.
- **CEREMA** : URL corrigée vers `/fr/mots-cles/appel-projet`. Contenu constaté majoritairement obsolète (2018-2024, un seul item 2026 dans l'échantillon) — à utiliser avec un filtre de fraîcheur strict, pas comme un flux actif.
- **Région Réunion (403 anti-bot)** : corrigé en remplaçant le User-Agent explicite `"VEILLE-FI/1.0 (...)"` par un User-Agent de navigateur standard dans les 4 modules concernés (`scraper_html.py`, `client_aides_territoires.py`, `region_reunion_detail.py`, `ademe_rss.py`), avec ajout d'en-têtes `Accept`/`Accept-Language`. Si le 403 persiste malgré ce changement, le blocage repose probablement sur un autre signal (fréquence, fingerprint TLS, JS requis) qu'il faudra investiguer séparément.
- **Bruit de l'extraction générique** (87 candidats sur Département 974, 157 sur CEREMA) : `_extraire_items_generique()` dans `scraper_html.py` supprime désormais les blocs `<nav>`, `<header>`, `<footer>` avant extraction, et le seuil de longueur minimale du texte est passé de 8 à 15 caractères. Un nouveau test (`test_filtre_structurel_nav_header_footer`) valide ce comportement sur un cas reproduisant le bruit constaté.
- **Filtre géographique ADEME trop strict** : sur les 210 entrées du flux RSS, seuls 5 AAP étaient retenus, tous explicitement "Outre-mer". Claude Code a justement remarqué que cette logique risquait d'exclure à tort les AAP nationaux génériques (sans restriction géographique) si leur résumé RSS ne mentionne aucune région. Corrigé : `_perimetre_concerne_reunion()` dans `ademe_rss.py` n'exclut désormais que les AAP mentionnant EXCLUSIVEMENT une autre région précise (ex. "Nouvelle-Aquitaine uniquement") ; en l'absence de toute mention géographique, l'inclusion est le comportement par défaut.

---

## 8. Prochaines étapes suggérées

- [ ] Tester en conditions réelles les paramètres de filtre de l'API Aides-territoires (`perimeter`, `targeted_audiences`) avant de coder le filtrage définitif — voir `api_aides_territoires.json`
- [x] **Les 10 sources ont été vérifiées par fetch réel le 24/06/2026** (voir sections 7bis, 7ter, 7quater) — toutes les URLs de `sources.json` correspondent désormais à des pages réellement inspectées, pas à des hypothèses
- [ ] Lancer `python3 run_veille.py --diagnostic` ET `python3 ademe_rss.py --diagnostic` en conditions réseau réelles côté Claude Code pour confirmer que l'extraction générique fonctionne correctement sur chaque source — la vérification de structure faite ici ne remplace pas un test du code réel contre les sites
- [ ] Confirmer la rubrique exacte sur departement974.fr et la-reunion.gouv.fr
- [ ] Faire relire et enrichir les mots-clés de `categorisation.py` par Xavier au fil des premiers passages réels
- [ ] Envisager, si le volume de PDF non capturés par `region_reunion_detail.py` s'avère important, une extraction de texte PDF (lib `pypdf` déjà présente dans l'environnement skills) pour récupérer les échéances qui n'existent que dans les pièces jointes
- [ ] Définir le format de diffusion final du rapport (lecture manuelle du `.md` généré ? envoi automatique par email ? affichage dans une mini-page HTML locale ?)

