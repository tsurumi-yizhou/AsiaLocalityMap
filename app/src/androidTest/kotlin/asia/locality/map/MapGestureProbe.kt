package asia.locality.map

import android.app.Activity
import android.app.Instrumentation
import android.content.Intent
import android.location.Location
import android.os.Bundle
import android.os.SystemClock
import android.view.InputDevice
import android.view.InputEvent
import android.view.MotionEvent

/** On-device geometry checks, plus a shell entry point for real two-pointer input. */
class MapGestureProbe : Instrumentation() {
    override fun onCreate(arguments: Bundle?) { super.onCreate(arguments); start() }

    override fun onStart() {
        try {
            val data = MapData.load(targetContext)
            check(data.features.size == 3422)
            check(data.at(135.7681, 35.0116).any { it.name == "葛野郡" && it.rank == 2 })
            check(data.at(126.978, 37.5665).any { it.rank == 2 && it.region == "kr" })
            check(data.at(121.5654, 25.033).isEmpty())
            check(data.nearestCountySeat(112.5283, 32.9908, 50.0)?.name == "南阳县")
            check(data.features.filter { it.point }.none { it.contains(it.lon, it.y) })
            for (lat in listOf(-70.0, 0.0, 22.3, 33.0, 65.0)) {
                check(kotlin.math.abs(MapData.latitude(MapData.mercator(lat)) - lat) < 1e-9)
            }
            val duplicates = data.features.filter { it.name == "山阴县" }
            check(duplicates.size >= 2)
            check(duplicates.map { data.contextNames(it) to (it.lon to it.lat) }.distinct().size == duplicates.size)
            val activity = startActivitySync(Intent(targetContext, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) as MainActivity
            try {
                runOnMainSync {
                    fun field(name: String) = MainActivity::class.java.getDeclaredField(name).apply { isAccessible = true }
                    fun state(name: String): Any? =
                        (field(name + "$" + "delegate").get(activity) as androidx.compose.runtime.State<*>).value
                    // A second request times out with an existing position: it must stop showing progress.
                    field("current").set(activity, Location("regression").apply { longitude = 112.5; latitude = 33.0 })
                    field("locating").setBoolean(activity, true)
                    (field("locationTimeout").get(activity) as Runnable).run()
                    check(state("locationStatusId") == R.string.location_timeout)
                    check(!field("locating").getBoolean(activity))
                    // Backgrounding a pending request also has to leave the progress state.
                    field("locating").setBoolean(activity, true)
                    callActivityOnStop(activity)
                    check(state("locationStatusId") == R.string.location_interrupted)
                    check(!field("locating").getBoolean(activity))
                    val choose = MainActivity::class.java.getDeclaredMethod("searchResult", MapData.Feature::class.java)
                        .apply { isAccessible = true }
                    choose.invoke(activity, data.features.first { it.point && it.system == "军事" })
                    check(state("statusId") == R.string.military_site_unknown_boundary)
                    check(state("locationStatusId") == null)
                    choose.invoke(activity, duplicates.first())
                    check(state("statusId") == R.string.seat_unknown_boundary)
                }
            } finally {
                runOnMainSync { activity.finish() }
            }
            finish(Activity.RESULT_OK, Bundle().apply { putString("stream", "Data and location/selection regression checks passed\n") })
        } catch (error: Throwable) {
            finish(Activity.RESULT_CANCELED, Bundle().apply { putString("stream", error.stackTraceToString()) })
        }
    }

    companion object {
        /** Runs only as adb shell on the emulator, outside the application process. */
        @JvmStatic
        fun main(args: Array<String>) {
            val manager = Class.forName("android.hardware.input.InputManagerGlobal")
            val instance = manager.getMethod("getInstance").invoke(null)
            val inject = manager.getMethod("injectInputEvent", InputEvent::class.java, Int::class.javaPrimitiveType)
            var down = SystemClock.uptimeMillis()
            val properties = Array(2) { i -> MotionEvent.PointerProperties().apply {
                id = i; toolType = MotionEvent.TOOL_TYPE_FINGER
            } }
            val coords = Array(2) { MotionEvent.PointerCoords().apply { pressure = 1f; size = 1f } }
            val x = args[0].toFloat(); val y = args[1].toFloat()
            val start = args.getOrNull(2)?.toFloat() ?: 0f
            val end = args.getOrNull(3)?.toFloat() ?: 0f
            coords[0].x = x - start; coords[1].x = x + start
            coords[0].y = y; coords[1].y = y
            fun send(action: Int, count: Int) {
                val event = MotionEvent.obtain(down, SystemClock.uptimeMillis(), action, count,
                    properties, coords, 0, 0, 1f, 1f, 0, 0, InputDevice.SOURCE_TOUCHSCREEN, 0)
                try { check(inject.invoke(instance, event, 2) == true) { "Input injection failed" } }
                finally { event.recycle() }
            }
            if (args.size == 2) {
                repeat(2) {
                    down = SystemClock.uptimeMillis()
                    send(MotionEvent.ACTION_DOWN, 1)
                    SystemClock.sleep(40)
                    send(MotionEvent.ACTION_UP, 1)
                    SystemClock.sleep(60)
                }
                return
            }
            send(MotionEvent.ACTION_DOWN, 1)
            send(MotionEvent.ACTION_POINTER_DOWN or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT), 2)
            for (step in 0..30) {
                val radius = start + (end - start) * step / 30
                coords[0].x = x - radius; coords[1].x = x + radius
                send(MotionEvent.ACTION_MOVE, 2)
                SystemClock.sleep(20)
            }
            send(MotionEvent.ACTION_POINTER_UP or (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT), 2)
            send(MotionEvent.ACTION_UP, 1)
        }
    }
}
