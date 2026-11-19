package fr.moncerveau.app;

import android.app.*;
import android.media.*;
import android.os.*;
import android.util.Base64;
import java.io.*;
import java.nio.file.Files;
import java.time.*;
import java.time.format.*;
import java.util.Locale;
import org.json.JSONObject;

final class Recorder {
  private final Main a;
  private MediaRecorder mic;
  private File file;
  private AlertDialog dialog;

  Recorder(Main a) {
    this.a = a;
  }

  void start() {
    if (mic != null) return;
    try {
      file = File.createTempFile("memo-", ".m4a", a.getCacheDir());
      mic = new MediaRecorder(a);
      mic.setAudioSource(MediaRecorder.AudioSource.MIC);
      mic.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4);
      mic.setAudioEncoder(MediaRecorder.AudioEncoder.AAC);
      mic.setAudioSamplingRate(16000);
      mic.setAudioEncodingBitRate(48000);
      mic.setMaxFileSize(10 * 1024 * 1024);
      mic.setMaxDuration(30 * 60 * 1000);
      mic.setOutputFile(file);
      mic.setOnInfoListener(
          (r, what, extra) -> {
            if (what == MediaRecorder.MEDIA_RECORDER_INFO_MAX_DURATION_REACHED
                || what == MediaRecorder.MEDIA_RECORDER_INFO_MAX_FILESIZE_REACHED) finish();
          });
      mic.prepare();
      mic.start();
      dialog =
          new AlertDialog.Builder(a)
              .setTitle("Mémo en cours")
              .setMessage(
                  "Parle, puis enregistre ton mémo. Le son sera disponible hors ligne, la"
                      + " transcription se fera sur ton PC après synchronisation.")
              .setCancelable(false)
              .setPositiveButton("Enregistrer", (d, w) -> finish())
              .setNegativeButton("Abandonner", (d, w) -> discard())
              .show();
    } catch (Exception e) {
      discard();
      a.toast("Micro indisponible : " + e.getMessage());
    }
  }

  void finish() {
    if (mic == null) return;
    try {
      mic.stop();
      String title =
          "Mémo · "
              + LocalDateTime.now()
                  .format(
                      DateTimeFormatter.ofPattern("d MMM 'à' HH:mm", Locale.FRENCH)
                          .withLocale(Locale.FRENCH));
      JSONObject v = Store.note("note", title, "");
      Store.set(
          v,
          "audio",
          "data:audio/mp4;base64,"
              + Base64.encodeToString(Files.readAllBytes(file.toPath()), Base64.NO_WRAP));
      Store.get(a).save(v);
      a.toast("Mémo enregistré sur le téléphone");
    } catch (Exception e) {
      a.toast("Impossible d’enregistrer ce mémo : " + e.getMessage());
    } finally {
      discard();
    }
  }

  private void discard() {
    if (mic != null) {
      mic.release();
      mic = null;
    }
    if (file != null) {
      file.delete();
      file = null;
    }
    if (dialog != null) {
      dialog.dismiss();
      dialog = null;
    }
  }
}
