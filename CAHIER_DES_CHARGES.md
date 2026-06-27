# Cahier des charges VEILLE-FI — version figée

**Statut : VALIDÉ avec Xavier, le 24/06/2026. Ce document est la référence unique.**

**Instruction pour tout agent (Claude Code ou autre) qui implémente ce projet :**
Implémente exactement ce qui est décrit ici, rien de plus. En cas de doute ou
d'ambiguïté, pose la question avant de coder plutôt que d'improviser une
solution alternative (interface web, base de données, authentification, etc.).
La section 6 liste explicitement ce qui est hors-périmètre — elle existe
précisément pour éviter les réinterprétations libres constatées par le passé
sur ce projet.

---

## 1. Périmètre fonctionnel

**RÉVISION DU 24/06/2026 (fin de session)** : le périmètre fonctionnel a été
revu en profondeur. La version précédente de cette section (destinée à tous
les services administratifs, diffusée au DGS/DGF) est remplacée par ce qui
suit. Voir l'historique en fin de document pour la trace de ce changement.

**Objectif** : VEILLE-FI aide les élus de la majorité (adjoints et conseillers
délégués) de Saint-Benoît à identifier les cofinancements mobilisables pour
les projets qu'ils portent, et à orienter ensuite les services administratifs
vers les bons dispositifs à instruire.

**Principe directeur — IMPORTANT** : l'outil sert un usage de **recherche
active**, pas de lecture passive d'un rapport exhaustif. Un élu qui a un
projet précis en tête (ex. "refaire l'aire de jeux de tel quartier") doit
pouvoir chercher un mot-clé dans le document et trouver directement les
dispositifs compatibles — l'outil ne classe pas par service administratif,
il reste cherchable librement par sujet.

**Diffusion** : tous les élus de la majorité (adjoints + conseillers
délégués). Le DGS/DGF n'est plus le destinataire principal — ils peuvent
continuer à recevoir le document si Xavier le souhaite, mais ce n'est plus
la cible de conception.

**Ce que l'outil fait** :
- Interroge les sources listées en section 2
- Détecte ce qui est nouveau ou mis à jour depuis le dernier passage
- Étiquette chaque nouveauté avec des mots-clés thématiques visibles dans le
  texte (pour rester cherchable au Ctrl+F), sans les ranger dans des
  sections fixes (section 3)
- Produit un seul fichier Markdown, trié par urgence d'échéance (section 4)
- Se met à jour automatiquement si nécessaire à l'ouverture (section 5)

**Ce que l'outil ne fait PAS** (voir aussi section 6) :
- Ne remplit pas de dossier de candidature
- Ne garantit pas l'exhaustivité réelle (limite des sources elles-mêmes)
- Ne notifie pas activement par email/SMS dans cette version
- **Ne fait PAS de raisonnement inverse** (identifier la typologie de projet
  qui maximiserait les financements obtenus) — cet axe a été explicitement
  écarté du périmètre de VEILLE-FI le 24/06/2026, jugé trop incertain
  méthodologiquement pour être présenté à des élus comme une recommandation
  fiable (un simple comptage de mots-clés RSS ne suffit pas à fonder une
  décision de pilotage de projets). Si cet axe est développé un jour, ce
  sera comme **un outil séparé, à usage strictement personnel de Xavier**,
  pas comme une extension de VEILLE-FI.

---

## 2. Sources à surveiller

10 sources, toutes vérifiées par fetch réel au 24/06/2026. La structure
technique détaillée de chaque source est dans `sources.json` et
`api_aides_territoires.json` — ce tableau est un résumé de pilotage.

| ID | Nom | Échelon | Mode de collecte | Statut |
|---|---|---|---|---|
| `aides_territoires` | Aides-territoires | multi-financeurs | API REST | ❌ **EN PANNE — accès JWT requis depuis le 24/06/2026**, voir section dédiée ci-dessous |
| `prefecture_reunion` | Préfecture de La Réunion — Appels à projets | État | Scraping HTML | ✅ Domaine corrigé (reunion.gouv.fr) ; date limite hors liste, fetch de second niveau requis |
| `europe_en_france` | Europe en France | Europe | Scraping HTML | ⚠️ Existence confirmée, structure détaillée non vérifiée |
| `region_reunion_aap` | Région Réunion — Appels à projets | Région | Scraping HTML | ❌ **EN PANNE — 403 anti-bot, contournement non tenté par décision (voir section 2ter)** |
| `region_reunion_feder` | Région Réunion — FEDER-FSE+ | Europe via Région | Scraping HTML | Même page que ci-dessus |
| `departement_974` | Département de La Réunion — Avis, AAP | Département | Scraping HTML | ✅ URL corrigée ; date limite déjà dans la liste |
| `ademe` | ADEME — Agir pour la transition (collectivités) | national | **Flux RSS** | ✅ Flux RSS officiel dédié confirmé, mis à jour quotidiennement ; filtre géographique URL natif confirmé sur la page web |
| `banque_des_territoires` | Banque des Territoires — AAP France 2030 | national | Scraping HTML | ✅ URL corrigée ; aucune date limite en liste, pertinence Réunion à confirmer sur la durée |
| `caf_reunion` | CAF Réunion — Lettres aux partenaires | protection sociale | Scraping HTML | ✅ Pas de flux structuré comme espéré — repensée vers la détection de nouvelle Lettre PDF |
| `cerema` | CEREMA | national | Scraping HTML | ⚠️ Existence confirmée, structure détaillée non vérifiée ; hors périmètre financement strict |

