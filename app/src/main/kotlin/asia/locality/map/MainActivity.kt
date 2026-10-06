package asia.locality.map

import android.Manifest
import android.content.ActivityNotFoundException
import android.content.Intent
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import androidx.core.net.toUri
import androidx.core.content.edit
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.provider.Settings
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import java.util.concurrent.Executors
import kotlin.math.abs
import kotlin.math.max

class MainActivity : ComponentActivity(), InkMapView.Listener {
    private var map: InkMapView? = null
    private var controlsHeight = 0
    private lateinit var locations: LocationManager
    private var data by mutableStateOf<MapData?>(null)
    private var year by mutableIntStateOf(Timeline.DEFAULT_YEAR)
    private var timeline by mutableStateOf<Timeline?>(null)
    private var viewRegion by mutableStateOf("cn")
    private var changingPeriod by mutableStateOf(false)
    // Retain immutable geometry for reuse when a later context becomes eligible again.
    // These cached features are never added to an ineligible snapshot.
    private var fixedReferences = emptyList<MapData.Feature>()
    private var loadGeneration = 0
    private var pendingLoad: java.util.concurrent.Future<*>? = null
    private var statusId by mutableStateOf<Int?>(R.string.loading)
    private var locationStatusId by mutableStateOf<Int?>(null)
    private var searchOpen by mutableStateOf(false)
    private var message by mutableStateOf<UiMessage?>(null)
    private var current: Location? = null
    private var restoredViewport: DoubleArray? = null
    private var selectedId: String? = null
    private val handler = Handler(Looper.getMainLooper())
    private val worker = Executors.newSingleThreadExecutor()
    private var locating = false
    private var destroyed = false
    private val permissionRequest = registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) {
        if (hasLocationPermission()) locate() else { locationStatusId = R.string.permission_denied }
    }
    private val locationTimeout = Runnable {
        stopLocation()
        locationStatusId = R.string.location_timeout
    }
    private val locationListener = LocationListener { location ->
        if (locating && SystemClock.elapsedRealtimeNanos() - location.elapsedRealtimeNanos in 0L..120_000_000_000L) {
            current = location
            restoredViewport = null
            map?.setHere(location.longitude, location.latitude)
            refreshHere()
            stopLocation()
            locationStatusId = null
            showAt(location.longitude, location.latitude, true)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        locations = getSystemService(LocationManager::class.java)
        restoredViewport = savedInstanceState?.getDoubleArray("viewport")
        selectedId = savedInstanceState?.getString("selected")
        searchOpen = savedInstanceState?.getBoolean("search") ?: false
        val preferences = getPreferences(0)
        year = savedInstanceState?.getInt("year")?.takeIf { it != 0 }
            ?: preferences.getInt("year", Timeline.DEFAULT_YEAR)
        viewRegion = savedInstanceState?.getString("region") ?: "cn"
        if (savedInstanceState?.containsKey("longitude") == true) {
            current = Location("saved-ui").apply {
                longitude = savedInstanceState.getDouble("longitude")
                latitude = savedInstanceState.getDouble("latitude")
            }
        }
        setContent {
            LocalityApp(
                data = data,
                timeline = timeline, year = year, region = viewRegion, changingPeriod = changingPeriod,
                onPeriod = { period -> timeline?.let { changeYear(it.contextYearFor(period, year)) } },
                statusId = locationStatusId ?: statusId,
                searchOpen = searchOpen,
                message = message,
                onMapReady = ::attachMap,
                onControlsHeight = { controlsHeight = it; map?.setLabelTopInset(it) },
                onMapReleased = { view ->
                    if (map === view) {
                        if (data != null && restoredViewport == null) restoredViewport = view.viewport()
                        map = null
                    }
                },
                onSearch = { searchOpen = true },
                onCloseSearch = { searchOpen = false },
                onLocate = ::locate,
                onZoom = { map?.zoom(it) },
                onChoose = ::searchResult,
                onDismissMessage = { message = null }
            )
        }
        worker.execute {
            try {
                val catalogue = Timeline.load(this)
                val requestedYear = year
                val loaded = MapData.load(this, catalogue.restoreYear(requestedYear))
                handler.post {
                    if (!destroyed) {
                        data = loaded
                        fixedReferences = loaded.fixedFeatures()
                        timeline = catalogue
                        year = loaded.year
                        preferences.edit { putInt("year", year) }
                        map?.let(::bindMap)
                        if (statusId == R.string.loading) statusId = null
                    }
                }
            } catch (ex: Exception) {
                Log.e("AsiaLocalityMap", "Offline data failed", ex)
                handler.post { if (!destroyed) { stopLocation(); locationStatusId = null; statusId = R.string.load_failed } }
            }
        }
    }

    private fun attachMap(view: InkMapView) {
        map = view
        view.setLabelTopInset(controlsHeight)
        view.listener = this
        view.post { if (!destroyed && map === view) bindMap(view) }
    }

    private fun bindMap(view: InkMapView) {
        val loaded = data ?: return
        view.setData(loaded)
        val saved = restoredViewport
        val savedSelection = selectedId
        current?.let {
            view.setHere(it.longitude, it.latitude)
            refreshHere()
            showAt(it.longitude, it.latitude, saved == null)
        }
        if (saved != null) {
            view.restoreViewport(saved)
            savedSelection?.let { id -> loaded.features.find { it.id == id }?.let(::choose) }
            restoredViewport = null
        }
    }

    private fun changeYear(value: Int) {
        val previous = data ?: return
        if (value == year || value !in (timeline?.years ?: emptySet())) return
        stopLocation()
        locationStatusId = null
        map?.stopCamera()
        changingPeriod = true
        statusId = R.string.loading
        val generation = ++loadGeneration
        pendingLoad?.cancel(true)
        pendingLoad = worker.submit {
            try {
                val loaded = MapData.load(this, value, previous.land, fixedReferences)
                handler.post { if (!destroyed && generation == loadGeneration) applySnapshot(loaded) }
            } catch (_: java.util.concurrent.CancellationException) {
                // A more recent selection owns the next snapshot.
            } catch (error: Exception) {
                Log.e("AsiaLocalityMap", "Historical snapshot failed: $value", error)
                handler.post {
                    if (!destroyed && generation == loadGeneration) {
                        changingPeriod = false
                        statusId = R.string.load_failed
                    }
                }
            }
        }
    }

    private fun applySnapshot(loaded: MapData) {
        val viewport = map?.viewport() ?: restoredViewport
        val selection = selectedId
        year = loaded.year
        data = loaded
        loaded.fixedFeatures().takeIf { it.isNotEmpty() }?.let { fixedReferences = it }
        changingPeriod = false
        getPreferences(0).edit { putInt("year", year) }
        map?.setData(loaded)
        selectedId = null
        refreshHere()
        // Keep the viewed place and zoom, including when a camera transition was in progress.
        if (viewport != null) {
            map?.restoreViewport(viewport)
            showAt(viewport[0], MapData.latitude(viewport[1]), false)
        } else {
            statusId = null
        }
        loaded.features.find { it.id == selection }?.let(::choose)
    }

    override fun onViewportChanged(lon: Double, lat: Double) {
        val view = map ?: return
        viewRegion = timeline?.regionForViewport(lon, lat, view.viewport()[2],
            view.height.toDouble() / view.width.coerceAtLeast(1), viewRegion) ?: viewRegion
    }

    /** Re-derive the current-location label and accessibility text from the loaded snapshot. */
    private fun refreshHere() {
        val loaded = data ?: return
        val here = current ?: return
        map?.nameHere(loaded.localAreaAt(here.longitude, here.latitude))
        map?.contentDescription = descriptionAt(here.longitude, here.latitude)
    }

    private fun hasLocationPermission() =
        checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED ||
            checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED

    private fun locate() {
        if (locating) return
        if (!hasLocationPermission()) {
            if (getPreferences(0).getBoolean("permissionAsked", false) &&
                !shouldShowRequestPermissionRationale(Manifest.permission.ACCESS_COARSE_LOCATION) &&
                !shouldShowRequestPermissionRationale(Manifest.permission.ACCESS_FINE_LOCATION)) {
                locationStatusId = R.string.permission_denied
                showMessage(getString(R.string.permission_title), getString(R.string.permission_body), getString(R.string.open_settings)) {
                    startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, "package:$packageName".toUri()))
                }
                return
            }
            getPreferences(0).edit { putBoolean("permissionAsked", true) }
            permissionRequest.launch(arrayOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION))
            locationStatusId = R.string.permission_prompt
            return
        }
        if (!locations.isLocationEnabled) {
            locationStatusId = R.string.location_disabled
            showMessage(getString(R.string.enable_location), getString(R.string.enable_location_body), getString(R.string.open_location_settings)) {
                startActivity(Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS))
            }
            return
        }
        locating = true
        locationStatusId = R.string.locating
        var requested = false
        try {
            val fine = checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
            for (provider in arrayOf(LocationManager.NETWORK_PROVIDER, LocationManager.GPS_PROVIDER)) {
                if (provider == LocationManager.GPS_PROVIDER && !fine) continue
                if (locations.isProviderEnabled(provider)) {
                    locations.requestLocationUpdates(provider, 1000L, 0f, locationListener, Looper.getMainLooper())
                    requested = true
                }
            }
        } catch (_: SecurityException) {
            stopLocation()
            locationStatusId = R.string.permission_disabled
            return
        }
        if (requested) handler.postDelayed(locationTimeout, 20_000L)
        else { locating = false; locationStatusId = R.string.location_unavailable }
    }
    private fun stopLocation() {
        if (::locations.isInitialized) locations.removeUpdates(locationListener)
        locating = false
        handler.removeCallbacks(locationTimeout)
    }

    override fun onPlace(feature: MapData.Feature) {
        stopLocation()
        locationStatusId = null
        choose(feature)
    }
    override fun onMapPoint(lon: Double, lat: Double) {
        stopLocation()
        locationStatusId = null
        showAt(lon, lat, false)
    }

    private fun choose(feature: MapData.Feature) {
        selectedId = feature.id
        map?.select(feature)
        statusId = null
    }

    private fun descriptionAt(lon: Double, lat: Double): String {
        val loaded = data ?: return getString(R.string.map_description)
        val area = loaded.localAreaAt(lon, lat)
        if (area != null) return getString(R.string.current_county_description, area.name)
        val seat = loaded.nearestSeat(lon, lat, 50.0)
        if (seat != null) return getString(R.string.current_nearby_description, seat.name)
        return getString(R.string.current_unknown_description)
    }

    private fun showAt(lon: Double, lat: Double, move: Boolean) {
        val loaded = data ?: return
        val area = loaded.localAreaAt(lon, lat)
        if (area != null) {
            choose(area)
            if (move) map?.focusCounty(lon, lat, area)
        } else {
            val seat = loaded.nearestSeat(lon, lat, 50.0)
            selectedId = seat?.id
            map?.select(seat)
            statusId = null
            if (move) {
                val view = map
                val aspect = if (view != null && view.height > 0) view.width.toDouble() / view.height else 1.0
                val extent = seat?.let { 2.6 * max(abs(lon - it.lon), abs(MapData.mercator(lat) - it.y) * aspect) } ?: 1.2
                view?.go(lon, lat, max(1.2, extent))
            }
        }
    }

    private fun searchResult(feature: MapData.Feature) {
        stopLocation()
        locationStatusId = null
        choose(feature)
        map?.go(feature.lon, feature.lat, if (feature.point) 1.2 else ((feature.maxX - feature.minX) * 1.4).coerceIn(0.2, 8.0))
        searchOpen = false
    }

    private fun showMessage(title: String, body: String, action: String, click: () -> Unit) {
        message = UiMessage(title, body, action) {
            message = null
            try { click() } catch (_: ActivityNotFoundException) { locationStatusId = R.string.location_unavailable }
        }
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        outState.putDoubleArray("viewport", restoredViewport ?: map?.takeIf { data != null }?.viewport())
        outState.putString("selected", selectedId)
        outState.putBoolean("search", searchOpen)
        outState.putInt("year", year)
        outState.putString("region", viewRegion)
        current?.let { outState.putDouble("longitude", it.longitude); outState.putDouble("latitude", it.latitude) }
    }
    override fun onResume() {
        super.onResume()
        if (::locations.isInitialized && current == null && !locating && locations.isLocationEnabled && hasLocationPermission()) locate()
    }
    override fun onStop() {
        super.onStop()
        if (locating) locationStatusId = R.string.location_interrupted
        stopLocation()
    }
    override fun onDestroy() {
        destroyed = true
        handler.removeCallbacksAndMessages(null)
        worker.shutdownNow()
        super.onDestroy()
    }
}
