/*
 * Universal SSL Pinning Bypass for Android
 * Works with most apps including Flutter/Dart
 */

Java.perform(function() {
    console.log("[*] Starting SSL Pinning Bypass...");

    // 1. TrustManagerImpl bypass
    try {
        var TrustManagerImpl = Java.use('com.android.org.conscrypt.TrustManagerImpl');
        TrustManagerImpl.verifyChain.implementation = function(untrustedChain, trustAnchorChain, host, clientAuth, ocspData, tlsSctData) {
            console.log('[+] TrustManagerImpl.verifyChain bypassed for: ' + host);
            return untrustedChain;
        };
    } catch (e) {
        console.log('[-] TrustManagerImpl not found');
    }

    // 2. OkHttp3 CertificatePinner bypass
    try {
        var CertificatePinner = Java.use('okhttp3.CertificatePinner');
        CertificatePinner.check.overload('java.lang.String', 'java.util.List').implementation = function(hostname, peerCertificates) {
            console.log('[+] OkHttp3 CertificatePinner.check bypassed for: ' + hostname);
            return;
        };
        CertificatePinner.check.overload('java.lang.String', '[Ljava.security.cert.Certificate;').implementation = function(hostname, peerCertificates) {
            console.log('[+] OkHttp3 CertificatePinner.check bypassed for: ' + hostname);
            return;
        };
    } catch (e) {
        console.log('[-] OkHttp3 CertificatePinner not found');
    }

    // 3. TrustManager bypass
    try {
        var X509TrustManager = Java.use('javax.net.ssl.X509TrustManager');
        var SSLContext = Java.use('javax.net.ssl.SSLContext');

        var TrustManager = Java.registerClass({
            name: 'com.custom.TrustManager',
            implements: [X509TrustManager],
            methods: {
                checkClientTrusted: function(chain, authType) {},
                checkServerTrusted: function(chain, authType) {},
                getAcceptedIssuers: function() { return []; }
            }
        });

        var TrustManagers = [TrustManager.$new()];
        var sslContext = SSLContext.getInstance('TLS');
        sslContext.init(null, TrustManagers, null);
        console.log('[+] Custom TrustManager installed');
    } catch (e) {
        console.log('[-] TrustManager bypass failed: ' + e);
    }

    // 4. HttpsURLConnection bypass
    try {
        var HttpsURLConnection = Java.use('javax.net.ssl.HttpsURLConnection');
        HttpsURLConnection.setDefaultHostnameVerifier.implementation = function(hostnameVerifier) {
            console.log('[+] HttpsURLConnection.setDefaultHostnameVerifier bypassed');
            return;
        };
        HttpsURLConnection.setSSLSocketFactory.implementation = function(factory) {
            console.log('[+] HttpsURLConnection.setSSLSocketFactory bypassed');
            return;
        };
    } catch (e) {
        console.log('[-] HttpsURLConnection bypass not needed');
    }

    // 5. WebViewClient bypass
    try {
        var WebViewClient = Java.use('android.webkit.WebViewClient');
        WebViewClient.onReceivedSslError.implementation = function(webView, sslErrorHandler, sslError) {
            console.log('[+] WebViewClient.onReceivedSslError bypassed');
            sslErrorHandler.proceed();
        };
    } catch (e) {
        console.log('[-] WebViewClient bypass not needed');
    }

    // 6. Network Security Config bypass (Android 7+)
    try {
        var NetworkSecurityConfig = Java.use('android.security.net.config.NetworkSecurityConfig');
        NetworkSecurityConfig.isCleartextTrafficPermitted.overload().implementation = function() {
            console.log('[+] NetworkSecurityConfig cleartext permitted');
            return true;
        };
    } catch (e) {
        console.log('[-] NetworkSecurityConfig not found');
    }

    // 7. Flutter/Dart SSL bypass
    try {
        // For newer Flutter versions
        var module = Process.findModuleByName("libflutter.so");
        if (module) {
            console.log('[*] Flutter detected, applying flutter-specific bypass...');

            // Hook ssl_crypto_x509_session_verify_cert_chain
            var symbols = Module.enumerateSymbolsSync("libflutter.so");
            for (var i = 0; i < symbols.length; i++) {
                var symbol = symbols[i];
                if (symbol.name.indexOf("ssl_crypto_x509_session_verify_cert_chain") !== -1) {
                    Interceptor.attach(symbol.address, {
                        onEnter: function(args) {},
                        onLeave: function(retval) {
                            retval.replace(0x1);
                        }
                    });
                    console.log('[+] Flutter SSL verification bypassed');
                    break;
                }
            }
        }
    } catch (e) {
        console.log('[-] Flutter bypass failed: ' + e);
    }

    console.log("[*] SSL Pinning Bypass Complete!");
});
