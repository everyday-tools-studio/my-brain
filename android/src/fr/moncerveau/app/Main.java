package fr.moncerveau.app;

import android.Manifest;
import android.app.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.graphics.Insets;
import android.net.*;
import android.os.*;
import android.provider.Settings;
import android.webkit.*;
import android.widget.*;
import java.io.*;
import java.lang.ref.WeakReference;
import java.util.*;
import org.json.*;

public class Main extends Activity {
  private WebView web;
  private Recorder recorder;
  private static WeakReference<Main> current = new WeakReference<>(null);
  private static final String ORIGIN = "https://moncerveau.invalid";
  private final Handler tick = new Handler(Looper.getMainLooper());
  private final Runnable refreshTick =
      new Runnable() {
        public void run() {
          Sync.requestSoon(getApplicationContext());
          tick.postDelayed(this, 60000);
        }
      };

  static void notifyUI() {
    Main a = current.get();
    if (a != null)
      a.runOnUiThread(
          () -> {
            if (!a.isDestroyed() && a.web != null)
              a.web.evaluateJavascript("window.dispatchEvent(new Event('itemschange'))", null);
          });
  }

  public void onCreate(Bundle state) {
    super.onCreate(state);
    current = new WeakReference<>(this);
    web = new WebView(this);
    FrameLayout frame = new FrameLayout(this);
    frame.setBackgroundColor(android.graphics.Color.rgb(245, 243, 236));
    frame.addView(web, new FrameLayout.LayoutParams(-1, -1));
    getWindow()
        .getInsetsController()
        .setSystemBarsAppearance(
            android.view.WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS
                | android.view.WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS,
            android.view.WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS
                | android.view.WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS);
    frame.setOnApplyWindowInsetsListener(
        (view, window) -> {
          Insets pad =
              window.getInsets(
                  android.view.WindowInsets.Type.systemBars()
                      | android.view.WindowInsets.Type.displayCutout()
                      | android.view.WindowInsets.Type.ime());
          view.setPadding(pad.left, pad.top, pad.right, pad.bottom);
          return window;
        });
    web.getSettings().setJavaScriptEnabled(true);
    web.getSettings().setDomStorageEnabled(true);
    web.getSettings().setAllowFileAccess(false);
    web.getSettings().setAllowContentAccess(false);
    web.getSettings().setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
    web.setWebViewClient(
        new WebViewClient() {
          public boolean shouldOverrideUrlLoading(WebView w, WebResourceRequest r) {
            return !ORIGIN.equals(r.getUrl().getScheme() + "://" + r.getUrl().getAuthority())
                || !"/index.html".equals(r.getUrl().getPath());
          }

          public WebResourceResponse shouldInterceptRequest(WebView w, WebResourceRequest r) {
            Uri uri = r.getUrl();
            String path = uri.getPath();
            if ("https".equals(uri.getScheme())
                && "moncerveau.invalid".equals(uri.getAuthority())
                && path != null
                && path.matches("/[a-zA-Z0-9_.-]+")
                && r.getMethod().equals("GET")) {
              String mime =
                  path.endsWith(".html")
                      ? "text/html"
                      : path.endsWith(".css")
                          ? "text/css"
                          : path.endsWith(".js") ? "application/javascript" : null;
              if (mime != null)
                try {
                  Map<String, String> headers = new HashMap<>();
                  headers.put(
                      "Content-Security-Policy",
                      "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline';"
                          + " img-src 'self' data:; media-src data: blob:; object-src 'none';"
                          + " frame-src 'none'; base-uri 'none'; form-action 'none'");
                  return new WebResourceResponse(
                      mime, "UTF-8", 200, "OK", headers, getAssets().open(path.substring(1)));
                } catch (IOException ignored) {
                }
            }
            return new WebResourceResponse(
                "text/plain",
                "UTF-8",
                404,
                "Not found",
                Collections.emptyMap(),
                new ByteArrayInputStream(new byte[0]));
          }
        });
    recorder = new Recorder(this);
    web.addJavascriptInterface(new Bridge(), "Android");
    setContentView(frame);
    if (state == null) receive(getIntent());
    web.loadUrl(ORIGIN + "/index.html");
    Sync.register(this);
  }

  protected void onResume() {
    super.onResume();
    tick.post(refreshTick);
  }

  protected void onPause() {
    super.onPause();
    tick.removeCallbacks(refreshTick);
  }

  protected void onDestroy() {
    recorder.finish();
    web.removeJavascriptInterface("Android");
    web.destroy();
    web = null;
    super.onDestroy();
  }

  protected void onNewIntent(Intent i) {
    super.onNewIntent(i);
    receive(i);
  }

  private void receive(Intent i) {
    if (i == null || !Intent.ACTION_SEND.equals(i.getAction()) || !"text/plain".equals(i.getType()))
      return;
    CharSequence shared = i.getCharSequenceExtra(Intent.EXTRA_TEXT);
    if (shared == null || shared.toString().trim().isEmpty()) return;
    String text = Extract.shorten(shared.toString().trim(), 65000);
    JSONObject v = Store.note("note", Extract.shorten(text.split("\n", 2)[0], 100), text);
    Store.get(this).save(v);
    toast("Partage enregistré sur le téléphone");
  }

  void toast(String msg) {
    Toast.makeText(this, msg, Toast.LENGTH_LONG).show();
  }

  class Bridge {
    @JavascriptInterface
    public String listItems() {
      return Store.result("items", Store.get(Main.this).visible()).toString();
    }

    @JavascriptInterface
    public String getItem(String id) {
      JSONObject v = Store.get(Main.this).item(id, true);
      return v == null
          ? Store.result("error", "Élément introuvable").toString()
          : Store.result("item", v).toString();
    }

