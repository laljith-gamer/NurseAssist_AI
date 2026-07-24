from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass
import json

from database.models import UserPreference, get_engine
from sqlmodel import Session, select


@dataclass
class UserPreferences:
    user_id: str
    display_name: Optional[str]
    voice_enabled: bool
    notification_sound: bool
    theme: str
    vital_display_format: str
    default_view: str
    quick_phrases: List[str]


class PreferenceEngine:
    def __init__(self):
        self.engine = get_engine()
        self.default_preferences = {
            "voice_enabled": True,
            "notification_sound": True,
            "theme": "light",
            "vital_display_format": "detailed",
            "default_view": "dashboard",
            "quick_phrases": []
        }
        
        self.vital_display_formats = {
            "compact": {
                "show_units": False,
                "show_trends": False,
                "decimal_places": 0
            },
            "standard": {
                "show_units": True,
                "show_trends": True,
                "decimal_places": 1
            },
            "detailed": {
                "show_units": True,
                "show_trends": True,
                "show_delta": True,
                "show_baseline": True,
                "decimal_places": 2
            }
        }
    
    def get_preferences(self, user_id: str) -> UserPreferences:
        with Session(self.engine) as session:
            statement = select(UserPreference).where(
                UserPreference.user_id == user_id
            )
            pref = session.exec(statement).first()
            
            if pref:
                quick_phrases = []
                if pref.quick_phrases:
                    try:
                        quick_phrases = json.loads(pref.quick_phrases)
                    except json.JSONDecodeError:
                        pass
                
                return UserPreferences(
                    user_id=pref.user_id,
                    display_name=pref.display_name,
                    voice_enabled=pref.voice_enabled,
                    notification_sound=pref.notification_sound,
                    theme=pref.theme,
                    vital_display_format=pref.vital_display_format,
                    default_view=pref.default_view,
                    quick_phrases=quick_phrases
                )
            
            return UserPreferences(
                user_id=user_id,
                display_name=None,
                voice_enabled=self.default_preferences["voice_enabled"],
                notification_sound=self.default_preferences["notification_sound"],
                theme=self.default_preferences["theme"],
                vital_display_format=self.default_preferences["vital_display_format"],
                default_view=self.default_preferences["default_view"],
                quick_phrases=self.default_preferences["quick_phrases"]
            )
    
    def save_preferences(self, user_id: str, preferences: Dict) -> UserPreferences:
        with Session(self.engine) as session:
            statement = select(UserPreference).where(
                UserPreference.user_id == user_id
            )
            existing = session.exec(statement).first()
            
            if existing:
                for key, value in preferences.items():
                    if key == "quick_phrases" and isinstance(value, list):
                        value = json.dumps(value)
                    if hasattr(existing, key):
                        setattr(existing, key, value)
                existing.updated_at = datetime.utcnow()
                session.add(existing)
            else:
                quick_phrases = preferences.get("quick_phrases", [])
                if isinstance(quick_phrases, list):
                    quick_phrases = json.dumps(quick_phrases)
                
                new_pref = UserPreference(
                    user_id=user_id,
                    display_name=preferences.get("display_name"),
                    voice_enabled=preferences.get("voice_enabled", True),
                    notification_sound=preferences.get("notification_sound", True),
                    theme=preferences.get("theme", "light"),
                    vital_display_format=preferences.get("vital_display_format", "detailed"),
                    default_view=preferences.get("default_view", "dashboard"),
                    quick_phrases=quick_phrases
                )
                session.add(new_pref)
            
            session.commit()
        
        return self.get_preferences(user_id)
    
    def update_preference(
        self, 
        user_id: str, 
        key: str, 
        value: Any
    ) -> UserPreferences:
        current = self.get_preferences(user_id)
        
        updates = {
            "display_name": current.display_name,
            "voice_enabled": current.voice_enabled,
            "notification_sound": current.notification_sound,
            "theme": current.theme,
            "vital_display_format": current.vital_display_format,
            "default_view": current.default_view,
            "quick_phrases": current.quick_phrases
        }
        
        updates[key] = value
        
        return self.save_preferences(user_id, updates)
    
    def add_quick_phrase(self, user_id: str, phrase: str) -> UserPreferences:
        prefs = self.get_preferences(user_id)
        
        if phrase not in prefs.quick_phrases:
            prefs.quick_phrases.append(phrase)
            return self.save_preferences(user_id, {
                "quick_phrases": prefs.quick_phrases
            })
        
        return prefs
    
    def remove_quick_phrase(self, user_id: str, phrase: str) -> UserPreferences:
        prefs = self.get_preferences(user_id)
        
        if phrase in prefs.quick_phrases:
            prefs.quick_phrases.remove(phrase)
            return self.save_preferences(user_id, {
                "quick_phrases": prefs.quick_phrases
            })
        
        return prefs
    
    def get_vital_display_config(self, user_id: str) -> Dict:
        prefs = self.get_preferences(user_id)
        format_name = prefs.vital_display_format
        
        return self.vital_display_formats.get(
            format_name, 
            self.vital_display_formats["detailed"]
        )
    
    def get_default_quick_phrases(self) -> List[str]:
        return [
            "BP 120/80",
            "HR 72",
            "Temp 98.6",
            "SpO2 98",
            "Vitals stable",
            "Patient resting comfortably",
            "No acute distress",
            "Lungs clear bilateral",
            "Heart regular rate rhythm",
            "Abdomen soft non-tender"
        ]
    
    def format_vital_value(
        self,
        vital_type: str,
        value: float,
        user_id: str
    ) -> str:
        config = self.get_vital_display_config(user_id)
        
        decimal_places = config.get("decimal_places", 1)
        show_units = config.get("show_units", True)
        
        units = {
            "bp_systolic": "mmHg",
            "bp_diastolic": "mmHg",
            "heart_rate": "bpm",
            "temperature": "C",
            "spo2": "%",
            "respiratory_rate": "/min",
            "weight": "kg",
            "glucose": "mg/dL"
        }
        
        if decimal_places == 0:
            formatted_value = str(int(round(value)))
        else:
            formatted_value = f"{value:.{decimal_places}f}"
        
        if show_units and vital_type in units:
            return f"{formatted_value} {units[vital_type]}"
        
        return formatted_value
    
    def format_vital_with_delta(
        self,
        vital_type: str,
        current_value: float,
        previous_value: Optional[float],
        user_id: str
    ) -> Dict:
        config = self.get_vital_display_config(user_id)
        
        result = {
            "formatted": self.format_vital_value(vital_type, current_value, user_id),
            "value": current_value
        }
        
        if config.get("show_delta") and previous_value is not None:
            delta = current_value - previous_value
            delta_sign = "+" if delta > 0 else ""
            result["delta"] = f"{delta_sign}{delta:.1f}"
            result["delta_value"] = delta
        
        if config.get("show_trends") and previous_value is not None:
            if current_value > previous_value:
                result["trend"] = "increasing"
            elif current_value < previous_value:
                result["trend"] = "decreasing"
            else:
                result["trend"] = "stable"
        
        return result
    
    def get_theme_config(self, user_id: str) -> Dict:
        prefs = self.get_preferences(user_id)
        
        themes = {
            "light": {
                "background": "#ffffff",
                "foreground": "#1a1a2e",
                "primary": "#3b82f6",
                "secondary": "#64748b",
                "success": "#22c55e",
                "warning": "#f59e0b",
                "danger": "#ef4444",
                "card_bg": "#f8fafc"
            },
            "dark": {
                "background": "#1a1a2e",
                "foreground": "#e2e8f0",
                "primary": "#60a5fa",
                "secondary": "#94a3b8",
                "success": "#4ade80",
                "warning": "#fbbf24",
                "danger": "#f87171",
                "card_bg": "#16213e"
            },
            "clinical": {
                "background": "#f0f9ff",
                "foreground": "#0f172a",
                "primary": "#0284c7",
                "secondary": "#475569",
                "success": "#16a34a",
                "warning": "#d97706",
                "danger": "#dc2626",
                "card_bg": "#ffffff"
            }
        }
        
        return themes.get(prefs.theme, themes["light"])
    
    def to_dict(self, prefs: UserPreferences) -> Dict:
        return {
            "user_id": prefs.user_id,
            "display_name": prefs.display_name,
            "voice_enabled": prefs.voice_enabled,
            "notification_sound": prefs.notification_sound,
            "theme": prefs.theme,
            "vital_display_format": prefs.vital_display_format,
            "default_view": prefs.default_view,
            "quick_phrases": prefs.quick_phrases
        }