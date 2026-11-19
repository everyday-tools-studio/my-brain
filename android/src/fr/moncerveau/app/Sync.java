package fr.moncerveau.app;

import android.app.job.*;
import android.content.*;
import android.net.*;
import java.io.*;
import java.net.URI;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.security.cert.*;
import java.util.concurrent.*;
import javax.net.ssl.*;
import org.json.*;

final class Sync {
  private static final ScheduledExecutorService worker =
      Executors.newSingleThreadScheduledExecutor();
  private static ScheduledFuture<?> queued;

  static android.content.SharedPreferences prefs(Context c) {
    return c.getSharedPreferences("liaison", Context.MODE_PRIVATE);
  }

  static synchronized void requestSoon(Context c) {
    if (prefs(c).getString("token", "").isEmpty()) return;
    if (queued != null && !queued.isDone()) queued.cancel(false);
    queued = worker.schedule(() -> run(c), 1, TimeUnit.SECONDS);
  }

  static void job(Context c, Runnable finish) {
    worker.execute(
        () -> {
          try {
            run(c);
          } finally {
            finish.run();
          }
        });
  }

  static synchronized void pair(Context c, String raw) throws Exception {
    JSONObject config = new JSONObject(raw);
    String token = config.getString("token"),
        pin = config.getString("fingerprint").replace(":", "").toLowerCase(java.util.Locale.ROOT);
    URI uri = new URI(config.getString("url"));
    if (!"https".equals(uri.getScheme())
        || uri.getHost() == null
        || uri.getUserInfo() != null
        || uri.getQuery() != null
        || uri.getFragment() != null
        || !(uri.getPath().isEmpty() || uri.getPath().equals("/"))
        || !pin.matches("[a-f0-9]{64}")
        || token.trim().isEmpty()
        || token.contains("\n")
        || token.contains("\r")) throw new IllegalArgumentException("Code d’appairage invalide.");
    String old = prefs(c).getString("pin", "");
    if (!old.isEmpty() && !old.equals(pin))
      throw new IllegalArgumentException("Ce téléphone est déjà associé à un autre certificat PC.");
    prefs(c)
        .edit()
        .putString("url", "https://" + uri.getRawAuthority())
        .putString("token", token)
        .putString("pin", pin)
        .apply();
    register(c);
    requestSoon(c);
  }

  static void register(Context ctx) {
    if (prefs(ctx).getString("token", "").isEmpty()) return;
    JobInfo info =
        new JobInfo.Builder(751, new ComponentName(ctx, SyncJob.class))
            .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
            .setPersisted(true)
            .setPeriodic(15 * 60 * 1000)
            .build();
    JobScheduler scheduler = ctx.getSystemService(JobScheduler.class);
    if (scheduler.getPendingJob(751) == null) scheduler.schedule(info);
  }

