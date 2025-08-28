# 🚶‍♂️ Walkability Analyzer für QGIS

Ein QGIS-Plugin zur Analyse der Fußgängerfreundlichkeit (Walkability) von Standorten in Münster und darüber hinaus.

![Plugin Status](https://img.shields.io/badge/status-beta-orange)
![QGIS Version](https://img.shields.io/badge/QGIS-3.0+-brightgreen)
![Python Version](https://img.shields.io/badge/Python-3.6+-blue)
![License](https://img.shields.io/badge/license-GPL%20v2+-green)

## Features

### Standort-Auswahl
- Stadtteil-Modus (Münster)
- Koordinaten-Modus (Lat/Lon)
- Adress-Modus (Geocodierung)

### Analyse
- Isochrone (5–20 min Fußweg)
- POIs via OpenStreetMap
- Walkability-Score (0–100)
- Service-Kategorien: Supermarkt, Apotheke, Arzt, Schule, Restaurant, Bank

### Ergebnisse
- QGIS-Layer (Isochrone, Zentrum, POIs)
- Bewertung + Empfehlungen
- PDF-Export für Berichte

## Schnellstart

Plugin nach QGIS Plugin-Ordner kopieren:
```bash
Windows: C:\Users\[Name]\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\
Linux:   ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/
```
## ReportLab Installation (für PDF-Export)

Der PDF-Export benötigt die Python-Bibliothek **reportlab**.  
Falls sie nicht installiert ist, kann man sie über die **OSGeo4W Shell** nachinstallieren:

### Windows (OSGeo4W Installation)
1. **OSGeo4W Shell** öffnen (Startmenü → „OSGeo4W Shell“).  
2. Folgenden Befehl eingeben:
    ```bash
    python3 -m pip install --user reportlab
    ```
### Linux
1. In einem Terminal ausführen
    ```bash
    python3 -m pip install --user reportlab
    ```

## Systemanforderungen
- QGIS 3.0+
- Python 3.6+
- Internetzugang (ORS & OSM)

## Walkability-Score – Wie wird er berechnet?

1. **POIs sammeln:** Für gewählte Services (z. B. Supermarkt, Arzt) werden alle erreichbaren POIs in der Isochrone gesucht.  
2. **Distanz zum nächsten POI:** Für jede Kategorie wird die Entfernung zum nächstgelegenen POI berechnet.  
3. **Einzugsradius:** Maximal mögliche Distanz = Gehgeschwindigkeit (80 m/min) × Zeitlimit.  
4. **Rohscore:**  
   ```math
   \text{raw} = 100 \times \left(1 - \frac{\text{Distanz}}{\text{Reichweite}}\right)
   ```
   Werte kleiner 0 → 0, größer 100 → 100.  
5. **Gewichtung:** Jede Kategorie hat ein Gewicht (z. B. Supermarkt = 0.2).  
6. **Gesamtwert:** Gewichtetes Mittel aller Kategorien.  

**Beispiel:**  
- Supermarkt 200 m → Score 90 × Gewicht 0.2 = 18  
- Apotheke 600 m → Score 60 × Gewicht 0.2 = 12  
- … usw.  
**Gesamt-Score = Summe der gewichteten Scores ÷ Summe der Gewichte**

### Bewertungsskala
- 🟢 80–100: Sehr gute Walkability  
- 🟡 60–79: Gute Walkability  
- 🟠 40–59: Durchschnittliche Walkability
- 🔴 0–39: Schwache Walkability

## Export
- **Layer:** Isochrone, Center, POIs  
- **PDF:** Zusammenfassung, Detailtabelle, Empfehlungen, Kartenausschnitt, Legende  

## Konfiguration
- **API-Key:** In `config.py` → `ORS_API_KEY` eintragen  