**Source explicitement exclue** : le CNFPT n'est PAS une source pertinente
pour cet outil. Ce n'est pas un système d'appels à projets mais un système de
cotisation obligatoire avec contrepartie en formations — vérifié par recherche
le 24/06/2026. Ne pas le réintégrer sans nouvelle vérification factuelle.

**Règle pour toute nouvelle source ajoutée plus tard** : vérifier son existence
réelle et son statut (authentification requise ou non, structure HTML
constatée ou non, existence d'une API/flux RSS plus fiable) avant de l'ajouter
au tableau ci-dessus — ne jamais supposer.

**Les 10 sources sont désormais vérifiées par fetch réel** (mise à jour du
24/06/2026, suite session) : Europe en France avait une URL fausse (corrigée
vers `/fr/appels-projets`, mais sa liste se charge en JavaScript — limite à
lever séparément) ; CEREMA a une page dédiée correcte mais un contenu très
majoritairement obsolète (2018-2024), à utiliser avec un filtre de fraîcheur
strict plutôt qu'une attente de flux actif.

---

## 2bis. Aides-territoires — accès API en panne (token JWT requis)

**Statut confirmé le 24/06/2026 par test direct (curl, avec et sans User-Agent
personnalisé — résultat identique dans les deux cas) :** l'API Aides-territoires
retourne désormais systématiquement `HTTP 401` avec le message `"JWT Token not
found"`, quel que soit le code appelant.

**Ce n'est PAS un bug du code de VEILLE-FI.** Ce n'est pas non plus un problème
de version d'API (`1.1` vs `1.4` — testé, aucune différence) ni de User-Agent.
C'est un changement de la politique d'accès côté plateforme Aides-territoires,
cohérent avec leur annonce officielle de mars 2026 recentrant le service sur les
seules collectivités territoriales et établissements publics.

**Démarche à mener pour rétablir l'accès (hors code, à faire par Xavier ou un
service de la mairie) :**
1. Créer un compte sur https://aides-territoires.beta.gouv.fr si la mairie n'en
   a pas déjà un.
2. Faire une demande d'accès à l'API en tant que réutilisateur de données
   (contact : aides-territoires@incubateur.anct.gouv.fr selon la documentation
   officielle).
3. Récupérer le token JWT délivré.
4. Une fois le token obtenu, revenir vers ce projet pour intégrer
   l'authentification (`Authorization: Bearer <token>`) dans
   `client_aides_territoires.py` — **ne pas stocker le token en clair dans
   `sources.json` ou tout fichier versionné**, prévoir un fichier de
   configuration local non partagé (ex. `.env` ignoré par tout futur dépôt Git).

**En attendant**, `client_aides_territoires.py` détecte ce cas précis dès le
premier appel et produit un message d'erreur explicite et actionnable dans le
rapport, plutôt qu'un échec réseau opaque — voir `_diagnostiquer_acces_api()`.
Le reste du pipeline (les 9 autres sources) continue de fonctionner
normalement : cette panne ne bloque pas le projet, elle réduit seulement sa
couverture en attendant la régularisation de l'accès.

---

## 2ter. Région Réunion — blocage anti-bot (403), décision de ne pas contourner

**Statut au 24/06/2026 :** le scraping de Région Réunion (`region_reunion_aap`
et `region_reunion_feder`) retourne systématiquement `HTTP 403 Forbidden`,
malgré le remplacement du User-Agent explicite par un User-Agent de navigateur
standard avec en-têtes `Accept`/`Accept-Language` (cf. historique). Cette
correction, qui a résolu d'autres blocages superficiels par le passé, ne
suffit pas ici — le blocage repose probablement sur un signal plus robuste
(fréquence de requêtes, fingerprint TLS/HTTP2, JavaScript requis, ou une
protection commerciale type Cloudflare/Datadome).

**DÉCISION ACTÉE : on ne va pas plus loin techniquement sur ce point.** Les
étapes suivantes qui permettraient théoriquement de contourner ce blocage
(rotation d'adresses IP, résolution automatisée de CAPTCHA, simulation de
comportement humain pour tromper un système anti-bot, navigateur headless
imitant un humain) sont explicitement HORS PÉRIMÈTRE de ce projet. Certaines
seraient contraires aux conditions d'utilisation du site ; toutes ajoutent une
complexité et un risque disproportionnés pour un outil de veille interne.

**Comportement retenu** : le rapport signale Région Réunion comme
temporairement inaccessible par scraping automatique, sans tenter de
contournement technique supplémentaire. **Recommandation pour Xavier** :
vérifier ce site manuellement de façon ponctuelle (la page
`/aides-services/appels-a-projets/` reste consultable normalement dans un
navigateur humain), au moins jusqu'à ce qu'une alternative légitime soit
identifiée (ex. si Région Réunion publie un jour un flux RSS ou une API
comme Aides-territoires ou ADEME).

---

