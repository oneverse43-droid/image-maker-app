import streamlit as st
import os
import json
import base64
import tempfile
import datetime
import io
import csv
from PIL import Image

# Vertex AI & Google Drive Libraries
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
    """SecretsからJSON文字列を読み込み、辞書として返す"""
    try:
        json_str = st.secrets["gcp"]["service_account_json"]
        return json.loads(json_str)
    except Exception as e:
        st.error(f"Secret読み込みエラー: {e}")
        return None

def authenticate_user():
    """ユーザーログイン処理"""
    if "logged_in_user" not in st.session_state:
        st.session_state.logged_in_user = None

    if st.session_state.logged_in_user:
        return True

    st.markdown("### 🔒 ログインしてください")
    
    # ユーザーリストをSecretsから取得
    users = st.secrets["app_users"]
    
    col1, col2 = st.columns(2)
    with col1:
        username = st.text_input("ユーザー名 (例: sato)")
    with col2:
        password = st.text_input("パスワード", type="password")

    if st.button("ログイン"):
        if username in users and users[username] == password:
            st.session_state.logged_in_user = username
            st.success(f"ようこそ、{username} さん！")
            st.rerun()
        else:
            st.error("ユーザー名かパスワードが違います")
    return False

# --- Google Drive 連携 ---
def save_to_drive(image_bytes, prompt, username):
    """画像をドライブに保存し、ログを更新する"""
    try:
        creds_info = get_service_account_info()
        creds = service_account.Credentials.from_service_account_info(
            creds_info, scopes=['https://www.googleapis.com/auth/drive']
        )
        service = build('drive', 'v3', credentials=creds)
        folder_id = st.secrets["app_settings"]["drive_folder_id"]

        # 1. 画像ファイル名を作成 (日時_ユーザー名.png)
        now_str = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        file_name = f"{now_str}_{username}.png"

        # 2. 画像をアップロード
        file_metadata = {'name': file_name, 'parents': [folder_id]}
        media = MediaIoBaseUpload(io.BytesIO(image_bytes), mimetype='image/png')
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        
        # 3. ログファイル (usage_log.csv) を更新
        update_log_file(service, folder_id, username, prompt, file_name)
        
        return True
    except Exception as e:
        st.error(f"Google Drive保存エラー: {e}")
        return False

def update_log_file(service, folder_id, username, prompt, image_filename):
    """Drive上のCSVログに追記する"""
    log_filename = "usage_log.csv"
    
    # 既存のログファイルを探す
    results = service.files().list(
        q=f"name='{log_filename}' and '{folder_id}' in parents and trashed=false",
        fields="files(id, name)").execute()
    items = results.get('files', [])

    # 今のデータ行
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    new_row = [timestamp, username, image_filename, prompt]
    
    csv_content = ""
    file_id = None

    if not items:
        # 新規作成
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Timestamp", "User", "ImageFile", "Prompt"]) # ヘッダー
        writer.writerow(new_row)
        csv_content = output.getvalue()
        
        metadata = {'name': log_filename, 'parents': [folder_id], 'mimeType': 'text/csv'}
        media = MediaIoBaseUpload(io.BytesIO(csv_content.encode('utf-8')), mimetype='text/csv')
        service.files().create(body=metadata, media_body=media).execute()
    else:
        # 追記 (既存ファイルをダウンロード -> 追記 -> アップデート)
        file_id = items[0]['id']
        request = service.files().get_media(fileId=file_id)
        downloaded = request.execute().decode('utf-8')
        
        output = io.StringIO()
        output.write(downloaded)
        writer = csv.writer(output)
        writer.writerow(new_row)
        csv_content = output.getvalue()
        
        media = MediaIoBaseUpload(io.BytesIO(csv_content.encode('utf-8')), mimetype='text/csv')
        service.files().update(fileId=file_id, media_body=media).execute()

# --- 画像生成 ---
def generate_image(prompt, brighten_flg):
    try:
        creds_info = get_service_account_info()
        
        # Vertex AI 初期化
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            json.dump(creds_info, f)
            key_path = f.name
        
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = key_path
        vertexai.init(project=creds_info["project_id"], location="us-central1")
        model = ImageGenerationModel.from_pretrained("imagen-3.0-generate-002")
        
        # プロンプト補正
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
        generate_btn = st.button("🚀 画像を作成 & ドライブ保存")

    if generate_btn and prompt:
        with st.spinner("AIが描画中... その後ドライブに保存します..."):
            img_bytes = generate_image(prompt, brighten)
            
            if img_bytes:
                # 画面表示
                st.image(Image.open(io.BytesIO(img_bytes)), caption="生成結果", use_container_width=True)
                
                # ドライブ保存 & ログ記録
                if save_to_drive(img_bytes, prompt, user):
                    st.success(f"✅ Googleドライブに保存しました！ (担当: {user})")
                
                # 手元へのダウンロード用
                st.download_button("📥 今すぐダウンロード", data=img_bytes, file_name="image.png", mime="image/png")
