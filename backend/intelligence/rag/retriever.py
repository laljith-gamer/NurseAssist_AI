from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import os
import hashlib
from datetime import datetime

from config import settings


@dataclass
class RetrievedDocument:
    content: str
    metadata: Dict
    score: float
    source: str


class RAGRetriever:
    def __init__(self):
        self.vector_store = None
        self.embeddings = None
        self._initialize_store()
    
    def _initialize_store(self):
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings
            
            self.client = chromadb.PersistentClient(
                path=str(settings.VECTOR_STORE_PATH),
                settings=ChromaSettings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            
            self.collection = self.client.get_or_create_collection(
                name="clinical_knowledge",
                metadata={"hnsw:space": "cosine"}
            )
            
            self._seed_clinical_knowledge()
            
        except ImportError:
            self.client = None
            self.collection = None
    
    def _seed_clinical_knowledge(self):
        if self.collection is None:
            return
        
        existing = self.collection.count()
        if existing > 0:
            return
        
        clinical_documents = [
            {
                "content": "Blood pressure classification according to JNC-8 guidelines: Normal BP is less than 120/80 mmHg. Elevated BP is 120-129/<80 mmHg. Hypertension Stage 1 is 130-139/80-89 mmHg. Hypertension Stage 2 is 140+/90+ mmHg. Hypertensive crisis is greater than 180/120 mmHg requiring immediate medical attention.",
                "metadata": {"type": "guideline", "topic": "blood_pressure", "source": "JNC-8"}
            },
            {
                "content": "Heart rate normal ranges: Adults resting heart rate 60-100 bpm. Bradycardia is less than 60 bpm. Tachycardia is greater than 100 bpm. Athletes may have normal resting rates of 40-60 bpm. Factors affecting heart rate include medications, fever, anxiety, and physical activity.",
                "metadata": {"type": "reference", "topic": "heart_rate", "source": "AHA"}
            },
            {
                "content": "Oxygen saturation (SpO2) interpretation: Normal SpO2 is 95-100%. Mild hypoxemia is 91-94%. Moderate hypoxemia is 86-90%. Severe hypoxemia is less than 85%. Supplemental oxygen should be considered when SpO2 falls below 92% in most patients.",
                "metadata": {"type": "guideline", "topic": "oxygen_saturation", "source": "Clinical Guidelines"}
            },
            {
                "content": "Temperature assessment: Normal body temperature ranges from 36.1-37.2 C (97-99 F). Fever is defined as temperature above 38 C (100.4 F). Hypothermia is below 35 C (95 F). Hyperthermia or heat stroke is above 40 C (104 F).",
                "metadata": {"type": "reference", "topic": "temperature", "source": "Clinical Standards"}
            },
            {
                "content": "Respiratory rate normal values: Adults 12-20 breaths per minute. Tachypnea is greater than 20/min. Bradypnea is less than 12/min. Respiratory rate is a sensitive indicator of patient deterioration and should be monitored regularly.",
                "metadata": {"type": "reference", "topic": "respiratory_rate", "source": "Clinical Standards"}
            },
            {
                "content": "Blood glucose targets for hospitalized patients: General ward patients target 140-180 mg/dL. ICU patients target 140-180 mg/dL. Hypoglycemia is less than 70 mg/dL. Severe hypoglycemia is less than 54 mg/dL. Hyperglycemia greater than 180 mg/dL may require insulin adjustment.",
                "metadata": {"type": "guideline", "topic": "glucose", "source": "ADA Guidelines"}
            },
            {
                "content": "Medication administration best practices: Verify patient identity using two identifiers. Check allergies before administration. Verify right patient, right drug, right dose, right route, right time. Document administration immediately after giving medication.",
                "metadata": {"type": "protocol", "topic": "medication_safety", "source": "ISMP"}
            },
            {
                "content": "Pain assessment scale: 0 indicates no pain. 1-3 is mild pain. 4-6 is moderate pain. 7-10 is severe pain. Pain should be reassessed after intervention within 30-60 minutes for oral medications and 15-30 minutes for IV medications.",
                "metadata": {"type": "reference", "topic": "pain_assessment", "source": "Clinical Standards"}
            },
            {
                "content": "Fall risk assessment factors: History of falls, gait instability, use of sedatives or hypnotics, urinary frequency, cognitive impairment, age over 65. High-risk patients require fall precautions including bed alarm, non-slip footwear, and frequent monitoring.",
                "metadata": {"type": "protocol", "topic": "fall_prevention", "source": "Safety Guidelines"}
            },
            {
                "content": "Early warning signs of patient deterioration: Respiratory rate changes, oxygen saturation decrease, heart rate changes, blood pressure changes, altered mental status, decreased urine output. These signs require immediate nursing assessment and potential rapid response activation.",
                "metadata": {"type": "protocol", "topic": "patient_safety", "source": "Clinical Guidelines"}
            },
            {
                "content": "ACE inhibitor medications include lisinopril, enalapril, ramipril, and benazepril. Common side effects include dry cough, hyperkalemia, and angioedema. Contraindicated in pregnancy. Monitor potassium and renal function.",
                "metadata": {"type": "medication", "topic": "ace_inhibitors", "source": "Pharmacology Reference"}
            },
            {
                "content": "Beta blocker medications include metoprolol, atenolol, carvedilol, and propranolol. Used for hypertension, heart failure, and arrhythmias. Side effects include bradycardia, fatigue, and bronchospasm. Do not stop abruptly.",
                "metadata": {"type": "medication", "topic": "beta_blockers", "source": "Pharmacology Reference"}
            },
            {
                "content": "Insulin administration: Rapid-acting insulin (lispro, aspart) onset 15-30 minutes. Short-acting regular insulin onset 30-60 minutes. Intermediate NPH onset 1-2 hours. Long-acting (glargine, detemir) onset 1-2 hours with 24-hour duration.",
                "metadata": {"type": "medication", "topic": "insulin", "source": "Pharmacology Reference"}
            },
            {
                "content": "Anticoagulation with warfarin: Target INR typically 2-3 for most indications. INR above 4 increases bleeding risk. Vitamin K foods affect levels. Multiple drug interactions exist. Monitor for signs of bleeding.",
                "metadata": {"type": "medication", "topic": "anticoagulation", "source": "Clinical Guidelines"}
            },
            {
                "content": "Diuretic medications: Loop diuretics (furosemide) for fluid overload. Monitor potassium, may cause hypokalemia. Thiazides (hydrochlorothiazide) for hypertension. Potassium-sparing (spironolactone) preserves potassium.",
                "metadata": {"type": "medication", "topic": "diuretics", "source": "Pharmacology Reference"}
            },
        ]
        
        ids = []
        documents = []
        metadatas = []
        
        for i, doc in enumerate(clinical_documents):
            doc_id = hashlib.md5(doc["content"].encode()).hexdigest()[:12]
            ids.append(doc_id)
            documents.append(doc["content"])
            metadatas.append(doc["metadata"])
        
        self.collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas
        )
    
    def retrieve(
        self,
        query: str,
        top_k: int = None,
        filter_metadata: Optional[Dict] = None
    ) -> List[RetrievedDocument]:
        if self.collection is None:
            return self._fallback_retrieve(query)
        
        top_k = top_k or settings.RAG_TOP_K
        
        try:
            where_filter = None
            if filter_metadata:
                where_filter = filter_metadata
            
            results = self.collection.query(
                query_texts=[query],
                n_results=top_k,
                where=where_filter
            )
            
            documents = []
            
            if results and results["documents"] and results["documents"][0]:
                for i, doc in enumerate(results["documents"][0]):
                    metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                    distance = results["distances"][0][i] if results["distances"] else 0
                    
                    score = 1 - distance
                    
                    if score >= settings.RAG_SIMILARITY_THRESHOLD:
                        documents.append(RetrievedDocument(
                            content=doc,
                            metadata=metadata,
                            score=score,
                            source=metadata.get("source", "unknown")
                        ))
            
            return documents
            
        except Exception:
            return self._fallback_retrieve(query)
    
    def _fallback_retrieve(self, query: str) -> List[RetrievedDocument]:
        query_lower = query.lower()
        
        fallback_knowledge = {
            "blood pressure": "Blood pressure classification: Normal <120/80, Elevated 120-129/<80, Stage 1 HTN 130-139/80-89, Stage 2 HTN >=140/90, Crisis >180/120.",
            "hypertension": "Blood pressure classification: Normal <120/80, Elevated 120-129/<80, Stage 1 HTN 130-139/80-89, Stage 2 HTN >=140/90, Crisis >180/120.",
            "heart rate": "Heart rate ranges: Normal 60-100 bpm, Bradycardia <60 bpm, Tachycardia >100 bpm.",
            "oxygen": "SpO2 ranges: Normal 95-100%, Mild hypoxemia 91-94%, Moderate 86-90%, Severe <85%.",
            "temperature": "Temperature: Normal 36.1-37.2C, Fever >38C, Hypothermia <35C.",
            "glucose": "Blood glucose: Target 140-180 mg/dL, Hypoglycemia <70 mg/dL, Severe <54 mg/dL.",
            "medication": "Medication safety: Verify patient, drug, dose, route, time. Check allergies. Document immediately.",
        }
        
        results = []
        for key, content in fallback_knowledge.items():
            if key in query_lower:
                results.append(RetrievedDocument(
                    content=content,
                    metadata={"type": "fallback", "topic": key},
                    score=0.8,
                    source="built-in"
                ))
        
        return results[:3]
    
    def add_document(
        self,
        content: str,
        metadata: Dict,
        doc_id: Optional[str] = None
    ) -> str:
        if self.collection is None:
            return ""
        
        if doc_id is None:
            doc_id = hashlib.md5(content.encode()).hexdigest()[:12]
        
        self.collection.add(
            ids=[doc_id],
            documents=[content],
            metadatas=[metadata]
        )
        
        return doc_id
    
    def add_patient_note(
        self,
        patient_id: str,
        note_content: str,
        note_type: str = "progress_note"
    ) -> str:
        metadata = {
            "type": "patient_note",
            "patient_id": patient_id,
            "note_type": note_type,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return self.add_document(note_content, metadata)
    
    def retrieve_patient_context(
        self,
        patient_id: str,
        query: str,
        top_k: int = 3
    ) -> List[RetrievedDocument]:
        return self.retrieve(
            query=query,
            top_k=top_k,
            filter_metadata={"patient_id": patient_id}
        )
    
    def get_relevant_guidelines(
        self,
        topic: str,
        top_k: int = 3
    ) -> List[RetrievedDocument]:
        return self.retrieve(
            query=topic,
            top_k=top_k,
            filter_metadata={"type": "guideline"}
        )
    
    def get_medication_info(
        self,
        medication_name: str
    ) -> List[RetrievedDocument]:
        return self.retrieve(
            query=f"{medication_name} medication information",
            top_k=3,
            filter_metadata={"type": "medication"}
        )
    
    def delete_document(self, doc_id: str) -> bool:
        if self.collection is None:
            return False
        
        try:
            self.collection.delete(ids=[doc_id])
            return True
        except Exception:
            return False
    
    def get_collection_stats(self) -> Dict:
        if self.collection is None:
            return {"status": "unavailable", "count": 0}
        
        return {
            "status": "available",
            "count": self.collection.count(),
            "name": self.collection.name
        }