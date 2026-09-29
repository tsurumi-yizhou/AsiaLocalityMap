package asia.locality.map

import android.graphics.Typeface
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.material3.adaptive.ExperimentalMaterial3AdaptiveApi
import androidx.compose.material3.adaptive.currentWindowAdaptiveInfoV2
import androidx.compose.material3.adaptive.layout.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.foundation.text.input.TextFieldState
import androidx.compose.foundation.text.input.rememberTextFieldState
import androidx.compose.foundation.text.input.TextFieldLineLimits
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView

class UiMessage(val title: String, val body: String, val action: String, val onConfirm: () -> Unit)

@OptIn(ExperimentalMaterial3Api::class, ExperimentalMaterial3AdaptiveApi::class)
@Composable
fun LocalityApp(
    data: MapData?, statusId: Int, searchOpen: Boolean, message: UiMessage?,
    onMapReady: (InkMapView) -> Unit, onMapReleased: (InkMapView) -> Unit,
    onSearch: () -> Unit, onCloseSearch: () -> Unit, onLocate: () -> Unit,
    onZoom: (Double) -> Unit, onChoose: (MapData.Feature) -> Unit, onDismissMessage: () -> Unit
) {
    val context = LocalContext.current
    val kai = remember { Typeface.createFromAsset(context.assets, "fonts/kaiti.ttf") }
    val family = remember(kai) { FontFamily(kai) }
    val base = Typography()
    val typography = Typography(
        bodyLarge = base.bodyLarge.copy(fontFamily = family),
        bodyMedium = base.bodyMedium.copy(fontFamily = family),
        bodySmall = base.bodySmall.copy(fontFamily = family),
        titleLarge = base.titleLarge.copy(fontFamily = family),
        titleMedium = base.titleMedium.copy(fontFamily = family),
        labelLarge = base.labelLarge.copy(fontFamily = family)
    )
    val directive = calculatePaneScaffoldDirective(currentWindowAdaptiveInfoV2())
    val wide = directive.maxHorizontalPartitions > 1
    val searchState = rememberTextFieldState()
    var infoPage by rememberSaveable { mutableIntStateOf(-1) }
    BackHandler(enabled = wide && searchOpen && infoPage < 0, onBack = onCloseSearch)
    MaterialTheme(
        colorScheme = lightColorScheme(primary = Color(0xFF30332F), onPrimary = Color.White,
            secondaryContainer = Color(0xFFF0F1EC), onSecondaryContainer = Color(0xFF30332F),
            surface = Color.White, surfaceContainerLow = Color(0xFFF8F8F5),
            background = Color.White), typography = typography
    ) {
        Surface(Modifier.fillMaxSize()) {
            SupportingPaneScaffold(
                directive = directive,
                value = ThreePaneScaffoldValue(
                    primary = PaneAdaptedValue.Expanded,
                    secondary = if (wide && searchOpen) PaneAdaptedValue.Expanded else PaneAdaptedValue.Hidden,
                    tertiary = PaneAdaptedValue.Hidden
                ),
                modifier = Modifier.windowInsetsPadding(WindowInsets.safeDrawing),
                mainPane = {
                    Box(Modifier.fillMaxSize()) {
                        AndroidView(
                            factory = { InkMapView(it).apply { setFont(kai); onMapReady(this) } },
                            onRelease = onMapReleased,
                            modifier = Modifier.fillMaxSize().padding(bottom = 100.dp).clipToBounds()
                        )
                        if (!searchOpen) FilledTonalButton(onClick = onSearch,
                            modifier = Modifier.align(Alignment.TopStart).padding(16.dp)) {
                            Icon(painterResource(R.drawable.ic_search), contentDescription = null,
                                modifier = Modifier.size(20.dp))
                            Spacer(Modifier.width(8.dp))
                            Text(stringResource(R.string.search))
                        }
                        TextButton(onClick = { infoPage = 0 },
                            modifier = Modifier.align(Alignment.TopEnd).padding(16.dp)) {
                            Text(stringResource(R.string.info_about))
                        }
                        Column(Modifier.align(Alignment.BottomCenter).padding(horizontal = 12.dp, vertical = 8.dp),
                            horizontalAlignment = Alignment.CenterHorizontally) {
                            if (statusId != 0) Text(stringResource(statusId), style = MaterialTheme.typography.bodySmall,
                                modifier = Modifier.padding(bottom = 8.dp))
                            Surface(shape = RoundedCornerShape(28.dp), color = MaterialTheme.colorScheme.surfaceContainerLow) {
                                Row(Modifier.padding(horizontal = 8.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                                    TextButton(onClick = onLocate) {
                                        Icon(painterResource(R.drawable.ic_locate), contentDescription = null,
                                            modifier = Modifier.size(20.dp))
                                        Spacer(Modifier.width(8.dp))
                                        Text(stringResource(R.string.return_here))
                                    }
                                    IconButton(onClick = { onZoom(0.6) }, modifier = Modifier.size(48.dp)) {
                                        Icon(painterResource(R.drawable.ic_plus),
                                            contentDescription = stringResource(R.string.zoom_in))
                                    }
                                    IconButton(onClick = { onZoom(1.6) }, modifier = Modifier.size(48.dp)) {
                                        Icon(painterResource(R.drawable.ic_minus),
                                            contentDescription = stringResource(R.string.zoom_out))
                                    }
                                }
                            }
                        }
                    }
                },
                supportingPane = {
                    if (wide && searchOpen) Surface(Modifier.fillMaxHeight().preferredWidth(360.dp).padding(12.dp),
                        shape = RoundedCornerShape(28.dp), color = MaterialTheme.colorScheme.surfaceContainerLow) {
                        SearchPanel(data, searchState, onCloseSearch, onChoose)
                    }
                }
            )
            if (searchOpen && !wide) ModalBottomSheet(
                onDismissRequest = onCloseSearch,
                sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
            ) {
                Box(Modifier.fillMaxHeight(0.85f).imePadding()) {
                    SearchPanel(data, searchState, onCloseSearch, onChoose)
                }
            }
            if (infoPage >= 0) InfoPages(infoPage, { infoPage = it }, { infoPage = -1 })
            if (message != null) AlertDialog(onDismissRequest = onDismissMessage,
                title = { Text(message.title) }, text = { Text(message.body) },
                confirmButton = { TextButton(onClick = message.onConfirm) { Text(message.action) } },
                dismissButton = { TextButton(onClick = onDismissMessage) { Text(stringResource(R.string.close)) } })
        }
    }
}

@Composable
private fun SearchPanel(data: MapData?, state: TextFieldState,
    onClose: () -> Unit, onChoose: (MapData.Feature) -> Unit) {
    val query = state.text.toString()
    val results = remember(data, query) {
        if (query.isBlank()) emptyList() else data?.features?.filter {
            it.name.contains(query.trim(), ignoreCase = true)
        }?.take(100).orEmpty()
    }
    Column(Modifier.fillMaxSize().padding(16.dp)) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text(stringResource(R.string.search), style = MaterialTheme.typography.titleLarge, modifier = Modifier.weight(1f))
            TextButton(onClick = onClose) { Text(stringResource(R.string.close)) }
        }
        OutlinedTextField(state = state, lineLimits = TextFieldLineLimits.SingleLine,
            leadingIcon = { Icon(painterResource(R.drawable.ic_search), contentDescription = null) },
            label = { Text(stringResource(R.string.search_hint)) },
            shape = RoundedCornerShape(20.dp), modifier = Modifier.fillMaxWidth())
        if (query.isNotBlank() && results.isEmpty()) Text(
            stringResource(if (data == null) R.string.loading else R.string.no_results),
            modifier = Modifier.padding(vertical = 20.dp))
        LazyColumn(Modifier.weight(1f)) {
            items(results, key = { it.id }) { feature ->
                val locality = remember(data, feature.id) { data?.contextNames(feature).orEmpty() }
                val region = stringResource(when (feature.region) {
                    "cn" -> R.string.region_cn
                    "jp" -> R.string.region_jp
                    "kr" -> R.string.region_kr
                    else -> R.string.region_other
                })
                val system = stringResource(when (feature.system) {
                    "军事" -> R.string.system_military
                    "土司" -> R.string.system_native
                    else -> R.string.system_civil
                })
                Column(Modifier.fillMaxWidth().clickable { onChoose(feature) }
                    .padding(horizontal = 12.dp, vertical = 16.dp)) {
                    Text(feature.name, style = MaterialTheme.typography.bodyLarge)
                    Text(listOf(region, locality, feature.kind, system).filter { it.isNotBlank() }.joinToString(" · "),
                        style = MaterialTheme.typography.bodySmall)
                    Text(stringResource(R.string.place_coordinates, feature.lat, feature.lon),
                        style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
}
