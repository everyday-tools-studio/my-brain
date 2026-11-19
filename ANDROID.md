# Mon cerveau sur le Pixel

L’APK se trouve dans `android/build/mon-cerveau.apk`. L’application demande Android 13 ou plus récent. Pour la reconstruire avec les pages de `web/`, lancer `android/build.sh` sur le PC avec un JDK, un SDK Android récent et ses Build Tools. Le script utilise la clé de développement Android du PC. Garder cette clé pour pouvoir mettre l’APK à jour sur le téléphone.

## Premier démarrage

1. Installer l’APK sur le Pixel, puis saisir une idée dans « Capture rapide ». Elle est immédiatement enregistrée sur l’appareil. Dans une autre application, partager un texte ou un lien vers « Mon cerveau » pour créer une note.
2. Ouvrir les réglages du Pixel **dans Mon cerveau** (icône de réglages). Activer « Lecture des notifications » pour récupérer les futurs aperçus de WhatsApp, Gmail et Proton Mail. Les boîtes Yahoo et GMX consultées dans Gmail utilisent la même voie.
3. Autoriser « Lecture directe des SMS » pour traiter les nouveaux SMS. Android peut restreindre cette autorisation selon le mode d’installation. À défaut, l’application utilise les notifications de Messages. Avec la lecture directe activée, les notifications de Google Messages sont ignorées pour éviter les doublons. Les RCS, qui passent par Internet, peuvent alors manquer.
4. Autoriser les notifications de rappel et, pour un déclenchement précis, les alarmes exactes. Mon cerveau programme un rappel 30 minutes avant chaque RDV horodaté. Un RDV ajouté moins de 30 minutes avant son début déclenche un rappel dès son ajout. Android peut retarder une alarme approximative.
5. À la maison, démarrer le serveur Wi-Fi du PC et générer le code d’appairage d’après [SERVER.md](SERVER.md). Coller son JSON dans « Associer le PC ». Le code contient un jeton d’accès personnel. L’appareil vérifie l’empreinte du certificat du PC à chaque connexion. « Synchroniser maintenant » lance un essai lorsque les deux appareils sont accessibles. La tâche Android périodique fonctionne selon la planification du système.
6. Toucher « Mémo vocal », autoriser le micro puis enregistrer. L’original AAC reste écoutable hors ligne. Sur le PC, le service transcrit en arrière-plan les mémos sans texte. Pour relancer manuellement, ouvrir la fiche, choisir « Transcrire sur ce PC » puis enregistrer le texte. La disponibilité de la transcription dépend du moteur français configuré sur le PC.

## Ce que les messages permettent de vérifier

- Envoyer un SMS de test « RDV demain à 9 h. Pense à apporter le dossier. Code de porte : 5839. » PC éteint. Chercher un rendez-vous daté selon le jour de réception, une tâche et une note. Répéter avec « mardi à 14 h » pour vérifier « À confirmer ». L’extraction utilise des règles locales en français. Certaines formulations et langues peuvent lui échapper.
- Pour chaque messagerie et boîte mail, essayer une notification contenant le texte, un aperçu tronqué et une discussion en sourdine. Un aperçu reçu peut permettre l’extraction. Une pièce jointe, un e-mail entier et une conversation ouverte ou silencieuse peuvent rester inaccessibles. Les fiches issues des notifications indiquent « Extrait de notification ». Un SMS reçu directement conserve son texte. Les messages sans élément reconnu ne sont pas archivés.
- Pour l’analyse facultative par un service en ligne, ouvrir sur PC la fiche synchronisée et valider le texte et le destinataire pour cet envoi.
- Modifier le même rendez-vous hors ligne sur les deux appareils. Le Pixel conserve la version PC sous l’identifiant initial et place la variante locale dans « À confirmer ». Si l’élément a été supprimé localement, la variante signale la demande de suppression.
