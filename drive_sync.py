"""
drive_sync.py
=============
Sync fail (CSV master, laporan JSON/MD) ke Google Drive sebagai depo pusat,
supaya content creator & CEO boleh terus buka dari Drive tanpa perlu masuk GitHub.

SETUP (buat SEKALI sahaja):
1. Pergi ke https://console.cloud.google.com -> buat/pilih projek
2. Enable "Google Drive API"
3. Buat Service Account (IAM & Admin -> Service Accounts -> Create)
4. Muat turun kunci JSON (Keys -> Add Key -> JSON) -> simpan sebagai
   `service_account.json` (JANGAN commit fail ini ke GitHub - letak dalam
   .gitignore, dan simpan sebagai secret di Railway/GitHub Actions)
5. Buat folder di Google Drive untuk depo, kongsi (Share) folder itu kepada
   email service account (format: xxxx@xxxx.iam.gserviceaccount.com) dengan
   akses "Editor"
6. Salin Folder ID daripada URL Drive
   (https://drive.google.com/drive/folders/<FOLDER_ID>)
7. Set environment variables:
   - GOOGLE_SERVICE_ACCOUNT_JSON  (isi kandungan JSON, atau path ke fail)
   - GDRIVE_FOLDER_ID             (Folder ID dari langkah 6)

Kos: Google Drive API - percuma untuk penggunaan biasa (quota harian sangat
tinggi untuk kegunaan sebegini kecil).
"""

import os
import json
import io

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def get_drive_service():
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON tidak ditetapkan")

    # Boleh terima sama ada path ke fail, atau isi JSON terus dalam env var
    if os.path.exists(raw):
        creds = service_account.Credentials.from_service_account_file(raw, scopes=SCOPES)
    else:
        info = json.loads(raw)
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)

    return build("drive", "v3", credentials=creds)


def find_file_id(service, folder_id, filename):
    """Cari sama ada fail dengan nama sama sudah wujud dalam folder (untuk update, bukan duplicate)."""
    query = f"'{folder_id}' in parents and name = '{filename}' and trashed = false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])
    return files[0]["id"] if files else None


def upload_file(local_path, folder_id=None, mimetype=None):
    """Upload (atau update jika sudah wujud) satu fail ke Google Drive folder."""
    service = get_drive_service()
    folder_id = folder_id or os.environ.get("GDRIVE_FOLDER_ID")
    if not folder_id:
        raise RuntimeError("GDRIVE_FOLDER_ID tidak ditetapkan")

    filename = os.path.basename(local_path)
    media = MediaFileUpload(local_path, mimetype=mimetype, resumable=True)

    existing_id = find_file_id(service, folder_id, filename)
    if existing_id:
        file = service.files().update(fileId=existing_id, media_body=media).execute()
        print(f"🔄 Dikemaskini di Drive: {filename}")
    else:
        metadata = {"name": filename, "parents": [folder_id]}
        file = service.files().create(body=metadata, media_body=media, fields="id").execute()
        print(f"⬆️ Dimuat naik ke Drive: {filename}")

    return file.get("id")


def sync_files(paths, folder_id=None):
    """Upload beberapa fail sekali gus (contoh: CSV master + laporan JSON + laporan MD)."""
    results = {}
    for p in paths:
        if os.path.exists(p):
            results[p] = upload_file(p, folder_id=folder_id)
        else:
            print(f"⚠️ Fail tidak dijumpai, dilangkau: {p}")
    return results


if __name__ == "__main__":
    import sys
    files_to_sync = sys.argv[1:]
    if not files_to_sync:
        print("Guna: python3 drive_sync.py <fail1> <fail2> ...")
        sys.exit(1)
    sync_files(files_to_sync)
