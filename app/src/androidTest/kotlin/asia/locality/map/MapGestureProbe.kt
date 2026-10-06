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
import android.view.accessibility.AccessibilityNodeInfo

/** On-device geometry checks, plus a shell entry point for real two-pointer input. */
class MapGestureProbe : Instrumentation() {
    private var benchmark = false
    private var software = false
    private var geometryBenchmark = false
    override fun onCreate(arguments: Bundle?) {
        super.onCreate(arguments)
        benchmark = arguments?.getString("benchmark") == "true"
        software = arguments?.getString("software") == "true"
        geometryBenchmark = arguments?.getString("geometryBenchmark") == "true"
        start()
    }

    override fun onStart() {
        try {
            if (geometryBenchmark) { MapGeometryBenchmark.run(this); return }
            if (benchmark) { MapRenderBenchmark.run(this, software); return }
            BoundaryRenderingProbe.verify()
            val activity = startActivitySync(Intent(targetContext, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) as MainActivity
            try {
                awaitData(activity)
                changeYear(activity, Timeline.DEFAULT_YEAR)
                val data = awaitData(activity, Timeline.DEFAULT_YEAR)
                val catalogue = Timeline.load(targetContext)
                check(catalogue.periods.none { it.id == "qing" })
                check(catalogue.forRegion("cn").map { it.id } == listOf("han", "tang", "song", "ming"))
                check(data.countyAt(112.5283, 32.9908) == null)
                check(data.localAreaAt(112.5283, 32.9908)?.name == "南阳府")
                check(catalogue.regionForViewport(138.0, 32.0, 10.0, 0.75, "cn") == "jp")
                check(data.features.none { it.name == "清" })
                check(data.features.all { it.layer == "administrative" && it.rank >= 1 })
                check(data.countyAt(135.7681, 35.0116)?.name == "葛野郡")
                check(data.features.count { it.region == "jp" } == 783)
                check(data.features.count { it.region == "kr" && it.rank == 2 && !it.point && it.boundary != null } == 334)
                check(data.countyAt(126.978, 37.5665)?.name == "漢城")
                check(data.features.any { it.name == "漢城" && it.nativeName == "한성" })
                check(data.features.any { it.name == "漢城" && it.searchText.contains("汉城") })
                check(data.referenceYears["cn"] == 1585 && data.referenceYears["kr"] == 1864)
                check(data.referenceYears["vn"] == null && data.referenceYears["jp"] == 1864)
                check(data.at(121.5654, 25.033).isEmpty())
                check(data.nearestCountySeat(112.5283, 32.9908, 50.0)?.name == "南阳县")
                check(data.features.filter { it.point }.none { it.contains(it.lon, it.y) })
                check(data.countyAt(124.39, 40.13) == null)
                check(data.localAreaAt(124.39, 40.13)?.name == "辽东都司")
                check(data.localAreaAt(115.06, 40.61)?.name == "万全都司")
                check(data.countyAt(115.06, 40.61) == null)
                check(data.features.single { it.name == "大宁都司" }.let { it.point && it.parent == "保定府" })
                for (lat in listOf(-70.0, 0.0, 22.3, 33.0, 65.0)) {
                    check(kotlin.math.abs(MapData.latitude(MapData.mercator(lat)) - lat) < 1e-9)
                }
                verifyLateSnapshot(data)
                val duplicates = data.features.filter { it.name == "山阴县" }
                check(duplicates.size >= 2)
                check(duplicates.map { data.contextNames(it) to (it.lon to it.lat) }.distinct().size == duplicates.size)
                lateinit var viewport: DoubleArray
                runOnMainSync {
                    field("current").set(activity, Location("regression").apply { longitude = 112.5; latitude = 33.0 })
                    field("locating").setBoolean(activity, true)
                    (field("locationTimeout").get(activity) as Runnable).run()
                    check(state(activity, "locationStatusId") == R.string.location_timeout)
                    check(!field("locating").getBoolean(activity))
                    field("locating").setBoolean(activity, true)
                    callActivityOnStop(activity)
                    check(state(activity, "locationStatusId") == R.string.location_interrupted)
                    val choose = MainActivity::class.java.getDeclaredMethod("searchResult", MapData.Feature::class.java)
                        .apply { isAccessible = true }
                    choose.invoke(activity, data.features.first { it.point && it.system == "军事" })
                    check(state(activity, "statusId") == null)
                    choose.invoke(activity, duplicates.first())
                    check(state(activity, "statusId") == null)
                    val view = field("map").get(activity) as InkMapView
                    view.restoreViewport(doubleArrayOf(113.0, MapData.mercator(23.0), 2.0))
                    viewport = view.viewport()
                    field("locating").setBoolean(activity, true)
                }
                changeYear(activity, 2)
                val early = awaitData(activity, 2)
                runOnMainSync {
                    val view = field("map").get(activity) as InkMapView
                    check(view.viewport().contentEquals(viewport))
                    check(!field("locating").getBoolean(activity))
                    check(state(activity, "locationStatusId") == null)
                    check(early.features.none { it.id.startsWith("ming-military:") })
                    check(early.localAreaAt(112.5283, 32.9908)?.name == "南阳郡")
                    check(early.features.none { it.region == "kr" || it.region == "jp" })
                    check(early.countyAt(135.7681, 35.0116) == null)
                    check(early.countyAt(126.978, 37.5665) == null)
                    check(early.localAreaAt(125.754, 39.033)?.name == "乐浪郡")
                    val selected = field("selectedId").get(activity)
                    check(selected == null || early.features.any { it.id == selected })
                    val saved = Bundle()
                    callActivityOnSaveInstanceState(activity, saved)
                    check(saved.getInt("year") == 2)
                    // A second configuration change before map binding must retain the
                    // pending restored camera, not save the placeholder view's camera.
                    val pending = doubleArrayOf(135.7681, MapData.mercator(35.0116), 1.2)
                    field("restoredViewport").set(activity, pending)
                    val duringLoad = Bundle()
                    callActivityOnSaveInstanceState(activity, duringLoad)
                    check(duringLoad.getDoubleArray("viewport")!!.contentEquals(pending))
                    field("restoredViewport").set(activity, null)
                }
                changeYear(activity, Timeline.DEFAULT_YEAR)
                val restored = awaitData(activity, Timeline.DEFAULT_YEAR)
                for (region in listOf("kr", "jp")) {
                    val original = data.features.first { it.region == region }
                    check(restored.features.first { it.id == original.id } === original)
                }
                verifyLabels(activity)
                verifyRegionalMenus(activity, catalogue)
                verifySearchPeriods(activity)
                clickText(targetContext.getString(R.string.close))
                verifyChineseBoundaries(activity, catalogue)
                verifyReferenceWindows(activity)
                verifyMingDusi(activity)
                captureSimplifiedCoasts(activity)
            } finally {
                runOnMainSync { activity.finish() }
            }
            finish(Activity.RESULT_OK, Bundle().apply { putString("stream", "Geometry, stable labels, regional menus, Chinese names, dynasty scope and search checks passed\n") })
        } catch (error: Throwable) {
            finish(Activity.RESULT_CANCELED, Bundle().apply { putString("stream", error.stackTraceToString()) })
        }
    }

    private fun field(name: String) = MainActivity::class.java.getDeclaredField(name).apply { isAccessible = true }

    private fun captureSimplifiedCoasts(activity: MainActivity) {
        for ((name, camera) in listOf(
            "korea-coast" to doubleArrayOf(126.3, 35.5, 4.0),
            "japan-coast" to doubleArrayOf(133.5, 34.2, 4.0),
            "tsushima" to doubleArrayOf(129.3, 34.3, 1.4)
        )) {
            runOnMainSync {
                (field("map").get(activity) as InkMapView).restoreViewport(
                    doubleArrayOf(camera[0], MapData.mercator(camera[1]), camera[2]))
            }
            SystemClock.sleep(1500)
            val bitmap = requireNotNull(uiAutomation.takeScreenshot())
            java.io.File(targetContext.filesDir, "simplified-$name.png").outputStream().use {
                check(bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it))
            }
            bitmap.recycle()
        }
    }
    private fun state(activity: MainActivity, name: String): Any? =
        (field(name + "$" + "delegate").get(activity) as androidx.compose.runtime.State<*>).value