## 3. Mots-clés thématiques (tags cherchables, pas de classement fixe)

**RÉVISION DU 24/06/2026 (fin de session)** : cette section décrivait
auparavant un classement en 8 sections fixes du rapport ("Voirie", "Culture",
etc.), pensé pour des services administratifs scannant chacun leur propre
section. Avec le recentrage sur les élus et l'usage de recherche libre
(section 1), ce classement en sections disparaît du rapport. Les mêmes
mots-clés thématiques restent calculés et utiles, mais affichés comme des
**tags en clair sur chaque ligne** plutôt que comme des titres de section —
ce qui permet à n'importe qui de chercher "agriculture" ou "voirie" au
Ctrl+F et de tomber directement sur les bonnes lignes, peu importe où elles
se trouvent dans le document.

Les mots-clés eux-mêmes (8 groupes thématiques) ne changent pas — seul leur
mode d'affichage change :

1. Voirie / Aménagement / Écarts ruraux
2. Environnement / Transition écologique
3. Agriculture / Ruralité
4. Action sociale / Petite enfance / Parentalité
5. Culture / Sport / Jeunesse
6. Affaires financières / Ingénierie
7. Europe / Coopération régionale
8. Autre / Non catégorisé

Une entrée peut porter plusieurs tags (ex. un AAP de voirie en zone agricole
peut être tagué à la fois "Voirie" et "Agriculture / Ruralité"). Aucune
entrée n'est jamais masquée pour défaut de tag reconnu — celles sans
correspondance restent tagguées "Autre / Non catégorisé", visibles comme
les autres.

**Historique de cette liste** : la catégorie "Agriculture / Ruralité" a été
ajoutée le 24/06/2026, après qu'un premier rapport réel ait montré plusieurs
AAP agricoles sans ambiguïté (apiculture, MAEC, conseil agricole) rattachés
par défaut à "Environnement / Transition écologique" faute de case dédiée.

---

## 4. Format de sortie

**RÉVISION DU 24/06/2026 (fin de session)** : le "Détail par thématique" en
8 sections fixes est retiré. Le rapport est désormais un seul bloc de
nouveautés, trié par urgence, avec les tags thématiques affichés en clair
sur chaque ligne pour rester cherchables au Ctrl+F — voir section 3.

**RÉVISION DU 27/06/2026 (diffusion publique)** : un second format est
ajouté en complément, destiné à la diffusion réelle aux élus — voir
ci-dessous "Format de diffusion (HTML public)". Le format Markdown local
(décrit dans cette section) reste utilisé pour le test/diagnostic et la
consultation locale par Xavier, mais n'est plus le canal de diffusion
principal.

### Format Markdown (local, conservé pour test/diagnostic)

**Type de fichier** : Markdown (`.md`).

**Emplacement** : dossier `rapports/`, un fichier par passage, nommé
`rapport_AAAA-MM-JJ.md`.

