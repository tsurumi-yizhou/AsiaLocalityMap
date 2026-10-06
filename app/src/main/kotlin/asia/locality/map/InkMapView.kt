package asia.locality.map

import android.content.Context
import android.animation.ValueAnimator
import android.view.animation.DecelerateInterpolator
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.Typeface
import android.util.AttributeSet
import android.os.SystemClock
import android.view.GestureDetector
import android.view.MotionEvent
import android.view.ScaleGestureDetector
import android.view.View
import kotlin.math.max
import kotlin.math.exp
import kotlin.math.ln
import kotlin.math.roundToInt
import kotlin.math.min

/** White paper, ink boundaries and names. Reuses label geometry across frames. */
class InkMapView @JvmOverloads constructor(
    context: Context, attrs: AttributeSet? = null, defStyleAttr: Int = 0
) : View(context, attrs, defStyleAttr) {
    interface Listener {
        fun onPlace(feature: MapData.Feature)
        fun onMapPoint(lon: Double, lat: Double)
        fun onViewportChanged(lon: Double, lat: Double)
    }

    var listener: Listener? = null
    private val density = resources.displayMetrics.density
    private val ink = Paint(Paint.ANTI_ALIAS_FLAG)
    private val boundaryBuffer = BoundaryLines.Buffer(max(4.0, density * 2.0))
    private val text = Paint(Paint.ANTI_ALIAS_FLAG).apply { textAlign = Paint.Align.CENTER }
    private var data: MapData? = null
    private var centerX = 122.0
    private var centerY = MapData.mercator(33.0)
    private var span = 40.0
    private var hereX: Double? = null
    private var hereY = 0.0
    private var selected: MapData.Feature? = null
    private var hereArea: MapData.Feature? = null
    private class Label {
        val bounds = RectF()
        var feature: MapData.Feature? = null
    }
    private val labels = Array(66) { Label() }
    private var labelCount = 0
    private var labelTopInset = 0
    private val candidateBounds = RectF()
    private var scaleMeters = 0L
    private var scaleCaption = ""
    private var scaleBarPixels = 0f
    private data class ScaleKey(val span: Double, val y: Double, val width: Int)
    private var scaleKey = ScaleKey(Double.NaN, Double.NaN, 0)
    private var scaleBarAnimator: ValueAnimator? = null
    private var tapX: Float? = null
    private var tapY = 0f
    private var markerX = Double.NaN
    private var markerY = 0.0
    private var twoFingerStart = 0L
    private var twoFingerMoved = false
    private var cameraAnimator: ValueAnimator? = null
    private var targetSpan = span
    private var hasDrawnMap = false
    private var frame = MapCamera(centerX, centerY, span, 1, 1)
    private var boundaryLayer: BoundaryLayer? = null
    private var layerCamera: MapCamera? = null
    private var boundarySettled = false
    private var touchActive = false
    private val refineBoundary = Runnable {
        if (!touchActive && cameraAnimator?.isRunning != true) {
            boundarySettled = true
            listener?.onViewportChanged(centerX, MapData.latitude(centerY))
            invalidate()
        }
    }
    private class StableLabel(val feature: MapData.Feature, var opacity: Float = 0f, var target: Boolean = false)
    private val stableLabels = mutableListOf<StableLabel>()
    private var labelsDirty = true
    // Name widths depend only on the feature, font and density; labels are re-placed every frame.
    private val nameWidths = HashMap<MapData.Feature, Float>()
    private var labelLevelInitialized = false
    private var detailedLabels = false
    private var lastLabelFrame = 0L

    private companion object { const val TWO_FINGER_TAP_MS = 250L }

    private val pinch = ScaleGestureDetector(context, object : ScaleGestureDetector.SimpleOnScaleGestureListener() {
        override fun onScale(detector: ScaleGestureDetector): Boolean {
            val oldScale = scale()
            val focusX = centerX + (detector.focusX - width / 2.0) / oldScale
            val focusY = centerY - (detector.focusY - height / 2.0) / oldScale
            if (detector.scaleFactor != 1f) twoFingerMoved = true
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
                twoFingerMoved = true
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
            performClick()
            return true
        }
    })

    init {
        setBackgroundColor(Color.WHITE)
        contentDescription = context.getString(R.string.map_description)
        isFocusable = true
        isClickable = true
    }

    fun setFont(font: Typeface) { text.typeface = font; nameWidths.clear(); invalidate() }
    fun setLabelTopInset(value: Int) {
        if (labelTopInset == value) return
        labelTopInset = value
        labelsDirty = true
        invalidate()
    }
    fun setData(value: MapData) {
        data = value
        selected = null
        hereArea = null
        labelCount = 0
        tapX = null
        markerX = Double.NaN
        stableLabels.clear()
        nameWidths.clear()
        labelsDirty = true
        labelLevelInitialized = false
        invalidate()
    }
    fun select(feature: MapData.Feature?) {
        selected = feature
        if (feature != null) markerX = Double.NaN
        labelsDirty = true
        invalidate()
    }
    fun go(lon: Double, lat: Double, width: Double) {
        animateCamera(lon, MapData.mercator(lat), width)
    }
    fun setHere(lon: Double, lat: Double) { hereX = lon; hereY = MapData.mercator(lat); invalidate() }
    fun nameHere(area: MapData.Feature?) { hereArea = area; labelsDirty = true; invalidate() }
    fun focusCounty(lon: Double, lat: Double, area: MapData.Feature) {
        val y = MapData.mercator(lat)
        val aspect = if (height > 0) width.toDouble() / height else 1.0
        val extent = 2.4 * max(max(lon - area.minX, area.maxX - lon), max(y - area.minY, area.maxY - y) * aspect)
        go(lon, lat, extent.coerceIn(0.12, 8.0))
    }
    fun zoom(factor: Double) {
        val base = if (cameraAnimator?.isRunning == true) targetSpan else span
        animateCamera(centerX, centerY, base * factor)
    }
    fun stopCamera() {
        cameraAnimator?.cancel()
        cameraAnimator = null
    }
    private fun animateCamera(x: Double, y: Double, requestedSpan: Double) {
        stopCamera()
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
        stopCamera()
        centerX = value[0]; centerY = value[1]; span = value[2].coerceIn(0.04, 100.0)
        constrain(); invalidate()
    }
    private fun scale() = max(1, width) / span
    private fun constrain() {
        centerX = centerX.coerceIn(-180.0, 180.0); centerY = centerY.coerceIn(-140.0, 140.0)
    }

    // GestureDetector calls performClick from onSingleTapConfirmed, after ruling out a double tap.
    @android.annotation.SuppressLint("ClickableViewAccessibility")
    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (event.actionMasked == MotionEvent.ACTION_DOWN) {
            stopCamera()
            scaleBarAnimator?.cancel()
            scaleKey = scaleKey.copy(y = Double.NaN)
            touchActive = true
            boundarySettled = false
            removeCallbacks(refineBoundary)
        }
        when (event.actionMasked) {
            MotionEvent.ACTION_POINTER_DOWN -> if (event.pointerCount == 2) {
                twoFingerStart = event.eventTime; twoFingerMoved = false
            }
            MotionEvent.ACTION_POINTER_UP -> if (twoFingerStart != 0L && !twoFingerMoved &&
                event.eventTime - twoFingerStart <= TWO_FINGER_TAP_MS) {
                zoom(1.6)
                twoFingerStart = 0L
            }
        }
        pinch.onTouchEvent(event)
        gestures.onTouchEvent(event)
        if (event.actionMasked == MotionEvent.ACTION_UP || event.actionMasked == MotionEvent.ACTION_CANCEL) {
            touchActive = false
            removeCallbacks(refineBoundary)
            postDelayed(refineBoundary, 120)
            invalidate()
        }
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
        markerX = centerX + (x - width / 2.0) / scale()
        markerY = centerY - (tapY - height / 2.0) / scale()
        invalidate()
        listener?.onMapPoint(markerX, MapData.latitude(markerY))
        return true
    }

    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        layerCamera = null
        boundaryLayer = BoundaryLayer { invalidate() }
    }

    override fun onDetachedFromWindow() {
        stopCamera()
        scaleBarAnimator?.cancel()
        removeCallbacks(refineBoundary)
        boundaryLayer?.close()
        boundaryLayer = null
        super.onDetachedFromWindow()
    }
    private fun sx(x: Double) = ((x - centerX) * frame.scale + width / 2.0).toFloat()
    private fun sy(y: Double) = ((centerY - y) * frame.scale + height / 2.0).toFloat()
    private fun snap(value: Float) = value.roundToInt().toFloat()
    private fun visible(f: MapData.Feature) = f.maxX >= frame.left && f.minX <= frame.right &&
        f.maxY >= frame.bottom && f.minY <= frame.top

    private fun appendBoundary(f: MapData.Feature) {
        if (!visible(f)) return
        f.boundary?.appendVisible(boundaryBuffer, frame.scale, frame.left, frame.bottom, frame.right, frame.top)
    }

    private fun strokeBoundaries(canvas: Canvas, color: Int, stroke: Float) {
        ink.color = color; ink.style = Paint.Style.STROKE; ink.strokeWidth = stroke * density
        boundaryBuffer.draw(canvas, ink)
        boundaryBuffer.clear()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        labelCount = 0
        val loaded = data ?: return
        hasDrawnMap = true
        frame = MapCamera(centerX, centerY, span, width, height)
        if (frame != layerCamera) {
            layerCamera = frame
            boundarySettled = false
            labelsDirty = true
            removeCallbacks(refineBoundary)
            postDelayed(refineBoundary, 120)
        }
        boundaryLayer?.draw(canvas, loaded, frame, density, boundarySettled)
        boundaryBuffer.clear()
        selected?.takeUnless { it.point }?.let {
            appendBoundary(it)
            strokeBoundaries(canvas, 0xff242424.toInt(), 1.3f)
        }
        if (!markerX.isNaN()) {
            ink.color = 0xff242424.toInt(); ink.style = Paint.Style.STROKE; ink.strokeWidth = 1.5f * density
            canvas.drawCircle(sx(markerX), sy(markerY), 6 * density, ink)
        }
        val area = hereArea
        if (hereX != null && area != null) drawLabel(canvas, area, sx(area.labelLon), sy(area.labelY), true)
        selected?.let { drawLabel(canvas, it, sx(it.labelLon), sy(it.labelY), true) }
        drawStableLabels(canvas, loaded)
        drawScaleBar(canvas)
    }

    private fun updateScaleBar() {
        val zooming = scaleKey.span != span
        val moved = zooming || scaleKey.y != centerY || scaleKey.width != width
        // Freeze both text and length for a pan, but follow actual zoom gestures.
        if (scaleMeters != 0L && !((!touchActive || zooming) && moved)) return
        val size = ScaleBar.size(MapData.latitude(centerY), span, width, density, scaleMeters)
        val changedTier = size.meters != scaleMeters
        scaleBarAnimator?.cancel()
        if (scaleMeters == 0L || changedTier || zooming || touchActive ||
            !isAttachedToWindow || !ValueAnimator.areAnimatorsEnabled()) {
            scaleBarPixels = size.pixels
        } else {
            scaleBarAnimator = ValueAnimator.ofFloat(scaleBarPixels, size.pixels).apply {
                duration = 180
                interpolator = DecelerateInterpolator()
                addUpdateListener {
                    scaleBarPixels = it.animatedValue as Float
                    invalidate()
                }
                start()
            }
        }
        if (changedTier) {
            scaleMeters = size.meters
            scaleCaption = if (scaleMeters >= 1000L) {
                resources.getString(R.string.scale_km, scaleMeters / 1000)
            } else resources.getString(R.string.scale_m, scaleMeters)
        }
        scaleKey = ScaleKey(span, centerY, width)
    }

    private fun drawScaleBar(canvas: Canvas) {
        updateScaleBar()
        text.textSize = 12 * density; text.color = 0xff999999.toInt(); text.textAlign = Paint.Align.LEFT
        canvas.drawText(scaleCaption, 16 * density, height - 16 * density, text)
        text.textAlign = Paint.Align.CENTER
        ink.color = 0xff999999.toInt(); ink.style = Paint.Style.STROKE; ink.strokeWidth = density * 0.6f
        val left = 16 * density
        val top = height - 35 * density
        val right = left + scaleBarPixels
        canvas.drawLine(left, top, right, top, ink)
        canvas.drawLine(left, top - 3 * density, left, top + 3 * density, ink)
        canvas.drawLine(right, top - 3 * density, right, top + 3 * density, ink)
    }

    private fun drawLabel(canvas: Canvas, f: MapData.Feature, x: Float, y: Float, force: Boolean) {
        if (placeLabel(f, x, y, force)) paintLabel(canvas, f, x, y, force, 1f)
    }

    private fun placeLabel(f: MapData.Feature, x: Float, y: Float, force: Boolean): Boolean {
        if (labelCount >= labels.size || x < 12 * density || x > width - 12 * density || y < 25 * density || y > height - 55 * density) return false
        for (i in 0 until labelCount) if (labels[i].feature?.labelId == f.labelId) return false
        val mainSize = labelSize(f, force)
        val secondary = f.secondaryName
        val nameWidth = if (force) measureName(f, mainSize) else nameWidths.getOrPut(f) { measureName(f, mainSize) }
        val halfWidth = nameWidth / 2 + 7 * density
        candidateBounds.set(x - halfWidth, y - mainSize, x + halfWidth, y + (if (secondary != null) 23 else 8) * density)
        if (candidateBounds.top < labelTopInset + 4 * density || candidateBounds.bottom > height - 42 * density) return false
        if (candidateBounds.left < 4 * density || candidateBounds.right > width - 4 * density) return false
        for (i in 0 until labelCount) if (RectF.intersects(candidateBounds, labels[i].bounds)) return false
        labels[labelCount].apply { bounds.set(candidateBounds); feature = f }
        labelCount++
        return true
    }

    private fun measureName(f: MapData.Feature, mainSize: Float): Float {
        text.textSize = mainSize
        var width = text.measureText(f.name)
        f.secondaryName?.let {
            text.textSize = 11 * density
            width = max(width, text.measureText(it))
        }
        return width
    }

    private fun drawStableLabels(canvas: Canvas, loaded: MapData) {
        val now = SystemClock.uptimeMillis()
        val step = if (lastLabelFrame == 0L) 1f else ((now - lastLabelFrame) / 160f).coerceIn(0f, 1f)
        lastLabelFrame = now
        val layout = !labelLevelInitialized || (boundarySettled && labelsDirty)
        if (layout) {
            detailedLabels = if (!labelLevelInitialized) span < 5 else when {
                span < 4.5 -> true
                span > 5.5 -> false
                else -> detailedLabels
            }
            labelLevelInitialized = true
            labelsDirty = false
        }
        fun eligible(f: MapData.Feature) = f.rank == 1 || (detailedLabels && f.rank >= 2) || f.region !in loaded.broadLabelRegions
        var fading = false
        for (state in stableLabels) {
            val f = state.feature
            // Selected/current-place labels already occupy their single, authoritative position.
            if (f.labelId == selected?.labelId || f.labelId == hereArea?.labelId) {
                state.target = false; state.opacity = 0f
                continue
            }
            val x = snap(sx(f.labelLon))
            val y = snap(sy(f.labelY))
            state.target = eligible(f) && placeLabel(f, x, y, false)
            state.opacity = if (state.target) min(1f, state.opacity + step) else max(0f, state.opacity - step)
            if (state.opacity > 0f) paintLabel(canvas, f, x, y, false, state.opacity)
            if (state.opacity != if (state.target) 1f else 0f) fading = true
        }
        if (boundarySettled) stableLabels.removeAll { !it.target && it.opacity == 0f }
        if (layout) {
            val existing = stableLabels.mapTo(HashSet()) { it.feature.labelId }
            for (f in loaded.labelFeatures) {
                if (labelCount >= 65 || stableLabels.size >= 130) break
                if (!eligible(f) || f.labelId in existing) continue
                val x = snap(sx(f.labelLon))
                val y = snap(sy(f.labelY))
                if (placeLabel(f, x, y, false)) {
                    val state = StableLabel(f, if (step == 1f) 1f else 0f, true)
                    stableLabels.add(state)
                    existing.add(f.labelId)
                    if (state.opacity > 0f) paintLabel(canvas, f, x, y, false, state.opacity)
                    else fading = true
                }
            }
        }
        if (fading) postInvalidateOnAnimation()
    }

    private fun labelSize(f: MapData.Feature, force: Boolean) =
        (if (force) 20 else if (f.rank <= 1) 18 else 16) * density

    private fun paintLabel(canvas: Canvas, f: MapData.Feature, x: Float, y: Float, force: Boolean, opacity: Float) {
        text.textSize = labelSize(f, force)
        if (y - text.textSize < labelTopInset + 4 * density) return
        text.color = if (force) 0xff111111.toInt() else 0xff4c4c4c.toInt()
        drawName(canvas, f.name, snap(x), snap(y), opacity)
        f.secondaryName?.let { secondary ->
            text.textSize = 11 * density
            text.color = 0xff777777.toInt()
            drawName(canvas, secondary, snap(x), snap(y + 17 * density), opacity)
        }
    }

    private fun drawName(canvas: Canvas, value: String, x: Float, y: Float, opacity: Float) {
        val color = text.color
        val alpha = (255 * opacity).roundToInt()
        // setColor resets alpha, so it is reapplied after each colour change.
        text.style = Paint.Style.STROKE; text.strokeWidth = 4 * density; text.color = Color.WHITE
        text.alpha = alpha
        canvas.drawText(value, x, y, text)
        text.style = Paint.Style.FILL; text.color = color
        text.alpha = alpha
        canvas.drawText(value, x, y, text)
        text.alpha = 255
    }
}
