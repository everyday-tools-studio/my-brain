package fr.moncerveau.app;

import android.content.*;
import android.database.Cursor;
import android.database.sqlite.*;
import java.util.*;
import org.json.*;

final class Store extends SQLiteOpenHelper {
  private static Store instance;
  private final Context ctx;

  static synchronized Store get(Context c) {
    if (instance == null) instance = new Store(c.getApplicationContext());
    return instance;
  }

  private Store(Context c) {
    super(c, "cerveau.db", null, 1);
    ctx = c;
  }

  public void onCreate(SQLiteDatabase db) {
    db.execSQL(
        "CREATE TABLE items (id TEXT PRIMARY KEY, payload TEXT NOT NULL, base INTEGER NOT NULL,"
            + " dirty INTEGER NOT NULL)");
    db.execSQL("CREATE TABLE audio_chunks (id TEXT, seq INTEGER, chunk TEXT, PRIMARY KEY(id,seq))");
    db.execSQL("CREATE TABLE imported (id TEXT PRIMARY KEY)");
  }

  public void onUpgrade(SQLiteDatabase db, int old, int newer) {
    throw new IllegalStateException("Version de base inconnue");
  }

  static JSONObject from(String json) {
    try {
      return new JSONObject(json);
    } catch (JSONException e) {
      throw new IllegalArgumentException(e);
    }
  }

  static JSONObject set(JSONObject obj, String key, Object value) {
    try {
      return obj.put(key, value);
    } catch (JSONException e) {
      throw new IllegalArgumentException(e);
    }
  }

  static JSONObject result(String key, Object val) {
    return set(new JSONObject(), key, val);
  }

  static JSONObject note(String kind, String title, String body) {
    JSONObject v = new JSONObject();
    set(v, "id", UUID.randomUUID().toString());
    set(v, "kind", kind);
    set(v, "title", title);
    set(v, "body", body);
    return v;
  }

  synchronized JSONObject item(String id, boolean audio) {
    SQLiteDatabase db = getReadableDatabase();
    try (Cursor c = db.rawQuery("SELECT payload FROM items WHERE id=?", new String[] {id})) {
      if (!c.moveToFirst()) return null;
      JSONObject obj = from(c.getString(0));
      if (audio)
        try (Cursor chunks =
            db.rawQuery(
                "SELECT chunk FROM audio_chunks WHERE id=? ORDER BY seq", new String[] {id})) {
          StringBuilder data = new StringBuilder();
          while (chunks.moveToNext()) data.append(chunks.getString(0));
          if (data.length() > 0) set(obj, "audio", data.toString());
        }
      return obj;
    }
  }

  synchronized List<String> ids(boolean pending) {
    List<String> rows = new ArrayList<>();
    try (Cursor c =
        getReadableDatabase()
            .rawQuery(
                "SELECT id FROM items" + (pending ? " WHERE dirty=1" : "") + " ORDER BY rowid DESC",
                null)) {
      while (c.moveToNext()) rows.add(c.getString(0));
    }
    return rows;
  }

  synchronized JSONArray visible() {
    JSONArray arr = new JSONArray();
    for (String id : ids(false)) {
      JSONObject v = item(id, false);
      if (!v.optBoolean("deleted")) arr.put(v);
    }
    return arr;
  }

  private long[] version(String id) {
    try (Cursor c =
        getReadableDatabase()
            .rawQuery("SELECT base,dirty FROM items WHERE id=?", new String[] {id})) {
      return c.moveToFirst() ? new long[] {c.getLong(0), c.getLong(1)} : new long[] {0, 0};
    }
  }

  private void write(JSONObject v, long base, boolean dirty) {
    SQLiteDatabase db = getWritableDatabase();
    String id = v.optString("id");
    JSONObject meta = new JSONObject();
    for (Iterator<String> names = v.keys(); names.hasNext(); ) {
      String key = names.next();
      if (!key.equals("audio")) set(meta, key, v.opt(key));
    }
    Object raw = v.opt("audio");
    String data = raw instanceof String ? (String) raw : "";
    if (!data.isEmpty()) set(meta, "hasAudio", true);
    else meta.remove("hasAudio");
    if (data.length() > 24 * 1024 * 1024)
      throw new IllegalArgumentException("Mémo trop volumineux.");
    db.execSQL(
        "INSERT OR REPLACE INTO items VALUES(?,?,?,?)",
        new Object[] {id, meta.toString(), base, dirty ? 1 : 0});
    db.delete("audio_chunks", "id=?", new String[] {id});
    for (int offset = 0; offset < data.length(); offset += 256 * 1024) {
      db.execSQL(
          "INSERT INTO audio_chunks VALUES(?,?,?)",
          new Object[] {
            id, offset, data.substring(offset, Math.min(offset + 256 * 1024, data.length()))
          });
    }
  }