**Comportement du terminal** : à la fin de l'exécution, le script affiche
uniquement le chemin complet du fichier généré (ou du dernier rapport existant
si aucune mise à jour n'était nécessaire). Il n'ouvre PAS automatiquement
d'application — c'est à l'utilisateur d'ouvrir le fichier lui-même.

**Structure interne du rapport, dans cet ordre** :
1. En-tête : date du rapport + âge en jours depuis la dernière mise à jour,
   avec un rappel court que le document est cherchable au Ctrl+F par mot-clé
   (thématique, nom de dispositif, source...)
2. Liste unique des nouveautés/mises à jour, triées par urgence d'échéance
   (les plus proches en premier, les échéances dépassées en dernier — jamais
   masquées, juste reléguées en fin de liste). Chaque ligne affiche le titre,
   le lien, la source, l'échéance si connue, et ses tags thématiques en
   clair entre parenthèses (ex. "tags : Voirie / Aménagement, Agriculture /
   Ruralité").
3. Section technique en fin de fichier : statut de chaque source de la
   section 2 (succès / échec réseau / échec parsing / vide), pour que les
   limites du passage soient visibles sans polluer la lecture utile en tête
   de document

### Format de diffusion (HTML public, ajouté le 27/06/2026)

**Type de fichier** : une page HTML autonome (un seul fichier, CSS/JS
inclus), générée par le script et publiée sur GitHub Pages.

**Contenu** : un tableau interactif, filtrable par mot-clé (titre,
thématique, source) en JavaScript côté navigateur — pas de recherche
serveur, tout se passe dans le navigateur de l'élu après chargement de la
page. **Différence importante avec le Markdown local** (décision validée
par Xavier le 27/06/2026) : la page HTML reconstruit l'intégralité du cache
connu (tous les dispositifs jamais détectés), pas seulement les nouveautés
du dernier passage — c'est une vraie page de référence cherchable, pas un
flash d'actualité hebdomadaire. Les dispositifs dont l'échéance est dépassée
depuis plus de 60 jours (`SEUIL_EXCLUSION_HTML_JOURS` dans `run_veille.py`)
sont exclus de l'affichage pour que la page ne grossisse pas indéfiniment ;
ceux dépassés plus récemment, ou sans échéance connue, restent visibles —
cette exclusion porte sur la PRÉSENTATION, jamais sur les données du cache
lui-même (principe de non-exclusion, Section 1, toujours respecté côté
données).

**Public visé** : tous les élus de la majorité, consultation depuis
n'importe quel appareil avec un navigateur, sans rien installer.

**Accès** : URL fixe sur GitHub Pages, à enregistrer une fois en favori par
chaque élu. Contenu public sur internet (cf. section 5 — décision actée sur
la confidentialité).

**Sécurité** : deux vulnérabilités XSS ont été trouvées et corrigées le
27/06/2026 lors de tests DOM réels (jsdom) avant la première publication —
voir l'historique pour le détail. Toute modification future de
`generer_html.py` touchant à l'insertion de données externes (titres/liens
scrapés) dans le HTML ou le JSON embarqué doit être revérifiée avec la même
rigueur (test DOM réel, pas seulement relecture du code).

---

## 5. Automatisation et diffusion

**RÉVISION DU 27/06/2026 (changement d'architecture majeur)** : cette
section décrivait auparavant un déclenchement local (script lancé
manuellement par Xavier sur son poste, avec une règle de fraîcheur à 7
jours). Ce mode reste utilisable pour du test/diagnostic local, mais N'EST
PLUS le mode de fonctionnement principal. **Cause du changement** : les
autres élus de la majorité (destinataires depuis la révision du périmètre,
section 1) n'ont pas Claude Code, Python, ni de compétence technique pour
lancer l'outil eux-mêmes — et n'ont pas vocation à le faire. Il fallait un
mode de diffusion qui ne demande RIEN à installer ni à exécuter côté élus.

**Nouvelle architecture retenue : GitHub Actions + GitHub Pages**
- Le code du projet vit dans un dépôt GitHub (créé par Xavier, qui a déjà un
  compte GitHub).
- **GitHub Actions** exécute automatiquement le script de collecte sur un
  calendrier hebdomadaire, sur les propres serveurs de GitHub — aucune
  machine de la mairie n'a besoin d'être allumée ou de faire quoi que ce
  soit. Gratuit pour un dépôt public.
- Le résultat de la collecte est transformé en une page HTML interactive
  (tableau filtrable, voir section 4) et publié automatiquement sur
  **GitHub Pages**, accessible par une URL fixe
  (`https://<compte>.github.io/<projet>/`).
- Les élus consultent cette URL depuis n'importe quel navigateur (ordinateur
  ou téléphone), sans rien installer, depuis n'importe où.

**Conséquence sur la confidentialité** : le contenu (liste d'aides
publiques et appels à projets) est en accès public sur internet par défaut
avec un dépôt GitHub public. **Validé explicitement par Xavier le
27/06/2026** : ces informations sont publiques par nature (aides publiques),
leur diffusion ouverte ne pose pas de problème.

**Détails d'implémentation concrets (27/06/2026) :**
- Fichier de workflow : `.github/workflows/veille-hebdomadaire.yml`.
  Déclenchement : tous les lundis à 05h00 UTC (≈ 08h00 La Réunion), plus un
  déclenchement manuel possible depuis l'onglet "Actions" du dépôt GitHub
  (`workflow_dispatch`) pour forcer une mise à jour sans attendre le lundi
  suivant.
- Le workflow lance `python3 run_veille.py --force` — le `--force` est
  nécessaire car dans l'environnement GitHub Actions, le concept de "vieux
  rapport local" (section précédente) n'a pas le même sens : on veut une
  collecte à chaque exécution planifiée, pas une vérification de fraîcheur.
- Le workflow committe ensuite `docs/`, `cache/`, et `rapports/` dans le
  dépôt — c'est ce commit qui déclenche la publication GitHub Pages et qui
  permet au cache de déduplication de persister d'une semaine à l'autre
  (sans ce commit, chaque exécution repartirait de zéro et republierait
  tout comme "nouveau").
- **Configuration GitHub Pages à faire une fois, manuellement, dans les
  paramètres du dépôt** : Settings → Pages → Source : "Deploy from a
  branch", branche `main` (ou celle utilisée), dossier `/docs`. Cette étape
  ne peut pas être automatisée par le code — elle se fait dans l'interface
  GitHub.
- `docs/index.html` est le chemin attendu par défaut par cette
  configuration GitHub Pages — voir `CHEMIN_PAGE_HTML` dans `run_veille.py`.
- `.gitignore` exclut volontairement les artefacts Python (`__pycache__`)
  mais PAS `cache/`, `rapports/`, `docs/` — ces trois dossiers doivent être
  versionnés pour que le mécanisme ci-dessus fonctionne. Ne jamais les
  ajouter au `.gitignore` sans avoir relu cette section.

**Mode local conservé en complément** : le script peut toujours être lancé
manuellement (`python3 run_veille.py`) pour du test ou du diagnostic — la
règle de fraîcheur à 7 jours (section précédente) reste valable dans ce
contexte précis, mais ne pilote plus la diffusion réelle aux élus, qui
dépend désormais du calendrier GitHub Actions.

---

## 6. Exclusions explicites de cette V1 — RÉVISÉES le 27/06/2026

Cette section existe pour éviter qu'un agent réinterprète librement le
projet. **Aucun des éléments suivants ne doit être ajouté sans validation
explicite de Xavier au préalable.**

**Ce qui reste exclu :**
- ❌ Pas de base de données (SQLite, PostgreSQL, etc.) — un cache JSON local
  suffit, y compris dans le dépôt GitHub
- ❌ Pas de serveur dynamique (Flask, Django, ou équivalent) — uniquement du
  contenu statique généré puis publié, jamais un processus serveur qui
  répond à des requêtes en temps réel
- ❌ Pas d'authentification utilisateur sur la page publiée — elle reste
  ouverte à tous, conformément à la décision sur la confidentialité
  (section 5)
- ❌ Pas de notification email/SMS automatique
- ❌ Pas de généralisation à d'autres communes que Saint-Benoît
- ❌ Pas de fichier `.bat`, `.ps1`, ou `.exe` — uniquement des scripts Python

**Ce qui n'est PLUS exclu (changement du 27/06/2026), avec justification :**
- ✅ **Interface web** : autorisée, mais strictement sous la forme d'une
  page HTML/JS statique générée par le script et publiée sur GitHub Pages —
  jamais un serveur qui tourne en continu et répond à des requêtes
  dynamiques. La distinction est importante : "interface" ne veut pas dire
  "serveur".
- ✅ **Authentification/token** pour la publication elle-même (GitHub) est
  désormais nécessaire et acceptée — à ne pas confondre avec une
  authentification utilisateur sur la page consultée, qui reste exclue.

Si un de ces points doit évoluer à nouveau, il faut d'abord mettre à jour ce
document avec Xavier, puis seulement ensuite coder.

---

## Historique

- 24/06/2026 — Première version figée, après un premier essai écarté (un
  agent avait construit de son propre chef un serveur Flask avec base de
  données et authentification JWT inventée, sans rapport avec les fichiers
  livrés). Ce document existe pour empêcher la répétition de cet écart.
- 24/06/2026 (même jour, suite de la session) — Révision du périmètre fonctionnel
  (Section 1) : l'outil doit servir tous les services administratifs, pas
  filtrer selon les priorités politiques de Xavier. `scoring.py` (filtre)
  remplacé par `categorisation.py` (étiquetage sans exclusion).
- 24/06/2026 (suite) — Vérification réelle de Département 974 et de la
  Préfecture de La Réunion : deux URLs/domaines précédemment renseignés
  étaient incorrects et ont été corrigés dans `sources.json` après fetch
  direct des pages réelles. Patrons de reconnaissance de date limite élargis
  dans `region_reunion_detail.py` pour couvrir 3 formats supplémentaires
  observés en réel ("1er juin 2026", "12/05/2026", "Au plus tard le ...").
  Restent à vérifier de la même façon : ADEME, Banque des Territoires, CAF Réunion.
- 24/06/2026 (suite, fin de session) — Vérification réelle des 3 dernières
  sources. Découverte majeure : ADEME expose un vrai flux RSS officiel dédié
  aux appels à projets collectivités, mis à jour quotidiennement — nouveau
  module `ademe_rss.py` créé pour l'exploiter (dépendance `feedparser` ajoutée
  partout où nécessaire, notamment `demarrer.sh`). Banque des Territoires
  corrigée (URL fausse) mais s'avère moins riche en opportunités Réunion que
  prévu. CAF Réunion repensée : pas de flux centralisé d'appels à projets
  comme espéré, la source cible désormais la détection de nouvelles "Lettres
  aux partenaires" (PDF mensuel) plutôt qu'un flux d'AAP qui n'existe pas
  sous cette forme. **Les 10 sources du référentiel sont désormais vérifiées
  par fetch réel.**
