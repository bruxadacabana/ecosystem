// ============================================================
//  HUB — commands/notify.rs
//  Notificações nativas do SO via tauri-plugin-notification.
//  Chamado pelo frontend quando detecta eventos relevantes
//  (app offline, LOGOS saturado, etc.).
// ============================================================

use crate::error::AppError;
use tauri_plugin_notification::NotificationExt;

#[tauri::command]
pub fn send_notification(
    app: tauri::AppHandle,
    title: String,
    body: String,
) -> Result<(), AppError> {
    app.notification()
        .builder()
        .title(&title)
        .body(&body)
        .show()
        .map_err(|e| AppError::Io(e.to_string()))
}
