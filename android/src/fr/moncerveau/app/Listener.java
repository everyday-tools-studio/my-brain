package fr.moncerveau.app;

import android.Manifest;
import android.app.Notification;
import android.app.Person;
import android.content.pm.PackageManager;
import android.os.*;
import android.service.notification.*;
import java.util.*;

public class Listener extends NotificationListenerService {
  private static final Set<String> SMS =
      new HashSet<>(
          Arrays.asList(
              "com.google.android.apps.messaging",
              "com.android.messaging",
              "com.samsung.android.messaging"));

  public void onNotificationPosted(StatusBarNotification sbn) {
    String pkg = sbn.getPackageName();
    String channel;
    switch (pkg) {
      case "com.whatsapp":
      case "com.whatsapp.w4b":
        channel = "WhatsApp";
        break;
      case "com.google.android.gm":
        channel = "Gmail";
        break;
      case "ch.protonmail.android":
        channel = "Proton Mail";
        break;
      default:
        if (!SMS.contains(pkg)
            || checkSelfPermission(Manifest.permission.RECEIVE_SMS)
                == PackageManager.PERMISSION_GRANTED) return;
        channel = "SMS";
        break;
    }
    Notification n = sbn.getNotification();
    if (n == null || n.extras == null || (n.flags & Notification.FLAG_GROUP_SUMMARY) != 0) return;
    Bundle b = n.extras;
    String title = value(b, Notification.EXTRA_TITLE);
    Parcelable[] messages = b.getParcelableArray(Notification.EXTRA_MESSAGES);
    if (messages != null && messages.length > 0) {
      for (Notification.MessagingStyle.Message m :
          Notification.MessagingStyle.Message.getMessagesFromBundleArray(messages)) {
        Person sender = m.getSenderPerson();
        if (sender == null) continue;
        String who = Objects.toString(sender.getName(), title);
        long timestamp = m.getTimestamp() > 0 ? m.getTimestamp() : sbn.getPostTime();
        Import.message(
            this,
            channel,
            who,
            Objects.toString(m.getText(), ""),
            timestamp,
            pkg + "|" + title + "|" + timestamp,
            true);
      }
      return;
    }
    String msg = value(b, Notification.EXTRA_BIG_TEXT);
    if (msg.isEmpty()) msg = value(b, Notification.EXTRA_TEXT);
    if (msg.isEmpty() && title.isEmpty()) return;
    long posted = n.when > 0 ? n.when : sbn.getPostTime();
    Import.message(this, channel, title, msg, posted, sbn.getKey() + "|" + posted, true);
  }

  private static String value(Bundle b, String key) {
    return Objects.toString(b.getCharSequence(key), "");
  }
}
