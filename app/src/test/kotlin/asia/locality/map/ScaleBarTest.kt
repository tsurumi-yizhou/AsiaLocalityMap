package asia.locality.map

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.asin
import kotlin.math.cos
import kotlin.math.pow
import kotlin.math.sin
import kotlin.math.sqrt

class ScaleBarTest {
    @Test fun distanceMatchesTheDrawnLengthAcrossLatitudesAndZooms() {
        for (latitude in listOf(-80.0, 0.0, 23.0, 33.0, 60.0, 80.0)) {
            for (span in listOf(0.04, 0.5, 2.0, 40.0, 100.0)) {
                for ((width, density) in listOf(320 to 1f, 1080 to 3f, 2560 to 2f)) {
                    val size = ScaleBar.size(latitude, span, width, density, 0)
                    val delta = Math.toRadians(size.pixels.toDouble() / width * span)
                    val haversine = cos(Math.toRadians(latitude)).pow(2) * sin(delta / 2).pow(2)
                    val actualMeters = 12_742_000 * asin(sqrt(haversine))
                    assertEquals(size.meters.toDouble(), actualMeters, size.meters * 0.000001)
                    assertTrue(size.pixels > 0 && size.pixels < width * 0.75)
                    var leading = size.meters
                    while (leading % 10 == 0L) leading /= 10
                    assertTrue(leading in listOf(1L, 2L, 5L))
                }
            }
        }
    }

    @Test fun panningRetainsTheCaptionAndAdjustsTheLength() {
        val start = ScaleBar.size(33.0, 10.0, 1080, 3f, 0)
        val north = ScaleBar.size(40.0, 10.0, 1080, 3f, start.meters)
        assertEquals(start.meters, north.meters)
        assertTrue(north.pixels > start.pixels)
    }

    @Test fun crossingAnInitialTierBoundaryDoesNotFlicker() {
        assertTrue(ScaleBar.size(33.0, 7.5, 1080, 3f, 0).meters !=
            ScaleBar.size(33.0, 7.7, 1080, 3f, 0).meters)
        var retained = 0L
        for (span in listOf(7.5, 7.7, 7.5, 7.7, 7.5)) {
            val next = ScaleBar.size(33.0, span, 1080, 3f, retained)
            if (retained != 0L) assertEquals(retained, next.meters)
            retained = next.meters
        }
    }

    @Test fun largeZoomChangesSwitchTiersAndStreetZoomUsesMeters() {
        val overview = ScaleBar.size(33.0, 40.0, 1080, 3f, 0)
        val street = ScaleBar.size(60.0, 0.04, 1080, 3f, overview.meters)
        assertTrue(street.meters in 1..999)
        assertTrue(street.pixels < 1080 * 0.4f)
        val zoomOut = ScaleBar.size(33.0, 100.0, 1080, 3f, street.meters)
        assertTrue(zoomOut.meters > overview.meters)
    }
}
