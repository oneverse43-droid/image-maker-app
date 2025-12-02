import streamlit as st
import os
import json
import base64
import tempfile
import datetime
import io
from PIL import Image

# Vertex AI & Google APIs
import vertexai
from vertexai.preview.vision_models import ImageGenerationModel
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# --- ページ設定 ---
st.set_page_config(page_title="Work Space", page_icon="🎨", layout="centered")

# --- CSS設定 ---
st.markdown("""
    <style>
    .stApp { background-color: #f0f2f6; }
    h1 { color: #333; }
    .stButton>button {
        background-color: #4CAF50; color: white; border-radius: 8px; font-size: 18px; width: 100%;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 認証 & サービスアカウント準備 ---
def get_service_account_info():
    try:
        json_str = st.secrets["gcp"]["service_account_json"]
        return json.loads(json_str)
    except Exception as e:
        st.error(f"Secret読み込みエラー: {e}")
        return None

def authenticate_user():
    if "logged_in_user" not in st.session_state:
        st.session_state.logged_in_user = None

    if st.session_state.logged_in_user:
        return True

    st.markdown("### 🔒 ログインしてください")
    users = st.secrets["app_users"]
    col1, col2 = st.columns(2)
    with col1:
        username = st.text_input("ユーザー名")
    with col2:
        password = st.text_input("パスワード", type="password")

    if st.button("ログイン"):
        if username in users and users[username] == password:
            st.session_state.logged_in_user = username
            st.success(f"ようこそ、{username} さん！")
            st.rerun()
        else:
            st.error("認証失敗")
    return False

# --- Google Drive & Sheets 連携 ---
def save_data(image_bytes, prompt, username):
    """
    1. 画像をDrive(共有ドライブ)に保存
    2. ログをSpreadsheetに追記
    """
    try:
        creds_info = get_service_account_info()
        # DriveとSheets両方の権限を持たせる
        scopes = [
            'https://www.googleapis.com/auth/drive',
            'https://www.googleapis.com/auth/spreadsheets'
        ]
        creds = service_account.Credentials.from_service_account_info(creds_info, scopes=scopes)
        
        # --- 1. Driveに画像を保存 ---
        drive_service = build('drive', 'v3', credentials=creds)
        folder_id = st.secrets["app_settings"]["drive_folder_id"]
        
        now = datetime.datetime.now()
        timestamp_str = now.strftime('%Y-%m-%d %H:%M:%S')
        file_name = f"{now.strftime('%Y%m%d_%H%M%S')}_{username}.png"

        file_metadata = {'name': file_name, 'parents': [folder_id]}
        media = MediaIoBaseUpload(io.BytesIO(image_bytes), mimetype='image/png')
        
        drive_service.files().create(
            body=file_metadata, 
            media_body=media, 
            supportsAllDrives=True
        ).execute()

        # --- 2. Spreadsheetにログを追記 ---
        sheet_service = build('sheets', 'v4', credentials=creds)
        spreadsheet_id = st.secrets["app_settings"]["spreadsheet_id"]
        
        # 書き込むデータ [日時, ユーザー, ファイル名, プロンプト]
        # 日付を集計しやすいように、A列は "2023/10/01" のような形式で入れます
        row_data = [[timestamp_str, username, file_name, prompt]]
        
        body = {'values': row_data}
        
        sheet_service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range="log!A:D",      # "log"というシート名のA列〜D列に追加
            valueInputOption="USER_ENTERED",
            body=body
        ).execute()
        
        return True

    except Exception as e:
        st.error(f"保存エラー: {e}")
        return False

# --- 画像生成 ---
def generate_image(prompt, brighten_flg):
    try:
        creds_info = get_service_account_info()
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            json.dump(creds_info, f)
            key_path = f.name
        
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = key_path
        vertexai.init(project=creds_info["project_id"], location="us-central1")
        model = ImageGenerationModel.from_pretrained("imagen-3.0-generate-002")
        
        final_prompt = prompt
        if brighten_flg:
            if "--ar 16:9" in final_prompt:
                 final_prompt = final_prompt.replace("--ar 16:9", "bright daylight, high-key lighting --ar 16:9")
            else:
                 final_prompt += " bright daylight, high-key lighting"

        instances = [{"prompt": final_prompt}]
        parameters = {
            "sampleCount": 1, 
            "safetySetting": "block_only_high",
            "personGeneration": "allow_all", 
            "aspectRatio": "16:9"
        }
        
        response = model._endpoint.predict(instances=instances, parameters=parameters)
        if response.predictions:
            for pred in response.predictions:
                if "bytesBase64Encoded" in pred:
                    return base64.b64decode(pred["bytesBase64Encoded"])
    except Exception as e:
        st.error(f"生成エラー: {e}")
    return None

# ==========================================
# ★ メイン処理 ★
# ==========================================
if authenticate_user():
    user = st.session_state.logged_in_user
    st.title(f"🎨 画像生成ツール ({user})")

    with st.container():
        prompt = st.text_area("プロンプトを入力", height=100)
        brighten = st.checkbox("☀️ 明るく補正", value=True)
        generate_btn = st.button("🚀 画像を作成 & 記録")

    if generate_btn and prompt:
        with st.spinner("AIが描画中... ドライブと管理表に保存します..."):
            img_bytes = generate_image(prompt, brighten)
            
            if img_bytes:
                st.image(Image.open(io.BytesIO(img_bytes)), caption="生成結果", use_container_width=True)
                
                if save_data(img_bytes, prompt, user):
                    st.success(f"✅ 保存完了！スプレッドシートに記録しました (担当: {user})")
                
                st.download_button("📥 ダウンロード", data=img_bytes, file_name="image.png", mime="image/png")
