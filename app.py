import streamlit as st
import os
import json
import base64
import tempfile
from PIL import Image
import io
import vertexai
from vertexai.preview.vision_models import ImageGenerationModel

# --- ページ設定 ---
st.set_page_config(page_title="✨ Magic Image Maker", page_icon="🎨", layout="centered")

# --- CSSで見た目をポップにする ---
st.markdown("""
    <style>
    .stApp {
        background-color: #FFF0F5;
    }
    .stButton>button {
        background-color: #FF69B4;
        color: white;
        font-size: 20px;
        border-radius: 10px;
        border: none;
        width: 100%;
    }
    .stButton>button:hover {
        background-color: #FF1493;
        color: white;
    }
    h1 {
        color: #FF1493;
        font-family: "Arial Rounded MT Bold";
    }
    </style>
    """, unsafe_allow_html=True)

# --- 認証機能 (パスワード確認) ---
def check_password():
    """パスワードが合っているか確認する"""
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False

    if st.session_state.password_correct:
        return True

    st.markdown("### 🔒 パスワードを入力してください")
    password = st.text_input("Password", type="password")
    
    # Secretsからパスワードを取得して照合
    if st.button("ログイン"):
        if password == st.secrets["app_settings"]["app_password"]:
            st.session_state.password_correct = True
            st.rerun()
        else:
            st.error("パスワードが違います 😢")
    return False

# --- Vertex AIのセットアップ ---
def setup_vertex_ai():
    try:
        # SecretsからJSONキー情報を取得して一時ファイルに書き出す
        # (Streamlit Cloudは環境変数をファイルとして持てないためこの工夫が必要です)
        key_info = st.secrets["gcp_service_account"]
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            json.dump(dict(key_info), f)
            key_path = f.name
        
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = key_path
        
        project_id = key_info["project_id"]
        vertexai.init(project=project_id, location="us-central1")
        return ImageGenerationModel.from_pretrained("imagen-3.0-generate-002")
    except Exception as e:
        st.error(f"接続設定エラー: {e}")
        return None

# --- 画像生成ロジック ---
def generate_image(model, prompt, brighten_flg):
    final_prompt = prompt
    if brighten_flg:
         # 元のコードにあった補正ロジック
        if "--ar 16:9" in final_prompt:
             final_prompt = final_prompt.replace("--ar 16:9", "bright daylight, high-key lighting --ar 16:9")
        else:
             final_prompt += " bright daylight, high-key lighting"
    
    try:
        instances = [{"prompt": final_prompt}]
        parameters = {
            "sampleCount": 1, 
            "safetySetting": "block_only_high",
            "personGeneration": "allow_all", 
            "includeRaiReason": True,
            "baseSteps": 100, 
            "aspectRatio": "16:9"
        }
        
        response = model._endpoint.predict(instances=instances, parameters=parameters)
        
        if response.predictions:
            for pred in response.predictions:
                if "bytesBase64Encoded" in pred:
                    image_data = base64.b64decode(pred["bytesBase64Encoded"])
                    return image_data
    except Exception as e:
        st.error(f"生成エラー: {e}")
    return None

# ==========================================
# ★ メイン処理 ★
# ==========================================
if check_password():
    st.title("🎨 Magic Image Maker")
    st.markdown("外注さん専用 画像生成ツールへようこそ！")

    # モデルの準備
    model = setup_vertex_ai()

    # 入力エリア
    with st.container():
        prompt = st.text_area("どんな画像を作りますか？ (プロンプト入力)", height=100, placeholder="例: 猫が宇宙でラーメンを食べている")
        
        brighten = st.checkbox("☀️ 明るくキレイに補正する", value=True)
        
        generate_btn = st.button("💖 画像を作る (Generate)")

    # 生成処理
    if generate_btn and prompt and model:
        with st.spinner("AIが一生懸命描いています... 🎨"):
            img_bytes = generate_image(model, prompt, brighten)
            
            if img_bytes:
                # 画像を表示
                image = Image.open(io.BytesIO(img_bytes))
                st.image(image, caption="生成された画像", use_container_width=True)
                
                # ダウンロードボタン
                st.download_button(
                    label="📥 画像をダウンロード",
                    data=img_bytes,
                    file_name="generated_image.png",
                    mime="image/png"
                )
                st.success("✨ 完成しました！")