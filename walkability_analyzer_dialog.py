import os
from datetime import datetime
from urllib.parse import urlencode

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog, QMessageBox, QFileDialog
from qgis.PyQt.QtCore import QUrl, QEventLoop, QTimer
from qgis.PyQt.QtNetwork import QNetworkRequest
from qgis.core import QgsMessageLog, Qgis, QgsNetworkAccessManager

from .config import MUENSTER_DISTRICTS, SERVICE_CATEGORIES, is_valid_coordinate, NOMINATIM_URL


FORM_CLASS, _ = uic.loadUiType(os.path.join(os.path.dirname(__file__), 'walkability_analyzer_dialog_base.ui'))


class WalkabilityAnalyzerDialog(QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        self.current_analysis = None
        self.current_coordinates = None
        self.analyzer = None
        self.current_display_name = None


        self.init_gui()
        self.connect_signals()

        self.lineEdit_address.textChanged.connect(self.on_address_changed)
        self.pushButton_geocode.clicked.connect(self.on_geocode_clicked)

    # ---------- UI init ----------
    def init_gui(self):
        self.comboBox_district.clear()
        self.comboBox_district.addItems(sorted(MUENSTER_DISTRICTS.keys()))

        self.slider_time.setMinimum(5); self.slider_time.setMaximum(20); self.slider_time.setValue(15)
        self.update_time_label()

        self.checkBox_supermarket.setChecked(True)
        self.checkBox_pharmacy.setChecked(True)
        self.checkBox_doctor.setChecked(True)
        self.checkBox_school.setChecked(True)
        self.checkBox_restaurant.setChecked(False)
        self.checkBox_bank.setChecked(False)

        self.tabWidget_location.setCurrentIndex(0)
        self.textBrowser_results.setPlainText("Bereit für Analyse...")
        self.pushButton_export.setEnabled(False)
        self.pushButton_geocode.setEnabled(False)

        self.lineEdit_latitude.textChanged.connect(self.validate_coordinates)
        self.lineEdit_longitude.textChanged.connect(self.validate_coordinates)

    def connect_signals(self):
        self.slider_time.valueChanged.connect(self.update_time_label)
        self.tabWidget_location.currentChanged.connect(self.on_location_tab_changed)
        self.pushButton_analyze.clicked.connect(self.analyze_walkability)
        self.pushButton_export.clicked.connect(self.export_pdf)
        self.pushButton_reset.clicked.connect(self.reset_analysis)
        self.pushButton_close.clicked.connect(self.close)
        self.comboBox_district.currentTextChanged.connect(self.on_district_changed)

    # ---------- Small sync HTTP helper ----------
    def _http_get_json(self, base_url: str, params: dict, timeout_ms: int = 8000):
        url = QUrl(base_url); url.setQuery(urlencode(params, doseq=True, safe=",:"))
        req = QNetworkRequest(url)
        req.setRawHeader(b"User-Agent", b"WA/1.0")
        nam = QgsNetworkAccessManager.instance()
        reply = nam.get(req)

        loop = QEventLoop()
        timer = QTimer(); timer.setSingleShot(True); timer.timeout.connect(loop.quit)
        timer.start(max(500, timeout_ms))
        reply.finished.connect(loop.quit)
        loop.exec_()

        raw = bytes(reply.readAll())
        status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute) or 0
        reply.deleteLater()

        if int(status) != 200 or not raw:
            return None
        import json
        try:
            return json.loads(raw.decode("utf-8", errors="replace"))
        except Exception:
            return None

    # ---------- Address search ----------
    def on_address_changed(self, text: str):
        self.current_display_name = None
        self.pushButton_geocode.setEnabled(bool((text or "").strip()))
        if not text:
            self.current_coordinates = None
            self.label_geocode_result.setText('Adresse eingeben und auf "Suchen" klicken.')
        self.update_analyze_button()

    def on_geocode_clicked(self):
        q = (self.lineEdit_address.text() or "").strip()
        if not q:
            return
        self.pushButton_geocode.setEnabled(False); self.pushButton_geocode.setText("🔄 Suche…")
        self.label_geocode_result.setText("🔄 Geocodierung…")

        params = {"q": q, "format": "json", "limit": 1, "countrycodes": "de", "addressdetails": 0, "accept-language": "de"}
        data = self._http_get_json(NOMINATIM_URL, params)
        if not data and "münster" not in q.lower():
            params["q"] = q + ", Münster, Germany"
            data = self._http_get_json(NOMINATIM_URL, params)

        if data:
            hit = data[0]
            lat, lon = float(hit["lat"]), float(hit["lon"])
            self.current_coordinates = [lon, lat]
            self.current_display_name = hit.get("display_name") or q
            self.label_geocode_result.setText(
                f"✅ {self.current_display_name}<br/><i>Koordinaten: {lat:.6f}, {lon:.6f}</i>"
            )
        else:
            self.current_coordinates = None
            self.current_display_name = None
            self.label_geocode_result.setText("❌ Adresse nicht gefunden.")


        self.pushButton_geocode.setEnabled(True); self.pushButton_geocode.setText("Suchen")
        self.update_analyze_button()

    # ---------- Generic UI handlers ----------
    def update_time_label(self):
        self.label_time.setText(f"{self.slider_time.value()} Minuten")

    def on_location_tab_changed(self, _):
        self.update_analyze_button()

    def on_district_changed(self, district_name):
        if district_name in MUENSTER_DISTRICTS:
            lat, lon = MUENSTER_DISTRICTS[district_name]
            self.current_coordinates = [lon, lat]
        self.update_analyze_button()

    def validate_coordinates(self):
        tlat = self.lineEdit_latitude.text().strip()
        tlon = self.lineEdit_longitude.text().strip()
        if not tlat or not tlon:
            self.current_coordinates = None
        else:
            try:
                lat, lon = float(tlat), float(tlon)
                if is_valid_coordinate(lat, lon):
                    self.current_coordinates = [lon, lat]
                    self.label_coord_info.setText("<i style='color: green;'>✅ Gültig.</i>")
                else:
                    self.current_coordinates = None
                    self.label_coord_info.setText("<i style='color: red;'>❌ Ungültig.</i>")
            except:
                self.current_coordinates = None
                self.label_coord_info.setText("<i style='color: red;'>❌ Zahlen nötig.</i>")
        self.update_analyze_button()

    # ---------- Analysis ----------
    def get_current_coordinates(self):
        idx = self.tabWidget_location.currentIndex()

        if idx == 0: 
            if self.current_coordinates:
                lon, lat = self.current_coordinates
                return [lon, lat], f"Koordinaten ({lat:.4f}, {lon:.4f})"
            return None, None

        elif idx == 1: 
            district = self.comboBox_district.currentText()
            if district in MUENSTER_DISTRICTS:
                lat, lon = MUENSTER_DISTRICTS[district]
                return [lon, lat], district
            return None, None

        else: 
            lat_txt = self.lineEdit_latitude.text().strip()
            lon_txt = self.lineEdit_longitude.text().strip()
            if not lat_txt or not lon_txt:
                return None, None
            try:
                lat = float(lat_txt); lon = float(lon_txt)
            except ValueError:
                return None, None
            return [lon, lat], f"Koordinaten ({lat:.4f}, {lon:.4f})"


    def get_selected_services(self):
        s = []
        if self.checkBox_supermarket.isChecked(): s.append("Supermarkt")
        if self.checkBox_pharmacy.isChecked():   s.append("Apotheke")
        if self.checkBox_doctor.isChecked():     s.append("Arzt")
        if self.checkBox_school.isChecked():     s.append("Schule")
        if self.checkBox_restaurant.isChecked(): s.append("Restaurant")
        if self.checkBox_bank.isChecked():       s.append("Bank")
        return s

    def analyze_walkability(self):
        coords, name = self.get_current_coordinates()
        if not coords:
            QMessageBox.warning(self, "Fehler", "Bitte Standort festlegen.")
            return
        services = self.get_selected_services()
        if not services:
            QMessageBox.warning(self, "Fehler", "Mindestens einen Service wählen.")
            return

        self.textBrowser_results.clear()
        self.textBrowser_results.append(f"🔍 Analysiere {name}…")
        self.textBrowser_results.append(f"📍 Koordinaten: {coords[1]:.6f}, {coords[0]:.6f}")
        self.textBrowser_results.append(f"⏱️ Gehzeit: {self.slider_time.value()} min")
        self.textBrowser_results.append(f"🏪 Services: {', '.join(services)}")
        self.textBrowser_results.append("─" * 40)

        if self.analyzer is None:
            from .walkability_engine import get_walkability_analyzer
            self.analyzer = get_walkability_analyzer()

        if name in MUENSTER_DISTRICTS:
            result = self.analyzer.analyze_district(name, self.slider_time.value(), services)
        else:
            result = self.analyzer.analyze_custom_location(name, coords, self.slider_time.value(), services)

        self.display_results(result)
        self.analyzer.add_layers_to_project(result['layers'])
        self.current_analysis = result
        self.pushButton_export.setEnabled(True)

    # ---------- Results & Export ----------
    def display_results(self, result):
       score = result['score']
       total = score['total_score']
       self.textBrowser_results.append(f"📊 Walkability-Score: {total:.1f}/100")    
       if total >= 80: rating = "🟢 Exzellent"
       elif total >= 60: rating = "🟡 Gut"
       elif total >= 40: rating = "🟠 Okay"
       else: rating = "🔴 Schlecht"
       self.textBrowser_results.append(f"⭐ Bewertung: {rating}\n\n") 
       self.textBrowser_results.append("📋 Services:")
       for st, s in score['service_scores'].items():
           tick = "✅" if s['count'] >= 1 else "❌"
           self.textBrowser_results.append(f"{tick} {st}: {s['count']} (Score {s['raw_score']:.1f})")   
       self.textBrowser_results.append(f"\n🎯 Gesamt-Services: {score['total_services']}")
       self.textBrowser_results.append("\n💡 Empfehlungen:")
       rec_lines = []   

       for st, s in score['service_scores'].items():
           c = s.get('count', 0)
           if c < 1:
               rec_lines.append(f"▸ {st}: Mindestens eine Einrichtung im Einzugsgebiet wäre wünschenswert.")
           elif c == 1:
               rec_lines.append(f"▸ {st}: Grundversorgung vorhanden; mehr Auswahl würde den Score verbessern.") 
               
       if score['service_scores']:
           worst_st, worst = min(
               score['service_scores'].items(),
               key=lambda kv: float(kv[1].get('raw_score', 0.0))
           )
           rec_lines.append(
               f"▸ Priorität: {worst_st} hat den niedrigsten Score "
               f"({float(worst.get('raw_score', 0.0)):.1f}/100). Angebot ausbauen."
           )    

       if not rec_lines:
           rec_lines = ["▸ Allgemein: Service-Vielfalt erhöhen (keine spezifischen Defizite erkannt)."] 

       for r in rec_lines:
           self.textBrowser_results.append(r)


    def export_pdf(self):
        if not self.current_analysis:
            QMessageBox.warning(self, "Fehler", "Keine Ergebnisse zum Export.")
            return

        default_name = f"Walkability_Analysis.pdf"
        path, _ = QFileDialog.getSaveFileName(self, "PDF speichern", default_name, "PDF-Dateien (*.pdf)")
        if not path: return
        from .pdf_exporter import export_walkability_pdf
        export_walkability_pdf(self.current_analysis, path)
        QMessageBox.information(self, "Fertig", f"PDF gespeichert:\n{path}")

    # ---------- Reset ----------
    def reset_analysis(self):
        self.current_analysis = None
        self.current_coordinates = None
        self.lineEdit_latitude.clear(); self.lineEdit_longitude.clear()
        self.lineEdit_address.clear()
        self.label_geocode_result.setText('Adresse eingeben und auf "Suchen" klicken.')
        self.label_coord_info.setText("WGS84 Dezimalgrad.")
        self.textBrowser_results.setPlainText("Bereit für Analyse…")
        self.pushButton_export.setEnabled(False)
        if self.analyzer:
            self.analyzer.remove_added_layers()
            self.analyzer.cleanup_temp_files()
        self.update_analyze_button()

    # ---------- Utils ----------
    def is_analysis_ready(self):
        coords, _ = self.get_current_coordinates()
        return coords is not None and len(self.get_selected_services()) > 0

    def update_analyze_button(self):
        ready = self.is_analysis_ready()
        self.pushButton_analyze.setEnabled(ready)
        self.pushButton_analyze.setStyleSheet(
            "QPushButton { background-color: %s; color: white; font-weight: bold; border-radius: 5px; }" %
            ("#4CAF50" if ready else "#aaaaaa")
        )
