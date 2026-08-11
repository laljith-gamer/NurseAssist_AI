import re
from typing import Any, Dict, List, Tuple, Optional
from dataclasses import dataclass
import unicodedata


@dataclass
class PreprocessedInput:
    original: str
    normalized: str
    tokens: List[str]
    numbers: List[Tuple[str, float]]
    medical_terms: List[str]
    abbreviations_expanded: Dict[str, str]
    is_question: bool
    is_command: bool
    language_code: str


class TextPreprocessor:
    def __init__(self):
        self.medical_abbreviations = self._load_medical_abbreviations()
        self.number_words = self._load_number_words()
        self.unit_mappings = self._load_unit_mappings()
        self.stop_words = self._load_stop_words()
    
    def _load_medical_abbreviations(self) -> Dict[str, str]:
        return {
            "bp": "blood pressure",
            "b.p.": "blood pressure",
            "hr": "heart rate",
            "h.r.": "heart rate",
            "rr": "respiratory rate",
            "r.r.": "respiratory rate",
            "temp": "temperature",
            "spo2": "oxygen saturation",
            "sp02": "oxygen saturation",
            "o2 sat": "oxygen saturation",
            "o2sat": "oxygen saturation",
            "wt": "weight",
            "ht": "height",
            "bpm": "beats per minute",
            "mg": "milligrams",
            "mcg": "micrograms",
            "ml": "milliliters",
            "po": "by mouth",
            "iv": "intravenous",
            "im": "intramuscular",
            "sc": "subcutaneous",
            "sq": "subcutaneous",
            "sl": "sublingual",
            "prn": "as needed",
            "bid": "twice daily",
            "tid": "three times daily",
            "qid": "four times daily",
            "qd": "once daily",
            "qh": "every hour",
            "q4h": "every 4 hours",
            "q6h": "every 6 hours",
            "q8h": "every 8 hours",
            "q12h": "every 12 hours",
            "ac": "before meals",
            "pc": "after meals",
            "hs": "at bedtime",
            "stat": "immediately",
            "npo": "nothing by mouth",
            "hx": "history",
            "dx": "diagnosis",
            "tx": "treatment",
            "rx": "prescription",
            "sx": "symptoms",
            "pt": "patient",
            "pts": "patients",
            "yo": "years old",
            "y/o": "years old",
            "c/o": "complaining of",
            "s/p": "status post",
            "w/": "with",
            "w/o": "without",
            "sob": "shortness of breath",
            "cp": "chest pain",
            "abd": "abdominal",
            "gi": "gastrointestinal",
            "gu": "genitourinary",
            "neuro": "neurological",
            "psych": "psychiatric",
            "ortho": "orthopedic",
            "cva": "cerebrovascular accident",
            "mi": "myocardial infarction",
            "chf": "congestive heart failure",
            "copd": "chronic obstructive pulmonary disease",
            "dm": "diabetes mellitus",
            "htn": "hypertension",
            "afib": "atrial fibrillation",
            "a-fib": "atrial fibrillation",
            "dvt": "deep vein thrombosis",
            "pe": "pulmonary embolism",
            "uti": "urinary tract infection",
            "uri": "upper respiratory infection",
            "cad": "coronary artery disease",
            "ckd": "chronic kidney disease",
            "esrd": "end stage renal disease",
            "bun": "blood urea nitrogen",
            "cr": "creatinine",
            "hgb": "hemoglobin",
            "hct": "hematocrit",
            "plt": "platelets",
            "wbc": "white blood cells",
            "rbc": "red blood cells",
            "ekg": "electrocardiogram",
            "ecg": "electrocardiogram",
            "cxr": "chest x-ray",
            "ct": "computed tomography",
            "mri": "magnetic resonance imaging",
            "us": "ultrasound",
            "bs": "blood sugar",
            "bg": "blood glucose",
            "fs": "finger stick",
            "accucheck": "blood glucose check",
        }
    
    def _load_number_words(self) -> Dict[str, int]:
        return {
            "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
            "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
            "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
            "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
            "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
            "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
            "eighty": 80, "ninety": 90, "hundred": 100
        }
    
    def _load_unit_mappings(self) -> Dict[str, str]:
        return {
            "milligrams": "mg",
            "milligram": "mg",
            "micrograms": "mcg",
            "microgram": "mcg",
            "milliliters": "ml",
            "milliliter": "ml",
            "liters": "L",
            "liter": "L",
            "grams": "g",
            "gram": "g",
            "kilograms": "kg",
            "kilogram": "kg",
            "pounds": "lbs",
            "pound": "lbs",
            "ounces": "oz",
            "ounce": "oz",
            "inches": "in",
            "inch": "in",
            "feet": "ft",
            "foot": "ft",
            "centimeters": "cm",
            "centimeter": "cm",
            "meters": "m",
            "meter": "m",
            "fahrenheit": "F",
            "celsius": "C",
            "centigrade": "C",
            "beats per minute": "bpm",
            "breaths per minute": "/min",
            "percent": "%",
            "percentage": "%",
        }
    
    def _load_stop_words(self) -> set:
        return {
            "a", "an", "the", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "must", "shall",
            "can", "need", "dare", "ought", "used", "to", "of", "in",
            "for", "on", "with", "at", "by", "from", "as", "into",
            "through", "during", "before", "after", "above", "below",
            "between", "under", "again", "further", "then", "once",
            "here", "there", "when", "where", "why", "how", "all",
            "each", "few", "more", "most", "other", "some", "such",
            "no", "nor", "not", "only", "own", "same", "so", "than",
            "too", "very", "just", "also"
        }
    
    def preprocess(self, text: str) -> PreprocessedInput:
        original = text
        
        normalized = self._normalize_unicode(text)
        normalized = self._normalize_whitespace(normalized)
        normalized = self._normalize_punctuation(normalized)
        
        is_question = self._detect_question(normalized)
        is_command = self._detect_command(normalized)
        
        numbers = self._extract_numbers(normalized)
        
        normalized, expansions = self._expand_abbreviations(normalized)
        
        normalized = self._convert_number_words(normalized)
        
        normalized = self._normalize_units(normalized)
        
        tokens = self._tokenize(normalized)
        
        medical_terms = self._extract_medical_terms(tokens)
        
        return PreprocessedInput(
            original=original,
            normalized=normalized.strip(),
            tokens=tokens,
            numbers=numbers,
            medical_terms=medical_terms,
            abbreviations_expanded=expansions,
            is_question=is_question,
            is_command=is_command,
            language_code="en"
        )
    
    def _normalize_unicode(self, text: str) -> str:
        text = unicodedata.normalize("NFKC", text)
        text = text.encode("ascii", "ignore").decode("ascii")
        return text
    
    def _normalize_whitespace(self, text: str) -> str:
        text = re.sub(r"\s+", " ", text)
        return text.strip()
    
    def _normalize_punctuation(self, text: str) -> str:
        text = re.sub(r"[\"'`]", "'", text)
        text = re.sub(r"[\u2013\u2014]", "-", text)
        text = re.sub(r"\.{2,}", ".", text)
        return text
    
    def _detect_question(self, text: str) -> bool:
        if text.rstrip().endswith("?"):
            return True
        
        question_starters = [
            "what", "why", "how", "when", "where", "who", "which",
            "is", "are", "was", "were", "do", "does", "did",
            "can", "could", "would", "should", "will", "shall"
        ]
        
        first_word = text.lower().split()[0] if text.split() else ""
        return first_word in question_starters
    
    def _detect_command(self, text: str) -> bool:
        command_starters = [
            "save", "cancel", "undo", "clear", "delete", "remove",
            "add", "update", "set", "record", "log", "enter",
            "show", "display", "list", "get", "fetch", "load",
            "select", "choose", "pick", "switch", "open", "close",
            "start", "stop", "pause", "resume", "refresh", "sync",
            "help", "exit", "quit"
        ]
        
        first_word = text.lower().split()[0] if text.split() else ""
        return first_word in command_starters
    
    def _extract_numbers(self, text: str) -> List[Tuple[str, float]]:
        numbers = []
        
        bp_pattern = r"(\d{2,3})\s*[/\\]\s*(\d{2,3})"
        for match in re.finditer(bp_pattern, text):
            numbers.append((match.group(0), float(match.group(1))))
            numbers.append((match.group(0), float(match.group(2))))
        
        decimal_pattern = r"(?<![/\\])(\d+\.?\d*)"
        for match in re.finditer(decimal_pattern, text):
            value = match.group(1)
            if not any(value in n[0] for n in numbers):
                try:
                    numbers.append((value, float(value)))
                except ValueError:
                    pass
        
        return numbers
    
    def _expand_abbreviations(self, text: str) -> Tuple[str, Dict[str, str]]:
        expansions = {}
        result = text
        
        sorted_abbrevs = sorted(
            self.medical_abbreviations.items(),
            key=lambda x: len(x[0]),
            reverse=True
        )
        
        for abbrev, expansion in sorted_abbrevs:
            if re.search(r"\W", abbrev):
                pattern = re.escape(abbrev)
            else:
                pattern = r"\b" + re.escape(abbrev) + r"\b"
            if re.search(pattern, result, re.IGNORECASE):
                expansions[abbrev] = expansion
                result = re.sub(pattern, expansion, result, flags=re.IGNORECASE)
        
        return result, expansions
    
    def _convert_number_words(self, text: str) -> str:
        result = text.lower()
        
        for word, value in sorted(
            self.number_words.items(),
            key=lambda x: len(x[0]),
            reverse=True
        ):
            pattern = r"\b" + word + r"\b"
            result = re.sub(pattern, str(value), result, flags=re.IGNORECASE)
        
        return result
    
    def _normalize_units(self, text: str) -> str:
        result = text
        
        for full_unit, abbrev in self.unit_mappings.items():
            pattern = r"\b" + re.escape(full_unit) + r"\b"
            result = re.sub(pattern, abbrev, result, flags=re.IGNORECASE)
        
        return result
    
    def _tokenize(self, text: str) -> List[str]:
        text = re.sub(r"([^\w\s./])", r" \1 ", text)
        tokens = text.split()
        return [t for t in tokens if t]
    
    def _extract_medical_terms(self, tokens: List[str]) -> List[str]:
        medical_terms = []
        
        known_terms = set(self.medical_abbreviations.keys())
        known_terms.update(self.medical_abbreviations.values())
        
        medication_suffixes = [
            "pril", "sartan", "olol", "pine", "statin", "prazole",
            "tidine", "azole", "cillin", "mycin", "cycline", "floxacin",
            "mab", "nib", "zumab", "ximab"
        ]
        
        for token in tokens:
            token_lower = token.lower()
            
            if token_lower in known_terms:
                medical_terms.append(token_lower)
                continue
            
            for suffix in medication_suffixes:
                if token_lower.endswith(suffix):
                    medical_terms.append(token_lower)
                    break
        
        return medical_terms
