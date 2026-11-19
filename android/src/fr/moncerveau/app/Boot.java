package fr.moncerveau.app;

import android.content.*;

public class Boot extends BroadcastReceiver {
  public void onReceive(Context c, Intent i) {
    rearm(c);
    Sync.register(c);
  }

  static void rearm(Context c) {
    Store s = Store.get(c);
    for (String id : s.ids(false)) Alarm.schedule(c, s.item(id, false));
  }
}
