#!/usr/bin/env bash
#
# demarrer.sh — Script de mise en route VEILLE-FI.
#
# Automatise :
#   1. Vérification de Python 3
#   2. Vérification/installation de requests + beautifulsoup4 + feedparser
#   3. Lancement des tests hors-réseau (logique interne + intégration mockée)
#   4. Proposition d'enchaîner sur le mode diagnostic (vrais sites)
#
# Usage :
#   chmod +x demarrer.sh   # une seule fois, pour le rendre exécutable
#   ./demarrer.sh
#
# Si une étape échoue, le script s'arrête et affiche un message clair plutôt
# que de continuer sur une base cassée.

set -e  # arrêt immédiat si une commande échoue

echo "=========================================="
echo "  VEILLE-FI — Script de mise en route"
echo "=========================================="
echo ""

# --- 1. Vérification de Python 3 ---
echo "[1/4] Vérification de Python 3..."
if ! command -v python3 &> /dev/null; then
    echo "❌ python3 n'est pas trouvé sur ce système."
    echo "   Installe Python 3 (https://www.python.org/downloads/) puis relance ce script."
    exit 1
fi
PYTHON_VERSION=$(python3 --version)
echo "✅ $PYTHON_VERSION trouvé."
echo ""

# --- 2. Vérification / installation des dépendances ---
echo "[2/4] Vérification des dépendances Python (requests, beautifulsoup4, feedparser)..."
if python3 -c "import requests, bs4, feedparser" &> /dev/null; then
    echo "✅ Les dépendances sont déjà installées."
else
    echo "⚠️  Dépendances manquantes — installation en cours..."
    if command -v pip3 &> /dev/null; then
        PIP_CMD="pip3"
    else
        PIP_CMD="pip"
    fi

    if $PIP_CMD install requests beautifulsoup4 feedparser --break-system-packages 2>/dev/null; then
        echo "✅ Installation réussie."
    elif $PIP_CMD install requests beautifulsoup4 feedparser 2>/dev/null; then
        echo "✅ Installation réussie (sans --break-system-packages)."
    else
        echo "❌ L'installation automatique a échoué."
        echo "   Essaie manuellement : pip3 install requests beautifulsoup4 feedparser --break-system-packages"
        exit 1
    fi

    # Re-vérification après installation
    if python3 -c "import requests, bs4, feedparser" &> /dev/null; then
        echo "✅ Dépendances confirmées disponibles."
    else
        echo "❌ Les dépendances ne sont toujours pas importables après installation."
        echo "   Il peut y avoir plusieurs versions de Python sur ce système."
        echo "   Essaie : python3 -m pip install requests beautifulsoup4 feedparser --break-system-packages"
        exit 1
    fi
fi
echo ""

# --- 3. Tests hors-réseau ---
echo "[3/4] Lancement des tests hors-réseau (aucun appel internet)..."
echo ""
echo "--- test_logique_interne.py ---"
python3 test_logique_interne.py
echo ""
echo "--- test_integration_complete.py ---"
python3 test_integration_complete.py
echo ""
echo "✅ Tous les tests hors-réseau sont passés."
echo ""

# --- 4. Proposition du mode diagnostic ---
echo "[4/4] Étape suivante : le mode diagnostic teste les VRAIS sites web."
echo ""
echo "Ce mode va se connecter à internet et tenter de récupérer les pages"
echo "réelles (Aides-territoires, Région Réunion, Préfecture, etc.) pour"
echo "vérifier que l'extraction fonctionne correctement."
echo ""
read -p "Lancer le mode diagnostic maintenant ? (o/n) " REPONSE

if [[ "$REPONSE" == "o" || "$REPONSE" == "O" ]]; then
    echo ""
    echo "--- Lancement de : python3 run_veille.py --diagnostic (sources HTML) ---"
    echo ""
    python3 run_veille.py --diagnostic
    echo ""
    echo "--- Lancement de : python3 ademe_rss.py --diagnostic (flux RSS ADEME) ---"
    echo ""
    python3 ademe_rss.py --diagnostic
else
    echo ""
    echo "OK, tu peux les lancer plus tard avec :"
    echo "    python3 run_veille.py --diagnostic"
    echo "    python3 ademe_rss.py --diagnostic"
fi

echo ""
echo "=========================================="
echo "  Mise en route terminée."
echo "=========================================="
