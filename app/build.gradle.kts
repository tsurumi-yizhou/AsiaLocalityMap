plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.plugin.compose")
}

val releaseVersionCode = providers.gradleProperty("releaseVersionCode").map { value ->
    requireNotNull(value.toIntOrNull()?.takeIf { it in 1..2100000000 }) {
        "releaseVersionCode must be an integer between 1 and 2100000000."
    }
}.getOrElse(1)
val releaseVersionName = providers.gradleProperty("releaseVersionName").getOrElse("0.1.0")

android {
    namespace = "asia.locality.map"
    compileSdk = 37
    buildFeatures { compose = true }
    androidResources { generateLocaleConfig = true; localeFilters += listOf("zh", "zh-rCN", "ja", "ko") }
    defaultConfig {
        applicationId = "asia.locality.map"
        minSdk = 30
        targetSdk = 37
        versionCode = releaseVersionCode
        versionName = releaseVersionName
        testInstrumentationRunner = "asia.locality.map.MapGestureProbe"
    }

    val uploadKeystorePath = providers.environmentVariable("ANDROID_KEYSTORE_PATH").orNull
    if (!uploadKeystorePath.isNullOrBlank()) {
        signingConfigs {
            create("release") {
                storeFile = file(uploadKeystorePath)
                storePassword = providers.environmentVariable("ANDROID_KEYSTORE_PASSWORD").get()
                keyAlias = providers.environmentVariable("ANDROID_KEY_ALIAS").get()
                keyPassword = providers.environmentVariable("ANDROID_KEY_PASSWORD").get()
            }
        }
        buildTypes.getByName("release").signingConfig = signingConfigs.getByName("release")
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    // Offline data must be prepared before building the app.
    sourceSets.getByName("main").assets.directories.add("../data/processed/android")
    lint { abortOnError = true; warningsAsErrors = true }
}
dependencies {
    testImplementation("junit:junit:4.13.2")
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
        for (name in listOf("map.jsonl", "land.json", "timeline.json", "regions.json", "reference-years.json")) {
            check(rootProject.file("data/processed/android/$name").isFile) {
                "Missing offline data: $name. Run .venv/bin/python scripts/prepare_data.py first."
            }
        }
    }
}

tasks.named("preBuild") { dependsOn("verifyOfflineData") }
