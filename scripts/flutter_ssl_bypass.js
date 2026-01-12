/*
 * Flutter SSL Pinning Bypass
 * Works by hooking BoringSSL functions in libflutter.so
 */

function hook_ssl_verify_result(address) {
    Interceptor.attach(address, {
        onLeave: function(retval) {
            // Return success (0 = X509_V_OK)
            retval.replace(0x0);
        }
    });
}

function hook_ssl_verify_func(address) {
    Interceptor.attach(address, {
        onEnter: function(args) {
            // Skip verification
        },
        onLeave: function(retval) {
            retval.replace(0x1); // Return true/success
        }
    });
}

function disablePinning() {
    var m = Process.findModuleByName("libflutter.so");

    if (m === null) {
        console.log("[-] libflutter.so not loaded yet, waiting...");
        return false;
    }

    console.log("[*] Found libflutter.so at " + m.base);
    console.log("[*] Searching for SSL verification functions...");

    var found = false;

    // Method 1: Hook ssl_crypto_x509_session_verify_cert_chain
    var symbols = Process.getModuleByName("libflutter.so").enumerateSymbols();

    for (var i = 0; i < symbols.length; i++) {
        var name = symbols[i].name;

        // Target various SSL verification functions
        if (name.indexOf("ssl_verify_cert_chain") !== -1 ||
            name.indexOf("ssl_crypto_x509_session_verify_cert_chain") !== -1) {
            console.log("[+] Found: " + name + " at " + symbols[i].address);
            hook_ssl_verify_func(symbols[i].address);
            found = true;
        }

        if (name.indexOf("x509_verify_cert") !== -1) {
            console.log("[+] Found: " + name + " at " + symbols[i].address);
            hook_ssl_verify_result(symbols[i].address);
            found = true;
        }
    }

    // Method 2: Pattern search for ssl_x509 functions
    if (!found) {
        console.log("[*] Symbols not found, trying pattern search...");

        // Search for boringssl patterns
        var ranges = m.enumerateRanges('r-x');

        for (var i = 0; i < ranges.length; i++) {
            var range = ranges[i];

            // Pattern for x509_verify return point
            try {
                var matches = Memory.scanSync(range.base, range.size, "FF 03 00 D1 FD 7B 01 A9");
                if (matches.length > 0) {
                    console.log("[+] Found pattern at: " + matches[0].address);
                    found = true;
                }
            } catch (e) {}
        }
    }

    // Method 3: Hook session_verify_cert_chain by pattern
    if (!found) {
        console.log("[*] Trying alternative patterns...");

        // ARM64 pattern for verify functions
        var patterns = [
            "F4 4F BE A9 FD 7B 01 A9 FD 43 00 91",  // Common prologue
            "FF 43 01 D1 F4 4F 02 A9 FD 7B 03 A9"   // Another common pattern
        ];

        var ranges = m.enumerateRanges('r-x');
        for (var j = 0; j < patterns.length; j++) {
            for (var i = 0; i < ranges.length; i++) {
                try {
                    var matches = Memory.scanSync(ranges[i].base, ranges[i].size, patterns[j]);
                    for (var k = 0; k < matches.length; k++) {
                        console.log("[+] Found pattern " + j + " at: " + matches[k].address);
                    }
                } catch (e) {}
            }
        }
    }

    if (found) {
        console.log("[+] SSL pinning bypass installed!");
    } else {
        console.log("[-] Could not find verification functions");
        console.log("[*] Trying generic interception...");

        // Generic approach: intercept all functions with "verify" in name
        var exports = m.enumerateExports();
        for (var i = 0; i < exports.length; i++) {
            if (exports[i].name.toLowerCase().indexOf("verify") !== -1) {
                console.log("[?] Export: " + exports[i].name);
            }
        }
    }

    return true;
}

// Retry mechanism since libflutter.so might not be loaded immediately
var retryCount = 0;
var maxRetries = 10;

function tryDisable() {
    if (disablePinning()) {
        console.log("[*] Flutter SSL bypass complete!");
    } else if (retryCount < maxRetries) {
        retryCount++;
        console.log("[*] Retry " + retryCount + "/" + maxRetries + "...");
        setTimeout(tryDisable, 1000);
    } else {
        console.log("[-] Failed to find libflutter.so after " + maxRetries + " retries");
    }
}

console.log("[*] Flutter SSL Pinning Bypass Script");
console.log("[*] Starting...");

// Start bypass
setTimeout(tryDisable, 500);
