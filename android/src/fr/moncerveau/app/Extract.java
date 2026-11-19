package fr.moncerveau.app;

import java.text.Normalizer;
import java.time.*;
import java.util.*;
import java.util.regex.*;

final class Extract {
  private static final int FLAGS = Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE;

  private static Pattern pattern(String re) {
    String accents =
        re.replace("à", "[aà]")
            .replace("é", "[eé]")
            .replace("è", "[eè]")
            .replace("ê", "[eê]")
            .replace("û", "[uû]");
    return Pattern.compile(accents, FLAGS);
  }

  private static String fold(String value) {
    return Normalizer.normalize(value.toLowerCase(Locale.FRENCH), Normalizer.Form.NFD)
        .replaceAll("\\p{M}+", "");
  }

  private static final Pattern EVENT =
      pattern(
          "\\b(rdv|rendez[-"
              + " ]vous|réunion|consultation|invitation|booking|appointment|réservation|confirmation"
              + " de votre visite)\\b");
  private static final Pattern HOUR =
      pattern(
          "\\b([01]?\\d|2[0-3])(?:\\s*h(?:eures?)?\\s*(?:([0-5]\\d)\\b(?!\\s+(?:rue|avenue|allée|boulevard|impasse|place|chemin)\\b))?|:([0-5]\\d)\\b)");
  private static final Pattern DATE =
      pattern("(?<![\\d/.-])(\\d{1,2})[/.\\-](\\d{1,2})(?:[/.\\-](\\d{4}|\\d{2}))?(?![\\d/.-])");
  private static final String MONTHS =
      "janvier février mars avril mai juin juillet août septembre octobre novembre décembre";
  private static final Pattern NAMED =
      pattern("\\b(\\d{1,2})(?:er)?\\s+(" + MONTHS.replace(" ", "|") + ")(?:\\s+(20\\d{2}))?\\b");
  private static final Pattern UNRELIABLE =
      pattern("\\b(annul\\p{L}*|reporté\\p{L}*|déplacé\\p{L}*|peut-être|éventuellement)\\b|\\?");
  private static final Pattern TASK =
      pattern(
          "\\b(pense[sz]? à|n.oublie[sz]? (?:pas )?de|il faut|merci de|à"
              + " faire\\s*[:：]|peux.tu|pourrais.tu)\\s+([^.!?\\n"
              + "]+)");
  private static final Pattern INFO =
      pattern(
          "\\b(?:(?:code (?:de (?:la )?porte|d.accès)|digicode|adresse)\\s*[:：=#]?\\s*[^.!?\\n"
              + "]+|\\d{1,4}(?:\\s*(?:bis|ter))?[,"
              + " ]+\\s*(?:rue|avenue|allée|boulevard|impasse|place|chemin)\\s+[^.!?\\n"
              + "]+)");

  static final class Candidate {
    final String kind, title, when;

    Candidate(String kind, String title, String when) {
      this.kind = kind;
      this.title = title;
      this.when = when;
    }
  }

  static List<Candidate> analyse(String subject, String body, Instant received, ZoneId zone) {
    List<Candidate> result = new ArrayList<>();
    String message = (subject + "\n" + body).trim();
    Matcher hour = HOUR.matcher(message);
    boolean hasHour = hour.find();
    boolean relative =
        pattern("\\b(aujourd.hui|demain|lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\\b")
            .matcher(message)
            .find();
    if (EVENT.matcher(message).find()
        || (hasHour
            && (relative || DATE.matcher(message).find() || NAMED.matcher(message).find()))) {
      LocalDate date = resolve(message, received.atZone(zone).toLocalDate());
      String when = "";
      if (date != null && hasHour && !UNRELIABLE.matcher(message).find()) {
        String minute = hour.group(2) != null ? hour.group(2) : hour.group(3);
        LocalTime time =
            LocalTime.of(
                Integer.parseInt(hour.group(1)), minute == null ? 0 : Integer.parseInt(minute));
        LocalDateTime local = date.atTime(time);
        if (!hour.find() && zone.getRules().getValidOffsets(local).size() == 1)
          when = local.atZone(zone).toInstant().toString();
      }
      String title = "Rendez-vous";
      for (String sentence : message.split("[.!?;]\\s+|\\n+")) {
        if (EVENT.matcher(sentence).find() || HOUR.matcher(sentence).find()) {
          String label = INFO.matcher(TASK.matcher(sentence).replaceAll("")).replaceAll("").trim();
          if (!label.isEmpty()) title = label;
          break;
        }
      }
      result.add(new Candidate(when.isEmpty() ? "review" : "event", shorten(title, 140), when));
    }
    Matcher tasks = TASK.matcher(message);
    while (tasks.find()) result.add(new Candidate("task", shorten(tasks.group(2).trim(), 140), ""));
    Matcher info = INFO.matcher(message);
    while (info.find()) result.add(new Candidate("note", shorten(info.group().trim(), 140), ""));
    return result;
  }

  static String shorten(String s, int max) {
    return s.length() <= max ? s : s.substring(0, max - 1) + "…";
  }

  private static LocalDate resolve(String message, LocalDate today) {
    Set<LocalDate> dates = new HashSet<>();
    String lower = fold(message);
    if (lower.contains("apres-demain") || lower.contains("apres demain"))
      dates.add(today.plusDays(2));
    else if (pattern("\\bdemain\\b").matcher(message).find()) dates.add(today.plusDays(1));
    if (pattern("\\baujourd.hui\\b").matcher(message).find()) dates.add(today);
    Matcher numeric = DATE.matcher(message), named = NAMED.matcher(message);
    try {
      while (numeric.find())
        dates.add(
            date(
                today,
                Integer.parseInt(numeric.group(1)),
                Integer.parseInt(numeric.group(2)),
                numeric.group(3)));
      while (named.find())
        dates.add(
            date(
                today,
                Integer.parseInt(named.group(1)),
                1 + Arrays.asList(fold(MONTHS).split(" ")).indexOf(fold(named.group(2))),
                named.group(3)));
    } catch (DateTimeException e) {
      return null;
    }
    return dates.size() == 1 ? dates.iterator().next() : null;
  }

  private static LocalDate date(LocalDate today, int day, int month, String y) {
    int year = y == null ? today.getYear() : Integer.parseInt(y);
    if (year < 100) year += 2000;
    LocalDate dayValue = LocalDate.of(year, month, day);
    return y == null && dayValue.isBefore(today) ? dayValue.plusYears(1) : dayValue;
  }
}
