# Mon cerveau

Projet personnel de Bastien, repris de zéro. Centraliser les idées, notes, tâches et rendez-vous sur son PC et les retrouver dans une même application sur Android et PC. La capture doit accepter le texte, la voix et le partage. Orca et d’autres agents doivent pouvoir travailler sur les mêmes données. Bastien souhaite pouvoir reprendre et finir ce qu’il commence.

## Cadrage

Retrouver les besoins exprimés dans les imports partiels de claude.ai, distinguer les décisions actuelles des anciennes pistes, puis proposer une première version à Bastien avant de développer. Les rendez-vous sont aujourd'hui dispersés. Aucun fournisseur d'agenda n'a été choisi.

Le dépôt Git reste local. Garder les données personnelles d’utilisation et les secrets hors du dépôt.

## Ouvrir l’application

Depuis ce dossier, lancer `./scripts/lancer-pc`, puis ouvrir [Mon cerveau sur ce PC](http://127.0.0.1:8743). Laisser ce processus ouvert pour recevoir les captures du téléphone sur le Wi-Fi. Au premier démarrage, le script prépare un environnement Python local et le modèle français de transcription. Pour préparer une installation séparément, utiliser `./scripts/preparer-pc.sh`.

Sur le Pixel, ouvrir le fichier [mon-cerveau.apk](android/build/mon-cerveau.apk) et confirmer son installation. Pour le reconstruire, lancer `./android/build.sh` avec le SDK Android et un JDK. L’APK utilise une signature de développement locale. Conserver la même clé de signature pour installer les mises à jour par-dessus la première version.

1. Sur le PC, ouvrir les réglages d’appairage et générer un code. Sur le même Wi-Fi, copier le JSON dans **Réglages du Pixel → Associer le PC**. Le code contient une autorisation personnelle à garder sur ses appareils.
2. Sur le Pixel, les réglages permettent de choisir l’accès aux notifications, la réception des SMS et les rappels. Activer les notifications de rendez-vous et, pour l’heure précise, autoriser les alarmes exactes. Le micro est demandé à la première dictée.
3. Pour capturer, écrire une idée, toucher **Mémo vocal** ou partager du texte vers **Mon cerveau**. Le mémo reste écoutable hors ligne. Après réception sur PC, la transcription française s’ajoute au mémo vide et devient recherchable. Une transcription manuelle peut aussi être demandée dans la fiche.
4. Transformer une note en tâche et préciser le prochain geste dans son contenu. Épingler la tâche pour la retrouver dans **Reprendre**. La vue **À confirmer** permet d’attribuer une date aux rendez-vous ambigus.

## Messages et rendez-vous

Le Pixel analyse localement les SMS reçus ou les aperçus disponibles de Messages, WhatsApp, Gmail et Proton Mail. Gmail regroupe ici Gmail, Yahoo et GMX. L’analyse par règles reconnaît des expressions françaises de rendez-vous, de tâches et d’informations à garder. Une heuristique peut manquer un message ou retenir un faux positif. La fiche affiche le texte source disponible. Les notifications peuvent être absentes, tronquées ou regroupées. Une pièce jointe, un message silencieux ou une conversation ouverte peuvent ainsi échapper au traitement. Le premier essai sur les boîtes personnelles consiste à vérifier ces situations pour chacune.

Les rendez-vous enregistrés sur le Pixel ont un rappel local 30 minutes avant. Les changements circulent dans les deux sens avec le PC, qui conserve aussi les notes et mémos. Le bouton **Synchroniser** déclenche un essai immédiat. En arrière-plan Android décide du moment d’exécution périodique.

### Agenda extérieur facultatif

L’agenda de Mon cerveau fonctionne avec le Pixel et le PC seuls. Pour relier en plus un calendrier CalDAV choisi, préparer l’URL HTTPS de la collection, le nom de compte et le mot de passe d’application dans les variables de session `CERVEAU_CALDAV_URL`, `CERVEAU_CALDAV_USER` et `CERVEAU_CALDAV_PASSWORD`. Choisir d’abord un calendrier d’essai dédié. La première synchronisation associe **tous les rendez-vous locaux datés** à cette collection et importe ses événements compatibles. Elle échange les titres et les heures. Les notes, l’audio et le champ contenant le message source restent dans Mon cerveau.

```sh
.venv/bin/python calendrier.py --data-dir "${XDG_DATA_HOME:-$HOME/.local/share}/mon-cerveau" --watch
```

Le connecteur prend en charge les événements simples avec une heure. Il ignore les séries récurrentes, les journées entières et les événements avec organisateur ou participants. Les modifications simultanées incompatibles suspendent l’échange de la fiche concernée. Après comparaison des deux versions, utiliser la même commande avec `--resolve ID local` ou `--resolve ID distant` pour choisir celle à garder. Le connecteur a été testé sur un calendrier simulé. Aucun fournisseur personnel n’a été configuré.

### Analyse en ligne d’un message

Sur PC, l’analyse en ligne facultative passe par la passerelle FreeLLMAPI sur `127.0.0.1:3001`. Pour l’activer, configurer dans l’environnement du service PC `FREELLMAPI_API_KEY`, `FREELLMAPI_MODEL` et `FREELLMAPI_PROVIDER`. Choisir dans la passerelle un modèle avec une destination connue et indiquer ce fournisseur dans la dernière variable. L’application montre le destinataire et le texte avant chaque envoi. Elle vérifie la version de la fiche au moment de la confirmation. Aucun envoi de message n’est nécessaire pour utiliser les autres fonctions.

## Agents, sauvegardes et vérification

Les commandes d’Orca, les droits d’écriture par agent, la sauvegarde chiffrée quotidienne vers un second support et la restauration dans un profil isolé sont décrits dans [SERVER.md](SERVER.md). Les données personnelles se trouvent dans le répertoire de données de l’utilisateur. Pour donner à Orca le droit de créer une tâche demandée, lancer une fois `python3 cerveau.py grant-task orca`.

Pour rejouer les tests du PC, lancer `.venv/bin/python -m unittest discover -s tests -v`. Pour vérifier le trajet complet sur ses propres appareils, suivre les scénarios du [plan](PLAN.md) avec des messages fictifs.
