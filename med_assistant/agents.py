# med_assistant/agents.py
import requests
import json
import re
import base64

class PlannerAgent:
    def __init__(self, model_name="qwen2.5-7b-instruct", base_url="http://127.0.0.1:1234/v1"):
        self.model_name = model_name
        self.base_url = base_url

    def chat(self, prompt):
        try:
            payload = {
                "model": self.model_name,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 2000,
                "temperature": 0.1
            }

            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=180
            )

            if response.status_code != 200:
                return {"error": f"HTTP {response.status_code}: {response.text}"}

            result = response.json()
            return result["choices"][0]["message"]["content"]

        except Exception as e:
            print("❌ Planner model error:", e)
            return {"error": str(e)}


class VisionAgent:
    def __init__(self, model_name="qwen2.5-vl-3b-instruct", base_url="http://127.0.0.1:1234/v1"):
        self.model_name = model_name
        self.base_url = base_url

    def extract(self, image_path, prompt_text):
        try:
            with open(image_path, "rb") as image_file:
                base64_image = base64.b64encode(image_file.read()).decode('utf-8')

            payload = {
                "model": self.model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt_text},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                        ]
                    }
                ],
                "max_tokens": 2000
            }

            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=180
            )

            if response.status_code != 200:
                return {"error": f"HTTP {response.status_code}: {response.text}"}

            result = response.json()
            resp_text = result["choices"][0]["message"]["content"] if result.get("choices") else ""

            try:
                return json.loads(resp_text)
            except Exception:
                return {"drug_name": resp_text.strip()}

        except Exception as e:
            print("❌ VL model error:", e)
            return {"error": str(e)}

    def parse_output(self, vl_out):
        """Parse the VL model output to extract JSON inside markdown code blocks or plain JSON."""
        if isinstance(vl_out, dict):
            if "error" in vl_out:
                return vl_out
            if all(k in vl_out for k in ("drug_name", "dosage", "manufacturer")):
                return vl_out
            vl_out_raw = vl_out.get("drug_name", "")
        else:
            vl_out_raw = str(vl_out)

        vl_out_raw = re.sub(r"```json|```", "", vl_out_raw, flags=re.IGNORECASE).strip()

        try:
            parsed = json.loads(vl_out_raw)
            return parsed if isinstance(parsed, dict) else {"drug_name": vl_out_raw}
        except Exception:
            return {"drug_name": vl_out_raw}