- 24/06/2026 (suite, après premier passage en conditions réelles côté Claude
  Code) — Un fichier `sources.json` périmé sur le disque (antérieur aux
  corrections Préfecture/Banque des Territoires) avait causé un faux
  diagnostic ; corrigé par remplacement complet des 14 fichiers. Diagnostic
  réel ensuite confirmé : Préfecture, Département 974, Banque des
  Territoires, CAF Réunion fonctionnels (200) ; flux RSS ADEME confirmé actif
  (209 entrées). Deux dernières corrections d'URL apportées suite à ce
  diagnostic : Europe en France (`/fr/appels-projets`, pas
  `/fr/appels-a-projets` — mais sa liste se charge en JavaScript, limite
  documentée) et CEREMA (`/fr/mots-cles/appel-projet`, pas la racine du
  site — mais contenu majoritairement obsolète, 2018-2024). Le blocage 403
  constaté sur Région Réunion a été traité en remplaçant le User-Agent
  explicite "VEILLE-FI/1.0" par un User-Agent de navigateur standard dans
  les 4 modules concernés, avec ajout d'en-têtes Accept/Accept-Language.
  L'extraction générique de `scraper_html.py` a été renforcée pour exclure
  les blocs `<nav>`/`<header>`/`<footer>` avant extraction, suite au bruit
  de menu constaté sur Département 974 (87 candidats) et CEREMA (157
  candidats) lors du diagnostic réel.
