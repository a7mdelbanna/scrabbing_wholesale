@echo off
set JAVA_HOME=C:\Program Files\Android\Android Studio\jbr
set SKIP_JDK_VERSION_CHECK=1
echo y | "C:\Users\ahmed\AppData\Local\Android\Sdk\cmdline-tools\latest\bin\sdkmanager.bat" "system-images;android-30;google_apis;arm64-v8a"
