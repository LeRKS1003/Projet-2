#!/bin/bash
# DÉRIVE — lanceur macOS / Linux : double-cliquez sur ce fichier (ou ./lancer_jeu.command).
# La première fois, il installe tout seul ce qu'il faut (une ou deux minutes).
cd "$(dirname "$0")" || exit 1
if [ ! -f .venv/installe.txt ]; then
    echo "Première installation du jeu, patientez une ou deux minutes..."
    python3 -m venv .venv || { echo "Python 3 est introuvable : installez-le depuis python.org"; read -r; exit 1; }
    .venv/bin/python -m pip install --upgrade pip
    .venv/bin/python -m pip install -r requirements.txt || { echo "Erreur d'installation."; read -r; exit 1; }
    echo ok > .venv/installe.txt
fi
.venv/bin/python main.py || { echo "Une erreur est survenue (appuyez sur Entrée)."; read -r; }
