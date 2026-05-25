fn main() {
    tauri_build::build();

    // On Windows, the test binary imports TaskDialogIndirect from comctl32.dll.
    // Without a manifest requesting ComCtl32 v6, Windows loads comctl32 v5.82 which
    // lacks that function, causing STATUS_ENTRYPOINT_NOT_FOUND at test startup.
    //
    // Fix: delay-load comctl32.dll so imports are only resolved on first actual call.
    // Tests never call TaskDialogIndirect, so the DLL is never loaded and the missing
    // export is never encountered. For hub.exe the Tauri manifest activates v6 before
    // any dialog code runs, so delay-loading is safe there too.
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("windows") {
        println!("cargo:rustc-link-arg=/DELAYLOAD:comctl32.dll");
        println!("cargo:rustc-link-arg=delayimp.lib");
    }
}
