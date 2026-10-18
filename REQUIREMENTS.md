# Anforderungen für Portfolio Insights Dashboard

## Projektzweck

Dieses Projekt bietet ein lokales Dashboard zur Analyse von Trade Republic Exportdateien. Es soll
Nutzern helfen, ihre Transaktionen, Portfolioentwicklung, Dividenden, realisierten Gewinne,
Ausgaben und Gebühren schnell, verständlich und sicher zu überblicken.

## Funktionale Anforderungen

- Benutzer können eine lokale Exportdatei hochladen (aktuell CSV; der Loader unterstützt
  zusätzlich Excel).
- Ohne eigene Datei startet die App mit einem Demo-Portfolio.
- Die App validiert die Datei und gibt klares Feedback bei Problemen.
- Die App stellt die importierten Transaktionen in einer filterbaren Tabelle dar.
- Die App zeigt Portfolio-Kennzahlen wie Portfoliowert, investiertes Kapital, Cash, Gebühren,
  Steuern und unrealisierten Gewinn/Verlust an.
- Die App bietet Übersichten für Portfolio, Allokation, Dividenden, Transaktionen, realisierte
  Gewinne, Ausgaben und einzelne Wertpapiere.
- Realisierte Gewinne und Verluste werden nach dem FIFO-Prinzip berechnet, vor und nach Steuern.
- Die App zeigt einfache Visualisierungen und Berichte im Streamlit-Interface.
- Erweiterungen an Importformaten oder Auswertungen sollen einfach hinzufügbar sein.

## Nicht-funktionale Anforderungen

- Die App läuft lokal ohne externe Authentifizierung.
- Transaktionsdaten verlassen den Rechner nicht. Für Marktdaten werden nur ISINs und Ticker an
  OpenFIGI und Yahoo Finance gesendet.
- Ohne Internetverbindung bleibt die App nutzbar; nur Marktdaten fehlen dann.
- Es werden keine Zugangsdaten gespeichert und keine Finanzdaten auf GitHub hochgeladen.
- Fehlermeldungen enthalten keine sensiblen Daten.
- Die Architektur soll modular sein, damit neue Analysemodule leicht hinzugefügt werden können.

## Ausgeschlossener Scope

- Keine Login-Automatisierung für Trade Republic.
- Kein Zugriff auf offizielle oder inoffizielle Trade Republic APIs.
- Keine automatische Synchronisierung des Portfolios.
- Kein Tracking oder Monitoring außerhalb der Kernfunktionalität.
- Keine Visualisierungen, die nicht direkt mit der Datenanalyse zusammenhängen.

## Wartbarkeit

- Das Hinzufügen neuer Einheiten (z. B. neue Importformate oder neue Auswertungen) soll ohne
  größeren Umbau möglich sein.
- Die Datenverarbeitung soll klar getrennt von der Darstellung sein.
- Code soll mit `pytest` testbar, mit `ruff` lintbar und mit `bandit` geprüft sein.
