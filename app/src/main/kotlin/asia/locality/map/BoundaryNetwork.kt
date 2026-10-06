package asia.locality.map

import org.json.JSONObject

/** One immutable projected copy and display cache for each shared boundary arc. */
class BoundaryNetwork(val key: String, row: JSONObject) {
    class Arc(val vertices: DoubleArray) {
        val boundary = BoundaryLines(listOf(vertices))
        internal val bounds get() = boundary.bounds
    }

    val arcs: List<Arc> = row.getJSONArray("arcs").let { values ->
        List(values.length()) { i ->
            val points = values.getJSONArray(i)
            Arc(DoubleArray(points.length() * 2).also { vertices ->
                for (p in 0 until points.length()) {
                    val point = points.getJSONArray(p)
                    vertices[p * 2] = point.getDouble(0)
                    vertices[p * 2 + 1] = MapData.mercator(point.getDouble(1))
                }
            })
        }
    }

    fun arc(index: Int): Arc = arcs[if (index < 0) index.inv() else index]
}
