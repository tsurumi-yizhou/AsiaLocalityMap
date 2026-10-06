package asia.locality.map

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.os.Handler
import android.os.Looper
import androidx.core.graphics.createBitmap
import java.util.concurrent.Executors
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sqrt

/** Map viewport: centre in projected degrees, horizontal span in degrees, and view size in pixels. */
data class MapCamera(val x: Double, val y: Double, val span: Double, val width: Int, val height: Int) {
    val scale get() = max(1, width) / span
    val left get() = x - span / 2
    val right get() = x + span / 2
    val top get() = y + height / (2 * scale)
    val bottom get() = y - height / (2 * scale)
}

/** Rasterize immutable boundary geometry off the UI thread; reuse it while the camera moves. */
class BoundaryLayer(private val invalidate: () -> Unit) {
    private class Tile(val bitmap: Bitmap, val camera: MapCamera, val scale: Double, val left: Double, val top: Double) {
        val right = left + bitmap.width / scale
        val bottom = top - bitmap.height / scale
    }
    private val worker = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())
    private val bitmapPaint = Paint(Paint.FILTER_BITMAP_FLAG)
    private val destination = RectF()
    private var source: MapData? = null
    private var tile: Tile? = null
    private var running = false
    private var generation = 0
    private var closed = false

    fun draw(canvas: Canvas, data: MapData, camera: MapCamera, density: Float, settled: Boolean) {
        if (closed || camera.width <= 0 || camera.height <= 0) return
        if (source !== data) { source = data; tile = null; generation++ }
        val scale = camera.scale
        val left = camera.left
        val top = camera.top
        val current = tile
        val reusable = current != null && abs(current.camera.scale / scale - 1) < 0.12 &&
            left >= current.left && camera.right <= current.right &&
            top <= current.top && camera.bottom >= current.bottom &&
            (camera.span <= 8) == (current.camera.span <= 8)
        if (!running && (!reusable || (settled && current?.camera != camera))) {
            running = true
            val version = generation
            worker.execute {
                val rendered = render(data, camera, density)
                main.post {
                    running = false
                    if (closed || generation != version) rendered.bitmap.recycle()
                    else tile = rendered
                    if (!closed) invalidate()
                }
            }
        }
        if (current != null) {
            destination.set(((current.left - left) * scale).toFloat(), ((top - current.top) * scale).toFloat(),
                ((current.right - left) * scale).toFloat(), ((top - current.bottom) * scale).toFloat())
            canvas.drawBitmap(current.bitmap, null, destination, bitmapPaint)
        }
    }

    fun close() {
        closed = true
        generation++
        tile = null
        source = null
        // Do not recycle a displayed bitmap while RenderThread may still reference it.
        worker.shutdown()
    }

    private fun render(data: MapData, camera: MapCamera, density: Float): Tile {
        // Overscan keeps newly exposed edges available during dragging. Cap each bitmap at 24 MB.
        val ratio = min(1.0, sqrt(6_000_000.0 / (camera.width.toDouble() * camera.height * 1.69)))
        val width = (camera.width * 1.3 * ratio).toInt().coerceAtLeast(1)
        val height = (camera.height * 1.3 * ratio).toInt().coerceAtLeast(1)
        val scale = camera.width / camera.span * ratio
        val left = camera.x - width / (2 * scale)
        val top = camera.y + height / (2 * scale)
        val right = left + width / scale
        val bottom = top - height / scale
        val bitmap = createBitmap(width, height)
        val canvas = Canvas(bitmap)
        canvas.drawColor(Color.WHITE)
        val paint = Paint(Paint.ANTI_ALIAS_FLAG)
        val buffer = BoundaryLines.Buffer()
        fun append(feature: MapData.Feature) {
            if (feature.maxX >= left && feature.minX <= right && feature.maxY >= bottom && feature.minY <= top) {
                feature.boundary?.appendVisible(buffer, scale, left, bottom, right, top)
            }
        }
        fun stroke(color: Int, thickness: Float, keepSeen: Boolean = false) {
            paint.color = color
            paint.strokeWidth = (thickness * density * ratio).toFloat()
            buffer.draw(canvas, paint)
            buffer.clear(keepSeen)
        }
        val boundaryVisible = data.features.any { !it.point && it.maxX >= camera.left &&
            it.minX <= camera.right && it.minY <= camera.top && it.maxY >= camera.bottom }
        if (camera.span > 8 || !boundaryVisible) {
            for (feature in data.land) append(feature)
            stroke(0xffbbbbbb.toInt(), 0.7f)
        }
        for (feature in data.features) if (!feature.point && feature.rank == 1) append(feature)
        stroke(0xff777777.toInt(), 0.8f, keepSeen = true)
        if (camera.span <= 8) {
            for (feature in data.features) if (!feature.point && feature.rank > 1) append(feature)
            stroke(0xffb0b0b0.toInt(), 0.5f)
        }
        return Tile(bitmap, camera, scale, left, top)
    }
}
