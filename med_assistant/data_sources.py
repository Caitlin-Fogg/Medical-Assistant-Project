# med_assistant/data_sources.py
import pandas as pd
import difflib
import requests
from bs4 import BeautifulSoup
import re
import PyPDF2
import io


class MedicineDatabase:
    def __init__(self, csv_path="medicine_db.csv"):
        self.csv_path = csv_path
        self.df = self._load_data()

    def _load_data(self):
        try:
            df = pd.read_csv(self.csv_path)
            df.columns = [c.strip() for c in df.columns]
            return df
        except Exception as e:
            print(f"❌ Error loading medicine database: {e}")
            return pd.DataFrame()

    def find_best_match(self, drug_name, threshold=0.7):
        if not drug_name or not isinstance(drug_name, str) or self.df.empty:
            return None

        drug_name_clean = drug_name.strip().lower()
        text_cols = [c for c in self.df.columns if self.df[c].dtype == object]

        # Exact match search
        for col in text_cols:
            try:
                res = self.df[self.df[col].str.contains(drug_name_clean, case=False, na=False)]
                if not res.empty:
                    return res.iloc[0].to_dict()
            except Exception:
                continue

        # Fuzzy match search
        candidate_cols = ['drug_name', 'drug', 'DrugName', 'name', 'Name', 'medicine']
        cols_to_try = [c for c in candidate_cols if c in self.df.columns] or text_cols[:3]

        names = []
        for c in cols_to_try:
            try:
                names.extend(self.df[c].dropna().astype(str).tolist())
            except Exception:
                continue

        matches = difflib.get_close_matches(drug_name_clean, names, n=1, cutoff=threshold)
        if matches:
            match = matches[0]
            for col in cols_to_try:
                try:
                    row = self.df[self.df[col].astype(str).str.lower() == match.lower()]
                    if not row.empty:
                        return row.iloc[0].to_dict()
                except Exception:
                    continue
        return None


