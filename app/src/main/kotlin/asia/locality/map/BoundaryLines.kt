package asia.locality.map

import android.graphics.Canvas
import android.graphics.Paint
import kotlin.math.max
import kotlin.math.min

/** Axis-aligned extent of projected vertices. */
internal class Bounds {
    var minX = Double.POSITIVE_INFINITY
        private set
    var minY = Double.POSITIVE_INFINITY
        private set
    var maxX = Double.NEGATIVE_INFINITY
        private set
    var maxY = Double.NEGATIVE_INFINITY
        private set

    fun add(x: Double, y: Double) {
        minX = min(minX, x); maxX = max(maxX, x)
        minY = min(minY, y); maxY = max(maxY, y)
    }

    fun add(other: Bounds) {
        add(other.minX, other.minY); add(other.maxX, other.maxY)
    }

    fun misses(left: Double, bottom: Double, right: Double, top: Double, margin: Double): Boolean =
        maxX < left - margin || minX > right + margin || maxY < bottom - margin || minY > top + margin
}

/** Display-only LOD; the shared projected arcs used by lookup remain untouched. */
class BoundaryLines private constructor(private val rings: List<DoubleArray>, private val shared: List<BoundaryLines>?) {
    constructor(rings: List<DoubleArray>) : this(rings, null)
    internal val bounds = Bounds()
    internal val minX get() = bounds.minX
    internal val minY get() = bounds.minY
    internal val maxX get() = bounds.maxX
    internal val maxY get() = bounds.maxY

    init {
        if (shared != null) for (arc in shared) bounds.add(arc.bounds)
        else for (ring in rings) for (i in ring.indices step 2) bounds.add(ring[i], ring[i + 1])
    }
    private class Segment(val vertices: DoubleArray, val first: Int, val last: Int) {
        val bounds = Bounds().also { box ->
            for (index in first..last) box.add(vertices[index * 2], vertices[index * 2 + 1])
        }
    }

    // Built on first use: most levels are never drawn, and the result is deterministic,
    // so a racing duplicate build is harmless.
    private val levels = if (shared == null) arrayOfNulls<List<Segment>>(tolerances.size) else null

    private fun level(index: Int): List<Segment> = levels!![index] ?: buildLevel(tolerances[index]).also { levels[index] = it }

    private fun buildLevel(tolerance: Double): List<Segment> = buildList {
        for (ring in rings) {
            val vertices = simplify(ring, tolerance)
            val count = vertices.size / 2
            var first = 0
            while (first < count - 1) {
                val last = min(first + 128, count - 1)
                add(Segment(vertices, first, last))
                first = last
            }
        }
    }

    fun appendVisible(buffer: Buffer, pixelsPerDegree: Double,
                      left: Double, bottom: Double, right: Double, top: Double) {
        val margin = buffer.margin / pixelsPerDegree
        // Reject entire areas/arcs before walking references or allocating dedup entries.
        if (bounds.misses(left, bottom, right, top, margin)) return
        if (shared != null) {
            for (arc in shared) arc.appendVisible(buffer, pixelsPerDegree, left, bottom, right, top)
            return
        }
        if (!buffer.include(this)) return
        val width = (right - left) * pixelsPerDegree
        val height = (top - bottom) * pixelsPerDegree
        for (segment in level(buffer.levelFor(pixelsPerDegree))) {
            if (segment.bounds.misses(left, bottom, right, top, margin)) continue
            val vertices = segment.vertices
            for (index in segment.first until segment.last) {
                buffer.line((vertices[index * 2] - left) * pixelsPerDegree,
                    (top - vertices[index * 2 + 1]) * pixelsPerDegree,
                    (vertices[index * 2 + 2] - left) * pixelsPerDegree,
                    (top - vertices[index * 2 + 3]) * pixelsPerDegree, width, height)
            }
        }
    }

    /** Reused across frames; submit clipped, screen-space lines in one call per ink style. */
    class Buffer(val margin: Double = 4.0) {
        private var coordinates = FloatArray(4096)
        private val seen = HashSet<BoundaryLines>()
        var size = 0
            private set

        fun clear(keepSeen: Boolean = false) {
            size = 0
            if (!keepSeen) seen.clear()
        }

        internal fun include(boundary: BoundaryLines): Boolean = seen.add(boundary)

