def classFactory(iface):
    """
    Load WalkabilityAnalyzer class from file walkability_analyzer.py
    
    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    from .walkability_analyzer import WalkabilityAnalyzer
    return WalkabilityAnalyzer(iface)