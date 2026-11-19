[Mon cerveau](../../README.fr.md) / Démarrage · [English](../en/getting-started.md)

# Ta première capture, du téléphone au PC

### 1. Démarrer sur le PC

Sur Linux, installe Python 3 avec les environnements virtuels (ou uv), OpenSSL, curl et unzip. Lance `./scripts/lancer-pc` depuis le dossier du projet. Le premier lancement utilise Internet pour télécharger les dépendances et le modèle vocal français. Garde le terminal ouvert et accède à [la boîte de réception](http://127.0.0.1:8743).

### 2. Compiler pour Android

Utilise OpenJDK 17+ et le SDK Android avec une plateforme récente et les Build Tools. Indique le chemin du SDK dans `ANDROID_HOME`. Lance `./android/build.sh` pour créer un APK signé pour le développement dans `android/build/mon-cerveau.apk`. Garde la clé de signature pour mettre à jour la même installation. Pour une distribution, `./android/build.sh --unsigned` produit `android/build/mon-cerveau-unsigned.apk`, à signer par le distributeur.

### 3. Associer les appareils sur le Wi-Fi de la maison

Dans les réglages du PC, génère un code d’appairage. Sur Android, ouvre **Réglages Android → Associer le PC** et colle le JSON. Garde-le aussi secret qu’un mot de passe. Le téléphone utilise l’empreinte du certificat pour reconnaître le PC. Si un téléphone est perdu, la commande `python3 cerveau.py unpair-all` sur le PC révoque tous les appareils appairés.

### 4. Vérifier un aller-retour

Partage un lien vers Mon cerveau sur Android, retrouve le Wi-Fi de la maison et touche **Synchroniser**. Ouvre la note sur le PC et convertis-la en tâche. Synchronise et retrouve la tâche sur le téléphone. Pour tester la voix, dicte une courte phrase en français et garde le service PC ouvert jusqu’à l’apparition du texte.

| Symptôme | À vérifier |
| --- | --- |
| Le téléphone attend le PC | Laisse le serveur ouvert, vérifie que les appareils sont sur le même Wi-Fi et que le pare-feu domestique autorise le port de synchronisation (TCP 8744). |
| Un e-mail manque | Autorise la lecture des notifications et vérifie le texte affiché par la messagerie. Une date mentionnée uniquement dans une pièce jointe échappe à cet aperçu. |
| Un rappel arrive en retard | Autorise les notifications et les alarmes précises dans les réglages de l’application. Android peut différer une alarme approximative. |
| Le mémo arrive sans texte | Vérifie le téléchargement du modèle français. Ouvre le mémo et touche **Transcrire sur ce PC** pour réessayer. |

[Suite : stockage et sauvegardes](donnees.md)
