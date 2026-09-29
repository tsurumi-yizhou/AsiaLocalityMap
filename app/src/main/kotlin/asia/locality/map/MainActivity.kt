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
    private lateinit var locations: LocationManager
    private var data by mutableStateOf<MapData?>(null)
    private var statusId by mutableIntStateOf(R.string.loading)
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
        if (savedInstanceState?.containsKey("longitude") == true) {
            current = Location("saved-ui").apply {
                longitude = savedInstanceState.getDouble("longitude")
                latitude = savedInstanceState.getDouble("latitude")
            }
        }
        setContent {
            LocalityApp(
                data = data,
                statusId = locationStatusId ?: statusId,
                searchOpen = searchOpen,
                message = message,
                onMapReady = ::attachMap,
                onMapReleased = { view ->
                    restoredViewport = view.viewport()
                    if (map === view) map = null
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
                val loaded = MapData.load(this)
                handler.post {
                    if (!destroyed) {
                        data = loaded
                        map?.let(::bindMap)
                        if (statusId == R.string.loading) statusId = R.string.location_or_search
                    }
                }
            } catch (ex: Exception) {
                Log.e("AsiaLocalityMap", "Offline data failed", ex)
                handler.post { if (!destroyed) { stopLocation(); locationStatusId = null; statusId = R.string.load_failed } }
            }
        }
        if (current == null) locate()
    }

    private fun attachMap(view: InkMapView) {
        map = view
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
            showAt(it.longitude, it.latitude, saved == null)
            view.contentDescription = descriptionAt(it.longitude, it.latitude)
        }
        if (saved != null) {
            view.restoreViewport(saved)
            savedSelection?.let { id -> loaded.features.find { it.id == id }?.let(::choose) }
            restoredViewport = null
        }
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
        statusId = if (!feature.point) 0 else when (feature.system) {
            "军事" -> R.string.military_site_unknown_boundary
            "土司" -> R.string.native_site_unknown_boundary
            else -> R.string.seat_unknown_boundary
        }
    }

    private fun descriptionAt(lon: Double, lat: Double): String {
        val loaded = data ?: return getString(R.string.map_description)
        val county = loaded.countyAt(lon, lat)
        if (county != null) return getString(R.string.current_county_description, county.name)
        val seat = loaded.nearestCountySeat(lon, lat, 50.0)
        return if (seat == null) getString(R.string.current_unknown_description)
        else getString(R.string.current_nearby_description, seat.name)
    }

    private fun showAt(lon: Double, lat: Double, move: Boolean) {
        val loaded = data ?: return
        val county = loaded.countyAt(lon, lat)
        if (county != null) {
            choose(county)
            if (move) { map?.nameHere(county); map?.focusCounty(lon, lat, county) }
        } else {
            val seat = loaded.nearestCountySeat(lon, lat, 50.0)
            selectedId = seat?.id
            map?.select(seat)
            statusId = if (seat == null) R.string.unknown_boundary else R.string.nearby_seat_unknown_boundary
            if (move) {
                map?.nameHere(null)
                val view = map
                val aspect = if (view != null && view.height > 0) view.width.toDouble() / view.height else 1.0
                val extent = seat?.let { 2.6 * max(abs(lon - it.lon), abs(MapData.mercator(lat) - it.y) * aspect) } ?: 1.2
                view?.go(lon, lat, max(1.2, extent))
            }
        }
        current?.let { map?.contentDescription = descriptionAt(it.longitude, it.latitude) }
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
        outState.putDoubleArray("viewport", map?.viewport() ?: restoredViewport)
        outState.putString("selected", selectedId)
        outState.putBoolean("search", searchOpen)
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
