package asia.locality.map

import android.content.Context
import android.graphics.Path
import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.*

/** Offline reference geometry. A seat never supplies an administrative boundary. */
class MapData {
    val features = mutableListOf<Feature>()
    val land = mutableListOf<Feature>()

    fun at(lon: Double, lat: Double): List<Feature> {
        val y = mercator(lat)
        return features.filter { !it.point && it.contains(lon, y) }
            .sortedWith(compareByDescending<Feature> { it.rank }.thenBy { it.area })
    }

    fun contextNames(feature: Feature): String =
        (listOf(feature.parent) + at(feature.lon, feature.lat)
            .filter { it.id != feature.id && it.region == feature.region && it.rank < feature.rank }
            .map { it.name }).filter { it.isNotBlank() }.distinct().joinToString(" · ")

    /** The civil county-level area containing the point, if the boundary is known. */
    fun countyAt(lon: Double, lat: Double): Feature? =
        at(lon, lat).firstOrNull { it.rank >= 2 && it.system == "民政" }

    fun nearestCountySeat(lon: Double, lat: Double, maxKm: Double): Feature? =
        features.asSequence()
            .filter { it.id.startsWith("chgis-county:") && it.system == "民政" }
            .map { it to distance(lon, lat, it.lon, it.lat) }
            .filter { it.second < maxKm }.minByOrNull { it.second }?.first

    class Feature(row: JSONObject) {
        val id: String = row.optString("id")
        val name: String = row.optString("name")
        val parent: String = row.optString("parent")
        val kind: String = row.optString("kind")
        val region: String = row.optString("region")
        val system: String = row.optString("system", "民政")
        val rank: Int = row.optInt("rank", 1)
        val point: Boolean = row.getJSONObject("geometry").getString("type") == "Point"
        val lon: Double = row.optJSONArray("center")?.getDouble(0) ?: 0.0
        val lat: Double = row.optJSONArray("center")?.getDouble(1) ?: 0.0
        val y: Double = mercator(lat)
        private val polygons = mutableListOf<List<DoubleArray>>()
        val path = Path().apply { fillType = Path.FillType.EVEN_ODD }
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
            val coordinates = geometry.getJSONArray("coordinates")
            when (geometry.getString("type")) {
                "Point" -> { minX = lon; maxX = lon; minY = y; maxY = y }
                "Polygon" -> addPolygon(coordinates)
                "MultiPolygon" -> for (i in 0 until coordinates.length()) addPolygon(coordinates.getJSONArray(i))
                else -> error("Unsupported geometry: ${geometry.getString("type")}")
            }
        }

        private fun addPolygon(rings: JSONArray) {
            val polygon = mutableListOf<DoubleArray>()
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
                    if (i == 0) path.moveTo(px.toFloat(), -py.toFloat())
                    else path.lineTo(px.toFloat(), -py.toFloat())
                }
                path.close()
                polygon.add(vertices)
            }
            polygons.add(polygon)
        }

        fun contains(px: Double, py: Double): Boolean {
            if (px !in minX..maxX || py !in minY..maxY) return false
            for (polygon in polygons) {
                var inside = false
                for (ring in polygon) {
                    var inRing = false
                    var j = ring.size - 2
                    for (i in ring.indices step 2) {
                        val xi = ring[i]; val yi = ring[i + 1]
                        val xj = ring[j]; val yj = ring[j + 1]
                        if ((yi > py) != (yj > py) && px < (xj - xi) * (py - yi) / (yj - yi) + xi) inRing = !inRing
                        j = i
                    }
                    if (inRing) inside = !inside
                }
                if (inside) return true
            }
            return false
        }
    }

    companion object {
        fun mercator(latitude: Double): Double =
            Math.toDegrees(ln(tan(PI / 4 + Math.toRadians(latitude.coerceIn(-80.0, 80.0)) / 2)))

        fun latitude(y: Double): Double = Math.toDegrees(2 * atan(exp(Math.toRadians(y))) - PI / 2)

        fun distance(lon: Double, lat: Double, lon2: Double, lat2: Double): Double {
            val a = sin(Math.toRadians(lat2 - lat) / 2).pow(2) +
                cos(Math.toRadians(lat)) * cos(Math.toRadians(lat2)) * sin(Math.toRadians(lon2 - lon) / 2).pow(2)
            return 6371 * 2 * asin(sqrt(a.coerceAtMost(1.0)))
        }

        fun load(context: Context): MapData = MapData().apply {
            context.assets.open("map.jsonl").bufferedReader(Charsets.UTF_8).useLines { lines ->
                lines.filter { it.isNotBlank() }.forEach { features.add(Feature(JSONObject(it))) }
            }
            val coast = context.assets.open("land.json").bufferedReader(Charsets.UTF_8).use { JSONArray(it.readText()) }
            for (i in 0 until coast.length()) land.add(Feature(JSONObject().put("geometry", coast.getJSONObject(i))))
        }
    }
}
