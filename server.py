"""
Lanceur du jeu (le code est dans server/).

    python3 server.py          -> ouvre http://localhost:8000 (vrai JEV, clé dans .env)
    python3 server.py --fake   -> sans API (JEV simulé), pour tester
    python3 server.py --help   -> options (port, modèle figé, budget)
"""
from server.app import main

if __name__ == "__main__":
    main()
