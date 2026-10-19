import java.util.Properties

plugins {
    id("com.android.application")
    id("kotlin-android")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

val personalSigningFile = rootProject.file("../../.private/android-signing.properties")
val personalSigning = Properties().apply {
    if (personalSigningFile.exists()) personalSigningFile.inputStream().use { load(it) }
}

android {
    namespace = "dev.elink.elink_frame"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = JavaVersion.VERSION_17.toString()
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "dev.elink.elink_frame"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    signingConfigs {
        if (personalSigningFile.exists()) {
            create("personal") {
                storeFile = file(personalSigning.getProperty("storeFile"))
                storePassword = personalSigning.getProperty("storePassword")
                keyAlias = "elink"
                keyPassword = personalSigning.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            signingConfig = signingConfigs.getByName(if (personalSigningFile.exists()) "personal" else "debug")
        }
    }
}

flutter {
    source = "../.."
}