        private var levelPixels = Double.NaN
        private var level = 0

        /** Only precomputed detail whose display error stays under half a pixel; cached per frame scale. */
        internal fun levelFor(pixelsPerDegree: Double): Int {
            if (pixelsPerDegree != levelPixels) {
                val tolerance = 0.5 / pixelsPerDegree
                level = tolerances.indexOfLast { it <= tolerance }.coerceAtLeast(0)
                levelPixels = pixelsPerDegree
            }
            return level
        }

        fun draw(canvas: Canvas, paint: Paint) {
            if (size > 0) canvas.drawLines(coordinates, 0, size, paint)
        }

        private fun outcode(x: Double, y: Double, width: Double, height: Double): Int =
            (if (x < -margin) 1 else if (x > width + margin) 2 else 0) or
                (if (y < -margin) 4 else if (y > height + margin) 8 else 0)

        fun line(startX: Double, startY: Double, endX: Double, endY: Double, width: Double, height: Double) {
            var ax = startX; var ay = startY; var bx = endX; var by = endY
            var a = outcode(ax, ay, width, height)
            var b = outcode(bx, by, width, height)
            while ((a or b) != 0) {
                if ((a and b) != 0) return
                val outside = if (a != 0) a else b
                val x: Double
                val y: Double
                when {
                    outside and 4 != 0 -> { y = -margin; x = ax + (bx - ax) * (y - ay) / (by - ay) }
                    outside and 8 != 0 -> { y = height + margin; x = ax + (bx - ax) * (y - ay) / (by - ay) }
                    outside and 1 != 0 -> { x = -margin; y = ay + (by - ay) * (x - ax) / (bx - ax) }
                    else -> { x = width + margin; y = ay + (by - ay) * (x - ax) / (bx - ax) }
                }
                if (outside == a) { ax = x; ay = y; a = outcode(ax, ay, width, height) }
                else { bx = x; by = y; b = outcode(bx, by, width, height) }
            }
            if (size + 4 > coordinates.size) coordinates = coordinates.copyOf(coordinates.size * 2)
            coordinates[size++] = ax.toFloat(); coordinates[size++] = ay.toFloat()
            coordinates[size++] = bx.toFloat(); coordinates[size++] = by.toFloat()
        }
    }

    companion object {
        private val tolerances = doubleArrayOf(0.0, 0.001, 0.002, 0.004, 0.008, 0.016, 0.032, 0.064, 0.128)
        fun shared(arcs: List<BoundaryLines>): BoundaryLines = BoundaryLines(emptyList(), arcs.distinct())
        /** Iterative Douglas–Peucker in projected coordinates; also preserves ring closure. */
        internal fun simplify(vertices: DoubleArray, tolerance: Double): DoubleArray {
            if (tolerance == 0.0 || vertices.size <= 6) return vertices
            val count = vertices.size / 2
            val keep = BooleanArray(count)
            keep[0] = true; keep[count - 1] = true
            val stack = IntArray(count * 2)
            var size = 0
            stack[size++] = 0; stack[size++] = count - 1
            val threshold = tolerance * tolerance
            while (size > 0) {
                val last = stack[--size]
                val first = stack[--size]
                val ax = vertices[first * 2]; val ay = vertices[first * 2 + 1]
                val dx = vertices[last * 2] - ax; val dy = vertices[last * 2 + 1] - ay
                val length = dx * dx + dy * dy
                var furthest = -1
                var maxDistance = threshold
                for (index in first + 1 until last) {
                    val px = vertices[index * 2] - ax; val py = vertices[index * 2 + 1] - ay
                    val t = if (length == 0.0) 0.0 else ((px * dx + py * dy) / length).coerceIn(0.0, 1.0)
                    val ex = px - t * dx; val ey = py - t * dy
                    val distance = ex * ex + ey * ey
                    if (distance > maxDistance) { maxDistance = distance; furthest = index }
                }
                if (furthest >= 0) {
                    keep[furthest] = true
                    stack[size++] = first; stack[size++] = furthest
                    stack[size++] = furthest; stack[size++] = last
                }
            }
            val result = DoubleArray(keep.count { it } * 2)
            var position = 0
            for (index in 0 until count) if (keep[index]) {
                result[position++] = vertices[index * 2]
                result[position++] = vertices[index * 2 + 1]
            }
            return result
        }
    }
}