class SAHPRAProvider:
    def __init__(self, base_url="https://pi-pil-repository.sahpra.org.za"):
        self.base_url = base_url

    def _extract_medicine_sections(self, text):
        text = re.sub(r'\r\n|\r', '\n', text)
        lines = [line.strip() for line in text.split('\n') if line.strip()]

        headings_map = {
            'uses': [
                r'what.*is.*used for', r'uses?', r'indications?',
                r'therapeutic.*indications', r'clinical.*uses',
                r'purpose', r'treatment of', r'for the.*of'
            ],
            'side_effects': [
                r'side\s*effects', r'adverse\s*effects', r'adverse\s*reactions',
                r'possible side effects', r'unwanted effects', r'undesirable effects',
                r'undesirable.*reactions', r'tolerability'
            ],
            'dosage': [
                r'dosage', r'dose', r'doses', r'how to take', r'administration',
                r'dosology', r'method of administration',
                r'directions for use', r'dosage and directions for use',
                r'recommended.*dose', r'recommended.*doses', r'dosage.*recommendation',
                r'dosage and administration'
            ],
            'warnings': [
                r'warnings', r'precautions', r'special warnings',
                r'important safety information', r'safety information',
                r'warning.*precaution', r'precautions.*warning'
            ],
            'contraindications': [
                r'contraindications', r'do not take', r'who should not take',
                r'should not.*use', r'must not.*take'
            ],
            'interactions': [
                r'drug interactions', r'interactions', r'interaction with',
                r'concomitant.*use', r'other.*medicines'
            ]
        }

        sections = {k: '' for k in headings_map}
        current_section = None
        buffer = []

        for i, line in enumerate(lines):
            line_lower = line.lower()
            line_clean = re.sub(r'[^a-zA-Z\s]', '', line_lower)

            is_likely_header = (
                    len(line) < 100 and
                    any(word in line_lower for word in ['use', 'effect', 'warning', 'dose', 'interaction']) or
                    line.isupper() or
                    line_lower in ['warnings and precautions', 'side effects', 'dosage and administration']
            )

            matched = False
            if is_likely_header:
                for section, patterns in headings_map.items():
                    for pat in patterns:
                        if re.search(pat, line_lower) or re.search(pat, line_clean):
                            if current_section and buffer:
                                sections[current_section] = ' '.join(buffer).strip()
                            current_section = section
                            buffer = []
                            matched = True
                            break
                    if matched:
                        break

            if not matched and current_section:
                if len(line) > 3 and not line.isdigit():
                    buffer.append(line)

        if current_section and buffer:
            sections[current_section] = ' '.join(buffer).strip()

        return sections

    def _extract_from_pdf(self, pdf_url, drug_name):
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(pdf_url, headers=headers, timeout=15)
            if response.status_code != 200:
                return None

            pdf_file = io.BytesIO(response.content)
            pdf_reader = PyPDF2.PdfReader(pdf_file)

            full_text = ""
            for page in pdf_reader.pages:
                full_text += page.extract_text() + "\n"

            if not full_text.strip():
                return None

            sections = self._extract_medicine_sections(full_text)

            formatted_content = []
            for k in ['uses', 'dosage', 'side_effects', 'warnings', 'contraindications']:
                if sections.get(k):
                    formatted_content.append(f"{k.upper()}:\n{sections[k]}")

            return {
                'source': 'sahpra_pdf',
                'content': "\n\n".join(formatted_content),
                'url': pdf_url,
                'sections': sections
            }

        except Exception as e:
            print(f"❌ PDF extraction error: {e}")
            return None

    def search(self, drug_name):
        try:
            search_terms = drug_name.split()
            primary_term = search_terms[0]
            search_url = f"{self.base_url}/?s={primary_term}"
            headers = {'User-Agent': 'Mozilla/5.0'}

            response = requests.get(search_url, headers=headers, timeout=15)
            if response.status_code != 200:
                return None

            soup = BeautifulSoup(response.content, 'html.parser')
            results = []

            for link in soup.find_all('a', href=True):
                link_text = link.get_text().lower()
                href = link['href']
                if any(term.lower() in link_text for term in search_terms):
                    if href.endswith('.pdf') or 'pil' in href.lower() or 'pi' in href.lower():
                        results.append({'title': link.get_text().strip(),
                                        'url': href if href.startswith('http') else f"{self.base_url}{href}",
                                        'type': 'pdf'})
                    else:
                        results.append({'title': link.get_text().strip(),
                                        'url': href if href.startswith('http') else f"{self.base_url}{href}",
                                        'type': 'page'})

            if results:
                results.sort(key=lambda x: sum(1 for term in search_terms if term.lower() in x['title'].lower()),
                             reverse=True)
                best_result = results[0]
                return self._extract_from_pdf(best_result['url'], drug_name)

            return None

        except Exception as e:
            print(f"❌ SAHPRA search error: {e}")
            return None


class OpenFDAProvider:
    def fetch_label(self, drug_name):
        if not drug_name:
            return None
        try:
            clean_name = drug_name.split()[0]
            url = f'https://api.fda.gov/drug/label.json?search=openfda.brand_name:"{clean_name}"&limit=1'
            r = requests.get(url, timeout=8)
            if r.status_code == 200:
                j = r.json()
                if 'results' in j and j['results']:
                    res = j['results'][0]
                    parts = []
                    for key in ['indications_and_usage', 'dosage_and_administration', 'adverse_reactions',
                                'contraindications', 'warnings_and_cautions']:
                        if key in res:
                            if isinstance(res[key], list):
                                parts.append(f"{key.replace('_', ' ').title()}:\n" + "\n".join(res[key]))
                            else:
                                parts.append(f"{key.replace('_', ' ').title()}:\n{res[key]}")
                    return "\n\n".join(parts).strip()
        except Exception as e:
            print("OpenFDA fetch error:", e)
        return None