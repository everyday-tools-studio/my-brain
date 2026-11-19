# Contributing · Contribuer

## English

Describe the user-visible change and the device or OS where you tested it. For a notification issue, a made-up sender, message, time zone and expected result usually suffice. Use the security reporting instructions for a privacy or security concern. [Security reporting](SECURITY.md)

Run the following checks from the repository root on Linux. The desktop tests use temporary profiles and synthetic messages. They exercise the local server, encrypted backups, calendar updates and single-message analysis. OpenSSL and GnuPG are needed to run the full suite. The parser runs on a JDK independently of the Android SDK.

## Français

Décris ce qui change pour la personne qui utilise l’application et précise l’appareil ou le système sur lequel tu as testé. Pour un souci de notification, indique un expéditeur fictif, un texte inventé, le fuseau horaire et le résultat attendu. Une question de confidentialité ou de sécurité se signale en privé. [Signalement](SECURITY.md)

Lance les vérifications ci-dessous depuis la racine du dépôt sous Linux. Les tests PC utilisent des profils temporaires et des messages fictifs. Ils couvrent le service local, la sauvegarde chiffrée, l’agenda et l’analyse d’un message. Installe OpenSSL et GnuPG pour exécuter toute la suite. Le test de l’extraction française utilise seulement un JDK.

## Local checks · Vérifications locales

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
node --check web/app.js

classes="$(mktemp -d)"
javac --release 11 -encoding UTF-8 -d "$classes" android/src/fr/moncerveau/app/Extract.java android/tests/ExtractTest.java
java -cp "$classes" fr.moncerveau.app.ExtractTest
```

With JDK 17+ and an Android SDK containing a platform and Build Tools, build the unsigned package. CI uses platform 36 and Build Tools 36.0.0. The publication allowlist in `.gitignore` must explicitly include each new public source or test file.

Avec un JDK 17+ et un SDK Android comportant une plateforme et les Build Tools, compile le paquet à signer. L’intégration continue utilise la plateforme 36 et les Build Tools 36.0.0. Pour ajouter un nouveau fichier source ou de test public, ajoute aussi son chemin exact à la liste autorisée dans `.gitignore`.

```sh
./android/build.sh --unsigned
unzip -tq android/build/mon-cerveau-unsigned.apk
```
