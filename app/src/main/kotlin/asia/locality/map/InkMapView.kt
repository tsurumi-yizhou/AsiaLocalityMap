package asia.locality.map

import android.content.Context
import android.animation.ValueAnimator
import android.view.animation.DecelerateInterpolator
import androidx.core.graphics.withTranslation
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.Typeface
import android.util.AttributeSet
import android.view.GestureDetector
import android.view.MotionEvent
import android.view.ScaleGestureDetector
import android.view.View
import kotlin.math.max
import kotlin.math.exp
import kotlin.math.ln
import kotlin.math.roundToLong

/** White paper, ink boundaries and names. Reuses label geometry across frames. */
class InkMapView @JvmOverloads constructor(
    context: Context, attrs: AttributeSet? = null, defStyleAttr: Int = 0
) : View(context, attrs, defStyleAttr) {
    interface Listener {
        fun onPlace(feature: MapData.Feature)
        fun onMapPoint(lon: Double, lat: Double)
    }

    var listener: Listener? = null
    private val density = resources.displayMetrics.density
    private val ink = Paint(Paint.ANTI_ALIAS_FLAG)
    private val text = Paint(Paint.ANTI_ALIAS_FLAG).apply { textAlign = Paint.Align.CENTER }
    private var data: MapData? = null
    private var centerX = 122.0
    private var centerY = MapData.mercator(33.0)
    private var span = 40.0
    private var hereX: Double? = null
    private var hereY = 0.0
    private var selected: MapData.Feature? = null
    private var hereCounty: MapData.Feature? = null
    private class Label {
        val bounds = RectF()
        var feature: MapData.Feature? = null
    }
    private val labels = Array(66) { Label() }
    private var labelCount = 0
    private val candidateBounds = RectF()
    private var scaleKilometers = Long.MIN_VALUE
    private var scaleCaption = ""
    private var tapX: Float? = null
    private var tapY = 0f
    private var confirmTap: (() -> Unit)? = null
    private var cameraAnimator: ValueAnimator? = null
    private var targetSpan = span
    private var hasDrawnMap = false

    private val pinch = ScaleGestureDetector(context, object : ScaleGestureDetector.SimpleOnScaleGestureListener() {
        override fun onScale(detector: ScaleGestureDetector): Boolean {
            val oldScale = scale()
            val focusX = centerX + (detector.focusX - width / 2.0) / oldScale
            val focusY = centerY - (detector.focusY - height / 2.0) / oldScale
            span = (span / detector.scaleFactor).coerceIn(0.04, 100.0)
            centerX = focusX - (detector.focusX - width / 2.0) / scale()
            centerY = focusY + (detector.focusY - height / 2.0) / scale()
            constrain(); invalidate()
            return true
        }
    })
    private val gestures = GestureDetector(context, object : GestureDetector.SimpleOnGestureListener() {
        override fun onDown(e: MotionEvent) = true
        override fun onScroll(a: MotionEvent?, b: MotionEvent, dx: Float, dy: Float): Boolean {
            if (!pinch.isInProgress) {
                centerX += dx / scale(); centerY -= dy / scale()
                constrain(); invalidate()
            }
            return true
        }
        override fun onDoubleTap(e: MotionEvent): Boolean {
            tapX = null; zoom(0.5)
            return true
        }
        override fun onSingleTapConfirmed(e: MotionEvent): Boolean {
            tapX = e.x; tapY = e.y
            confirmTap?.invoke()
            return true
        }
    })

    init {
        setBackgroundColor(Color.WHITE)
        contentDescription = context.getString(R.string.map_description)
        isFocusable = true
        isClickable = true
    }

    fun setFont(font: Typeface) { text.typeface = font; invalidate() }
    fun setData(value: MapData) { data = value; invalidate() }
    fun select(feature: MapData.Feature?) { selected = feature; invalidate() }
    fun go(lon: Double, lat: Double, width: Double) {
        animateCamera(lon, MapData.mercator(lat), width)
    }
    fun setHere(lon: Double, lat: Double) { hereX = lon; hereY = MapData.mercator(lat); invalidate() }
    fun nameHere(county: MapData.Feature?) { hereCounty = county; invalidate() }
    fun focusCounty(lon: Double, lat: Double, county: MapData.Feature) {
        val y = MapData.mercator(lat)
        val aspect = if (height > 0) width.toDouble() / height else 1.0
        val extent = 2.4 * max(max(lon - county.minX, county.maxX - lon), max(y - county.minY, county.maxY - y) * aspect)
        go(lon, lat, extent.coerceIn(0.12, 8.0))
    }
    fun zoom(factor: Double) {
        val base = if (cameraAnimator?.isRunning == true) targetSpan else span
        animateCamera(centerX, centerY, base * factor)
    }
    private fun stopCameraAnimation() {
        cameraAnimator?.cancel()
        cameraAnimator = null
    }
    private fun animateCamera(x: Double, y: Double, requestedSpan: Double) {
        stopCameraAnimation()
        val endX = x.coerceIn(-180.0, 180.0)
        val endY = y.coerceIn(-140.0, 140.0)
        targetSpan = requestedSpan.coerceIn(0.04, 100.0)
        if (!hasDrawnMap || !isAttachedToWindow || !ValueAnimator.areAnimatorsEnabled()) {
            centerX = endX; centerY = endY; span = targetSpan
            invalidate()
            return
        }
        val startX = centerX
        val startY = centerY
        val startLogSpan = ln(span)
        val endLogSpan = ln(targetSpan)
        cameraAnimator = ValueAnimator.ofFloat(0f, 1f).apply {
            duration = 260
            interpolator = DecelerateInterpolator()
            addUpdateListener { animation ->
                val fraction = (animation.animatedValue as Float).toDouble()
                centerX = startX + (endX - startX) * fraction
                centerY = startY + (endY - startY) * fraction
                span = exp(startLogSpan + (endLogSpan - startLogSpan) * fraction)
                invalidate()
            }
            start()
        }
    }
    fun viewport(): DoubleArray = doubleArrayOf(centerX, centerY, span)
    fun restoreViewport(value: DoubleArray) {
        if (value.size != 3) return
        stopCameraAnimation()
        centerX = value[0]; centerY = value[1]; span = value[2].coerceIn(0.04, 100.0)
        constrain(); invalidate()
    }
    private fun scale() = max(1, width) / span
    private fun constrain() {
        centerX = centerX.coerceIn(-180.0, 180.0); centerY = centerY.coerceIn(-140.0, 140.0)
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (event.actionMasked == MotionEvent.ACTION_DOWN) stopCameraAnimation()
        // GestureDetector confirms a single tap only after excluding double tap.
        // Route it through the same click action used by accessibility services.
        if (confirmTap == null) confirmTap = { performClick() }
        pinch.onTouchEvent(event)
        gestures.onTouchEvent(event)
        return true
    }

    override fun performClick(): Boolean {
        super.performClick()
        val x = tapX
        tapX = null
        if (x == null) {
            selected?.let { listener?.onPlace(it) }
                ?: listener?.onMapPoint(centerX, MapData.latitude(centerY))
            return true
        }
        for (i in labelCount - 1 downTo 0) {
            val label = labels[i]
            if (label.bounds.contains(x, tapY)) {
                label.feature?.let { select(it); listener?.onPlace(it) }
                return true
            }
        }
        listener?.onMapPoint(centerX + (x - width / 2.0) / scale(), MapData.latitude(centerY - (tapY - height / 2.0) / scale()))
        return true
    }

    override fun onDetachedFromWindow() {
        stopCameraAnimation()
        confirmTap = null
        super.onDetachedFromWindow()
    }
    private fun sx(x: Double) = ((x - centerX) * scale() + width / 2.0).toFloat()
    private fun sy(y: Double) = ((centerY - y) * scale() + height / 2.0).toFloat()
    private fun visible(f: MapData.Feature) = sx(f.maxX) >= 0 && sx(f.minX) <= width && sy(f.minY) >= 0 && sy(f.maxY) <= height

    private fun drawBoundary(canvas: Canvas, f: MapData.Feature, color: Int, stroke: Float) {
        if (!visible(f)) return
        ink.color = color; ink.style = Paint.Style.STROKE; ink.strokeWidth = (stroke * density / scale()).toFloat()
        canvas.withTranslation(width / 2f, height / 2f) {
            scale(scale().toFloat(), scale().toFloat())
            translate(-centerX.toFloat(), centerY.toFloat())
            drawPath(f.path, ink)
        }
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        labelCount = 0
        val loaded = data ?: return
        hasDrawnMap = true
        val boundaryVisible = loaded.features.any { !it.point && visible(it) }
        if (span > 8 || !boundaryVisible) for (f in loaded.land) drawBoundary(canvas, f, 0xffbbbbbb.toInt(), 0.7f)
        for (f in loaded.features) {
            if (f.point || (f.rank > 1 && span > 8)) continue
            drawBoundary(canvas, f, if (f.rank == 1) 0xff777777.toInt() else 0xffb0b0b0.toInt(), if (f.rank == 1) 0.8f else 0.5f)
        }
        selected?.takeUnless { it.point }?.let { drawBoundary(canvas, it, 0xff242424.toInt(), 1.3f) }
        val county = hereCounty
        val lon = hereX
        if (lon != null && county != null) drawLabel(canvas, county, sx(lon), sy(hereY), true)
        selected?.let { drawLabel(canvas, it, sx(it.lon), sy(it.y), true) }
        for (f in loaded.features) {
            if (f !== selected && (!f.point || span < 5) &&
                (if (span >= 5) f.rank == 1 else f.rank >= 2 && f.system == "民政")) {
                drawLabel(canvas, f, sx(f.lon), sy(f.y), false)
            }
            if (labelCount >= 65) break
        }
        text.textSize = 12 * density; text.color = 0xff999999.toInt(); text.textAlign = Paint.Align.LEFT
        val km = MapData.distance(centerX, MapData.latitude(centerY), centerX + span / 5, MapData.latitude(centerY)).roundToLong()
        if (km != scaleKilometers) { scaleKilometers = km; scaleCaption = resources.getString(R.string.scale_km, km) }
        canvas.drawText(scaleCaption, 16 * density, height - 16 * density, text)
        text.textAlign = Paint.Align.CENTER
        ink.color = 0xff999999.toInt(); ink.style = Paint.Style.STROKE; ink.strokeWidth = density * 0.6f
        canvas.drawLine(16 * density, height - 35 * density, 16 * density + width / 5f, height - 35 * density, ink)
    }

    private fun drawLabel(canvas: Canvas, f: MapData.Feature, x: Float, y: Float, force: Boolean) {
        if (labelCount >= labels.size || x < 12 * density || x > width - 12 * density || y < 25 * density || y > height - 55 * density) return
        for (i in 0 until labelCount) if (labels[i].feature?.id == f.id) return
        text.textSize = (if (force) 20 else if (f.rank == 1) 18 else 16) * density
        text.color = if (force) 0xff111111.toInt() else 0xff4c4c4c.toInt()
        val halfWidth = text.measureText(f.name) / 2 + 7 * density
        candidateBounds.set(x - halfWidth, y - text.textSize, x + halfWidth, y + 8 * density)
        for (i in 0 until labelCount) if (RectF.intersects(candidateBounds, labels[i].bounds)) return
        drawName(canvas, f.name, x, y)
        labels[labelCount].apply { bounds.set(candidateBounds); feature = f }
        labelCount++
    }

    private fun drawName(canvas: Canvas, value: String, x: Float, y: Float) {
        val color = text.color
        text.style = Paint.Style.STROKE; text.strokeWidth = 4 * density; text.color = Color.WHITE
        canvas.drawText(value, x, y, text)
        text.style = Paint.Style.FILL; text.color = color
        canvas.drawText(value, x, y, text)
    }
}