- 24/06/2026 (suite) — Correction d'un biais identifié par Claude Code lors
  de la validation du flux RSS ADEME (5 AAP retenus sur 210, tous
  explicitement "Outre-mer") : la logique de filtrage géographique excluait
  par défaut tout AAP dont le résumé RSS ne mentionnait aucune région
  explicitement — ce qui risquait d'exclure à tort des AAP nationaux
  génériques (éligibles à toute la France, donc à La Réunion aussi) faute de
  mention dans le résumé court du flux. Nouvelle règle dans
  `_perimetre_concerne_reunion()` (ademe_rss.py) : un AAP est exclu
  seulement s'il mentionne EXCLUSIVEMENT d'autres régions précises sans
  mentionner la Réunion ; en l'absence de toute mention géographique,
  l'inclusion est désormais le comportement par défaut (mieux vaut un faux
  positif visible et ignorable dans le rapport qu'un faux négatif qui prive
  la mairie d'une opportunité éligible). Test permanent ajouté reproduisant
  ce cas précis.
- 24/06/2026 (suite, vérification du filtre élargi) — Confirmation en
  conditions réelles : 194/210 AAP retenus après la correction (contre 5/210
  avant). Deux points vérifiés en détail par Claude Code suite à des
  vigilances légitimes :
  (1) **Décision de design actée et testée** : un AAP réservé explicitement
  à un autre DROM nommé (ex. "Martinique uniquement") reste exclu, par
  asymétrie volontaire avec les mentions génériques "Outre-mer" — documentée
  dans `ademe_rss.py` au-dessus de `AUTRES_TERRITOIRES_EXCLUSIFS`, cohérente
  avec le principe de la Section 1 (informer les services sur ce qui sert
  LEURS dossiers, pas faire de la veille DROM générale).
  (2) **Fausse alerte vérifiée et écartée** : deux paires de titres
  apparemment dupliqués dans le flux RSS se sont révélées être des éditions
  annuelles distinctes du même AAP récurrent (liens différents malgré un
  titre parfois identique). Testé concrètement : la déduplication par
  (titre, lien) traite bien ces éditions comme des entrées séparées, aucune
  fusion à tort. Documenté comme point de vigilance dans `cache_dedup.py`
  pour de futures sources qui republieraient avec titre ET lien identiques.
