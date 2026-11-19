use std::fs;

/// exFAT drives (this repo's home) create AppleDouble `._*` files whenever a
/// file is written. Tauri's capability loader reads every file in
/// `capabilities/` and refuses the binary ones, so clear them before building.
fn clean_appledouble(dir: &str) {
    if let Ok(entries) = fs::read_dir(dir) {
        for entry in entries.flatten() {
            let name = entry.file_name();
            if name.to_string_lossy().starts_with("._") {
                let _ = fs::remove_file(entry.path());
            }
        }
    }
}

fn main() {
    clean_appledouble("capabilities");
    clean_appledouble("icons");
    tauri_build::build()
}