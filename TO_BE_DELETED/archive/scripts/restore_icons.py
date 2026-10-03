import shutil
import os

ARTIFACTS_DIR = r"C:\Users\stati\.gemini\antigravity\brain\d82bcfcf-5a7e-4d6a-ab27-12eaadf0cbd8"
DEST_DIR = r"c:\Users\stati\Desktop\Projects\AlphaHoundGUI\backend\static\icons_backup_premium"

mapping = {
    "history_icon_v2_1765466643855.png": "history.png",
    "settings_icon_1765466563002.png": "settings.png",
    "theme_icon_1765466595188.png": "theme.png",
    "device_icon_1765466680180.png": "device.png",
    "refresh_icon_v2_1765466734785.png": "refresh.png",
    "play_icon_1765466783260.png": "play.png",
    "stop_icon_1765466829931.png": "stop.png",
    "upload_icon_1765466920270.png": "upload.png",
    "pdf_icon_1765466966750.png": "pdf.png",
    "compare_icon_v2_1765467031796.png": "compare.png",
    "analysis_icon_1765467076133.png": "analysis.png",
    "rocket_icon_1765467122237.png": "rocket.png"
}

if not os.path.exists(DEST_DIR):
    os.makedirs(DEST_DIR)

print(f"Restoring icons to {DEST_DIR}...")
for src_name, dest_name in mapping.items():
    src_path = os.path.join(ARTIFACTS_DIR, src_name)
    dest_path = os.path.join(DEST_DIR, dest_name)
    
    if os.path.exists(src_path):
        shutil.copy2(src_path, dest_path)
        print(f"Restored: {dest_name}")
    else:
        print(f"Warning: Source not found: {src_name}")

print("Restoration complete.")
