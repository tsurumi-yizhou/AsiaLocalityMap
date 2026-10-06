# 此地 · Asia Locality Map

Android 本地历史地图 demo，包名 **asia.locality.map**。打开后请求当前位置，直接浏览当地历史底图。纯白背景、灰黑细线、楷体文字，常用操作配简洁线条图标，时期菜单随视野切换，仅提供有地方资料的选项。

应用与 Android 测试全部使用 Kotlin，分别位于 `app/src/main/kotlin/`、`app/src/androidTest/kotlin/`；数据下载、清洗和截图调度保留 Python。Gradle 使用 Kotlin DSL。Lint 启用 `warningsAsErrors`，不使用警告屏蔽或 baseline。

支持单指拖动、双指缩放、双击放大、加减号缩放按钮、重新定位、地名检索。搜索与定位保留文字并配图标，缩放按钮提供无障碍操作名称。点击地名只选中，不显示资料、来源或沿革面板。地图和定位匹配完全离线，无网络权限。

界面使用 Compose Material 3 Adaptive：默认仅显示地图与常用操作，手机搜索为底部面板，平板搜索为侧栏；地图通过 AndroidView 保留 Canvas 绘制。支持中文、日文、韩文界面，跟随系统语言，也可通过 Android 13+ 的应用语言设置切换。朝鲜地名以有依据的汉字名为主，谚文以小字显示，搜索兼容原文与简繁体；越南地方资料仍待接入。

默认优先显示县／旧郡／府郡县层级。同一实体只在图上标注一次，同名但不同实体分别保留，去掉重复底栏和定位精度说明。有县级边界时，以当前位置为中心适配辖区范围；缺县界时保持当地视野，只标注附近治所，不推断县界归属，不再自动扩大到整府。

搜索结果附地区、上级辖区（资料可判定时）、原始类型、行政体系及坐标，便于区分同名地点。直接选中的民政治所、军事驻地、土司治所分别说明，不使用“附近县治”概括所有点位。

定位请求状态与地图选中状态分开管理；重复定位超时和切后台中断会结束等待提示。主动选择地点会停止未完成的定位请求，避免迟到的结果覆盖搜索跳转。

缩放、双击放大、返回定位与搜索跳转使用约 260 毫秒的平滑过渡，手动拖动或捏合可立即接管地图；系统关闭动画时直接切换。

原始边界完整保存在研究库；应用只打包轻量参考几何，绘图和归属查询使用同一套简化面。导出时移除无其他行政区占用的水域孔洞、约10平方公里以下的附属碎岛；每个具名区划的主要陆块及其在上级区划中的对应岛屿始终保留。相邻区划和上下级区划先组成共边分区，再统一简化并按原成员关系重组，避免独立简化产生裂缝或新增交叠。采用0.008度VW面积阈值；节点网格从0.001度逐步细化，必须通过拓扑检查才导出。底图海岸使用0.01度简化。缩减统计见 `data/processed/display-geometry.json`。

运行时边界再按可见范围分段裁剪，并按屏幕精度选择简化层级。底图边界在后台绘入带余量的缓存，拖动／缩放时复用并变换，停稳后补绘当前精度。每张缓存限制在约 24 MB；切换朝代后丢弃旧图层的缓存和迟到结果。地名与选中边界仍随当前视野实时绘制，不增加界面提示。

