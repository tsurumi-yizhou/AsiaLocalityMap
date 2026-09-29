# 此地 · Asia Locality Map

Android 本地历史地图 demo，包名 **asia.locality.map**。打开后请求当前位置，直接浏览当地历史底图。纯白背景、灰黑细线、楷体文字，常用操作配简洁线条图标，无年代选择器。

应用与 Android 测试全部使用 Kotlin，分别位于 `app/src/main/kotlin/`、`app/src/androidTest/kotlin/`；数据下载、清洗和截图调度保留 Python。Gradle 使用 Kotlin DSL。Lint 启用 `warningsAsErrors`，不使用警告屏蔽或 baseline。

支持单指拖动、双指缩放、双击放大、加减号缩放按钮、重新定位、地名检索。搜索与定位保留文字并配图标，缩放按钮提供无障碍操作名称。点击地名只选中，不显示资料、来源或沿革面板。地图和定位匹配完全离线，无网络权限。

界面使用 Compose Material 3 Adaptive：默认仅显示地图与常用操作，手机搜索为底部面板，平板搜索为侧栏；地图通过 AndroidView 保留 Canvas 绘制。支持中文、日文、韩文界面，跟随系统语言，也可通过 Android 13+ 的应用语言设置切换。历史地名保留来源原文。

默认优先显示县／旧郡／府郡县层级。同一实体只在图上标注一次，同名但不同实体分别保留，去掉重复底栏和定位精度说明。有县级边界时，以当前位置为中心适配辖区范围；缺县界时保持当地视野，标注附近县治并提示“县界待考”，不再自动扩大到整府。

搜索结果附地区、上级辖区（资料可判定时）、原始类型、行政体系及坐标，便于区分同名地点。直接选中的民政治所、军事驻地、土司治所分别说明，不使用“附近县治”概括所有点位。

定位请求状态与地图选中状态分开管理；重复定位超时和切后台中断会结束等待提示。主动选择地点会停止未完成的定位请求，避免迟到的结果覆盖搜索跳转。

缩放、双击放大、返回定位与搜索跳转使用约 260 毫秒的平滑过渡，手动拖动或捏合可立即接管地图；系统关闭动画时直接切换。

## 当前资料

完整下载与本地结构化库并不等于历史覆盖完整。原数据保存在 `data/raw/`，统一研究库为 `data/processed/history.sqlite`，质量清单为 `data/processed/quality.json`。

| 来源 | 原始记录 | demo 使用 |
| --- | ---: | ---: |
| CHGIS 县级治所时序 | 10,522 | 1,434 |
| CHGIS 府级治所时序 | 5,226 | 255 |
| CHGIS 府级辖区时序 | 3,830 | 231 |
| 明代卫所驻地点 | 375 | 375 |
| 日本旧国／旧郡 | 85 国、806 郡 | 68 国、715 郡 |
| 朝鲜道级／府郡县级空间记录 | 1,013 | 9 道级、335 府郡县级 |
| 朝鲜沿革表 | 4,183 行 | 本地保留原文，界面暂不显示 |

日本原始多岛几何按相同 ID 合并保存。默认图层排除北海道明治新国与琉球参考记录，合并明治初年分置的陆奥、出羽新国。朝鲜按来源要求筛选 `base_year=s1864`，不使用不可靠的几何起止年查询。中国用年区间包含 1644 的候选记录；异常年份被隔离，保留同年变更提示。

**县治所不是县界**。当前位置只能匹配已收录的辖区面；缺界时显示待考，附近治所不作为归属。军事、土司与民政分别标注。都司完整隶属、三宣六慰缺项、中国完整县界和古迹专题仍待补齐。台湾不套用清代府县。

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

## 文档

- [资料约定与历史口径](docs/product.html)
- [来源许可与限制](docs/data-rights.html)
- [开源与再分发](docs/open-source.html)
- [隐私政策](docs/privacy.html)
- [当前手机／平板及中日韩界面截图](docs/index.html)（图片位于 `docs/assets/screenshots/`，运行 `python3 tests/capture_site_emulator.py` 按现有文件更新）

数据、派生图层、APK 与本机配置不进入代码仓库。代码开放与数据授权分别处理；转换格式不改变来源许可。文鼎楷体随附原始许可，韩文及缺字使用 Android 系统字体回退。
