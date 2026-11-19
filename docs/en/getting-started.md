[My Brain](../../README.md) / Getting started · [Français](../fr/demarrage.md)

# Your first capture, from phone to PC

### 1. Start the desktop

On Linux, install Python 3 with virtual environment support (or uv), OpenSSL, curl and unzip. Run `./scripts/lancer-pc` from the project directory. The first run needs internet access for dependencies and the French speech model. Keep the terminal open and visit [the desktop inbox](http://127.0.0.1:8743).

### 2. Build Android

Use OpenJDK 17+ and an Android SDK with a recent platform and Build Tools. Set `ANDROID_HOME` to the SDK directory. Run `./android/build.sh` to create a locally signed development build at `android/build/mon-cerveau.apk`. Keep the signing key to update the same installation later. For packaging, `./android/build.sh --unsigned` produces `android/build/mon-cerveau-unsigned.apk` for a distributor to sign.

### 3. Pair on home Wi-Fi

In the desktop settings, generate a pairing code. On Android, open **Réglages Android → Associer le PC** and paste the JSON. Treat it like a password. The phone uses its fingerprint to verify the PC certificate. If a phone is lost, `python3 cerveau.py unpair-all` on the PC revokes all paired devices.

### 4. Confirm a round trip

Share a link into My Brain on Android, return to home Wi-Fi and tap **Synchroniser**. Open the link’s note on the PC and turn it into a task. Sync again and check the task on the phone. For a voice test, record a short French sentence and leave the desktop service running until its text appears.

| Symptom | Check |
| --- | --- |
| The phone is waiting for the PC | Keep the server running, use the same Wi-Fi and check whether the home firewall permits the sync port (TCP 8744). |
| An email never appears | Enable notification access and check what the mail app shows in its preview. A date visible only inside an attachment is outside that preview. |
| A reminder is late | Allow notifications and precise alarms in the app settings. Android can defer approximate alarms. |
| The audio arrives without text | Check that the French model was downloaded. Open the memo and use **Transcrire sur ce PC** to retry. |

[Next: storage and backups](data.md)
