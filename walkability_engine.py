import json
import os
import tempfile
from qgis.core import (
    QgsVectorLayer, QgsFeature, QgsGeometry, QgsProject,
    QgsMarkerSymbol, QgsCategorizedSymbolRenderer, QgsRendererCategory,
    QgsFillSymbol, QgsPointXY, QgsField, QgsDistanceArea
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor
from qgis.utils import iface

from .ors_client import ORSClient
from .overpass_client import OverpassClient
from .config import MUENSTER_DISTRICTS, SERVICE_CATEGORIES


class WalkabilityAnalyzer:
    """Straightforward walkability analysis."""

    def __init__(self):
        self.ors_client = ORSClient()
        self.overpass_client = OverpassClient()
        self._temp_files = []
        self._added_layers = []

    # ---------- Analysis ----------
    def analyze_district(self, district_name, time_limit, service_types):
        lat, lon = MUENSTER_DISTRICTS[district_name]
        coords = [lon, lat]  # ORS expects [lon, lat]
        iso = self.ors_client.get_isochrone(coords, time_limit)
        pois = self.overpass_client.get_pois_in_area(iso, service_types)
        score = self.calculate_walkability_score(pois, service_types, center=coords, time_limit=time_limit)
        layers = self.create_qgis_layers(district_name, iso, pois, coords)
        return {
            'district': district_name,
            'coordinates': coords,
            'time_limit': time_limit,
            'service_types': service_types,
            'isochrone': iso,
            'services': pois,
            'score': score,
            'layers': layers
        }

    def analyze_custom_location(self, location_name, coordinates, time_limit, service_types):
        iso = self.ors_client.get_isochrone(coordinates, time_limit)
        pois = self.overpass_client.get_pois_in_area(iso, service_types)
        score = self.calculate_walkability_score(pois, service_types, center=coordinates, time_limit=time_limit)
        layers = self.create_qgis_layers(location_name, iso, pois, coordinates)
        return {
            'location_name': location_name,
            'coordinates': coordinates,
            'time_limit': time_limit,
            'service_types': service_types,
            'isochrone': iso,
            'services': pois,
            'score': score,
            'layers': layers
        }

    # ---------- Scoring ----------
    def calculate_walkability_score(self, pois_data, service_types, center=None, time_limit=15):
        walk_speed_m_per_min = 80.0
        T = max(1.0, float(time_limit))
        reach_m = max(200.0, walk_speed_m_per_min * T)

        if not center:
            return {'total_score': 0.0, 'service_scores': {}, 'total_services': 0, 'total_weight': 1.0}

        cx, cy = float(center[0]), float(center[1])
        dcalc = QgsDistanceArea(); dcalc.setEllipsoid('WGS84')

        service_scores, total_weighted, total_weight, total_services = {}, 0.0, 0.0, 0
        for st in service_types:
            pois = pois_data.get(st, []) if pois_data else []
            total_services += len(pois)

            nearest_m = None
            for poi in pois:
                lon, lat = float(poi['lon']), float(poi['lat'])
                m = dcalc.measureLine(QgsPointXY(cx, cy), QgsPointXY(lon, lat))
                nearest_m = m if nearest_m is None else min(nearest_m, m)

            raw = 0.0 if nearest_m is None else max(0.0, min(100.0, 100.0 * (1.0 - nearest_m / reach_m)))
            w = SERVICE_CATEGORIES.get(st, {}).get('weight', 0.1)
            service_scores[st] = {'count': len(pois), 'nearest_m': nearest_m or -1.0, 'raw_score': raw, 'weight': w, 'weighted_score': raw * w}
            total_weighted += raw * w
            total_weight += w

        total_score = (total_weighted / total_weight) if total_weight > 0 else 0.0
        return {'total_score': total_score, 'service_scores': service_scores, 'total_services': total_services, 'total_weight': total_weight}

    # ---------- QGIS Layers ----------
    def create_qgis_layers(self, name, isochrone_data, pois_data, center_coords):
        return {
            'isochrone': self.create_isochrone_layer(name, isochrone_data),
            'center': self.create_center_layer(name, center_coords),
            'pois': self.create_poi_layer(name, pois_data),
        }

    def create_isochrone_layer(self, name, isochrone_data):
        # temp GeoJSON layer
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.geojson', delete=False)
        json.dump(isochrone_data, tmp); tmp.close()
        layer = QgsVectorLayer(tmp.name, f"WA_Isochrone_{name}", "ogr")
        symbol = QgsFillSymbol.createSimple({'color': '70,130,180,100', 'outline_color': '30,80,120,255', 'outline_width': '2'})
        layer.renderer().setSymbol(symbol)
        self._temp_files.append(tmp.name)
        return layer

    def create_center_layer(self, name, center_coords):
        layer = QgsVectorLayer("Point?crs=EPSG:4326", f"WA_Center_{name}", "memory")
        pr = layer.dataProvider()
        pr.addAttributes([QgsField('name', QVariant.String), QgsField('lon', QVariant.Double), QgsField('lat', QVariant.Double)])
        layer.updateFields()
        f = QgsFeature()
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(center_coords[0], center_coords[1])))
        f.setAttributes([name, center_coords[0], center_coords[1]])
        pr.addFeatures([f]); layer.updateExtents()
        symbol = QgsMarkerSymbol.createSimple({'name': 'star', 'color': 'red', 'size': '8', 'outline_color': 'black', 'outline_width': '1'})
        layer.renderer().setSymbol(symbol)
        return layer

    def create_poi_layer(self, name, pois_data):
        layer = QgsVectorLayer("Point?crs=EPSG:4326", f"WA_POIs_{name}", "memory")
        pr = layer.dataProvider()
        pr.addAttributes([QgsField('name', QVariant.String), QgsField('service_type', QVariant.String)])
        layer.updateFields()

        feats = []
        for st, pois in (pois_data or {}).items():
            for p in pois:
                f = QgsFeature()
                f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(float(p['lon']), float(p['lat']))))
                f.setAttributes([p.get('name') or 'POI', st])
                feats.append(f)
        if feats:
            pr.addFeatures(feats); layer.updateExtents()

        color_map = {
            'Supermarkt': QColor(34, 139, 34),
            'Apotheke':   QColor(220, 20, 60),
            'Arzt':       QColor(65, 105, 225),
            'Schule':     QColor(255, 140, 0),
            'Restaurant': QColor(138, 43, 226),
            'Bank':       QColor(184, 134, 11)
        }
        cats = []
        for label, qcolor in color_map.items():
            sym = QgsMarkerSymbol.createSimple({'name': 'circle', 'color': qcolor.name(), 'size': '5', 'outline_color': 'black', 'outline_width': '0.5'})
            cats.append(QgsRendererCategory(label, sym, label))
        layer.setRenderer(QgsCategorizedSymbolRenderer('service_type', cats))
        return layer

    # ---------- Project ops ----------
    def add_layers_to_project(self, layers):
        prj = QgsProject.instance()
        for key in ['isochrone', 'center', 'pois']:
            lyr = layers.get(key)
            if lyr:
                prj.addMapLayer(lyr)
                self._added_layers.append(lyr.id())
        if layers.get('isochrone'):
            iface.setActiveLayer(layers['isochrone'])
            iface.zoomToActiveLayer()

    def remove_added_layers(self):
        prj = QgsProject.instance()
        for lid in self._added_layers:
            lyr = prj.mapLayer(lid)
            if lyr:
                prj.removeMapLayer(lyr.id())
        self._added_layers = []

    def cleanup_temp_files(self):
        for p in self._temp_files:
            try: os.remove(p)
            except: pass
        self._temp_files = []


def get_walkability_analyzer():
    return WalkabilityAnalyzer()
