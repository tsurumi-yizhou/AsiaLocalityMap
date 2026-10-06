package asia.locality.map

import android.graphics.Typeface
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
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
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.foundation.text.input.clearText
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.layout.onSizeChanged

/** Regions whose menu offers more than one historical period. */
private val PERIOD_REGIONS = setOf("cn", "kr")

class UiMessage(val title: String, val body: String, val action: String, val onConfirm: () -> Unit)

@OptIn(ExperimentalMaterial3Api::class, ExperimentalMaterial3AdaptiveApi::class)
@Composable
fun LocalityApp(
    data: MapData?, statusId: Int?, searchOpen: Boolean, message: UiMessage?,
    timeline: Timeline?, year: Int, region: String, changingPeriod: Boolean, onPeriod: (HistoryPeriod) -> Unit,
    onMapReady: (InkMapView) -> Unit, onMapReleased: (InkMapView) -> Unit,
    onControlsHeight: (Int) -> Unit,
    onSearch: () -> Unit, onCloseSearch: () -> Unit, onLocate: () -> Unit,
    onZoom: (Double) -> Unit, onChoose: (MapData.Feature) -> Unit, onDismissMessage: () -> Unit
) {
    val context = LocalContext.current
    val kai = remember {
        fun family(file: String) = android.graphics.fonts.FontFamily.Builder(
            android.graphics.fonts.Font.Builder(context.assets, file).build()).build()
        Typeface.CustomFallbackBuilder(family("fonts/kaiti.ttf"))
            .addCustomFallback(family("fonts/kaiti-traditional.ttf"))
            .setSystemFallback("serif").build()
    }
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
    var periodsOpen by rememberSaveable { mutableStateOf(false) }
    val density = LocalDensity.current
    var bottomBarHeight by remember { mutableIntStateOf(0) }
    val periodChoices = if (region in PERIOD_REGIONS) timeline?.forRegion(region).orEmpty() else emptyList()
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
                            modifier = Modifier.fillMaxSize().padding(bottom = with(density) { bottomBarHeight.toDp() }).clipToBounds()
                        )
                        Column(Modifier.align(Alignment.TopCenter).fillMaxWidth()
                            .onSizeChanged { onControlsHeight(it.height) }
                            .padding(horizontal = 16.dp, vertical = 8.dp)) {
                            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                                if (!searchOpen) FilledTonalButton(onClick = onSearch) {
                                    Icon(painterResource(R.drawable.ic_search), contentDescription = null,
                                        modifier = Modifier.size(20.dp))
                                    Spacer(Modifier.width(8.dp))
                                    Text(stringResource(R.string.search))
                                }
                                Spacer(Modifier.weight(1f))
                                TextButton(onClick = { infoPage = 0 }) {
                                    Text(stringResource(R.string.info_about))
                                }
                            }
                            // One control slot for every region, so panning never moves the button.
                            val choosable = periodChoices.size > 1
                            val localYear = data?.referenceYears?.get(region)
                            val period = timeline?.atYear(region, year)
                            val periodLabel = when {
                                region == "jp" && localYear != null -> stringResource(
                                    if ("jp" in data.fineBoundaryRegions) R.string.japan_early_modern else R.string.japan_provinces)
                                choosable && period != null && localYear != null ->
                                    period.title(context)
                                else -> stringResource(regionName(region))
                            }
                            if (choosable) TextButton(onClick = { periodsOpen = true }, enabled = data != null && !changingPeriod) {
                                Text(periodLabel)
                                Spacer(Modifier.width(8.dp))
                                Icon(painterResource(R.drawable.ic_expand_more), contentDescription = null,
                                    modifier = Modifier.size(18.dp))
                            } else Box(Modifier.heightIn(min = 40.dp).padding(horizontal = 12.dp), contentAlignment = Alignment.CenterStart) {
                                Text(periodLabel, style = MaterialTheme.typography.labelLarge)
                            }
                        }
                        if (changingPeriod) LinearProgressIndicator(Modifier.align(Alignment.TopCenter).fillMaxWidth())
                        Column(Modifier.align(Alignment.BottomCenter).padding(horizontal = 12.dp, vertical = 8.dp),
                            horizontalAlignment = Alignment.CenterHorizontally) {
                            // Transient notes float over the map so the map never resizes when they come and go.
                            if (statusId != null) Surface(shape = RoundedCornerShape(16.dp),
                                color = MaterialTheme.colorScheme.surfaceContainerLow,
                                modifier = Modifier.padding(bottom = 8.dp)) {
                                Text(stringResource(statusId), style = MaterialTheme.typography.bodySmall,
                                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp))
                            }
                            Surface(shape = RoundedCornerShape(28.dp), color = MaterialTheme.colorScheme.surfaceContainerLow,
                                modifier = Modifier.onSizeChanged { bottomBarHeight = it.height + with(density) { 16.dp.roundToPx() } }) {
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
            if (periodsOpen && periodChoices.size > 1) PeriodPicker(periodChoices, region, year, {
                onPeriod(it)
                periodsOpen = false
            }, { periodsOpen = false })
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
    val focus = remember { FocusRequester() }
    val keyboard = LocalSoftwareKeyboardController.current
    LaunchedEffect(Unit) { focus.requestFocus() }
    val results = remember(data, query) {
        val needle = MapData.normalizeSearch(query.trim())
        if (needle.isBlank()) emptyList() else data?.labelFeatures?.filter {
            it.searchText.contains(needle)
        }?.distinctBy { it.labelId }?.take(100).orEmpty()
    }
    Column(Modifier.fillMaxSize().padding(16.dp)) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text(stringResource(R.string.search), style = MaterialTheme.typography.titleLarge, modifier = Modifier.weight(1f))
            TextButton(onClick = onClose) { Text(stringResource(R.string.close)) }
        }
        OutlinedTextField(state = state, lineLimits = TextFieldLineLimits.SingleLine,
            leadingIcon = { Icon(painterResource(R.drawable.ic_search), contentDescription = null) },
            trailingIcon = if (query.isEmpty()) null else {
                {
                    IconButton(onClick = { state.clearText() }) {
                        Icon(painterResource(R.drawable.ic_clear), contentDescription = stringResource(R.string.clear_search))
                    }
                }
            },
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
            onKeyboardAction = { keyboard?.hide() },
            label = { Text(stringResource(R.string.search_hint)) },
            shape = RoundedCornerShape(20.dp), modifier = Modifier.fillMaxWidth().focusRequester(focus))
        if (query.isNotBlank() && results.isEmpty()) Column(Modifier.padding(vertical = 20.dp)) {
            Text(stringResource(if (data == null) R.string.loading else R.string.no_results))
            if (data != null) Text(stringResource(R.string.no_results_period_hint),
                style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(top = 4.dp))
        }
        LazyColumn(Modifier.weight(1f)) {
            items(results, key = { it.id }) { feature ->
                val locality = remember(data, feature.id) { data?.contextNames(feature).orEmpty() }
                val region = stringResource(regionName(feature.region))
                val system = stringResource(when (feature.system) {
                    "军事" -> R.string.system_military
                    "土司" -> R.string.system_native
                    "政权" -> R.string.system_polity
                    else -> R.string.system_civil
                })
                Column(Modifier.fillMaxWidth().clickable { onChoose(feature) }
                    .padding(horizontal = 12.dp, vertical = 16.dp)) {
                    Text(feature.name, style = MaterialTheme.typography.bodyLarge)
                    if (feature.nativeName.isNotBlank() && feature.nativeName != feature.name) {
                        Text(feature.nativeName, style = MaterialTheme.typography.bodySmall)
                    }
                    Text(listOf(region, locality, feature.kind, system).filter { it.isNotBlank() }.joinToString(" · "),
                        style = MaterialTheme.typography.bodySmall)
                    Text(stringResource(R.string.place_coordinates, feature.lat, feature.lon),
                        style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
}

@Composable
private fun PeriodPicker(choices: List<HistoryPeriod>, region: String, year: Int, onChoose: (HistoryPeriod) -> Unit, onClose: () -> Unit) {
    val context = LocalContext.current
    AlertDialog(onDismissRequest = onClose,
        containerColor = MaterialTheme.colorScheme.surface,
        title = { Text(stringResource(regionName(region)), style = MaterialTheme.typography.titleLarge) },
        text = {
                Column(Modifier.verticalScroll(rememberScrollState()).selectableGroup()) {
                    for (option in choices) {
                        Row(Modifier.fillMaxWidth().selectable(selected = option.contains(year), role = Role.RadioButton,
                            onClick = { onChoose(option) }).padding(vertical = 8.dp),
                            verticalAlignment = Alignment.CenterVertically) {
                            RadioButton(selected = option.contains(year), onClick = null)
                            Text(option.title(context),
                                modifier = Modifier.padding(start = 8.dp).weight(1f))
                        }
                    }
                }
        },
        confirmButton = {})
}


private fun regionName(region: String): Int = when (region) {
    "cn" -> R.string.region_cn
    "jp" -> R.string.region_jp
    "kr" -> R.string.region_kr
    "vn" -> R.string.region_vn
    "ea" -> R.string.region_ea
    else -> R.string.region_other
}
