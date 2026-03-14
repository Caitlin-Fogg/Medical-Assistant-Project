# med_assistant/processors.py
import json
import re
from .agents import PlannerAgent, VisionAgent
from .data_sources import MedicineDatabase, SAHPRAProvider, OpenFDAProvider


class MedicalProcessor:
    def __init__(self):
        self.planner_agent = PlannerAgent()
        self.vision_agent = VisionAgent()
        self.database = MedicineDatabase()
        self.sahpra = SAHPRAProvider()
        self.openfda = OpenFDAProvider()

    def _create_vl_fallback_summary(self, vl_data, drug_name):
        """Create a summary directly from VL model data without using planner"""
        summary = self._summarize_med_info(json.dumps(vl_data), drug_name, 'vl_model_raw', vl_data)
        return summary

    def _summarize_med_info(self, source_text, drug_name, source_type='unknown', vl_data=None):
        if not source_text or source_text.strip() in ["No source text provided.", ""]:
            print(f"⚠️ No source text for {source_type}, using VL model fallback")
            return self._create_vl_fallback_summary(vl_data, drug_name)

        try:
            prompt = (
                    f"You are a medical info assistant. Given the following raw authoritative text for '{drug_name}', "
                    "please extract and summarize into clear bullet points with these fields: "
                    "Name, Uses/Indications, Typical Dosage (if present), Common Side Effects, Warnings/Interactions, Source.\n\n"
                    "Raw text:\n" + source_text +
                    "\n\nReturn ONLY valid JSON with keys: name, uses, dosage, side_effects, warnings, source. "
                    "DO NOT add any text before or after the JSON object."
            )

            out = self.planner_agent.chat(prompt)

            if isinstance(out, dict) and "error" in out:
                print(f"❌ Planner returned error for {source_type}, using VL model fallback")
                return self._create_vl_fallback_summary(vl_data, drug_name)

            out_str = str(out).strip()
            start_idx = out_str.find('{')
            end_idx = out_str.rfind('}') + 1

            if start_idx >= 0 and end_idx > start_idx:
                json_str = out_str[start_idx:end_idx]
            else:
                return self._create_vl_fallback_summary(vl_data, drug_name)

            try:
                result = json.loads(json_str)
                result['source'] = source_type
                return result
            except json.JSONDecodeError:
                return self._create_vl_fallback_summary(vl_data, drug_name)

        except Exception:
            return self._create_vl_fallback_summary(vl_data, drug_name)

    def _safe_database_search(self, drug_name, vl_data):
        """Safely search databases with comprehensive error handling and VL fallback"""
        # Local DB search
        if not self.database.df.empty:
            try:
                local = self.database.find_best_match(drug_name)
                if local:
                    print("📊 Found in local database")
                    keys_of_interest = ['uses', 'side_effects', 'reviews', 'benefits', 'adverse_effects']
                    combined = [f"{k}:\n{local[k]}" for k in keys_of_interest if
                                k in local and local[k] and str(local[k]) != 'nan']
                    source_blob = "\n\n".join(combined) if combined else json.dumps(local)
                    summary = self._summarize_med_info(source_blob, drug_name, 'kaggle_dataset', vl_data)
                    if summary.get('source') != 'vl_model_direct':
                        return summary
                    print("⚠️ Local DB processing failed, trying next source...")
            except Exception as e:
                print(f"❌ Local DB search error: {e}")

        # SAHPRA search
        try:
            print("🇿🇦 Searching SAHPRA database...")
            sahpra_content = self.sahpra.search(drug_name)
            if sahpra_content:
                print("✅ Found in SAHPRA database")
                summary = self._summarize_med_info(sahpra_content['content'], drug_name, 'sahpra', vl_data)
                if summary.get('source') != 'vl_model_direct':
                    summary['source_url'] = sahpra_content.get('url', '')
                    return summary
                print("⚠️ SAHPRA processing failed, trying next source...")
        except Exception as e:
            print(f"❌ SAHPRA search error: {e}")

        # OpenFDA search
        try:
            print("🌐 Searching OpenFDA...")
            web_text = self.openfda.fetch_label(drug_name)
            if web_text:
                print("✅ Found in OpenFDA")
                summary = self._summarize_med_info(web_text, drug_name, 'openfda', vl_data)
                if summary.get('source') != 'vl_model_direct':
                    return summary
                print("⚠️ OpenFDA processing failed, using VL model fallback...")
        except Exception as e:
            print(f"❌ OpenFDA search error: {e}")

        # If all external sources failed or returned fallbacks, return VL model data directly
        print("⚠️ Using VL model output as fallback")
        return self._create_vl_fallback_summary(vl_data, drug_name)

    def _is_drug_name_query(self, query):
        query_lower = query.strip().lower()
        words = query_lower.split()
        if len(words) <= 3:
            if any(word in query_lower for word in
                   ['panado', 'paracetamol', 'aspirin', 'ibuprofen', 'viagra', 'insulin', 'metformin']):
                return True

            if re.match(r'^[A-Za-z]+([- ][A-Za-z]+)*$', query.strip()) and len(query.strip()) > 2:
                question_indicators = ['what', 'how', 'when', 'where', 'why', 'can', 'should', 'is', 'are', 'does',
                                       'do']
                if not any(indicator == words[0] for indicator in question_indicators):
                    return True
        return False

    def _process_drug_name_query(self, drug_name):
        print(f"🔍 Processing drug name query: {drug_name}")
        clean_drug_name = drug_name.strip()
        vl_data = {
            "drug_name": clean_drug_name,
            "dosage": "Unknown",
            "manufacturer": "Unknown"
        }
        return self._safe_database_search(clean_drug_name, vl_data)

    def _process_general_medical_query(self, query):
        prompt = (
            f"You are a helpful and reliable medical assistant.\n"
            f"Answer the following user question clearly and accurately:\n\n"
            f"{query}\n\n"
            "If it refers to a drug or medication, include details on its uses, dosage, side effects, "
            "warnings, and interactions if relevant. Provide a structured response that can be easily displayed."
        )

        out = self.planner_agent.chat(prompt)

        if isinstance(out, dict):
            if "error" in out:
                return {"error": out["error"]}
            return out
        elif isinstance(out, str):
            return {
                "response": out.strip(),
                "name": "General Medical Information",
                "source": "planner_model"
            }
        else:
            return {"response": str(out)}

    def process_medication_image(self, image_path):
        import os
        if not os.path.exists(image_path):
            return {"error": f"Image file not found: {image_path}"}

        prompt = (
            "Look at the provided image of a medication package or blister pack. "
            "Extract the drug name (brand or generic), the dosage strength (e.g., 500 mg), "
            "and any manufacturer name you can find. Return ONLY valid JSON with keys: drug_name, dosage, manufacturer."
        )

        print("🔍 Analyzing image with VL model...")
        vl_out_raw = self.vision_agent.extract(image_path, prompt)
        vl_out = self.vision_agent.parse_output(vl_out_raw)
        print("VL output:", vl_out)

        if "error" in vl_out:
            return {"error": f"VL model extraction failed: {vl_out['error']}"}

        drug_name = vl_out.get("drug_name", "").strip()
        if not drug_name:
            return {"error": "VL model did not extract drug name."}

        print(f"💊 Found drug: {drug_name}")
        return self._safe_database_search(drug_name, vl_out)

    def process_query(self, query_text=None, image_path=None):
        try:
            if image_path:
                return self.process_medication_image(image_path)
            elif query_text:
                if self._is_drug_name_query(query_text):
                    return self._process_drug_name_query(query_text)
                else:
                    return self._process_general_medical_query(query_text)
            else:
                return {"error": "No query_text or image_path provided."}
        except Exception as e:
            print(f"❌ process_query error: {e}")
            return {"error": str(e)}