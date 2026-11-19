[Mon cerveau](../../README.fr.md) / Données et intégrations · [English](../en/data.md)

# Où vont tes données ?

| Action | Destination | Données concernées |
| --- | --- | --- |
| Saisir une note ou lire une notification | Stockage de l’application Android | L’élément reconnu et son texte source disponible. Les messages sans élément reconnu sont écartés. |
| Synchroniser un appareil appairé | Ton PC Linux et ton téléphone | Modifications, enregistrements audio et texte source, sur le Wi-Fi en HTTPS authentifié. |
| Transcrire un mémo | PC Linux | Le moteur vocal local lit l’enregistrement. La transcription revient sur le téléphone à la synchronisation. |
| Lancer une analyse IA locale | Modèle local sur ton PC Linux (`127.0.0.1`) | Le seul message sélectionné. Rien ne quitte ta machine. |
| Connecter un fournisseur IA externe (facultatif) | Ton point de terminaison HTTPS configuré (ex. Claude, Codex/OpenAI) | Le seul message affiché dans la fenêtre de confirmation. L’accord vaut pour cet envoi. |
| Activer CalDAV | Le calendrier de ton choix | Titres et heures des rendez-vous pris en charge. Un titre saisi peut lui-même contenir des informations personnelles. |

### Stocker et restaurer

Le PC conserve SQLite dans `$XDG_DATA_HOME/mon-cerveau`, généralement `~/.local/share/mon-cerveau`. La base active est en clair. Protège le compte système et le disque. Avec GnuPG installé, crée un instantané chiffré sur un second support. Remplace le chemin d’exemple par celui du support monté :

```sh
python3 cerveau.py backup /chemin/second-support/mon-cerveau.gpg
python3 cerveau.py --data-dir ./profil-restaure restore /chemin/second-support/mon-cerveau.gpg
python3 cerveau.py --data-dir ./profil-restaure list
```

Restaure dans un dossier vide. Vérifie un rendez-vous et écoute un mémo avant de compter sur cette sauvegarde. Garde la phrase secrète à part. Sur un nouveau PC, il faudra appairer les appareils et autoriser les agents de nouveau.

### Agents locaux

Les agents peuvent chercher et lire des fiches avec les commandes locales. Autorise un agent à créer des tâches en le désignant par son nom. Réutilise le même identifiant pour retenter une demande :

```sh
python3 cerveau.py list --kind task
python3 cerveau.py grant-task assistant
python3 cerveau.py add-task --agent assistant --id exemple-001 'Rapporter le livre à la bibliothèque'
python3 cerveau.py revoke-task assistant
```

Ces autorisations régissent les commandes de l’application. Un logiciel ayant accès à ton compte Linux peut aussi lire ses fichiers.

### IA locale en priorité et fournisseur au choix

L’analyse par modèle IA est **désactivée par défaut** et conçue pour tourner **en local en priorité**.

**1. Modèle local sur ton PC (recommandé par défaut) :** lance un serveur local compatible OpenAI comme [Ollama](https://ollama.com) ou `llama.cpp`, puis définis `CERVEAU_AI_MODEL`. Aucune clé API n’est nécessaire sur la boucle locale (`127.0.0.1`, `localhost`, `::1`) :

```sh
export CERVEAU_AI_MODEL="qwen2.5:7b"
# Par défaut : http://127.0.0.1:11434/v1/chat/completions
# Port ou serveur local personnalisé (facultatif) :
# export CERVEAU_AI_URL="http://127.0.0.1:8080/v1/chat/completions"
```

**2. Connecter ton propre fournisseur (facultatif) :** si tu préfères utiliser Claude, Codex / OpenAI ou un autre fournisseur compatible, configure une adresse **HTTPS**, le modèle et ta clé API hors de Git :

```sh
# Exemple : Anthropic Claude
export CERVEAU_AI_PROVIDER="Claude"
export CERVEAU_AI_URL="https://api.anthropic.com/v1/messages"
export CERVEAU_AI_MODEL="claude-sonnet-4-5"
export CERVEAU_AI_API_KEY="..."

# Exemple : OpenAI / Codex ou toute API HTTPS compatible OpenAI
export CERVEAU_AI_PROVIDER="OpenAI"
export CERVEAU_AI_URL="https://api.openai.com/v1/chat/completions"
export CERVEAU_AI_MODEL="gpt-5-mini"
export CERVEAU_AI_API_KEY="..."
```

Les adresses non chiffrées `http://` sont refusées en dehors de la boucle locale. L’interface PC affiche systématiquement le texte exact et le modèle cible avant chaque analyse.

### Synchronisation CalDAV facultative

CalDAV s’active sur demande. Commence avec un calendrier de test dédié : le premier passage exporte les rendez-vous locaux horodatés et importe les événements compatibles. Configure `CERVEAU_CALDAV_URL`, `CERVEAU_CALDAV_USER` et `CERVEAU_CALDAV_PASSWORD` hors de Git, puis lance `.venv/bin/python calendrier.py --data-dir "${XDG_DATA_HOME:-$HOME/.local/share}/mon-cerveau" --watch`. Les récurrences, les journées entières et les invitations avec participants sont ignorées. Un conflit demande de choisir la version locale ou distante.