行政区与边界分开存储：`snapshots/*.jsonl` 中的面只保留属性与有方向的边界段引用，坐标集中存放在 `boundaries/<地区>-<资料年>.json`。采用 [TopoJSON 的共享弧段与反向索引规则](https://github.com/topojson/topojson-specification)，不在此步骤再次取整或简化；编码后逐个还原，检查辖区、孔洞和离岛不变。日韩参考图跨时期复用同一网络。Android 只投影、缓存每条弧段一次，归属查询直接遍历共享坐标，不重建每区完整多边形；绘制按弧段去重，共用粗层边界不再被细层重复覆盖，单独选中时仍绘制该区完整轮廓。统计见 `data/processed/boundary-topology.json`。

地名在连续手势期间保留候选顺序，停稳后补排；县级与府级标注使用不同的进入／退出阈值，避免在临界比例尺反复切换。标注避让采用约 160 毫秒的淡入淡出，文字锚点对齐到像素；选中地名始终优先且只显示一次。

比例尺采用 1／2／5 系列整档距离，近距离以米显示。平移期间冻结数字和尺条，松手后按中心纬度在约 180 毫秒内调整尺条长度；缩放时实时跟随，尺条超出合理长度才切换档位，并保留缓冲范围以避免反复跳档。

## 地区朝代与录入口径

菜单按地图视野中心所在地区切换；中心在海上时参考可见陆地，只列该地区的朝代／时期。所有地区共用一个全局年份，平移不改变年份；中国或朝鲜的任一时间选项会切换整张地图、搜索和定位所用快照。时期入口与选项只显示朝代／时期名称，不显示年份；全局年份和资料参考年均作为内部数据保留。缺少对应时期资料的地区不回退到别的时代。

中国菜单只显示**汉、唐、宋、明**，默认明代；朝鲜菜单只显示**新羅、高麗、朝鮮**。每个时期只有一个选项，选择后优先保留该时期内当前共同年代，否则选用该时期内中朝均有资料的快照，再按该年代确定其他地区的时期，不按朝代序号配对。“朝鮮”使用1585年全局快照联动到明代，朝鲜区划资料的参考年仍保留1864年；旧版保存的1864年状态在启动时迁移到1585年。日本不设切换菜单，按同一全局年份控制令制国与郡界的显示。地图、搜索及定位只使用地方行政区划与治所；不显示国家、幕府或割据势力范围。

| 地区 | 可选时期与实际资料 |
| --- | --- |
| 朝鲜 | 新羅757年：9个州级辖区与九州五小京参考点；高麗：五道、两界及京畿共8个上级辖区，八牧沿革治所参考1370年；上级面按公开源图数字化；朝鮮1864年：334个府郡县级辖区及9个上级辖区。新罗、高丽尚无完整郡县界 |
| 日本 | 固定近世国郡参考图（资料基准1864年）；地图只显示“近世”，无可点击的时期菜单 |
| 越南 | 尚无已核验的历史府县空间数据，暂不提供时期选项或势力图替代层 |

中国目前保留郡州府级参考辖界和县治点，内部县界尚未补齐。新罗、高丽的上级边界已改为源图数字化面（9州／8辖区），治所参考点继续保留；内部县界仍待补充。地图地名锚定有依据的同期治所；无可确认治所的府州名仍使用辖区内参考点，绝不随定位移动。

中国、朝鲜均可选择时期，所有时期选择都可加载并保存。中国与朝鲜按当前全局年份选择各自的参考资料：朝鲜668—935年对应新罗757年、936—1391年对应高丽1370年、1392—1897年对应朝鲜1864年；日本仍为国郡参考1864年，资料适用范围保持分层限制。新罗上级为九州，高丽上级为五道、两界及京畿。高丽原图未注明精确年份，1370年是治所及内部快照的参考槽位，源图面保留时期级年代，不标作1370年逐年复原；八牧点为沿革参考。上下级分别存储；不使用朝鲜后期界线代替早期边界。


## 资料与层级

- **汉唐宋郡州界**：[Zheng & Wu公开数据](https://doi.org/10.6084/m9.figshare.30518417)，CC BY 4.0。使用从历史地图集数字化的 `ResearchArea` 郡州面，接入汉103、唐307、宋313个单独辖区；统计合并区、非行政区域及名称未能核定者隔离。检查了该研究的 `SimulatedCountyBoundaries`，其只有县编号，没有县名；与同期县治不能全部一一对应，未直接挂接名称。县界补充留待后续。原始英文名、属性、几何与汉字名核对依据保存在研究库；汉字名匹配CHGIS地名及校核后的史籍名称。青藏、西北及部分边疆仍有空白。
- **明代及补充府州界**：CHGIS时序面与县治点。明代原CHGIS有228个府州级面（显示227个，永平府改用与辽东同源的1582年参考面）；汉唐宋以新郡州面为主，CHGIS面只补其未覆盖部分，避免双重边界。面内的重复府州治所标注不再导出，县治点保留独立查询。县治点和府州面保留；内部县界后续补充。辽东新增1582年的都司整体参考面（用于1585年背景），内层卫所仍为驻地点。原始军卫表把铁岭卫错置于海州附近，已据1393年迁银州及清代同城改县的记载，以CHGIS铁岭旧县治点校正城市参考位置；原坐标和校正依据均保留。万全都司原有面纳入军事区划定位回退。大宁都司以迁驻保定的驻城参考点表示，不沿用明初旧辖区。
- **新罗、高丽上级边界**：新罗9州取自[统一新罗图](https://commons.wikimedia.org/wiki/File:统一新罗图(Unified_Silla).jpg)（GeorgeZhao，CC BY-SA 3.0；上传修订注明757年州名）；高丽5道、两界及京畿取自[高丽五道两界图](https://commons.wikimedia.org/wiki/File:高丽五道两界图.jpg)（Evawen，CC BY-SA 4.0）。`scripts/digitize_korean_maps.py` 按源图色块、可见界线和海岸提取面，共边只转换一次，不生成控制点分区，不借用其他时期行政界。原图校验值、图上描线、配准参考点、误差及派生几何保存在 `data/reference/korean-upper/`，原图叠加审核图在 `build/korean-upper-review/`。新罗原图为2436×2888像素、高丽原图为437×799像素；配准拟合RMS分别约16.47公里、2.44公里，代表参考点拟合残差，不是独立边界精度验证。高丽源图只确认五道两界框架，未注明精确地图年份，`geometry_year` 保持空值；不声称精确复原1370年每段界线。个别源图近岸误差不通过扩张行政面修补。
- **日本国郡**：[CODH](https://geoshape.ex.nii.ac.jp/kg/index.html.ja) 提供68国、715郡参考面。合并同ID岛屿，排除明治北海道新国，恢复分国前陆奥与出羽。
- **朝鲜地方区划**：[HisGeo](https://www.hisgeo.info/wiki/조선_행정구역_DB) 的完成辖区面采用1864年，应用只加载有边界的基准。汉字名按沿革表年份取值，谚文小字；来源冲突记录隔离。缩小地图也显示道级治所，不因点状资料而隐藏整个地区。
- **越南资料缺口**：[Liu与Fujii的研究](https://economics.smu.edu.sg/sites/economics.smu.edu.sg/files/2023-09/Liu%20Meng_JMP.pdf) 涉及217个历史县，并说明按《同庆地舆志》重建的方法，但本项目尚未取得可核验的县级空间文件。原势力图已撤下；不以现代县界或国境填补。
- **明代边区都司**：永平府—辽东都司两个相邻参考面取自[舆图1582年行政图层](https://geojsoncn.com/cn-historical-atlas/#f=ming)，该站声明依据《中国历史地图集》数字化；永平府与辽东按同源面共同显示，原CHGIS永平府仍保存在研究库。这是第三方简化参考，不宣称逐卫精确界。原图与朝鲜异年参考图在鸭绿江附近略有重叠，保留各自原形，不缓冲扩张或手绘补缝。此材料限当前本地研究核验，未获源数据再发布许可。大宁迁驻保定依据[国家博物馆](https://www.chnmuseum.cn/zp/zpml/csp/202008/t20200826_247448.shtml)，驻城坐标借用CHGIS同年保定府治，不表示都司衙署遗址的精确位置。
- **地区定位**：Natural Earth现代地区轮廓只用于菜单定位，不画作历史国境。

Cliopatria保留在研究处理链中，用于中国朝代范围筛选，不再用于生成朝鲜早期行政边界。政权要素不随APK导出；应用只显示有来源的行政区划或治所。构建检查要求每个菜单选项确有地方资料，所有应用要素必须是行政区划或治所。

原始资料在 `data/raw/`；完整来源与候选记录在 `data/processed/history.sqlite`，质量记录在 `quality.json`。`snapshot` 表保留来源候选年份，`display_snapshot` 表记录实际显示的时代与各地参考年，便于复核筛选。应用按时代分别加载 `snapshots/`，不一次载入全部时期的边界；`published.jsonl` 研究全集位于 APK 之外。

## 新罗、高丽源图与边界复现

应用默认导入版本化的 `data/reference/korean-upper/korea-upper-757.geojson` 与 `korea-upper-1370.geojson`，附同名前缀 `.source.json`。生成器先核对原图SHA-256，再按 `silla.trace.json`、`goryeo.trace.json` 复现像素域边界；像素共边组成网络后统一配准，防止分别投影造成裂缝。可在下载原图后运行 `.venv/bin/python scripts/digitize_korean_maps.py`，核对 `build/korean-upper-review/*-source-overlay.png`。

可用 `data/raw/` 中同名GeoJSON与来源清单替换版本化资料。每个WGS84要素必须包含来源 `id`（或 `properties.source_id`），属性包含 `name`、`native_name`、`year`；清单包含 `year`、`source_url`、`rights`、`sha256`。`boundary_basis` 仅接受 `published_boundary_geometry` 或 `digitized_published_map`；后者还保留原图校验、年代证据和配准参考点。构建要求9州及8辖区完整，缺失、异年、来源或校验失败、非法几何、模型控制点等情况均失败，不生成替代面，也不增加说明 UI。字段声明及校验值不能代替史料核验。

## 构建

需要 JDK 17+（本地验证 JDK 25）、Android SDK 37 和 Python。`local.properties` 设置本机 `sdk.dir`。

```sh
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt
# 首次取得来源文件后生成离线资料；原始文件清单见 scripts/download_sources.py。
.venv/bin/python scripts/download_sources.py
.venv/bin/python scripts/fetch_japan.py
.venv/bin/python scripts/prepare_data.py
.venv/bin/python -m unittest discover -s tests -v
./gradlew :app:assembleDebug :app:assembleDebugAndroidTest :app:lintDebug :app:lintRelease
```

APK：`app/build/outputs/apk/debug/app-debug.apk`。这是包含本地研究数据的演示包，当前不作为公开再分发版本。

安装应用及 Android 测试 APK 后，可在模拟器上运行以下交互检查（默认设备 `emulator-5554`，不对实体手机注入位置）。Windows 宿主机启动 AVD 与 ADB 服务后，WSL 的 ADB 可连接该服务；也可通过 `ASIA_ADB` 指定 Windows 的 `adb.exe`。截图与结果保存在 `build/screenshots/`。

```sh
adb -s emulator-5554 shell am instrument -w asia.locality.map.test/asia.locality.map.MapGestureProbe
adb -s emulator-5554 shell am instrument -w -e benchmark true asia.locality.map.test/asia.locality.map.MapGestureProbe
python3 tests/dynasty_emulator.py
python3 tests/regional_emulator.py
python3 tests/local_period_emulator.py
python3 tests/adaptive_emulator.py
```

设备测试覆盖视野与地区菜单联动、汉字检索、朝代范围筛选、定位请求与选中状态、视野保持、时期记忆和手机／平板中日韩界面。布局脚本退出时恢复设备尺寸、密度和应用语言。

性能基准在当前 AVD（`android-dev`）上执行五组固定的平移／缩放轨迹，输出实际窗口帧耗时的中位数和 P95。比较版本时应保持同一 AVD、分辨率与密度；模拟器结果不代表实体手机帧率。

GitHub Actions 的 `.github/workflows/build.yml` 在每次推送时自动执行测试性构建，也支持手动触发。流程使用 JDK 25、Android SDK 37 与仓库的 Gradle Wrapper，编译 Debug APK 和 Android 测试 APK，并执行 Debug／Release Lint。所用 Action 均采用配置时核实的最新稳定版本。

CI 使用空地图、空地区轮廓与完整时期目录作为占位文件，下载产物 `test-apks-no-map-data` 不含历史地图数据，仅用于构建验证；产物与 Lint 报告保留 7 天。完整研究数据的 Python 校验和模拟器交互测试仍按本地流程运行。

## Google Play 内部测试发布

`.github/workflows/release.yml` 在推送 `v*` 标签时自动发布，也支持在 GitHub Actions 页面选择该工作流后手动运行。流程下载来源数据、生成真实离线地图、运行 Python 数据校验和 Release Lint，再构建以 upload key 签名的 AAB，上传到包名 `asia.locality.map` 的 `internal` 轨道，发布状态为 `completed`。

### 首次配置

1. 在 Google Cloud 项目中启用 Google Play Android Developer API，创建服务账号和 JSON 密钥。
2. 在 Play Console 的“用户和权限”中邀请服务账号邮箱，为此应用授予“查看应用信息”和“将应用发布到测试轨道”的权限（[权限说明](https://support.google.com/googleplay/android-developer/answer/9844686)）。应用应已通过 Console 上传过一个版本，并配置 Play App Signing。
3. 在 GitHub 仓库的 **Settings → Secrets and variables → Actions → Secrets** 添加以下内容：

| Secret | 内容 |
| --- | --- |
| `ANDROID_KEYSTORE_BASE64` | Play 已登记的 upload keystore 的 Base64 内容 |
| `ANDROID_KEYSTORE_PASSWORD` | Keystore 密码 |
| `ANDROID_KEY_ALIAS` | Upload key 的 alias |
| `ANDROID_KEY_PASSWORD` | Upload key 的密码 |
| `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON` | 服务账号 JSON 密钥文件的完整内容 |

Keystore 使用现有 upload key；可在 Linux 上运行 `base64 -w 0 /path/to/upload.jks`，将输出保存到对应的 Secret。使用 GitHub CLI 时可直接写入，避免在终端显示凭据：

```sh
base64 -w 0 /path/to/upload.jks | gh secret set ANDROID_KEYSTORE_BASE64
gh secret set GOOGLE_PLAY_SERVICE_ACCOUNT_JSON < /path/to/service-account.json
```

### 版本与触发

当前 Play 最大 `versionCode` 为 **1**，工作流以 `1 + github.run_number` 生成新版本号，第一次运行生成 **2**。`versionName` 取标签去掉 `v` 的部分，手动运行时填写 `version_name`，例如 `0.1.1`。后续每次新运行的 `versionCode` 自动递增。

将工作流及相关改动提交并推送到默认分支后，可推送版本标签触发发布：

```sh
git tag v0.1.1
git push origin v0.1.1
```

若将来通过其他渠道上传更高的 `versionCode`，可在同一设置页的 **Variables** 配置 `ANDROID_VERSION_CODE_BASE` 为当时已上传的最大整数值。重新运行同一个 Actions run 会保留原版本号；若该版本号已被 Play 接收，需发起一次新的手动运行，并填写相同的 `version_name`。

签名文件仅在 runner 临时目录中还原，工作流结束时删除；密码通过环境变量传入 Gradle。Release 流程保存 Lint 报告 7 天。实际上传需要上述凭据与 Play 权限配置就绪。

参考：[Google Play API 接入](https://developers.google.com/android-publisher/getting_started)、[应用签名与 upload key](https://developer.android.com/studio/publish/app-signing)、[上传 Action](https://github.com/r0adkll/upload-google-play)。

## 文档

- [资料约定与历史口径](docs/product.html)
- [来源许可与限制](docs/data-rights.html)
- [开源与再分发](docs/open-source.html)
- [隐私政策](docs/privacy.html)
- [当前手机／平板及中日韩界面截图](docs/index.html)（图片位于 `docs/assets/screenshots/`，运行 `python3 tests/capture_site_emulator.py` 按现有文件更新）

数据、派生图层、APK 与本机配置不进入代码仓库。代码开放与数据授权分别处理；转换格式不改变来源许可。文鼎楷体随附原始许可，韩文及缺字使用 Android 系统字体回退。
