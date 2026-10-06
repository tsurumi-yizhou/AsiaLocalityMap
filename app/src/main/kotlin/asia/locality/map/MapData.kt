package asia.locality.map

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.text.Normalizer
import java.util.Locale
import kotlin.math.*

internal fun Context.assetText(name: String): String =
    assets.open(name).bufferedReader(Charsets.UTF_8).use { it.readText() }

/** Offline reference geometry. A seat never supplies an administrative boundary. */
class MapData private constructor(
    val features: List<Feature>, val land: List<Feature>, val year: Int, val referenceYears: Map<String, Int?>
) {

    fun at(lon: Double, lat: Double): List<Feature> {
        val y = mercator(lat)
        return features.filter { !it.point && it.contains(lon, y) }
            .sortedWith(areaOrder)
    }

    fun contextNames(feature: Feature): String =
        (listOf(feature.parent) + at(feature.lon, feature.lat)
            .filter { it.labelId != feature.labelId && it.region == feature.region && it.rank < feature.rank }
            .map { it.name }).filter { it.isNotBlank() }.distinct().joinToString(" · ")

    /** The most detailed available area, with the same policy in every region. */
    fun localAreaAt(lon: Double, lat: Double): Feature? = at(lon, lat).firstOrNull()

    val labelFeatures: List<Feature> = features.sortedWith(compareBy<Feature> { it.point }.then(areaOrder))
    val broadLabelRegions: Set<String> = features.filter { it.rank == 1 }.map { it.region }.toSet()
    val fineBoundaryRegions: Set<String> = features.filter { !it.point && it.rank >= 2 }.map { it.region }.toSet()

    /** Reference features whose geometry is identical in every snapshot, so they can be shared. */
    fun fixedFeatures(): List<Feature> = features.filter { it.region == FIXED_REGION }

    fun nearestSeat(lon: Double, lat: Double, maxKm: Double): Feature? {
        var best: Feature? = null
        var bestDistance = maxKm
        for (feature in features) {
            if (!feature.point || feature.rank < 2) continue
            val km = distance(lon, lat, feature.lon, feature.lat)
            if (km >= maxKm) continue
            // Civil seats outrank other systems; distance only breaks ties within a class.
            val better = best == null || (feature.system != "民政") < (best.system != "民政") ||
                ((feature.system != "民政") == (best.system != "民政") && km < bestDistance)
            if (better) { best = feature; bestDistance = km }
        }
        return best
    }

    class Feature(row: JSONObject, internal val network: BoundaryNetwork? = null) {
        val id: String = row.optString("id")
        val name: String = row.optString("name")
        val nativeName: String = row.optString("native_name")
        val searchText: String = normalizeSearch(buildString {
            append(name); append('\n'); append(nativeName)
            row.optJSONArray("search_names")?.let { aliases ->
                for (index in 0 until aliases.length()) { append('\n'); append(aliases.getString(index)) }
            }
        })
        val labelId: String = row.optString("label_id", id)
        val parent: String = row.optString("parent")
        val kind: String = row.optString("kind")
        val region: String = row.optString("region")
        val system: String = row.optString("system", "民政")
        val layer: String = row.optString("layer", "administrative")
        val year: Int = row.optInt("year")
        val rank: Int = row.optInt("rank", 1)
        val secondaryName: String? = nativeName.takeIf { it.isNotBlank() && it != name }
        val point: Boolean = row.getJSONObject("geometry").getString("type") == "Point"
        init {
            if (region == "kr" && year in setOf(757, 1370) && !point) {
                require(!row.optBoolean("inferred", false) &&
                    row.optString("boundary_basis") in setOf("published_boundary_geometry", "digitized_published_map")) {
                    "Early Korean boundaries require documented source geometry: $id"
                }
            }
        }
        val lon: Double = row.optJSONArray("center")?.getDouble(0) ?: 0.0
        val lat: Double = row.optJSONArray("center")?.getDouble(1) ?: 0.0
        val y: Double = mercator(lat)
        val labelLon: Double = row.optJSONArray("label_center")?.getDouble(0) ?: lon
        val labelY: Double = mercator(row.optJSONArray("label_center")?.getDouble(1) ?: lat)
        // polygon -> rings -> shared open arcs (or one legacy closed ring).
        // Lookup uses the shared vertex arrays directly, without reconstructing
        // another full polygon for every administrative area.
        private val polygons = mutableListOf<List<List<DoubleArray>>>()
        val boundary: BoundaryLines?
        var minX = Double.POSITIVE_INFINITY
            private set
        var minY = Double.POSITIVE_INFINITY
            private set
        var maxX = Double.NEGATIVE_INFINITY
            private set
        var maxY = Double.NEGATIVE_INFINITY
            private set
        val area: Double get() = (maxX - minX) * (maxY - minY)

        init {
            val geometry = row.getJSONObject("geometry")
            val sharedArcs = mutableListOf<BoundaryLines>()
            if (geometry.has("arcs")) {
                val arcs = geometry.getJSONArray("arcs")
                val source = requireNotNull(network) { "Missing boundary network for $id" }
                if (geometry.getString("type") == "Polygon") addSharedPolygon(arcs, source, sharedArcs)
                else for (i in 0 until arcs.length()) addSharedPolygon(arcs.getJSONArray(i), source, sharedArcs)
            } else when (geometry.getString("type")) {
                "Point" -> { minX = lon; maxX = lon; minY = y; maxY = y }
                "Polygon" -> addPolygon(geometry.getJSONArray("coordinates"))
                "MultiPolygon" -> geometry.getJSONArray("coordinates").let { coordinates ->
                    for (i in 0 until coordinates.length()) addPolygon(coordinates.getJSONArray(i))
                }
                else -> error("Unsupported geometry: ${geometry.getString("type")}")
            }
            boundary = if (point || layer == "ui_region") null else if (network != null)
                BoundaryLines.shared(sharedArcs) else BoundaryLines(polygons.flatten().flatten())
        }

        private fun addSharedPolygon(rings: JSONArray, source: BoundaryNetwork, outlines: MutableList<BoundaryLines>) {
            polygons.add(List(rings.length()) { r ->
                val indices = rings.getJSONArray(r)
                List(indices.length()) { i ->
                    val arc = source.arc(indices.getInt(i))
                    minX = min(minX, arc.bounds.minX); maxX = max(maxX, arc.bounds.maxX)
                    minY = min(minY, arc.bounds.minY); maxY = max(maxY, arc.bounds.maxY)
                    outlines.add(arc.boundary)
                    // Ray crossings are direction-independent. Signed references
                    // therefore need no reversed coordinate allocation for lookup.
                    arc.vertices
                }
            })
        }

        private fun addPolygon(rings: JSONArray) {
            val polygon = mutableListOf<List<DoubleArray>>()
            for (r in 0 until rings.length()) {
                val ring = rings.getJSONArray(r)
                val vertices = DoubleArray(ring.length() * 2)
                for (i in 0 until ring.length()) {
                    val p = ring.getJSONArray(i)
                    val px = p.getDouble(0)
                    val py = mercator(p.getDouble(1))
                    vertices[2 * i] = px; vertices[2 * i + 1] = py
                    minX = min(minX, px); maxX = max(maxX, px)
                    minY = min(minY, py); maxY = max(maxY, py)
                }
                polygon.add(listOf(vertices))
            }
            polygons.add(polygon)
        }

        fun contains(px: Double, py: Double): Boolean {
            if (px !in minX..maxX || py !in minY..maxY) return false
            for (polygon in polygons) {
                var inside = false
                for (ring in polygon) {
                    var inRing = false
                    for (arc in ring) {
                        for (i in 2 until arc.size step 2) {
                            val xi = arc[i]; val yi = arc[i + 1]
                            val xj = arc[i - 2]; val yj = arc[i - 1]
                            if ((yi > py) != (yj > py) && px < (xj - xi) * (py - yi) / (yj - yi) + xi) inRing = !inRing
                        }
                    }
                    if (inRing) inside = !inside
                }
                if (inside) return true
            }
            return false
        }
    }

    companion object {
        /** The region whose reference geometry is shared across snapshots. */
        const val FIXED_REGION = "jp"
        const val EARTH_RADIUS_M = 6_371_000.0

        private val areaOrder = compareByDescending<Feature> { it.rank }
            .thenBy { it.system != "民政" }.thenBy { it.area }

        private val combiningMarks = Regex("\\p{M}+")
        fun normalizeSearch(value: String): String = combiningMarks.replace(
            Normalizer.normalize(value, Normalizer.Form.NFKD), "")
            .replace('đ', 'd').replace('Đ', 'D').lowercase(Locale.ROOT)

        fun mercator(latitude: Double): Double =
            Math.toDegrees(ln(tan(PI / 4 + Math.toRadians(latitude.coerceIn(-80.0, 80.0)) / 2)))

        fun latitude(y: Double): Double = Math.toDegrees(2 * atan(exp(Math.toRadians(y))) - PI / 2)

        fun distance(lon: Double, lat: Double, lon2: Double, lat2: Double): Double {
            val a = sin(Math.toRadians(lat2 - lat) / 2).pow(2) +
                cos(Math.toRadians(lat)) * cos(Math.toRadians(lat2)) * sin(Math.toRadians(lon2 - lon) / 2).pow(2)
            return EARTH_RADIUS_M / 1000 * 2 * asin(sqrt(a.coerceAtMost(1.0)))
        }

        @Volatile private var referenceYearsCache: JSONObject? = null
        private fun referenceYears(context: Context): JSONObject = referenceYearsCache
            ?: JSONObject(context.assetText("reference-years.json")).also { referenceYearsCache = it }

        fun load(context: Context, year: Int = Timeline.DEFAULT_YEAR, existingLand: List<Feature>? = null,
                 existingFeatures: List<Feature> = emptyList()): MapData {
            // Fixed reference features and their immutable projected boundary caches
            // can be shared across Chinese snapshots without parsing them again.
            val fixed = existingFeatures.filter { it.region == FIXED_REGION }.associateBy { it.id }
            val networks = fixed.values.mapNotNull { it.network }.associateBy { it.key }.toMutableMap()
            val features = mutableListOf<Feature>()
            val file = if (year == Timeline.DEFAULT_YEAR) "map.jsonl" else "snapshots/$year.jsonl"
            context.assets.open(file).bufferedReader(Charsets.UTF_8).useLines { lines ->
                lines.filter { it.isNotBlank() }.forEach {
                    if (Thread.currentThread().isInterrupted) throw java.util.concurrent.CancellationException()
                    // The compiler writes an unescaped source ID as the first field.
                    // Noncanonical JSON still takes the regular parser path below.
                    val end = if (it.startsWith("{\"id\":\"")) it.indexOf('"', 7) else -1
                    val shared = if (end > 7) fixed[it.substring(7, end)] else null
                    if (shared != null) {
                        features.add(shared)
                        return@forEach
                    }
                    val row = JSONObject(it)
                    if (row.optString("layer", "administrative") == "administrative") {
                        val key = row.optString("boundary_set")
                        val network = if (key.isEmpty()) null else networks.getOrPut(key) {
                            BoundaryNetwork(key, JSONObject(context.assetText("boundaries/$key.json")))
                        }
                        features.add(Feature(row, network))
                    }
                }
            }
            val land = existingLand ?: mutableListOf<Feature>().apply {
                val coast = JSONArray(context.assetText("land.json"))
                for (i in 0 until coast.length()) add(Feature(JSONObject().put("geometry", coast.getJSONObject(i))))
            }
            val references = referenceYears(context).getJSONObject(year.toString())
            return MapData(features, land, year, listOf("cn", "kr", "jp", "vn").associateWith {
                if (references.isNull(it)) null else references.getInt(it)
            })
        }
    }
}
