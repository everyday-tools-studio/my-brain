package fr.moncerveau.app;

import android.content.Context;
import java.nio.charset.StandardCharsets;
import java.time.*;
import java.util.*;
import org.json.JSONObject;

final class Import {
  static void message(
      Context ctx,
      String origin,
      String sender,
      String message,
      long timestamp,
      String key,
      boolean excerpt) {
    if (message.isBlank() && sender.isBlank()) return;
    sender = Extract.shorten(sender, 300);
    message = Extract.shorten(message, 16000);
    Instant at = Instant.ofEpochMilli(timestamp);
    String source =
        origin
            + " · "
            + sender
            + "\n"
            + at
            + "\n"
            + (excerpt ? "Extrait de notification : " : "")
            + message;
    List<JSONObject> items = new ArrayList<>();
    for (Extract.Candidate found : Extract.analyse(sender, message, at, ZoneId.systemDefault())) {
      JSONObject v = Store.note(found.kind, found.title, "");
      Store.set(v, "source", source);
      Store.set(v, "when", found.when);
      items.add(v);
    }
    String digest =
        UUID.nameUUIDFromBytes(
                (origin + "\n" + key + "\n" + sender + "\n" + message)
                    .getBytes(StandardCharsets.UTF_8))
            .toString();
    Store.get(ctx).saveExtract(digest, items);
  }
}