- 24/06/2026 (suite, premier rapport complet généré en conditions réelles —
  472 entrées) — Analyse du rapport réel par Claude Code, révélant 4 défauts,
  3 corrigés immédiatement et testés :
  (1) **Tri par urgence cassé** : des AAP clôturés (échéance dépassée de
  plusieurs centaines de jours) apparaissaient en tête du rapport, avant les
  AAP réellement actifs — un tri croissant naïf traitait une échéance très
  négative comme "plus urgente". Corrigé dans `trier_par_urgence()`
  (categorisation.py) : nouvel ordre actifs (croissant) → sans échéance
  connue → dépassées (toujours en dernier, jamais exclues du rapport).
  (2) **Bruit de boutons UI** : "Afficher plus de contenus" (pagination)
  remonté comme un faux AAP ; liens de partage social et `javascript:;`
  ralentissant le fetch de second niveau. Corrigé dans `scraper_html.py` par
  un filtre par motifs (regex) plutôt qu'une liste figée de libellés exacts.
  (3) **Catégorisation thématique défaillante** : "transport"/"maritime"
  classés à tort dans "Culture / Sport / Jeunesse" via un matching par
  sous-chaîne ("sport" trouvé dans tranSPORT, "culture" dans agriCULTUre —
  même classe de bug que le cas rural/eau corrigé précédemment, mais non
  détecté à l'époque). Corrigé structurellement : `categoriser()` utilise
  désormais un matching par MOT ENTIER (regex avec limites \\b) au lieu de
  `in` sur sous-chaîne brute, éliminant toute cette classe de bugs d'un
  coup. Mots-clés enrichis pour couvrir les cas réels ADEME observés
  (agriculture, forestier, apiculture, économie circulaire, décarbonation,
  transport/mobilité, textile, engins de chantier...).
  (4) **Aides-territoires en 401, Région Réunion en 403** : pour
  Aides-territoires, hypothèse retenue et appliquée — la version d'API en
  dur (`1.1`) a probablement été dépréciée, le guide officiel documente
  désormais `1.4` comme version courante ; corrigé dans
  `client_aides_territoires.py`, **à confirmer en conditions réelles**. Pour
  Région Réunion, le 403 persiste malgré le changement de User-Agent
  précédent et reste un **point ouvert non résolu** — aucune cause certaine
  identifiée à ce stade, pas de nouveau correctif appliqué sur une simple
  supposition.
- 24/06/2026 (suite, confirmation en conditions réelles après synchronisation
  correcte des fichiers) — Les 2 corrections les plus critiques (tri par
  urgence, matching par mot entier) ont été confirmées comme fonctionnelles
  sur un rapport réel (472 → 395 entrées après filtre anti-nav ; AAP clôturés
  passés en fin de classement ; MAEC-Apiculture ne matche plus "Culture").
  Le 401 Aides-territoires persiste malgré le changement de version d'API —
  hypothèse invalidée, cause toujours inconnue, reste un point ouvert non
  résolu comme le 403 Région Réunion. **Décision validée par Xavier** suite
  à ce rapport : création d'une 8ème thématique "Agriculture / Ruralité",
  positionnée juste après "Environnement / Transition écologique", pour ne
  plus fusionner les AAP agricoles (apiculture, MAEC, conseil agricole,
  forestier) dans une catégorie environnementale qui ne leur correspond pas
  vraiment. Mots-clés agricoles migrés depuis "Environnement" vers la
  nouvelle catégorie ; tests de non-régression mis à jour en conséquence.
- 24/06/2026 (suite, cause du 401 Aides-territoires confirmée) — Test direct
  par Claude Code (curl, avec et sans User-Agent personnalisé) : le 401 est
  bien causé par une exigence de token JWT côté plateforme
  ("JWT Token not found"), pas par un problème de version d'API comme
  supposé précédemment (hypothèse invalidée et abandonnée). Ajout dans
  `client_aides_territoires.py` d'un diagnostic précoce
  (`_diagnostiquer_acces_api`) qui détecte ce cas dès le premier appel et
  produit un message d'erreur explicite et actionnable plutôt qu'un échec
  réseau opaque. Démarche de résolution documentée en section 2bis — hors
  périmètre du code, nécessite une démarche administrative (création de
  compte, demande d'accès API) à mener par Xavier ou un service de la
  mairie. Pipeline non bloqué : les 9 autres sources continuent de
  fonctionner normalement en attendant.
- 24/06/2026 (suite, deux derniers défauts de bruit corrigés sur Préfecture
  et Département 974) — (1) Le motif anti-bruit de `scraper_html.py` ne
  couvrait que "Partager sur X (anciennement Twitter)" mais pas la variante
  sans préfixe "x (anciennement twitter)" seule, constatée en réel sur
  Préfecture — motif élargi pour reconnaître les noms de réseaux sociaux
  isolés. (2) Département 974 pose parfois un `<a>` distinct sur le titre
  ET sur les premiers mots du résumé d'une même carte d'actualité, les deux
  pointant vers la même URL — l'extraction générique les remontait comme
  deux entrées séparées. Corrigé en deux temps : `_extraire_items_generique`
  utilise maintenant `find_all("a")` au lieu de `find("a")` (sinon le second
  lien d'un conteneur n'était jamais collecté du tout), puis une passe de
  déduplication par URL seule garde le texte le plus court parmi les
  candidats de même URL (un titre est presque toujours plus court qu'un
  extrait de résumé) — robuste à l'ordre d'apparition titre/résumé dans le
  HTML, testé dans les deux sens.
- 24/06/2026 (suite, décision actée sur Région Réunion) — Après confirmation
  que le changement de User-Agent ne suffit pas à lever le 403 (toujours
  bloqué malgré l'en-tête navigateur standard), **décision explicite de ne
  pas pousser plus loin techniquement** : aucune tentative de rotation d'IP,
  de contournement anti-bot avancé, ou de navigateur headless ne sera faite.
  Voir section 2ter pour la justification complète et la recommandation de
  vérification manuelle ponctuelle en attendant une alternative légitime
  (flux RSS ou API officielle, si Région Réunion en propose un jour).
- 24/06/2026 (fin de session, recentrage majeur du périmètre) — **Xavier a
  reformulé la demande initiale.** Changement de public : de "tous les
  services administratifs" vers "tous les élus de la majorité (adjoints +
  conseillers délégués)". Changement d'usage : de "rapport exhaustif à
  lecture passive" vers "outil de recherche active projet→financement".
  Un second axe a été envisagé (raisonnement inverse : identifier la
  typologie de projet qui maximiserait les financements obtenus) puis
  **explicitement écarté** du périmètre de VEILLE-FI après discussion — jugé
  trop incertain méthodologiquement pour fonder une recommandation présentée
  à des élus (un comptage de mots-clés RSS ne suffit pas à garantir une
  vraie analyse d'optimisation). Cet axe pourra faire l'objet d'un outil
  séparé, à usage strictement personnel de Xavier, mais ne fait pas partie
  de ce projet. Conséquence sur le format (section 4) : le classement en 8
  sections thématiques fixes est retiré du rapport, remplacé par une liste
  unique triée par urgence avec les mêmes mots-clés affichés comme tags en
  clair sur chaque ligne — pour rester cherchable au Ctrl+F sans réintroduire
  d'interface (qui reste hors périmètre, section 6).
- 27/06/2026 — Premier rapport généré avec le nouveau format (liste unique,
  tags inline) examiné en détail : le top 10 ne montrait AUCUN marqueur
  d'échéance, alors que la source ADEME (la plus volumineuse, ~194 entrées)
  contient pourtant des dates "Ouvert jusqu'au ..." en clair dans son résumé
  RSS. Cause identifiée : `ademe_rss.py` n'a jamais extrait l'échéance
  depuis sa création — limite documentée dès l'origine mais jamais comblée,
  et l'adaptateur `_ItemCompatADEME` dans `run_veille.py` ne transportait
  même pas le champ jusqu'au cache. Corrigé en trois temps : (1) nouveau
  patron `PATRON_OUVERT_JUSQU_AU` ajouté à `region_reunion_detail.py`
  (réutilisé tel quel, pas dupliqué) ; (2) `ademe_rss.py` extrait désormais
  l'échéance à la construction de chaque `AppelAProjetADEME` (nouveau champ
  `date_limite_iso`) ; (3) `run_veille.py` propage ce champ jusqu'au rapport
  via l'adaptateur. Sans ce correctif, le tri par urgence (pourtant corrigé
  et testé précédemment) restait inopérant sur la quasi-totalité du rapport
  faute de dates à trier. Test de non-régression ajouté dans les deux
  modules concernés.
- 27/06/2026 (suite, correction de l'hypothèse fausse sur le format ADEME) —
  La correction précédente, bien que testée et validée sur tous les tests
  automatisés, s'est révélée **inopérante en conditions réelles** : un
  nouveau rapport généré après synchronisation montrait toujours zéro
  marqueur d'échéance sur les entrées ADEME. Cause identifiée par Claude
  Code via lecture directe (`repr()`) du résumé RSS réel : le format supposé
  ("Ouvert jusqu'au [date texte]") était une **hypothèse jamais vérifiée**
  sur le vrai contenu du flux, construite par erreur à partir d'un souvenir
  de la page web plutôt que du flux RSS lui-même. Le vrai format est
  "du JJ/MM/AAAA - HH:MM au JJ/MM/AAAA - HH:MM" (c'est la DEUXIÈME date qui
  est l'échéance, la première étant la date d'ouverture). Le piège
  méthodologique à retenir : les tests automatisés passaient tous, parce que
  le flux RSS simulé dans les tests reproduisait la même hypothèse fausse
  que le code testé — un test ne vaut que ce que vaut la donnée simulée sur
  laquelle il s'appuie. `PATRON_OUVERT_JUSQU_AU` corrigé pour le vrai
  format (tolérant aux retours à ligne et espaces insécables entre les deux
  dates) ; tous les flux RSS simulés des tests (`region_reunion_detail.py`,
  `ademe_rss.py`, `test_integration_complete.py`) mis à jour pour refléter
  le vrai format plutôt que l'ancienne hypothèse.
- 27/06/2026 (suite, confirmation finale en conditions réelles) — Nouveau
  rapport généré après cette correction : le tri par urgence fonctionne
  enfin sur l'ensemble du rapport. Top 10 vérifié avec des échéances
  croissantes cohérentes (3, 9, 31, 66, 90, 97, 107, 110, 187, 187 jours),
  alertes ⚠️ correctement positionnées sur les échéances ≤15 jours. L'AAP le
  plus urgent ("eXtrême Défi Logistique", 3 jours) est passé de la position
  ~17 (ancien tri non fonctionnel) à la position 1. **Limite de vigilance
  à garder en tête** : le tri dépend désormais largement de la robustesse du
  patron `PATRON_OUVERT_JUSQU_AU`, qui ne reconnaît qu'un seul format de
  texte (confirmé sur un échantillon de 5 entrées). Si ADEME republie un
  jour avec une formulation différente, l'entrée concernée retombera
  silencieusement dans le groupe "sans échéance connue" (comportement de
  repli déjà géré, pas un risque de crash, mais une perte de précision
  potentiellement invisible). Si un futur rapport montre une proportion
  anormalement élevée d'entrées ADEME sans échéance, c'est la première
  piste à vérifier (repr() du résumé RSS réel, comme la première fois).
- 27/06/2026 (changement d'architecture majeur — diffusion publique) —
  Xavier signale que les autres élus de la majorité n'ont pas Claude Code
  ni de compétence technique pour lancer l'outil eux-mêmes. Après examen
  de plusieurs options (dossier partagé, exécutable autonome, serveur
  classique), **décision retenue : GitHub Actions + GitHub Pages.** Le
  script tourne automatiquement chaque lundi sur les serveurs de GitHub
  (gratuit, dépôt public), sans qu'aucune machine de la mairie ait besoin
  d'être allumée. Confidentialité validée par Xavier : les données (aides
  publiques) n'ont pas besoin d'être protégées, diffusion ouverte acceptée.
  Nouveau module `generer_html.py` créé : page HTML autonome avec tableau
  filtrable en JavaScript (recherche et tri côté navigateur, sans serveur).
  **Deux vulnérabilités XSS trouvées et corrigées avant publication**, via
  un vrai test DOM (jsdom, pas seulement relecture de code) : (1) un titre
  contenant "</script>" pouvait fermer prématurément le bloc JavaScript du
  document, empêchant toute exécution — corrigé en échappant "</" en JSON ;
  (2) la fonction d'échappement JS ne neutralisait pas les guillemets
  doubles, permettant à un lien malveillant de s'échapper de l'attribut
  `href` et d'injecter un gestionnaire d'événement exécutable — corrigée en
  réécrivant l'échappement pour couvrir explicitement guillemets et
  apostrophes. Décision de contenu validée par Xavier : la page HTML
  reconstruit l'intégralité du cache (pas seulement les nouveautés de la
  semaine), avec exclusion d'affichage des dispositifs dont l'échéance est
  dépassée depuis plus de 60 jours. Section 6 du cahier des charges révisée
  pour autoriser explicitement une interface web STATIQUE (générée puis
  publiée), tout en maintenant l'exclusion d'un serveur dynamique.