  synchronized JSONObject save(JSONObject v) {
    String id = v.optString("id");
    if (id.isEmpty()) {
      id = UUID.randomUUID().toString();
      set(v, "id", id);
    }
    JSONObject previous = item(id, false);
    if (previous != null && v.optLong("rev") != previous.optLong("rev"))
      throw new IllegalStateException("Cet élément a changé. Recharge-le avant la modification.");
    if (previous != null && previous.optBoolean("hasAudio") && !v.has("audio"))
      set(v, "audio", item(id, true).optString("audio"));
    long base = version(id)[0];
    set(v, "rev", previous == null ? 1 : previous.optLong("rev") + 1);
    SQLiteDatabase db = getWritableDatabase();
    db.beginTransaction();
    try {
      if (v.optBoolean("pinned") && !v.optBoolean("done") && !v.optBoolean("deleted")) {
        for (String other : ids(false)) {
          if (other.equals(id)) continue;
          JSONObject row = item(other, false);
          if (row.optBoolean("pinned")) {
            row = item(other, true);
            set(row, "pinned", false);
            set(row, "rev", row.optLong("rev") + 1);
            write(row, version(other)[0], true);
          }
        }
      }
      write(v, base, true);
      db.setTransactionSuccessful();
    } finally {
      db.endTransaction();
    }
    Alarm.schedule(ctx, v);
    changed();
    return v;
  }

  synchronized boolean saveExtract(String key, List<JSONObject> elements) {
    if (elements.isEmpty()) return false;
    SQLiteDatabase db = getWritableDatabase();
    db.beginTransaction();
    try {
      ContentValues seen = new ContentValues();
      seen.put("id", key);
      if (db.insertWithOnConflict("imported", null, seen, SQLiteDatabase.CONFLICT_IGNORE) < 0)
        return false;
      for (JSONObject v : elements) {
        set(v, "rev", 1);
        write(v, 0, true);
      }
      db.setTransactionSuccessful();
    } finally {
      db.endTransaction();
    }
    for (JSONObject v : elements) Alarm.schedule(ctx, v);
    changed();
    return true;
  }

  synchronized JSONObject pending(String id) {
    long[] ver = version(id);
    if (ver[1] == 0) return null;
    JSONObject v = item(id, true);
    set(v, "localGeneration", v.optLong("rev"));
    set(v, "rev", ver[0]);
    return v;
  }

  synchronized void acknowledge(String id, JSONObject sent, JSONObject received) {
    JSONObject current = item(id, false);
    if (current == null) return;
    long rev = received.optLong("rev");
    boolean same = current.optLong("rev") == sent.optLong("localGeneration");
    getWritableDatabase()
        .execSQL(
            "UPDATE items SET base=?, dirty=? WHERE id=?", new Object[] {rev, same ? 0 : 1, id});
  }

  synchronized void remote(JSONObject remote) {
    String id = remote.optString("id");
    long[] ver = version(id);
    long remoteRev = remote.optLong("rev");
    if (remoteRev <= ver[0]) return;
    SQLiteDatabase db = getWritableDatabase();
    db.beginTransaction();
    JSONObject previous = item(id, true);
    try {
      if (ver[1] != 0 && previous != null) {
        JSONObject copy = from(previous.toString());
        set(copy, "id", UUID.randomUUID().toString());
        set(copy, "rev", 1);
        set(copy, "title", "Conflit à vérifier · " + copy.optString("title"));
        set(copy, "kind", "review");
        set(copy, "deleted", false);
        set(copy, "pinned", false);
        if (previous.optBoolean("deleted"))
          set(copy, "body", "Suppression locale en conflit.\n" + copy.optString("body"));
        write(copy, 0, true);
      }
      JSONObject v = from(remote.toString());
      set(v, "rev", previous == null ? 1 : previous.optLong("rev") + 1);
      write(v, remoteRev, false);
      db.setTransactionSuccessful();
    } finally {
      db.endTransaction();
    }
    Alarm.schedule(ctx, remote);
  }

  private void changed() {
    Main.notifyUI();
    Sync.requestSoon(ctx);
  }
}
