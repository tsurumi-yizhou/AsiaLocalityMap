plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "asia.locality.map"
    compileSdk = 37
    buildFeatures { compose = true }
    androidResources { generateLocaleConfig = true; localeFilters += listOf("zh", "zh-rCN", "ja", "ko") }
    defaultConfig {
        applicationId = "asia.locality.map"
        minSdk = 30
        targetSdk = 37
        versionCode = 1
        versionName = "0.1.0"
        testInstrumentationRunner = "asia.locality.map.MapGestureProbe"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    // Locally prepared research data is packaged only for this local demo.
    sourceSets.getByName("main").assets.directories.add("../data/processed/android")
    lint { abortOnError = true; warningsAsErrors = true }
}
dependencies {
    implementation(platform("androidx.compose:compose-bom:2026.09.00"))
    implementation("androidx.activity:activity-compose:1.13.0")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material3.adaptive:adaptive:1.3.0")
    implementation("androidx.compose.material3.adaptive:adaptive-layout:1.3.0")
}

tasks.register("verifyOfflineData") {
    doLast {
        for (name in listOf("map.jsonl", "land.json")) {
            check(rootProject.file("data/processed/android/$name").isFile) {
                "Missing offline data: $name. Run .venv/bin/python scripts/prepare_data.py first."
            }
        }
    }
}

tasks.named("preBuild") { dependsOn("verifyOfflineData") }
