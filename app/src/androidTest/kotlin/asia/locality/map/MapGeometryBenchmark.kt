package asia.locality.map

import android.app.Activity
import android.app.Instrumentation
import android.os.Bundle
import android.os.SystemClock
import org.json.JSONArray
import org.json.JSONObject

/** Geometry costs measured independently of emulator GPU / window-compositor load. */
object MapGeometryBenchmark {
    fun run(probe: Instrumentation) {
        val start = SystemClock.elapsedRealtimeNanos()
        val data = MapData.load(probe.targetContext)
        val loadMs = (SystemClock.elapsedRealtimeNanos() - start) / 1e6
        val scenes = listOf(
            "china_overview" to doubleArrayOf(112.5, 33.0, 40.0),
            "liaodong" to doubleArrayOf(123.0, 41.0, 6.0),
            "korea_coast" to doubleArrayOf(126.3, 35.5, 4.0),
            "japan_coast" to doubleArrayOf(133.5, 34.2, 4.0),
            "kyoto_close" to doubleArrayOf(135.7681, 35.0116, .08)
        )
        val rows = JSONArray()
        val buffer = BoundaryLines.Buffer()
        for ((name, camera) in scenes) {
            val durations = mutableListOf<Double>()
            var segments = 0
            repeat(30) { iteration ->
                val scale = 1600 / camera[2]
                val left = camera[0] - camera[2] / 2
                val top = MapData.mercator(camera[1]) + 500 / scale
                buffer.clear()
                val began = SystemClock.elapsedRealtimeNanos()
                for (feature in data.features) if (!feature.point && (camera[2] <= 8 || feature.rank == 1)) {
                    feature.boundary?.appendVisible(buffer, scale, left, top - 1000 / scale,
                        left + camera[2], top)
                }
                if (iteration >= 5) durations.add((SystemClock.elapsedRealtimeNanos() - began) / 1e6)
                segments = buffer.size / 4
            }
            durations.sort()
            rows.put(JSONObject().put("scene", name).put("segments", segments)
                .put("p50_ms", durations[durations.size / 2]).put("p95_ms", durations[23]))
        }
        val result = JSONObject().put("load_ms", loadMs).put("scenes", rows)
        probe.finish(Activity.RESULT_OK, Bundle().apply { putString("stream", result.toString() + "\n") })
    }
}
