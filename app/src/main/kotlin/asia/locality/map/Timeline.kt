package asia.locality.map

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.abs

class HistoryPeriod internal constructor(
    val id: String, val region: String, val year: Int,
    private val start: Int, private val end: Int, private val titles: Map<String, String>
) {
    constructor(row: JSONObject) : this(row.getString("id"), row.getString("region"), row.getInt("year"),
        row.getInt("start"), row.getInt("end"), row.getJSONObject("titles").let { names ->
            names.keys().asSequence().associateWith { names.getString(it) }
        })
    fun contains(value: Int): Boolean = value in start..end
    fun title(context: Context): String = titles[context.resources.configuration.locales[0].language] ?: titles.getValue("zh")
}

/** Geographic menu lenses, kept separate from historical ownership and area queries. */
class Timeline internal constructor(val periods: List<HistoryPeriod>, private val regions: List<MapData.Feature> = emptyList()) {
    val years: Set<Int> = periods.map { it.year }.toSet()
    fun forRegion(region: String): List<HistoryPeriod> = periods.filter { it.region == region }
    fun atYear(region: String, year: Int): HistoryPeriod? = forRegion(region).firstOrNull { it.contains(year) }
    /** Select a shared snapshot inside this period, independently of its source date. */
    fun contextYearFor(period: HistoryPeriod, currentYear: Int): Int {
        val candidates = years.filter { period.contains(it) }
        val shared = candidates.filter { atYear("cn", it) != null && atYear("kr", it) != null }
        val eligible = shared.ifEmpty { candidates }
        if (currentYear in eligible) return currentYear
        if (period.year in eligible) return period.year
        return eligible.minBy { abs(it - period.year) }
    }

    fun restoreYear(value: Int): Int {
        val period = atYear("cn", value) ?: atYear("kr", value) ?: return DEFAULT_YEAR
        return contextYearFor(period, value)
    }
    fun regionForViewport(lon: Double, lat: Double, span: Double, aspect: Double, previous: String): String {
        val y = MapData.mercator(lat)
        regions.firstOrNull { it.contains(lon, y) }?.let { return it.region }
        // A sea-centered view of Japan/Korea should not keep the old mainland menu.
        val scores = mutableMapOf<String, Double>()
        for (dx in listOf(-0.45, -0.225, 0.0, 0.225, 0.45)) {
            for (dy in listOf(-0.45, -0.225, 0.0, 0.225, 0.45)) {
                val region = regions.firstOrNull { it.contains(lon + dx * span, y + dy * span * aspect) }?.region ?: continue
                scores[region] = (scores[region] ?: 0.0) + 1.0 / (0.1 + dx * dx + dy * dy)
            }
        }
        val best = scores.maxByOrNull { it.value } ?: return previous
        return if (scores[previous] == best.value) previous else best.key
    }

    companion object {
        const val DEFAULT_YEAR = 1585
        fun load(context: Context): Timeline {
            val catalogue = JSONArray(context.assetText("timeline.json"))
            val outlines = JSONArray(context.assetText("regions.json"))
            return Timeline((0 until catalogue.length()).map { HistoryPeriod(catalogue.getJSONObject(it)) },
                (0 until outlines.length()).map { MapData.Feature(outlines.getJSONObject(it)) })
        }
    }
}