    private fun awaitData(activity: MainActivity, expected: Int? = null): MapData {
        val deadline = SystemClock.uptimeMillis() + 60_000
        while (SystemClock.uptimeMillis() < deadline) {
            var value: MapData? = null
            runOnMainSync { value = state(activity, "data") as MapData? }
            if (value != null && (expected == null || value?.year == expected)) return requireNotNull(value)
            SystemClock.sleep(100)
        }
        error("Historical snapshot did not load: $expected")
    }

    private fun changeYear(activity: MainActivity, year: Int) {
        val change = MainActivity::class.java.getDeclaredMethod("changeYear", Int::class.javaPrimitiveType)
            .apply { isAccessible = true }
        runOnMainSync { change.invoke(activity, year) }
    }

    private fun verifyLateSnapshot(data: MapData) {
        val late = MapData.load(targetContext, 1864, data.land, data.features)
        check(late.features.none { it.region == "cn" })
        check(late.countyAt(135.7681, 35.0116)?.name == "葛野郡")
        check(late.countyAt(126.978, 37.5665)?.name == "漢城")
    }

    private fun clickText(text: String) {
        var node = awaitNode { it.text?.toString() == text }
        while (!node.isClickable) node = requireNotNull(node.parent)
        check(node.performAction(AccessibilityNodeInfo.ACTION_CLICK))
    }

