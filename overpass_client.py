import json
from qgis.core import Qgis, QgsMessageLog, QgsGeometry, QgsPointXY, QgsNetworkAccessManager
from qgis.PyQt.QtCore import QUrl, QByteArray, QEventLoop, QTimer
from qgis.PyQt.QtNetwork import QNetworkRequest

TAG = "Walkability"

def _log(msg, lvl=Qgis.Info):
    QgsMessageLog.logMessage(msg, TAG, lvl)

class OverpassClient:
    """Fetch POIs from Overpass in a bbox, then filter by isochrone polygon."""

    def __init__(self):
        self.base_url = "https://overpass-api.de/api/interpreter"
        self.service_mappings = {
            "Supermarkt": ["shop=supermarket", "shop=convenience", "shop=grocery"],
            "Apotheke": ["amenity=pharmacy"],
            "Arzt": ["amenity=doctors", "amenity=clinic", "amenity=hospital", "healthcare=doctor"],
            "Schule": ["amenity=school", "amenity=kindergarten"],
            "Restaurant": ["amenity=restaurant", "amenity=fast_food", "amenity=cafe"],
            "Bank": ["amenity=bank", "amenity=atm"],
        }

    # --- sync POST ---
    def _post_overpass_json(self, query: str, timeout_ms: int = 60000):
        nam = QgsNetworkAccessManager.instance()
        req = QNetworkRequest(QUrl(self.base_url))
        req.setHeader(QNetworkRequest.ContentTypeHeader, "application/x-www-form-urlencoded; charset=UTF-8")
        payload = QByteArray(); payload.append("data="); payload.append(QUrl.toPercentEncoding(query))
        reply = nam.post(req, payload)

        loop = QEventLoop()
        timer = QTimer(); timer.setSingleShot(True); timer.timeout.connect(loop.quit)
        timer.start(max(1000, timeout_ms))
        reply.finished.connect(loop.quit)
        loop.exec_()

        status = int(reply.attribute(QNetworkRequest.HttpStatusCodeAttribute) or 0)
        raw = bytes(reply.readAll()); reply.deleteLater()
        if status != 200: return status, None, f"HTTP {status}"
        return status, json.loads(raw.decode("utf-8", "replace")), None

    # --- query helpers ---
    def _bbox_from_ring(self, ring_lonlat):
        lons = [x for x, y in ring_lonlat]; lats = [y for x, y in ring_lonlat]
        return [min(lats), min(lons), max(lats), max(lons)]

    def _build_query(self, bbox, service_types):
        s, w, n, e = bbox
        lines = ["[out:json][timeout:60];", "(", ""]
        for st in service_types:
            for tag in self.service_mappings.get(st, []):
                k, v = tag.split("=", 1)
                lines.append(f'  node["{k}"="{v}"]({s},{w},{n},{e});')
                lines.append(f'  way["{k}"="{v}"]({s},{w},{n},{e});')
        lines += [");", "out center meta;"]
        return "\n".join(lines)

    # --- main ---
    def get_pois_in_area(self, isochrone_geojson: dict, service_types):
        feat = (isochrone_geojson or {}).get("features", [{}])[0]
        ring = feat.get("geometry", {}).get("coordinates", [[[]]])[0] 
        if not ring:
            _log("Isochrone missing polygon", Qgis.Warning)
            return {}

        bbox = self._bbox_from_ring(ring)
        query = self._build_query(bbox, service_types)
        _log("Overpass query built.", Qgis.Info)

        status, data, err = self._post_overpass_json(query)
        if status != 200 or not data:
            _log(f"Overpass error: {status} {err}", Qgis.Critical)
            return {}

        poly = QgsGeometry.fromPolygonXY([[QgsPointXY(lon, lat) for lon, lat in ring]])

        results = {st: [] for st in service_types}
        for el in data.get("elements", []):
            if el.get("type") == "node":
                lat, lon = el.get("lat"), el.get("lon")
            elif el.get("type") == "way" and "center" in el:
                lat, lon = el["center"].get("lat"), el["center"].get("lon")
            else:
                continue
            if lat is None or lon is None:
                continue

            pt = QgsGeometry.fromPointXY(QgsPointXY(float(lon), float(lat)))
            if not (poly.contains(pt) or poly.intersects(pt)):
                continue

            tags = el.get("tags", {})
            for st in service_types:
                for mapping in self.service_mappings.get(st, []):
                    k, v = mapping.split("=", 1)
                    if tags.get(k) == v:
                        results[st].append({
                            "id": el.get("id"),
                            "lat": float(lat), "lon": float(lon),
                            "name": tags.get("name", "Unbenannt"),
                            "type": el.get("type"),
                            "service_type": st,
                            "osm_type": f"{k}={v}",
                            "tags": tags
                        })
                        break

        _log(f"POIs total: {sum(len(v) for v in results.values())}", Qgis.Info)
        return results