    @JavascriptInterface
    public String saveItem(String json) {
      try {
        return Store.result("item", Store.get(Main.this).save(new JSONObject(json))).toString();
      } catch (Exception e) {
        return Store.result("error", e.getMessage()).toString();
      }
    }

    @JavascriptInterface
    public String deleteItem(String id, long rev) {
      JSONObject v = Store.get(Main.this).item(id, true);
      if (v == null) return Store.result("error", "Élément introuvable").toString();
      Store.set(v, "deleted", true);
      Store.set(v, "rev", rev);
      return saveItem(v.toString());
    }

    @JavascriptInterface
    public String getStatus() {
      return Sync.prefs(Main.this).getString("status", "PC à associer");
    }

    @JavascriptInterface
    public void refresh() {
      Sync.requestSoon(getApplicationContext());
    }

    @JavascriptInterface
    public void settings() {
      runOnUiThread(() -> menu());
    }

    @JavascriptInterface
    public void record() {
      runOnUiThread(
          () -> {
            if (checkSelfPermission(Manifest.permission.RECORD_AUDIO)
                != PackageManager.PERMISSION_GRANTED)
              requestPermissions(new String[] {Manifest.permission.RECORD_AUDIO}, 10);
            else recorder.start();
          });
    }

    @JavascriptInterface
    public void openLink(String value) {
      runOnUiThread(
          () -> {
            Uri u = Uri.parse(value);
            if (u.getHost() != null
                && ("https".equals(u.getScheme()) || "http".equals(u.getScheme())))
              open(new Intent(Intent.ACTION_VIEW, u).addCategory(Intent.CATEGORY_BROWSABLE));
          });
    }
  }

  private void open(Intent i) {
    try {
      startActivity(i);
    } catch (ActivityNotFoundException e) {
      toast("Aucune application disponible");
    }
  }

  private void menu() {
    boolean listen =
        getSystemService(NotificationManager.class)
            .isNotificationListenerAccessGranted(new ComponentName(this, Listener.class));
    String[] choices = {
      "Associer le PC",
      "Lecture des notifications · " + (listen ? "active" : "à autoriser"),
      "Lecture directe des SMS · " + permitted(Manifest.permission.RECEIVE_SMS),
      "Rappels de rendez-vous · " + permitted(Manifest.permission.POST_NOTIFICATIONS),
      "Précision des rappels · "
          + (getSystemService(AlarmManager.class).canScheduleExactAlarms()
              ? "exacte"
              : "approximative"),
      "Synchroniser maintenant"
    };
    new AlertDialog.Builder(this)
        .setTitle("Réglages Android")
        .setItems(
            choices,
            (d, index) -> {
              switch (index) {
                case 0:
                  pairDialog();
                  break;
                case 1:
                  new AlertDialog.Builder(this)
                      .setTitle("Lecture locale des notifications")
                      .setMessage(
                          "Android demande un accès général aux notifications. Mon cerveau traite"
                              + " les aperçus de Gmail, Proton Mail, WhatsApp et Messages. Les"
                              + " discussions en sourdine, les aperçus masqués et les pièces"
                              + " jointes peuvent manquer.")
                      .setPositiveButton(
                          "Ouvrir les réglages",
                          (p, x) ->
                              open(new Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)))
                      .setNegativeButton("Fermer", null)
                      .show();
                  break;
                case 2:
                  permission(Manifest.permission.RECEIVE_SMS, 11);
                  break;
                case 3:
                  permission(Manifest.permission.POST_NOTIFICATIONS, 12);
                  break;
                case 4:
                  if (!getSystemService(AlarmManager.class).canScheduleExactAlarms())
                    open(
                        new Intent(
                            Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM,
                            Uri.parse("package:" + getPackageName())));
                  else toast("Les rappels exacts sont autorisés");
                  break;
                case 5:
                  Sync.requestSoon(getApplicationContext());
                  toast("Recherche du PC sur le Wi-Fi");
                  break;
              }
            })
        .show();
  }

  private String permitted(String p) {
    return checkSelfPermission(p) == PackageManager.PERMISSION_GRANTED ? "autorisé" : "à autoriser";
  }

  private void permission(String perm, int id) {
    if (checkSelfPermission(perm) == PackageManager.PERMISSION_GRANTED) {
      open(
          new Intent(
              Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
              Uri.parse("package:" + getPackageName())));
      return;
    }
    requestPermissions(new String[] {perm}, id);
  }

  private void pairDialog() {
    EditText edit = new EditText(this);
    edit.setHint("Colle le code JSON affiché sur le PC");
    edit.setSingleLine(false);
    edit.setInputType(
        android.text.InputType.TYPE_CLASS_TEXT
            | android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD);
    new AlertDialog.Builder(this)
        .setTitle("Associer le PC")
        .setMessage("Sur le PC, ouvre le service Wi-Fi puis génère un code d’appairage.")
        .setView(edit)
        .setPositiveButton(
            "Associer",
            (d, w) -> {
              try {
                Sync.pair(getApplicationContext(), edit.getText().toString());
                edit.setText("");
                toast("Liaison enregistrée");
              } catch (Exception e) {
                toast("Appairage impossible : " + e.getMessage());
              }
            })
        .setNegativeButton("Annuler", null)
        .show();
  }

  public void onRequestPermissionsResult(int code, String[] permissions, int[] results) {
    super.onRequestPermissionsResult(code, permissions, results);
    if (results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED) {
      if (code == 10) recorder.start();
      if (code == 12) Boot.rearm(this);
    } else toast("Autorisation désactivée. Tu peux la modifier dans les réglages Android.");
  }
}
