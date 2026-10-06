package asia.locality.map

import android.app.Activity
import android.app.Instrumentation
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.HandlerThread
import android.os.SystemClock
import android.view.Choreographer
import android.view.FrameMetrics
import android.view.Window
import android.view.View
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlin.math.sin

/** Deterministic on-device pan/zoom workload, using actual hardware-rendered frames. */
object MapRenderBenchmark {
    fun run(probe: Instrumentation, software: Boolean = false) {
        val activity = probe.startActivitySync(Intent(probe.targetContext, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) as MainActivity
        val metricsThread = HandlerThread("map-frame-metrics").apply { start() }
        try {
            val getter = MainActivity::class.java.getDeclaredMethod("getData").apply { isAccessible = true }
            var ready = false
            val deadline = SystemClock.uptimeMillis() + 60_000
            while (!ready && SystemClock.uptimeMillis() < deadline) {
                probe.runOnMainSync { ready = getter.invoke(activity) != null }
                if (!ready) SystemClock.sleep(100)
            }
            check(ready) { "Offline map did not load" }
            val viewField = MainActivity::class.java.getDeclaredField("map").apply { isAccessible = true }
            lateinit var view: InkMapView
            probe.runOnMainSync {
                MainActivity::class.java.getDeclaredMethod("stopLocation").apply { isAccessible = true }.invoke(activity)
                view = viewField.get(activity) as InkMapView
                if (software) view.setLayerType(View.LAYER_TYPE_SOFTWARE, null)
            }
            val result = JSONArray()
            val scenes = listOf(
                "china_overview" to doubleArrayOf(112.5, 33.0, 40.0),
                "hong_kong_close" to doubleArrayOf(114.17, 22.3, 0.12),
                "japan_overview" to doubleArrayOf(135.0, 36.0, 12.0),
                "kyoto_close" to doubleArrayOf(135.7681, 35.0116, 0.08),
                "seoul_close" to doubleArrayOf(126.978, 37.5665, 0.08)
            )
            for ((name, camera) in scenes) {
                val samples = mutableListOf<DoubleArray>()
                val frameTimes = mutableListOf<Long>()
                val lock = Any()
                val complete = CountDownLatch(1)
                var dropped = 0
                val listener = Window.OnFrameMetricsAvailableListener { _, metrics, skipped ->
                    synchronized(lock) {
                        samples.add(doubleArrayOf(
                            metrics.getMetric(FrameMetrics.TOTAL_DURATION) / 1e6,
                            metrics.getMetric(FrameMetrics.DRAW_DURATION) / 1e6,
                            metrics.getMetric(FrameMetrics.COMMAND_ISSUE_DURATION) / 1e6
                        ))
                        dropped += skipped
                    }
                }
                probe.runOnMainSync {
                    view.restoreViewport(doubleArrayOf(camera[0], MapData.mercator(camera[1]), camera[2]))
                }
                // Settle the new region/layer before measuring continuous camera motion.
                SystemClock.sleep(500)
                probe.runOnMainSync {
                    activity.window.addOnFrameMetricsAvailableListener(listener, Handler(metricsThread.looper))
                    var frame = 0
                    val callback = object : Choreographer.FrameCallback {
                        override fun doFrame(frameTimeNanos: Long) {
                            frameTimes.add(frameTimeNanos)
                            val phase = frame / 20.0
                            view.restoreViewport(doubleArrayOf(camera[0] + sin(phase) * camera[2] * 0.08,
                                MapData.mercator(camera[1]) + sin(phase * 0.7) * camera[2] * 0.04,
                                camera[2] * (1 + sin(phase * 0.5) * 0.15)))
                            if (++frame < 140) Choreographer.getInstance().postFrameCallback(this)
                            else complete.countDown()
                        }
                    }
                    Choreographer.getInstance().postFrameCallback(callback)
                }
                check(complete.await(90, TimeUnit.SECONDS)) { "Rendering timed out: $name" }
                SystemClock.sleep(100)
                probe.runOnMainSync { activity.window.removeOnFrameMetricsAvailableListener(listener) }
                val frames = synchronized(lock) { samples.drop(20) }
                check(frames.size >= 60) { "Too few rendered frames: $name (${frames.size})" }
                fun percentile(column: Int, fraction: Double): Double =
                    frames.map { it[column] }.sorted()[((frames.size - 1) * fraction).toInt()]
                val intervals = frameTimes.drop(20).zipWithNext { a, b -> (b - a) / 1e6 }.sorted()
                val row = JSONObject().put("scene", name).put("frames", frames.size)
                    .put("total_p50_ms", percentile(0, 0.5)).put("total_p95_ms", percentile(0, 0.95))
                    .put("draw_p95_ms", percentile(1, 0.95)).put("issue_p95_ms", percentile(2, 0.95))
                    .put("interval_p50_ms", intervals[intervals.size / 2])
                    .put("interval_p95_ms", intervals[((intervals.size - 1) * 0.95).toInt()])
                    .put("over_32ms", frames.count { it[0] > 32.0 }).put("dropped_metric_reports", dropped)
                    .put("width", view.width).put("height", view.height)
                result.put(row)
                probe.sendStatus(0, Bundle().apply { putString("stream", row.toString() + "\n") })
            }
            probe.finish(Activity.RESULT_OK, Bundle().apply { putString("stream", result.toString() + "\n") })
        } finally {
            probe.runOnMainSync { activity.finish() }
            metricsThread.quitSafely()
        }
    }
}