    private fun verifyRegionalMenus(activity: MainActivity, catalogue: Timeline) {
        val expectedYear = awaitData(activity).year
        for ((region, coordinates) in listOf("cn" to (112.5 to 33.0), "kr" to (126.978 to 37.5665),
            "jp" to (135.7681 to 35.0116), "vn" to (105.8342 to 21.0278))) {
            runOnMainSync {
                (field("map").get(activity) as InkMapView).restoreViewport(doubleArrayOf(coordinates.first,
                    MapData.mercator(coordinates.second), 1.2))
            }
            SystemClock.sleep(500)
            var actual: Any? = null
            runOnMainSync { actual = state(activity, "viewRegion") }
            check(actual == region) { "Region menu did not follow viewport: $region / $actual" }
            val data = awaitData(activity)
            check(data.year == expectedYear) { "Panning changed the historical period" }
            if (region == "vn") {
                check(catalogue.forRegion(region).isEmpty())
                check(data.features.none { it.region == "vn" })
                continue
            }
            if (region == "kr") {
                val option = catalogue.forRegion(region).single()
                val label = targetContext.getString(R.string.period_label, option.title(targetContext),
                    targetContext.getString(R.string.year_ce, option.year))
                check(!awaitNode { it.text?.toString() == label }.isClickable)
                continue
            }
            if (region == "jp") {
                val label = awaitNode { it.text?.toString() == targetContext.getString(R.string.japan_early_modern) }
                check(!label.isClickable)
                check(catalogue.forRegion(region).size == 1)
                continue
            }
            val localYear = requireNotNull(data.referenceYears[region])
            val active = requireNotNull(catalogue.atYear(region, expectedYear))
            val date = targetContext.getString(if (localYear < 0) R.string.year_bce else R.string.year_ce, kotlin.math.abs(localYear))
            clickText(targetContext.getString(R.string.period_label, active.title(targetContext), date))
            val first = catalogue.forRegion(region).first()
            val firstDate = targetContext.getString(if (first.year < 0) R.string.year_bce else R.string.year_ce, kotlin.math.abs(first.year))
            awaitNode { it.text?.toString() == targetContext.getString(R.string.period_label, first.title(targetContext), firstDate) }
            if (region != "cn") check(findNode { it.text?.toString()?.contains("汉 ·") == true } == null)
            check(findNode { it.text?.toString() == "清" } == null)
            clickText(targetContext.getString(R.string.close))
        }
    }

