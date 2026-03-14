# med_assistant/utils.py
import json
import os
import base64
from datetime import datetime


def save_chat_to_disk(messages, chat_dir="chats"):
    """Save current session chat to a JSON file in /chats"""
    if not messages:
        return None

    # Create a serializable copy of messages
    serializable_messages = []

    for msg in messages:
        serializable_msg = msg.copy()  # Create a copy to avoid modifying original

        # Handle image messages - convert bytes to base64 string for JSON
        if msg["type"] == "image" and isinstance(msg.get("content"), bytes):
            # Convert image bytes to base64 string for JSON storage
            serializable_msg["content"] = base64.b64encode(msg["content"]).decode('utf-8')
            serializable_msg["content_type"] = "image_base64"  # Mark as encoded

        # Remove temporary file paths that can't be serialized
        if "temp_path" in serializable_msg:
            del serializable_msg["temp_path"]

        serializable_messages.append(serializable_msg)

    os.makedirs(chat_dir, exist_ok=True)
    filename = datetime.now().strftime("%Y-%m-%d_%H-%M-%S.json")
    path = os.path.join(chat_dir, filename)

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(serializable_messages, f, ensure_ascii=False, indent=2)
        return filename
    except Exception as e:
        print(f"❌ Error saving chat: {e}")
        return None


def load_chat_from_disk(filename, chat_dir="chats"):
    """Load a stored chat from disk"""
    path = os.path.join(chat_dir, filename)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                messages = json.load(f)

            # Convert base64 images back to bytes
            for msg in messages:
                if msg.get("content_type") == "image_base64" and msg["type"] == "image":
                    # Convert base64 string back to bytes
                    msg["content"] = base64.b64decode(msg["content"])
                    # Remove the marker since we've converted back to bytes
                    del msg["content_type"]

            return messages
        except Exception as e:
            print(f"❌ Error loading chat: {e}")
            return None
    return None


def list_stored_chats(chat_dir="chats"):
    """Return a sorted list of stored chat files"""
    if not os.path.exists(chat_dir):
        return []
    files = [f for f in os.listdir(chat_dir) if f.endswith(".json")]
    return sorted(files, reverse=True)


def format_medication_response(response):
    """Format medication response into user-friendly display (same for text and image queries)"""
    if isinstance(response, dict):
        if "error" in response:
            return f"⚠️ {response['error']}"
        elif "response" in response:
            return response["response"]
        else:
            reply_parts = []
            name = response.get("name")
            uses = response.get("uses", [])
            dosage = response.get("dosage")
            side_effects = response.get("side_effects", [])
            warnings = response.get("warnings", [])
            source = response.get("source", "")
            source_url = response.get("source_url", "")

            if name:
                reply_parts.append(f"💊 **{name}**")
            if uses:
                if isinstance(uses, list):
                    reply_parts.append("**Uses:**\n- " + "\n- ".join(uses))
                else:
                    reply_parts.append(f"**Uses:** {uses}")
            if dosage:
                if isinstance(dosage, list):
                    dosage = ", ".join(dosage)
                elif isinstance(dosage, dict):
                    dosage = "\n- ".join([f"{k.replace('_', ' ').title()}: {v}" for k, v in dosage.items()])
                reply_parts.append(f"**Dosage:** {dosage}")
            if side_effects:
                if isinstance(side_effects, list):
                    reply_parts.append("**Side Effects:**\n- " + "\n- ".join(side_effects))
                else:
                    reply_parts.append(f"**Side Effects:** {side_effects}")
            if warnings:
                if isinstance(warnings, list):
                    reply_parts.append("**Warnings:**\n- " + "\n- ".join(warnings))
                else:
                    reply_parts.append(f"**Warnings:** {warnings}")
            if source_url:
                reply_parts.append(f"**Source:** {source_url}")
            elif source:
                reply_parts.append(f"**Source:** {source}")

            if reply_parts:
                return "\n\n".join([p for p in reply_parts if p])
            else:
                return json.dumps(response, indent=2, ensure_ascii=False)
    else:
        return str(response)