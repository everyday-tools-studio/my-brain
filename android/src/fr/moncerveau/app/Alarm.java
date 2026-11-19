package fr.moncerveau.app;

import android.app.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.net.Uri;
import java.time.*;
import org.json.JSONObject;

public class Alarm extends BroadcastReceiver {
  static long time(String value) {
    try {
      return Instant.parse(value).toEpochMilli();
    } catch (Exception e) {
      try {
        return OffsetDateTime.parse(value).toInstant().toEpochMilli();
      } catch (Exception ignored) {
        try {
          return LocalDateTime.parse(value)
              .atZone(ZoneId.systemDefault())
              .toInstant()
              .toEpochMilli();
        } catch (Exception ignored2) {
          return 0;
        }
      }
    }
  }

  static void schedule(Context c, JSONObject v) {
    String id = v.optString("id");
    Intent intent =
        new Intent(c, Alarm.class)
            .setData(
                new Uri.Builder().scheme("moncerveau").authority("rdv").appendPath(id).build());
    PendingIntent p =
        PendingIntent.getBroadcast(
            c, 0, intent, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
    AlarmManager am = c.getSystemService(AlarmManager.class);
    am.cancel(p);
    if (!v.optString("kind").equals("event") || v.optBoolean("deleted") || v.optBoolean("done"))
      return;
    long start = time(v.optString("when")), now = System.currentTimeMillis();
    if (start <= now) return;
    long at = Math.max(now + 500, start - 30 * 60 * 1000L);
    if (at <= now + 500
        && id.concat("@" + start).equals(c.getSharedPreferences("rappels", 0).getString(id, "")))
      return;
    if (am.canScheduleExactAlarms()) am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, p);
    else am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, p);
  }

  public void onReceive(Context c, Intent i) {
    if (i.getData() == null) return;
    String id = i.getData().getLastPathSegment();
    JSONObject v = Store.get(c).item(id, false);
    if (v == null
        || !v.optString("kind").equals("event")
        || v.optBoolean("deleted")
        || v.optBoolean("done")) return;
    long start = time(v.optString("when"));
    if (start <= System.currentTimeMillis()) return;
    if (c.checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS)
        != PackageManager.PERMISSION_GRANTED) return;
    NotificationManager nm = c.getSystemService(NotificationManager.class);
    nm.createNotificationChannel(
        new NotificationChannel(
            "rendezvous", "Rappels de rendez-vous", NotificationManager.IMPORTANCE_HIGH));
    PendingIntent open =
        PendingIntent.getActivity(c, 0, new Intent(c, Main.class), PendingIntent.FLAG_IMMUTABLE);
    String clock =
        java.time.Instant.ofEpochMilli(start)
            .atZone(ZoneId.systemDefault())
            .toLocalTime()
            .format(java.time.format.DateTimeFormatter.ofPattern("HH:mm"));
    Notification alert =
        new Notification.Builder(c, "rendezvous")
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle("Rendez-vous à " + clock)
            .setContentText(v.optString("title"))
            .setContentIntent(open)
            .setAutoCancel(true)
            .setVisibility(Notification.VISIBILITY_PRIVATE)
            .build();
    nm.notify(id, 1, alert);
    c.getSharedPreferences("rappels", 0).edit().putString(id, id + "@" + start).apply();
  }
}
