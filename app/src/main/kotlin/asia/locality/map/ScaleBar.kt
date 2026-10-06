package asia.locality.map

import kotlin.math.abs
import kotlin.math.asin
import kotlin.math.cos
import kotlin.math.ln
import kotlin.math.pow
import kotlin.math.sin

/** Rounded ground distances, with a wide retention range to prevent tier flicker. */
internal object ScaleBar {
    data class Size(val meters: Long, val pixels: Float)

    fun size(latitude: Double, span: Double, width: Int, density: Float, previous: Long): Size {
        val target = (width / 5f).coerceIn(64f * density, 160f * density)
            .coerceAtMost(width * 0.4f).toDouble()
        val latitudeCos = cos(Math.toRadians(latitude))
        fun pixels(meters: Long): Double {
            val halfAngle = sin(meters / (2 * MapData.EARTH_RADIUS_M)) / latitudeCos
            return Math.toDegrees(2 * asin(halfAngle.coerceIn(0.0, 1.0))) * width / span
        }
        if (previous > 0) {
            val retained = pixels(previous)
            if (retained in target * 0.5..target * 1.8) return Size(previous, retained.toFloat())
        }
        // Pick the closest 1/2/5 distance in logarithmic space; supports meters at street zoom.
        var bestMeters = 1L
        var bestError = Double.POSITIVE_INFINITY
        for (exponent in 0..7) {
            val unit = 10.0.pow(exponent).toLong()
            for (factor in longArrayOf(1, 2, 5)) {
                val meters = unit * factor
                if (meters > 20_000_000) continue
                val error = abs(ln(pixels(meters) / target))
                if (error < bestError) { bestError = error; bestMeters = meters }
            }
        }
        return Size(bestMeters, pixels(bestMeters).toFloat())
    }
}
