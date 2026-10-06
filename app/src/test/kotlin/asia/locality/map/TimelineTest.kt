package asia.locality.map

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class TimelineTest {
    private fun period(id: String, region: String, year: Int, start: Int, end: Int) =
        HistoryPeriod(id, region, year, start, end, mapOf("zh" to id))

    private val timeline = Timeline(listOf(
        period("han", "cn", 2, -202, 220),
        period("tang", "cn", 742, 618, 906),
        period("song", "cn", 1102, 960, 1278),
        period("ming", "cn", 1585, 1368, 1644),
        period("silla", "kr", 757, 668, 935),
        period("goryeo", "kr", 1370, 936, 1391),
        period("joseon_late", "kr", 1864, 1392, 1897),
        period("jp_early_modern", "jp", 1864, 1333, 1867)
    ))

    @Test fun regionalMenusContainEachPeriodOnce() {
        assertEquals(listOf("han", "tang", "song", "ming"), timeline.forRegion("cn").map { it.id })
        assertEquals(listOf("silla", "goryeo", "joseon_late"), timeline.forRegion("kr").map { it.id })
    }

    @Test fun selectingEitherRegionResolvesAllCountriesFromOneYear() {
        for (region in listOf("cn", "kr")) {
            for (period in timeline.forRegion(region)) {
                assertTrue(period.year in timeline.years)
                assertEquals(period.id, timeline.atYear(region, period.year)?.id)
            }
        }
        // Chinese selections also switch Korea, using its period interval.
        assertEquals("silla", timeline.atYear("kr", timeline.forRegion("cn")[1].year)?.id)
        assertEquals("goryeo", timeline.atYear("kr", timeline.forRegion("cn")[2].year)?.id)
        assertEquals("joseon_late", timeline.atYear("kr", timeline.forRegion("cn")[3].year)?.id)
        // Korean selections also switch China; the period orders do not align.
        assertEquals("tang", timeline.atYear("cn", timeline.forRegion("kr")[0].year)?.id)
        assertEquals("ming", timeline.atYear("cn", timeline.forRegion("kr")[1].year)?.id)
        // A selected radio item uses containment, even when reference years differ.
        assertTrue(timeline.forRegion("kr").single { it.id == "goryeo" }.contains(1102))
        assertTrue(timeline.forRegion("cn").single { it.id == "ming" }.contains(1370))
    }

    @Test fun missingPeriodsDoNotUseAnotherCenturyAsFallback() {
        assertNull(timeline.atYear("cn", 1864))
        assertNull(timeline.atYear("kr", 2))
        assertTrue(timeline.forRegion("vn").isEmpty())
        assertEquals("silla", timeline.atYear("kr", 935)?.id)
        assertEquals("goryeo", timeline.atYear("kr", 936)?.id)
        assertEquals("goryeo", timeline.atYear("kr", 1391)?.id)
        assertEquals("joseon_late", timeline.atYear("kr", 1392)?.id)
    }

    @Test fun joseonSelectionUsesMingContextInsteadOfItsLateSourceDate() {
        val joseon = timeline.forRegion("kr").single { it.id == "joseon_late" }
        for (previous in listOf(2, 742, 757, 1102, 1370, 1585, 1864)) {
            val selected = timeline.contextYearFor(joseon, previous)
            assertEquals(1585, selected)
            assertEquals("ming", timeline.atYear("cn", selected)?.id)
            assertEquals("joseon_late", timeline.atYear("kr", selected)?.id)
        }
        assertEquals(1864, joseon.year) // The underlying source date is retained.
    }

    @Test fun eachKoreanSelectionHasContemporaryChineseData() {
        for (period in timeline.forRegion("kr")) {
            val selected = timeline.contextYearFor(period, 2)
            assertTrue(selected in timeline.years)
            assertEquals(period.id, timeline.atYear("kr", selected)?.id)
            assertTrue(timeline.atYear("cn", selected) != null)
        }
        val goryeo = timeline.forRegion("kr").single { it.id == "goryeo" }
        assertEquals(1102, timeline.contextYearFor(goryeo, 1102))
        assertEquals(1370, timeline.contextYearFor(goryeo, 1585))
    }

    @Test fun restoringPreviouslySavedJoseonDateRepairsBlankChina() {
        assertEquals(1585, timeline.restoreYear(1864))
        for (year in listOf(2, 742, 757, 1102, 1370, 1585)) {
            assertEquals(year, timeline.restoreYear(year))
        }
    }
}
