import json
from qgis.core import Qgis, QgsMessageLog, QgsNetworkAccessManager
from qgis.PyQt.QtCore import QUrl, QByteArray, QEventLoop, QTimer
from qgis.PyQt.QtNetwork import QNetworkRequest
from .config import ORS_API_KEY, ORS_ISOCHRONE_URL

TAG = "Walkability"

def _log(msg, lvl=Qgis.Info):
    QgsMessageLog.logMessage(msg, TAG, lvl)

class ORSClient:
    """Tiny ORS client: only isochrones we need."""

    def __init__(self):
        self.api_key = ORS_API_KEY

    def _post_json(self, url: str, payload: dict, timeout_ms: int = 20000):
        nam = QgsNetworkAccessManager.instance()
        req = QNetworkRequest(QUrl(url))
        req.setRawHeader(b"Authorization", self.api_key.encode("utf-8"))
        req.setHeader(QNetworkRequest.ContentTypeHeader, "application/json; charset=UTF-8")

        body = QByteArray(json.dumps(payload).encode("utf-8"))
        reply = nam.post(req, body)

        loop = QEventLoop()
        timer = QTimer(); timer.setSingleShot(True); timer.timeout.connect(loop.quit)
        timer.start(max(1000, timeout_ms))
        reply.finished.connect(loop.quit)
        loop.exec_()

        status = int(reply.attribute(QNetworkRequest.HttpStatusCodeAttribute) or 0)
        raw = bytes(reply.readAll()); reply.deleteLater()
        if status != 200:
            return status, None, f"HTTP {status}"
        return status, json.loads(raw.decode("utf-8", "replace")), None

    def test_connection(self) -> bool:
        coords = [7.6261347, 51.9606649] 
        payload = {"locations":[coords], "range":[300], "range_type":"time", "units":"m"}
        st, data, _ = self._post_json(ORS_ISOCHRONE_URL, payload, timeout_ms=8000)
        ok = bool(st == 200 and data and data.get("features"))
        _log(f"ORS Connection: {'OK' if ok else 'fail'}", Qgis.Info if ok else Qgis.Warning)
        return ok

    def get_isochrone(self, coordinates, time_minutes):
        """Return ORS isochrone GeoJSON for [lon,lat] and minutes."""
        secs = int(max(1.0, float(time_minutes)) * 60)
        payload = {"locations":[coordinates], "range":[secs], "range_type":"time", "units":"m"}
        _log(f"ORS request {coordinates}, {time_minutes} min")
        st, data, err = self._post_json(ORS_ISOCHRONE_URL, payload)
        if st == 200 and data and data.get("features"):
            return data
        _log(f"ORS error: {st} {err}", Qgis.Critical)
        return None
