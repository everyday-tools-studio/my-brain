package fr.moncerveau.app;

import java.time.*;
import java.util.*;

final class ExtractTest {
  private static List<Extract.Candidate> parse(String input) {
    return Extract.analyse(
        "Camille", input, Instant.parse("2026-11-18T23:15:00Z"), ZoneId.of("Europe/Paris"));
  }

  private static void check(boolean value, String reason) {
    if (!value) throw new AssertionError(reason);
  }

  public static void main(String[] args) {
    List<Extract.Candidate> all =
        parse("RDV demain à 9 h. Pense à apporter le dossier. Code de porte : 5839.");
    check(all.size() == 3, "Extraire 3 éléments");
    check(all.get(0).title.equals("RDV demain à 9 h"), "Limiter le titre au rendez-vous");
    check(
        all.get(0).kind.equals("event") && all.get(0).when.equals("2026-11-20T08:00:00Z"),
        "Jour local du message");
    check(all.get(1).kind.equals("task") && all.get(2).kind.equals("note"), "Tâche et information");
    check(parse("Mardi à 14 h").get(0).kind.equals("review"), "Date ambiguë");
    check(
        parse("RDV le 20 novembre à 9h15").get(0).when.equals("2026-11-20T08:15:00Z"),
        "Date en lettres");
    check(parse("RDV 31/02 à 10h").get(0).kind.equals("review"), "Date impossible");
    check(parse("Rendez-vous demain 9h ou 17h").get(0).kind.equals("review"), "Plusieurs options");
    check(parse("RDV demain 9h annulé").get(0).kind.equals("review"), "Annulation");
    check(parse("Merci, à bientôt !").isEmpty(), "Message sans élément utile");
    check(
        parse("RDV le 28/03/2027 à 2h30").get(0).kind.equals("review"),
        "Heure inexistante du passage à l’heure d’été");
    check(parse("Pense a apporter le dossier.").get(0).kind.equals("task"), "Clavier sans accent");
    check(
        parse("Reunion le 20 aout 2027 a 9h 12 rue des Fleurs").size() == 2,
        "Adresse et réunion sans ponctuation");
    check(
        parse("Reunion le 20 aout 2027 a 9h 12 rue des Fleurs")
            .get(0)
            .when
            .equals("2027-08-20T07:00:00Z"),
        "Le numéro de rue ne représente pas les minutes");
    System.out.println("Extraction française : parcours vérifiés");
  }
}