    private fun verifyLabels(activity: MainActivity) {
        lateinit var view: InkMapView
        runOnMainSync {
            view = MainActivity::class.java.getDeclaredField("map").apply { isAccessible = true }.get(activity) as InkMapView
        }
        fun value(name: String): Any? {
            var result: Any? = null
            runOnMainSync { result = InkMapView::class.java.getDeclaredField(name).apply { isAccessible = true }.get(view) }
            return result
        }
        fun camera(span: Double) {
            runOnMainSync { view.restoreViewport(doubleArrayOf(112.5, MapData.mercator(33.0), span)) }
        }
        for ((span, detail) in listOf(4.4 to true, 5.1 to true, 4.9 to true, 5.6 to false,
            4.9 to false, 5.1 to false, 4.4 to true)) {
            camera(span)
            SystemClock.sleep(400)
            check(value("detailedLabels") == detail) { "Label level oscillated near the zoom threshold" }
        }
        fun ids(): List<String> {
            var result = emptyList<String>()
            runOnMainSync {
                val states = InkMapView::class.java.getDeclaredField("stableLabels").apply { isAccessible = true }.get(view) as List<*>
                result = states.map { entry ->
                    requireNotNull(entry)
                    (entry.javaClass.getDeclaredField("feature").apply { isAccessible = true }.get(entry) as MapData.Feature).id
                }
            }
            return result
        }
        val downTime = SystemClock.uptimeMillis()
        fun touch(action: Int) = runOnMainSync {
            MotionEvent.obtain(downTime, SystemClock.uptimeMillis(), action, 20f, 200f, 0).let {
                view.onTouchEvent(it)
                it.recycle()
            }
        }
        touch(MotionEvent.ACTION_DOWN)
        try {
            val before = ids()
            check(before.isNotEmpty())
            repeat(20) { frame -> camera(4.4 + kotlin.math.sin(frame / 3.0) * 0.1); SystemClock.sleep(16) }
            // A slow frame or a held finger must not be mistaken for gesture end.
            SystemClock.sleep(250)
            check(ids() == before) { "Labels were replaced during an active zoom gesture" }
        } finally { touch(MotionEvent.ACTION_CANCEL) }
    }

    private fun findNode(predicate: (AccessibilityNodeInfo) -> Boolean): AccessibilityNodeInfo? {
        fun visit(node: AccessibilityNodeInfo): AccessibilityNodeInfo? {
            if (predicate(node)) return node
            for (index in 0 until node.childCount) {
                node.getChild(index)?.let { child -> visit(child)?.let { return it } }
            }
            return null
        }
        return uiAutomation.rootInActiveWindow?.let(::visit)
    }

    private fun awaitNode(predicate: (AccessibilityNodeInfo) -> Boolean): AccessibilityNodeInfo {
        val deadline = SystemClock.uptimeMillis() + 10_000
        while (SystemClock.uptimeMillis() < deadline) {
            findNode(predicate)?.let { return it }
            SystemClock.sleep(100)
        }
        error("Expected UI node did not appear")
    }

