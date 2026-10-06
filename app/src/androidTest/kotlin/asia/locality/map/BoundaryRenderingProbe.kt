package asia.locality.map

import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import androidx.core.graphics.createBitmap
import org.json.JSONObject
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin

/** Guard against false chunk-closing edges, clipping artifacts and altered area lookup. */
object BoundaryRenderingProbe {
    fun verify() {
        val ring = DoubleArray(802)
        for (i in 0..400) {
            val angle = (i % 400) * 2 * PI / 400
            ring[2 * i] = cos(angle)
            ring[2 * i + 1] = sin(angle)
        }
        val original = ring.copyOf()
        val boundary = BoundaryLines(listOf(ring))
        check(ring.contentEquals(original)) { "Display preprocessing changed source coordinates" }
        val buffer = BoundaryLines.Buffer()
        // The viewport is inside the ring, but contains none of its outline.
        boundary.appendVisible(buffer, 1000.0, -0.01, -0.01, 0.01, 0.01)
        check(buffer.size == 0) { "Offscreen ring introduced a false interior edge" }
        buffer.clear()
        boundary.appendVisible(buffer, 100.0, -1.5, -1.5, 1.5, 1.5)
        check(buffer.size > 0)
        val bitmap = createBitmap(300, 300)
        try {
            val canvas = Canvas(bitmap)
            val paint = Paint().apply { color = Color.BLACK; strokeWidth = 2f }
            canvas.drawColor(Color.WHITE)
            buffer.draw(canvas, paint)
            check(bitmap.getPixel(150, 150) == Color.WHITE)
            check((248..251).any { bitmap.getPixel(it, 150) != Color.WHITE })
            buffer.clear()
            buffer.line(-1e9, 150.0, 1e9, 150.0, 300.0, 300.0)
            buffer.line(150.0, -1e9, 150.0, 1e9, 300.0, 300.0)
            buffer.line(-20.0, 0.0, -20.0, 300.0, 300.0, 300.0)
            check(buffer.size == 8) { "Clipping failed to reject an offscreen edge" }
            canvas.drawColor(Color.WHITE)
            buffer.draw(canvas, paint)
            check(bitmap.getPixel(150, 150) == Color.BLACK)
            check(bitmap.getPixel(0, 150) == Color.BLACK && bitmap.getPixel(299, 150) == Color.BLACK)
            check(bitmap.getPixel(10, 10) == Color.WHITE)
        } finally { bitmap.recycle() }
        val feature = MapData.Feature(JSONObject("""{
            "geometry":{"type":"Polygon","coordinates":[
                [[0,0],[4,0],[4,4],[0,4],[0,0]],
                [[1,1],[3,1],[3,3],[1,3],[1,1]]
            ]}
        }"""))
        check(feature.contains(0.5, MapData.mercator(0.5)))
        check(!feature.contains(2.0, MapData.mercator(2.0)))
        check(!feature.contains(5.0, MapData.mercator(2.0)))
        verifyEarlyKoreanSourcePolicy()
        verifySharedBoundaries()
    }

    private fun verifyEarlyKoreanSourcePolicy() {
        for (year in listOf(757, 1370)) {
            val row = JSONObject("""{"id":"source-test","region":"kr","year":$year,
                "geometry":{"type":"Polygon","coordinates":[[[126,36],[127,36],[127,37],[126,37],[126,36]]]}}
            """)
            check(runCatching { MapData.Feature(row) }.exceptionOrNull() is IllegalArgumentException)
            row.put("boundary_basis", "published_boundary_geometry")
            check(!MapData.Feature(row).point)
            row.put("boundary_basis", "digitized_published_map")
            check(!MapData.Feature(row).point)
            row.put("inferred", true)
            check(runCatching { MapData.Feature(row) }.exceptionOrNull() is IllegalArgumentException)
        }
    }

    private fun verifySharedBoundaries() {
        val network = BoundaryNetwork("test", JSONObject("""{"arcs":[
            [[1,0],[0,0],[0,1],[1,1]], [[1,0],[1,1]], [[1,1],[2,1],[2,0],[1,0]]
        ]}"""))
        val left = MapData.Feature(JSONObject("""{"id":"left","geometry":{"type":"Polygon","arcs":[[0,-2]]}}"""), network)
        val right = MapData.Feature(JSONObject("""{"id":"right","geometry":{"type":"Polygon","arcs":[[1,2]]}}"""), network)
        check(left.network === right.network)
        check(left.contains(.5, MapData.mercator(.5)))
        check(!left.contains(1.5, MapData.mercator(.5)))
        check(right.contains(1.5, MapData.mercator(.5)))
        check(!right.contains(.5, MapData.mercator(.5)))
        val buffer = BoundaryLines.Buffer()
        left.boundary!!.appendVisible(buffer, 100.0, -1.0, -1.0, 3.0, 3.0)
        right.boundary!!.appendVisible(buffer, 100.0, -1.0, -1.0, 3.0, 3.0)
        check(buffer.size == 7 * 4) { "Shared edge was drawn twice" }
        buffer.clear(keepSeen = true)
        right.boundary.appendVisible(buffer, 100.0, -1.0, -1.0, 3.0, 3.0)
        check(buffer.size == 0) { "Fine layer repainted a previously drawn shared edge" }
        buffer.clear()
        right.boundary.appendVisible(buffer, 100.0, -1.0, -1.0, 3.0, 3.0)
        check(buffer.size == 4 * 4) { "Selection lost part of its complete outline" }
    }
}
