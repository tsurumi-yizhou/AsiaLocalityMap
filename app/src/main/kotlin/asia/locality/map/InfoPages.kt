package asia.locality.map

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp

private class Section(val title: Int, val body: Int)

private val privacy = listOf(
    Section(R.string.info_p1_t, R.string.info_p1_b), Section(R.string.info_p2_t, R.string.info_p2_b),
    Section(R.string.info_p3_t, R.string.info_p3_b), Section(R.string.info_p4_t, R.string.info_p4_b)
)
private val openSource = listOf(
    Section(R.string.info_o1_t, R.string.info_o1_b), Section(R.string.info_o2_t, R.string.info_o2_b),
    Section(R.string.info_o3_t, R.string.info_o3_b), Section(R.string.info_o4_t, R.string.info_o4_b)
)

/** Full-screen about pages: [page] 0 = privacy policy, 1 = open source and redistribution. */
@Composable
fun InfoPages(page: Int, onPage: (Int) -> Unit, onClose: () -> Unit) {
    BackHandler(onBack = onClose)
    Surface(Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize().windowInsetsPadding(WindowInsets.safeDrawing)) {
            Row(Modifier.fillMaxWidth().padding(start = 16.dp, end = 8.dp, top = 8.dp)) {
                Text(stringResource(R.string.info_about_title), style = MaterialTheme.typography.titleLarge,
                    modifier = Modifier.weight(1f).align(androidx.compose.ui.Alignment.CenterVertically))
                TextButton(onClick = onClose) { Text(stringResource(R.string.info_back)) }
            }
            PrimaryTabRow(selectedTabIndex = page, containerColor = MaterialTheme.colorScheme.surface) {
                Tab(selected = page == 0, onClick = { onPage(0) }, text = { Text(stringResource(R.string.info_privacy_tab)) })
                Tab(selected = page == 1, onClick = { onPage(1) }, text = { Text(stringResource(R.string.info_oss_tab)) })
            }
            Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 20.dp, vertical = 16.dp)) {
                for (section in if (page == 0) privacy else openSource) {
                    Text(stringResource(section.title), style = MaterialTheme.typography.titleMedium,
                        modifier = Modifier.padding(top = 16.dp, bottom = 6.dp))
                    Text(stringResource(section.body), style = MaterialTheme.typography.bodyMedium)
                }
            }
        }
    }
}