    private fun verifyChineseBoundaries(activity: MainActivity, catalogue: Timeline) {
        val show = MainActivity::class.java.getDeclaredMethod("showAt", Double::class.javaPrimitiveType,
            Double::class.javaPrimitiveType, Boolean::class.javaPrimitiveType).apply { isAccessible = true }
        runOnMainSync {
            field("current").set(activity, Location("reference-test").apply { longitude = 112.5283; latitude = 32.9908 })
            (field("map").get(activity) as InkMapView).setHere(112.5283, 32.9908)
            show.invoke(activity, 112.5283, 32.9908, true)
        }
        SystemClock.sleep(700)
        for (period in catalogue.forRegion("cn")) {
            val before = awaitData(activity)
            val active = requireNotNull(catalogue.atYear("cn", before.year))
            clickText(targetContext.getString(R.string.period_label, active.title(targetContext),
                targetContext.getString(R.string.year_ce, before.year)))
            clickText(targetContext.getString(R.string.period_label, period.title(targetContext),
                targetContext.getString(R.string.year_ce, period.year)))
            val loaded = awaitData(activity, period.year)
            val expected = when(period.id) { "han" -> "南阳郡"; "ming" -> "南阳府"; else -> "邓州" }
            val area = requireNotNull(loaded.localAreaAt(112.5283, 32.9908))
            check(area.name == expected && !area.point && area.rank == 1 && area.boundary != null)
            check(loaded.countyAt(112.5283, 32.9908) == null)
            runOnMainSync { show.invoke(activity, 112.5283, 32.9908, true) }
            SystemClock.sleep(800)
            val bitmap = requireNotNull(uiAutomation.takeScreenshot())
            java.io.File(targetContext.filesDir, "china-four-${period.year}.png").outputStream().use {
                check(bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it))
            }
            bitmap.recycle()
        }
    }

    private fun verifyReferenceWindows(activity: MainActivity) {
        val show = MainActivity::class.java.getDeclaredMethod("showAt", Double::class.javaPrimitiveType,
            Double::class.javaPrimitiveType, Boolean::class.javaPrimitiveType).apply { isAccessible = true }
        for (year in listOf(2, 742, 1102, 1585)) {
            changeYear(activity, year)
            val loaded = awaitData(activity, year)
            runOnMainSync {
                field("current").set(activity, Location("reference-window-test").apply {
                    longitude = 125.754; latitude = 39.033
                })
                (field("map").get(activity) as InkMapView).setHere(125.754, 39.033)
                show.invoke(activity, 125.754, 39.033, true)
            }
            SystemClock.sleep(800)
            if (year != 1585) {
                check(loaded.features.none { it.region == "kr" })
                if (year == 2) check(loaded.features.none { it.region == "jp" })
                else check(loaded.features.count { it.region == "jp" && it.rank == 1 } == 68)
                check(findNode { it.text?.toString()?.contains("朝鮮後期") == true } == null)
                check(findNode { it.text?.toString() == targetContext.getString(R.string.japan_early_modern) } == null)
            } else {
                check(loaded.countyAt(125.754, 39.033)?.name == "平壤")
                check(loaded.features.count { it.region == "kr" } == 343)
                check(loaded.features.count { it.region == "jp" } == 783)
            }
            if (year == 2) check(loaded.localAreaAt(125.754, 39.033)?.name == "乐浪郡")
            if (year == 2 || year == 1585) {
                val bitmap = requireNotNull(uiAutomation.takeScreenshot())
                java.io.File(targetContext.filesDir, "reference-window-$year.png").outputStream().use {
                    check(bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it))
                }
                bitmap.recycle()
            }
        }
    }

    private fun verifyMingDusi(activity: MainActivity) {
        changeYear(activity, Timeline.DEFAULT_YEAR)
        val loaded=awaitData(activity, Timeline.DEFAULT_YEAR)
        val show = MainActivity::class.java.getDeclaredMethod("showAt", Double::class.javaPrimitiveType,
            Double::class.javaPrimitiveType, Boolean::class.javaPrimitiveType).apply { isAccessible = true }
        for ((name,coordinate) in listOf("辽东都司" to (123.17 to 41.27), "万全都司" to (115.06 to 40.61))) {
            runOnMainSync {
                field("current").set(activity, Location("dusi-test").apply {
                    longitude=coordinate.first; latitude=coordinate.second
                })
                val view=field("map").get(activity) as InkMapView
                view.setHere(coordinate.first, coordinate.second)
                show.invoke(activity,coordinate.first,coordinate.second,true)
                check(field("selectedId").get(activity)==loaded.localAreaAt(coordinate.first,coordinate.second)?.id)
            }
            SystemClock.sleep(800)
            val bitmap=requireNotNull(uiAutomation.takeScreenshot())
            java.io.File(targetContext.filesDir,"ming-$name.png").outputStream().use {
                check(bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG,100,it))
            }
            bitmap.recycle()
        }
        runOnMainSync {
            val view=field("map").get(activity) as InkMapView
            view.select(null);view.nameHere(null)
            view.restoreViewport(doubleArrayOf(123.0,MapData.mercator(40.0),12.0))
        }
        SystemClock.sleep(800)
        val bitmap=requireNotNull(uiAutomation.takeScreenshot())
        java.io.File(targetContext.filesDir,"ming-liaodong-korea.png").outputStream().use {
            check(bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG,100,it))
        }
        bitmap.recycle()
        runOnMainSync {
            (field("map").get(activity) as InkMapView).restoreViewport(doubleArrayOf(123.8,MapData.mercator(40.9),3.5))
        }
        SystemClock.sleep(800)
        val detail=requireNotNull(uiAutomation.takeScreenshot())
        java.io.File(targetContext.filesDir,"ming-liaodong-detail.png").outputStream().use {
            check(detail.compress(android.graphics.Bitmap.CompressFormat.PNG,100,it))
        }
        detail.recycle()
        clickText(targetContext.getString(R.string.search))
        val input=awaitNode { it.isEditable && it.packageName==targetContext.packageName }
        check(input.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,"大宁都司")
        }))
        var result = awaitNode { !it.isEditable && it.text?.toString()?.startsWith("大宁都司") == true }
        while (!result.isClickable) result = requireNotNull(result.parent)
        check(result.performAction(AccessibilityNodeInfo.ACTION_CLICK))
        SystemClock.sleep(300)
        check(field("selectedId").get(activity) == loaded.features.single { it.name == "大宁都司" }.id)
        SystemClock.sleep(700)
        val daning=requireNotNull(uiAutomation.takeScreenshot())
        java.io.File(targetContext.filesDir,"ming-daning.png").outputStream().use {
            check(daning.compress(android.graphics.Bitmap.CompressFormat.PNG,100,it))
        }
        daning.recycle()
    }

    private fun verifySearchPeriods(activity: MainActivity) {
        changeYear(activity, Timeline.DEFAULT_YEAR)
        awaitData(activity, Timeline.DEFAULT_YEAR)
        clickText(targetContext.getString(R.string.search))
        val input = awaitNode { it.isEditable && it.packageName == targetContext.packageName }
        check(input.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, "汉城")
        }))
        awaitNode { it.text?.toString() == "漢城" && !it.isEditable }
        changeYear(activity, 2)
        awaitData(activity, 2)
        // Fixed references must disappear from search as well as the map.
        awaitNode { it.text?.toString() == targetContext.getString(R.string.no_results) }
        check(awaitData(activity, 2).features.none { it.region == "kr" || it.region == "jp" })
        changeYear(activity, Timeline.DEFAULT_YEAR)
        awaitData(activity, Timeline.DEFAULT_YEAR)
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

private fun MapData.countyAt(lon: Double, lat: Double): MapData.Feature? =
    at(lon, lat).firstOrNull { it.rank >= 2 && it.system == "民政" }

private fun MapData.nearestCountySeat(lon: Double, lat: Double, maxKm: Double): MapData.Feature? =
    features.filter { it.id.startsWith("chgis-county:") && it.system == "民政" }
        .minByOrNull { MapData.distance(lon, lat, it.lon, it.lat) }
        ?.takeIf { MapData.distance(lon, lat, it.lon, it.lat) < maxKm }
