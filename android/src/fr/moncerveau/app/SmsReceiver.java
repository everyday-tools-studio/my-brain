package fr.moncerveau.app;

import android.content.*;
import android.provider.Telephony;
import android.telephony.SmsMessage;
import java.util.Objects;

public class SmsReceiver extends BroadcastReceiver {
  public void onReceive(Context c, Intent intent) {
    if (!Telephony.Sms.Intents.SMS_RECEIVED_ACTION.equals(intent.getAction())) return;
    SmsMessage[] parts = Telephony.Sms.Intents.getMessagesFromIntent(intent);
    if (parts == null || parts.length == 0) return;
    StringBuilder text = new StringBuilder();
    for (SmsMessage p : parts) if (p != null) text.append(Objects.toString(p.getMessageBody(), ""));
    SmsMessage first = parts[0];
    if (first == null) return;
    Import.message(
        c,
        "SMS",
        Objects.toString(first.getOriginatingAddress(), ""),
        text.toString(),
        first.getTimestampMillis(),
        Long.toString(first.getTimestampMillis()),
        false);
  }
}
