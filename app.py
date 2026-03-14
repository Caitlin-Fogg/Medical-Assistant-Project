# app.py
import streamlit as st
import os, tempfile
from med_assistant.processors import MedicalProcessor
from med_assistant.utils import format_medication_response, save_chat_to_disk, load_chat_from_disk, list_stored_chats

# ----------------------------
# 🎨 PAGE CONFIG
# ----------------------------
st.set_page_config(page_title="Medical Assistant 💊", page_icon="💬", layout="wide")

# ----------------------------
# 📂 INITIALIZATION
# ----------------------------
@st.cache_resource
def get_processor():
    return MedicalProcessor()

processor = get_processor()
CHAT_DIR = "chats"
os.makedirs(CHAT_DIR, exist_ok=True)

# ----------------------------
# 💬 SESSION STATE
# ----------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []

if "last_uploaded_file" not in st.session_state:
    st.session_state.last_uploaded_file = None

# ----------------------------
# 💬 SIDEBAR
# ----------------------------
st.sidebar.title("💊 Medical Assistant")

if st.sidebar.button("🆕 New Chat"):
    st.session_state.messages = []
    st.session_state.last_uploaded_file = None
    st.rerun()

st.sidebar.markdown("### 📂 Stored Chats")
stored = list_stored_chats(CHAT_DIR)
if stored:
    selected = st.sidebar.selectbox("Load previous chat", ["Select..."] + stored)
    if selected != "Select...":
        loaded_messages = load_chat_from_disk(selected, CHAT_DIR)
        if loaded_messages:
            st.session_state.messages = loaded_messages
            st.session_state.last_uploaded_file = None
            st.sidebar.info(f"Loaded chat: {selected}")
else:
    st.sidebar.write("No stored chats yet.")

if st.sidebar.button("💾 Save Current Chat"):
    filename = save_chat_to_disk(st.session_state.messages, CHAT_DIR)
    if filename:
        st.sidebar.success(f"Chat saved as {filename}")

st.sidebar.markdown("---")
st.sidebar.caption("Built with ❤️ using Streamlit and your LM Studio models")

# ----------------------------
# 💬 MAIN CHAT INTERFACE
# ----------------------------
st.title("💬 Medical Assistant")

# Display chat messages
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["type"] == "text":
            st.markdown(msg["content"])
        elif msg["type"] == "image":
            st.image(msg["content"], caption="Uploaded Image", use_container_width=True)

# ----------------------------
# ➕ ATTACHMENT / CAMERA MENU
# ----------------------------
st.markdown("---")
col1, col2, col3 = st.columns([0.1, 0.8, 0.1])

with col1:
    with st.popover("➕", width="stretch"):
        st.markdown("#### Add to chat")
        option = st.radio("Choose input type", ["Upload Image", "Take Picture"])
        uploaded_file = None

        if option == "Upload Image":
            uploaded_file = st.file_uploader("Upload an image", type=["png", "jpg", "jpeg"], key="upload_img")
        elif option == "Take Picture":
            uploaded_file = st.camera_input("Take a picture", key="camera_img")

        if uploaded_file is not None:
            current_file_id = f"{uploaded_file.name}_{uploaded_file.size}"
            if current_file_id != st.session_state.get("last_uploaded_file"):
                st.session_state.last_uploaded_file = current_file_id
                image_bytes = uploaded_file.getvalue()

                with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
                    tmp.write(image_bytes)
                    tmp_path = tmp.name

                st.session_state.messages.append({
                    "role": "user",
                    "type": "image",
                    "content": image_bytes,
                    "temp_path": tmp_path,
                    "processed": False
                })
                st.rerun()

# ----------------------------
# 🧠 PROCESS TEXT INPUT
# ----------------------------
with col2:
    user_prompt = st.chat_input("Ask your medical question...")

if user_prompt:
    st.session_state.messages.append({"role": "user", "type": "text", "content": user_prompt})

    with st.chat_message("user"):
        st.markdown(user_prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            response = processor.process_query(query_text=user_prompt)
            reply = format_medication_response(response)
            st.markdown(reply)

    st.session_state.messages.append({"role": "assistant", "type": "text", "content": reply})
    st.rerun()

# ----------------------------
# 📸 PROCESS IMAGE QUERIES
# ----------------------------
unprocessed_images = [
    (i, msg) for i, msg in enumerate(st.session_state.messages)
    if msg["role"] == "user" and msg["type"] == "image" and not msg.get("processed")
]

if unprocessed_images:
    idx, msg = unprocessed_images[0]
    st.session_state.messages[idx]["processed"] = True

    with st.chat_message("assistant"):
        with st.spinner("Processing image..."):
            response = processor.process_query(image_path=msg["temp_path"])
            reply = format_medication_response(response)
            st.markdown(reply)

    st.session_state.messages.append({"role": "assistant", "type": "text", "content": reply})

    # Clean up temporary file
    try:
        if "temp_path" in msg and os.path.exists(msg["temp_path"]):
            os.remove(msg["temp_path"])
            if "temp_path" in st.session_state.messages[idx]:
                del st.session_state.messages[idx]["temp_path"]
    except Exception as e:
        print(f"Warning: Could not delete temp file: {e}")

    st.rerun()