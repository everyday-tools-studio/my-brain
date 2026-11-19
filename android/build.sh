#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
SDK=${ANDROID_HOME:-${ANDROID_SDK_ROOT:-$HOME/Android/Sdk}}
bt=$(find "$SDK/build-tools" -mindepth 1 -maxdepth 1 -type d | sort -V | tail -1)
platform=$(find "$SDK/platforms" -name android.jar | sort -V | tail -1)
if ! command -v javac >/dev/null; then
    jdk=${JAVA_HOME:-/var/lib/flatpak/app/com.google.AndroidStudio/current/active/files/extra/jbr}
    export JAVA_HOME="$jdk" PATH="$jdk/bin:$PATH"
fi
command -v javac >/dev/null || { echo 'Définir JAVA_HOME (JDK 17 ou supérieur).' >&2; exit 1; }
test -f "$platform" && test -f ../web/index.html
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/classes" build
"$bt/aapt2" compile --dir res -o "$work/res.zip"
"$bt/aapt2" link -I "$platform" --manifest AndroidManifest.xml -A ../web -o "$work/base.apk" "$work/res.zip"
javac -encoding UTF-8 -source 11 -target 11 -classpath "$platform" -d "$work/classes" src/fr/moncerveau/app/*.java
(cd "$work/classes" && jar cf "$work/app.jar" .)
"$bt/d8" --min-api 33 --lib "$platform" --output "$work" "$work/app.jar"
(cd "$work" && zip -q base.apk classes.dex)
"$bt/zipalign" -f 4 "$work/base.apk" "$work/aligned.apk"
# F-Droid signs the release after compiling the published source.
if [[ ${1:-} == --unsigned ]]; then
    cp "$work/aligned.apk" build/mon-cerveau-unsigned.apk
    echo "APK pour signature de distribution : $PWD/build/mon-cerveau-unsigned.apk"
    exit 0
fi
if [[ ! -f "$HOME/.android/debug.keystore" ]]; then
    mkdir -p "$HOME/.android"
    keytool -genkeypair -keystore "$HOME/.android/debug.keystore" -storepass android -keypass android -alias androiddebugkey -dname CN=AndroidDebug -keyalg RSA -validity 10000
fi
"$bt/apksigner" sign --ks "$HOME/.android/debug.keystore" --ks-pass pass:android --out build/mon-cerveau.apk "$work/aligned.apk"
"$bt/apksigner" verify build/mon-cerveau.apk
echo "APK signé : $PWD/build/mon-cerveau.apk"
