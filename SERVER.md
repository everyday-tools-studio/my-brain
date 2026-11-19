# Service PC et commandes locales

Le service utilise Python 3, SQLite et le profil `~/.local/share/mon-cerveau` (ou `$XDG_DATA_HOME/mon-cerveau`). L’audio, les transcriptions et l’historique vivent dans cette base. Les options de profil se placent **avant** la commande, par exemple `python3 cerveau.py --data-dir /chemin/essai list`. Utiliser le Python de l’environnement préparé pour activer les intégrations supplémentaires.

## Ouvrir Mon cerveau et appairer le Pixel

```sh
.venv/bin/python cerveau.py serve --lan
```

Ouvrir [Mon cerveau sur ce PC](http://127.0.0.1:8743). Le serveur HTTP de l’interface écoute exclusivement sur la boucle locale. Avec `--lan`, un second serveur expose la synchronisation HTTPS sur le port 8744. L’option `--lan-host` permet de choisir l’adresse de l’interface Wi-Fi. Pour utiliser le PC seul, omettre `--lan`.

Dans l’interface PC, ouvrir l’appairage et générer le code. Sur le Pixel, lire le QR comme texte avec un lecteur local, puis coller son contenu dans « Réglages du Pixel → Associer le PC ». Le bouton de copie du PC fournit le même JSON. Chaque code autorise un nouvel appareil et contient un jeton personnel. La génération de QR utilise le paquet qrcode de l’environnement PC.

Pour effectuer aussi cet appairage en ligne de commande sur le même PC, remplacer l’adresse ci-dessous par son adresse **sur le Wi-Fi de la maison**. Cette commande crée un accès appareil et affiche ses paramètres. Garder le jeton dans les réglages du téléphone et hors des journaux, du dépôt et des captures d’écran.

```sh
python3 cerveau.py pair --url https://192.168.1.42:8744
```

Reporter l’adresse, le jeton et l’empreinte du certificat affichés dans l’application Android. L’empreinte SHA-256 identifie le PC même avec un certificat autosigné. L’accès réseau exige le jeton à chaque appel. Si nécessaire, ouvrir le port TCP 8744 uniquement sur le réseau domestique. En cas de perte du téléphone, `python3 cerveau.py unpair-all` révoque tous les appareils. Refaire l’appairage des appareils conservés.

## Commandes des agents

```sh
python3 cerveau.py list --kind task
python3 cerveau.py list --search dossier
python3 cerveau.py get IDENTIFIANT
python3 cerveau.py history IDENTIFIANT
```

La liste fournit le texte en JSON. La lecture d’une fiche ou de son historique inclut également son audio. Pour accorder à Orca le droit de créer les tâches demandées par Bastien, exécuter une fois `python3 cerveau.py grant-task orca`. Orca peut alors lancer la commande suivante et confirmer la création après réception du JSON avec l’identifiant et la révision.

```sh
python3 cerveau.py add-task --agent orca --id demande-001 --body 'Préparer le dossier' 'Rappeler Léa'
```

Conserver le même identifiant pour retenter la même opération après une interruption. `python3 cerveau.py revoke-task orca` retire la permission de création par la CLI. Les droits de cette CLI régissent des agents de confiance partageant le compte utilisateur du PC. Un programme disposant d’un accès arbitraire aux fichiers de ce compte peut aussi accéder directement à SQLite.

## Sauvegarde chiffrée et restauration

Brancher le second support et remplacer les chemins d’exemple. GnuPG chiffre un instantané SQLite cohérent, audio et révisions compris. La première commande demande une phrase secrète deux fois. La seconde demande cette même phrase pour restaurer dans un **répertoire vide**. La copie restaurée dispose de ses propres identifiants d’appairage après un nouvel appairage.

```sh
python3 cerveau.py backup /media/bastien/sauvegarde/mon-cerveau-essai.gpg
python3 cerveau.py --data-dir ~/restauration-mon-cerveau restore /media/bastien/sauvegarde/mon-cerveau-essai.gpg
python3 cerveau.py --data-dir ~/restauration-mon-cerveau list
```

Contrôler la restauration en lançant l’interface sur `--port 8745` avec le profil restauré, puis en ouvrant une note, un RDV et un mémo audio. Garder une copie de la phrase secrète séparée du support. Le certificat du PC, les appareils appairés, les autorisations d’agents et les réglages externes à la base doivent être reconfigurés si le PC est remplacé.

Pour automatiser, préparer un fichier de phrase secrète lisible seulement par Bastien (`chmod 600`) dans son répertoire personnel. Créer le répertoire de sauvegarde sur le support monté. Indiquer au service ce répertoire et le fichier de phrase secrète. Tant que le service fonctionne, il vérifie chaque heure et crée au plus une sauvegarde par jour. Vérifier que le support est monté et contrôler périodiquement une restauration.

```sh
.venv/bin/python cerveau.py serve --lan \
  --backup-dir /media/bastien/sauvegarde/mon-cerveau \
  --passphrase-file ~/.config/mon-cerveau/phrase-sauvegarde
```

## Synchronisation

Chaque fiche porte un identifiant stable. Une création utilise la révision 0. Un enregistrement renvoie la nouvelle révision. Une répétition à contenu identique renvoie la révision courante. Une écriture concurrente incompatible reçoit un statut 409 avec la version actuelle. Une suppression conserve une trace pour les appareils hors ligne. Les changements sont enregistrés en transaction. La synchronisation reprend avec `GET /api/items?since=CURSEUR` et le curseur retourné par le serveur. Le paramètre facultatif `limit=1` réduit le volume transféré par page. Continuer avec le curseur retourné tant que `more` est vrai. L’interface PC charge ses listes avec `audio=summary` puis récupère le détail via `/api/item?id=IDENTIFIANT`. L’API accepte une note audio jusqu’à 24 Mio après encodage base64, soit environ 18 Mio d’audio binaire.
