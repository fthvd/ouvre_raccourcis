import math
from pathlib import Path

from qgis.PyQt.QtCore import Qt, QUrl
try:
    from qgis.PyQt.QtGui import QAction, QDesktopServices, QIcon
except ImportError:  # PyQt5 / anciens environnements QGIS
    from qgis.PyQt.QtGui import QDesktopServices, QIcon
    from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtWidgets import QMessageBox, QToolBar
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsPointXY,
    QgsProject,
)


WEB_MERCATOR_INITIAL_RESOLUTION = 156543.03392804097
WEB_MERCATOR_MAX_LATITUDE = 85.05112878
EARTH_FIELD_OF_VIEW_DEGREES = 35.0


class OuvreRaccourcisPlugin:
    """Open web maps at the current QGIS center and display scale."""

    MENU_NAME = "&OuvreRaccourcis"
    TOOLBAR_NAME = "ouvre_raccourcis"
    TOOLBAR_OBJECT_NAME = "ouvre_raccourcis"

    ACTION_OBJECT_NAMES = {
        "Remonter le Temps": "OuvreRaccourcis.action_ign",
        "Ouvrir Maps": "OuvreRaccourcis.action_maps",
        "Ouvrir Google Earth": "OuvreRaccourcis.action_earth",
        "Ouvrir GPU": "OuvreRaccourcis.action_geourba",
    }

    def __init__(self, iface, cleanup_failures=None):
        self.iface = iface
        self.actions = []
        self.toolbar = None
        self.cleanup_failures = cleanup_failures or []
        self.plugin_dir = Path(__file__).resolve().parent

    def initGui(self):
        # Une mise à jour ZIP peut laisser des actions ou une barre d'outils de
        # l'ancienne instance tant que QGIS n'a pas redémarré. On les enlève
        # d'abord pour garantir une interface sans doublon.
        self._remove_orphan_actions()
        self._remove_orphan_toolbars()
        self._create_toolbar()

        self.action_ign = self._add_action(
            "Remonter le Temps",
            "icons/ign.svg",
            "Ouvre IGN Remonter le Temps au centre et au zoom actuels de QGIS.",
            self.open_ign_remonter_le_temps,
        )
        self.action_maps = self._add_action(
            "Ouvrir Maps",
            "icons/maps.svg",
            "Ouvre Google Maps au centre et au zoom actuels de QGIS.",
            self.open_maps,
        )
        self.action_earth = self._add_action(
            "Ouvrir Google Earth",
            "icons/google_earth.svg",
            "Ouvre Google Earth Web au centre et à une échelle équivalente à QGIS.",
            self.open_google_earth,
        )
        self.action_geourba = self._add_action(
            "Ouvre le GPU",
            "icons/geourba.svg",
            "Ouvre le Géoportail de l’Urbanisme au centre et au zoom actuels de QGIS.",
            self.open_geourba,
        )

    def _create_toolbar(self):
        self.toolbar = self.iface.addToolBar(self.TOOLBAR_NAME)
        self.toolbar.setObjectName(self.TOOLBAR_OBJECT_NAME)
        self.toolbar.setWindowTitle(self.TOOLBAR_NAME)

        # Force l'affichage sous forme d'icônes, quel que soit le réglage
        # global des autres barres d'outils QGIS. Compatible Qt5/Qt6.
        tool_button_style = getattr(Qt, "ToolButtonStyle", Qt)
        self.toolbar.setToolButtonStyle(tool_button_style.ToolButtonIconOnly)

    def _add_action(self, text, icon_relative_path, status_tip, callback):
        icon_path = self.plugin_dir / icon_relative_path
        action = QAction(QIcon(str(icon_path)), text, self.iface.mainWindow())
        action.setObjectName(self.ACTION_OBJECT_NAMES.get(text, ""))

        # L'infobulle demandée reprend exactement le nom historique de l'outil.
        action.setToolTip(text)
        action.setStatusTip(status_tip)
        action.setWhatsThis(status_tip)
        action.triggered.connect(callback)

        self.toolbar.addAction(action)
        self.iface.addPluginToMenu(self.MENU_NAME, action)
        self.actions.append(action)
        return action

    def unload(self):
        for action in tuple(self.actions):
            self._remove_action(action)
        self.actions.clear()
        self._remove_toolbar(self.toolbar)
        self.toolbar = None

    def _remove_action(self, action):
        """Fully detach and delete one plugin action."""
        if self.toolbar is not None:
            try:
                self.toolbar.removeAction(action)
            except RuntimeError:
                pass

        # Compatibilité avec les versions <= 1.1.1 qui plaçaient les actions
        # dans la barre d'outils générale des extensions QGIS.
        try:
            self.iface.removeToolBarIcon(action)
        except RuntimeError:
            pass

        try:
            self.iface.removePluginMenu(self.MENU_NAME, action)
        except RuntimeError:
            pass

        try:
            action.triggered.disconnect()
        except (TypeError, RuntimeError):
            action.setEnabled(False)
        action.deleteLater()

    def _remove_orphan_actions(self):
        """Remove actions left by a previous live installation of the plugin."""
        plugin_menu = self.iface.pluginMenu()
        stale_actions = []

        # Actions situées dans le sous-menu OuvreRaccourcis.
        for top_action in plugin_menu.actions():
            submenu = top_action.menu()
            if submenu is None:
                continue
            title = submenu.title().replace("&", "").strip()
            if title.casefold() != self.MENU_NAME.replace("&", "").casefold():
                continue
            stale_actions.extend(submenu.actions())

        # Noms d'objet stables : capture également les actions encore présentes
        # dans une ancienne barre d'outils.
        known_names = set(self.ACTION_OBJECT_NAMES.values())
        for action in self.iface.mainWindow().findChildren(QAction):
            if action.objectName() in known_names:
                stale_actions.append(action)

        seen = set()
        for action in stale_actions:
            identity = id(action)
            if identity in seen:
                continue
            seen.add(identity)
            self._remove_action(action)

    def _remove_orphan_toolbars(self):
        """Delete obsolete OuvreRaccourcis toolbars before recreating ours."""
        main_window = self.iface.mainWindow()
        for toolbar in main_window.findChildren(QToolBar):
            object_name = toolbar.objectName().strip().casefold()
            title = toolbar.windowTitle().strip().casefold()
            if (
                object_name == self.TOOLBAR_OBJECT_NAME.casefold()
                or title == self.TOOLBAR_NAME.casefold()
            ):
                self._remove_toolbar(toolbar)

    def _remove_toolbar(self, toolbar):
        if toolbar is None:
            return
        try:
            self.iface.mainWindow().removeToolBar(toolbar)
        except RuntimeError:
            return
        toolbar.deleteLater()

    def _current_view(self):
        """
        Return the current QGIS view as (longitude, latitude, web_zoom,
        ground_metres_per_pixel, viewport_height_pixels).

        The web zoom is derived from one rendered QGIS screen pixel transformed
        to EPSG:3857. This makes the result independent from the project CRS and
        reproduces the visual map scale much more accurately than a fixed zoom.
        """
        canvas = self.iface.mapCanvas()
        settings = canvas.mapSettings()
        source_crs = settings.destinationCrs()
        if not source_crs.isValid():
            raise ValueError("Le SCR du canevas QGIS n'est pas valide.")

        project = QgsProject.instance()
        wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
        web_mercator = QgsCoordinateReferenceSystem("EPSG:3857")

        center = canvas.center()
        to_wgs84 = QgsCoordinateTransform(source_crs, wgs84, project)
        center_wgs84 = to_wgs84.transform(center)
        longitude = center_wgs84.x()
        latitude = center_wgs84.y()

        output_size = settings.outputSize()
        width_px = max(1, output_size.width())
        height_px = max(1, output_size.height())

        mercator_metres_per_pixel = self._mercator_resolution_per_pixel(
            settings,
            center,
            source_crs,
            web_mercator,
            project,
        )

        if not math.isfinite(mercator_metres_per_pixel) or mercator_metres_per_pixel <= 0:
            mercator_metres_per_pixel = self._fallback_mercator_resolution(
                canvas.scale(), settings.outputDpi(), latitude
            )

        web_zoom = math.log2(
            WEB_MERCATOR_INITIAL_RESOLUTION / mercator_metres_per_pixel
        )
        web_zoom = max(0.0, min(23.0, web_zoom))

        latitude_for_scale = max(
            -WEB_MERCATOR_MAX_LATITUDE,
            min(WEB_MERCATOR_MAX_LATITUDE, latitude),
        )
        ground_metres_per_pixel = (
            mercator_metres_per_pixel
            * math.cos(math.radians(latitude_for_scale))
        )

        return (
            longitude,
            latitude,
            web_zoom,
            ground_metres_per_pixel,
            height_px,
        )

    @staticmethod
    def _mercator_resolution_per_pixel(
        settings,
        center,
        source_crs,
        web_mercator,
        project,
    ):
        """Return the local EPSG:3857 distance represented by one QGIS pixel.

        QgsMapToPixel.toMapCoordinates() has different Python overloads across
        QGIS/PyQt generations (notably int-only bindings in QGIS 3.44 builds).
        Using QgsMapSettings.mapUnitsPerPixel() avoids that fragile overload
        entirely and gives us the native map-coordinate size of one pixel.
        """
        try:
            map_units_per_pixel = float(settings.mapUnitsPerPixel())
        except (AttributeError, TypeError, ValueError):
            return float("nan")

        if (
            not math.isfinite(map_units_per_pixel)
            or map_units_per_pixel <= 0
        ):
            return float("nan")

        p0 = QgsPointXY(center.x(), center.y())
        px = QgsPointXY(center.x() + map_units_per_pixel, center.y())
        py = QgsPointXY(center.x(), center.y() + map_units_per_pixel)

        try:
            to_mercator = QgsCoordinateTransform(
                source_crs, web_mercator, project
            )
            m0 = to_mercator.transform(p0)
            mx = to_mercator.transform(px)
            my = to_mercator.transform(py)
        except Exception:
            # Transformation failures are handled by the scale-based fallback
            # in _current_view(). Do not make opening a web map fail outright.
            return float("nan")

        resolution_x = math.hypot(
            mx.x() - m0.x(),
            mx.y() - m0.y(),
        )
        resolution_y = math.hypot(
            my.x() - m0.x(),
            my.y() - m0.y(),
        )
        resolutions = [
            value
            for value in (resolution_x, resolution_y)
            if math.isfinite(value) and value > 0
        ]
        if not resolutions:
            return float("nan")

        # The geometric mean is stable for CRSs whose local X/Y scale differs
        # slightly after conversion to Web Mercator, while preserving a visual
        # scale close to the QGIS canvas in both directions.
        if len(resolutions) == 2:
            return math.sqrt(resolutions[0] * resolutions[1])
        return resolutions[0]

    @staticmethod
    def _fallback_mercator_resolution(scale, dpi, latitude):
        """Fallback based on QGIS scale if the one-pixel transform is unavailable."""
        if not scale or scale <= 0:
            raise ValueError("L'échelle courante de QGIS est invalide.")
        if not dpi or dpi <= 0:
            dpi = 96.0

        ground_metres_per_pixel = scale * 0.0254 / dpi
        latitude = max(
            -WEB_MERCATOR_MAX_LATITUDE,
            min(WEB_MERCATOR_MAX_LATITUDE, latitude),
        )
        cos_latitude = max(1e-6, math.cos(math.radians(latitude)))
        return ground_metres_per_pixel / cos_latitude

    @staticmethod
    def _earth_camera_distance(ground_metres_per_pixel, height_px):
        """
        Approximate a top-down Google Earth eye-to-target distance producing
        the same vertical ground span as the current QGIS canvas.
        """
        visible_ground_height = max(1.0, ground_metres_per_pixel * height_px)
        half_fov = math.radians(EARTH_FIELD_OF_VIEW_DEGREES / 2.0)
        distance = (visible_ground_height / 2.0) / math.tan(half_fov)
        return max(20.0, min(25_000_000.0, distance))

    @staticmethod
    def _open_url(url):
        if not QDesktopServices.openUrl(QUrl(url)):
            raise RuntimeError("Le navigateur par défaut n'a pas pu être ouvert.")

    def open_ign_remonter_le_temps(self):
        try:
            longitude, latitude, zoom, _, _ = self._current_view()
            ign_zoom = max(0.0, min(21.0, zoom))
            url = (
                "https://remonterletemps.ign.fr/comparer/"
                f"?lat={latitude:.8f}&lon={longitude:.8f}&z={ign_zoom:.2f}"
            )
            self._open_url(url)
        except Exception as exc:
            self._show_error(exc)

    def open_maps(self):
        try:
            longitude, latitude, zoom, _, _ = self._current_view()
            maps_zoom = max(0.0, min(21.0, zoom))
            url = (
                "https://www.google.fr/maps/"
                f"@{latitude:.8f},{longitude:.8f},{maps_zoom:.2f}z?hl=fr"
            )
            self._open_url(url)
        except Exception as exc:
            self._show_error(exc)

    def open_google_earth(self):
        try:
            longitude, latitude, _, ground_mpp, height_px = self._current_view()
            distance = self._earth_camera_distance(ground_mpp, height_px)
            url = (
                "https://earth.google.com/web/"
                f"@{latitude:.8f},{longitude:.8f},0a,{distance:.2f}d,"
                f"{EARTH_FIELD_OF_VIEW_DEGREES:.0f}y,0h,0t,0r"
            )
            self._open_url(url)
        except Exception as exc:
            self._show_error(exc)

    def open_geourba(self):
        try:
            longitude, latitude, zoom, _, _ = self._current_view()

            # Le prototype GéoURBA utilisait un zoom fixe de 17. On reprend
            # ici le zoom courant de QGIS, comme pour les autres raccourcis,
            # avec une plage prudente adaptée au visualiseur du GPU.
            geourba_zoom = int(round(max(2.0, min(20.0, zoom))))
            url = (
                "https://www.geoportail-urbanisme.gouv.fr/map/"
                f"#tile=1&lon={longitude:.6f}&lat={latitude:.6f}"
                f"&zoom={geourba_zoom}"
            )
            self._open_url(url)
        except Exception as exc:
            self._show_error(exc)

    def _show_error(self, exc):
        QMessageBox.critical(
            self.iface.mainWindow(),
            "OuvreRaccourcis - Erreur",
            f"Impossible d'ouvrir la carte : {exc}",
        )