  private static Network wifi(Context ctx) {
    ConnectivityManager cm = ctx.getSystemService(ConnectivityManager.class);
    Network n = cm.getActiveNetwork();
    NetworkCapabilities cap = n == null ? null : cm.getNetworkCapabilities(n);
    return cap != null && cap.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) ? n : null;
  }

  private static void run(Context ctx) {
    android.content.SharedPreferences pref = prefs(ctx);
    String base = pref.getString("url", "");
    if (base.isEmpty()) return;
    Network wifi = wifi(ctx);
    if (wifi == null) {
      status(ctx, "En attente du Wi-Fi");
      return;
    }
    try {
      String pin = pref.getString("pin", "");
      String token = pref.getString("token", "");
      Store s = Store.get(ctx);
      for (String id : s.ids(true)) {
        JSONObject v = s.pending(id);
        if (v == null) continue;
        JSONObject response = request(wifi, base + "/api/items", token, pin, v);
        if (response.optString("error").equals("conflict"))
          s.remote(response.getJSONObject("item"));
        else s.acknowledge(id, v, response.getJSONObject("item"));
      }
      long since = pref.getLong("cursor", 0);
      while (true) {
        JSONObject page =
            request(wifi, base + "/api/items?limit=1&since=" + since, token, pin, null);
        JSONArray records = page.getJSONArray("items");
        for (int i = 0; i < records.length(); i++) s.remote(records.getJSONObject(i));
        long next = page.getLong("cursor");
        pref.edit().putLong("cursor", next).apply();
        if (!page.optBoolean("more")) break;
        if (next <= since) throw new IOException("Curseur de synchronisation bloqué");
        since = next;
      }
      status(
          ctx,
          "Synchronisé · "
              + java.time.LocalTime.now()
                  .format(java.time.format.DateTimeFormatter.ofPattern("HH:mm")));
    } catch (Exception e) {
      status(
          ctx,
          "En attente du PC · "
              + (e instanceof IOException ? "connexion indisponible" : e.getMessage()));
    }
    Main.notifyUI();
  }

  static JSONObject request(Network n, String address, String token, String pin, JSONObject payload)
      throws Exception {
    X509TrustManager tm =
        new X509TrustManager() {
          public void checkClientTrusted(X509Certificate[] chain, String auth)
              throws CertificateException {
            throw new CertificateException();
          }

          public X509Certificate[] getAcceptedIssuers() {
            return new X509Certificate[0];
          }

          public void checkServerTrusted(X509Certificate[] chain, String auth)
              throws CertificateException {
            try {
              if (chain.length == 0) throw new CertificateException();
              StringBuilder hex = new StringBuilder();
              for (byte b : MessageDigest.getInstance("SHA-256").digest(chain[0].getEncoded()))
                hex.append(String.format(java.util.Locale.ROOT, "%02x", b & 255));
              if (!pin.contentEquals(hex))
                throw new CertificateException("Empreinte du PC différente.");
            } catch (GeneralSecurityException e) {
              throw new CertificateException(e);
            }
          }
        };
    SSLContext tls = SSLContext.getInstance("TLS");
    tls.init(null, new TrustManager[] {tm}, null);
    URL url = new URL(address);
    HttpsURLConnection h = (HttpsURLConnection) n.openConnection(url);
    try {
      h.setSSLSocketFactory(tls.getSocketFactory());
      h.setHostnameVerifier((host, session) -> host.equalsIgnoreCase(url.getHost()));
      h.setInstanceFollowRedirects(false);
      h.setConnectTimeout(3500);
      h.setReadTimeout(30000);
      h.setRequestProperty("Authorization", "Bearer " + token);
      if (payload != null) {
        byte[] bytes = payload.toString().getBytes(StandardCharsets.UTF_8);
        h.setRequestMethod("POST");
        h.setDoOutput(true);
        h.setFixedLengthStreamingMode(bytes.length);
        h.setRequestProperty("Content-Type", "application/json");
        try (OutputStream out = h.getOutputStream()) {
          out.write(bytes);
        }
      }
      int code = h.getResponseCode();
      if (code == 401 || code == 403)
        throw new IllegalArgumentException("autorisation refusée par le PC");
      if (code != 409 && (code < 200 || code >= 300))
        throw new IllegalArgumentException("réponse PC " + code);
      try (InputStream in = code == 409 ? h.getErrorStream() : h.getInputStream();
          ByteArrayOutputStream bytes = new ByteArrayOutputStream()) {
        byte[] buffer = new byte[16384];
        int read;
        while ((read = in.read(buffer)) != -1) {
          if (bytes.size() + read > 64 * 1024 * 1024) throw new IOException("Réponse trop grande");
          bytes.write(buffer, 0, read);
        }
        return new JSONObject(bytes.toString("UTF-8"));
      }
    } finally {
      h.disconnect();
    }
  }

  static void status(Context ctx, String msg) {
    prefs(ctx).edit().putString("status", msg).apply();
  }
}
