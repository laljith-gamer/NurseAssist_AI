from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class PromptTemplate:
    name: str
    system_prompt: str
    user_template: str
    requires_context: bool
    requires_docs: bool


class PromptTemplates:
    def __init__(self):
        self.templates = self._load_templates()
    
    def _load_templates(self) -> Dict[str, PromptTemplate]:
        return {
            "clinical_assistant": PromptTemplate(
                name="clinical_assistant",
                system_prompt="""You are an advanced, natural-sounding clinical nursing assistant AI. You help nurses manage up to 100,000 patients dynamically.

Core Guidelines:
1. Speak Naturally: Talk in a user-friendly, natural, and helpful tone (e.g., "Sure, I've noted that down for you!" or "I can help with that.").
2. Take Notes & Summarize: Actively summarize the context and take concise notes based on the user's input.
3. Warn & Alert: Scrutinize the clinical context (like abnormal vitals or drug interactions) and EXPLICITLY WARN the user if there is a safety risk.
4. Accuracy: Ensure all medical advice is evidence-based and prioritize patient safety. Keep responses concise but comprehensive.""",
                user_template="""
{context}

Relevant Clinical Information:
{retrieved_docs}

Question: {query}

Provide a helpful, clinically-appropriate response:""",
                requires_context=False,
                requires_docs=False
            ),
            
            "patient_summary": PromptTemplate(
                name="patient_summary",
                system_prompt="""You are a clinical documentation assistant. Generate concise patient summaries following SBAR format (Situation, Background, Assessment, Recommendation).

Guidelines:
- Be factual and objective
- Highlight critical findings
- Note trends and changes
- Keep summary under 200 words
- Use standard abbreviations appropriately""",
                user_template="""
Patient Information:
{context}

{retrieved_docs}

Generate a clinical summary:""",
                requires_context=True,
                requires_docs=False
            ),
            
            "trend_analysis": PromptTemplate(
                name="trend_analysis",
                system_prompt="""You are a clinical data analyst. Analyze vital sign trends and provide clinical interpretation.

Guidelines:
- Identify significant patterns
- Note concerning trends early
- Compare to normal ranges
- Suggest monitoring frequency
- Flag values requiring intervention""",
                user_template="""
Clinical Data:
{context}

{retrieved_docs}

Analysis Request: {query}

Provide trend analysis:""",
                requires_context=True,
                requires_docs=False
            ),
            
            "clinical_qa": PromptTemplate(
                name="clinical_qa",
                system_prompt="""You are a clinical knowledge assistant. Answer questions about medications, procedures, and patient care.

Guidelines:
- Cite guidelines when applicable
- Provide practical information
- Include safety considerations
- Acknowledge uncertainty when appropriate
- Recommend verification for critical information""",
                user_template="""
Patient Context:
{context}

Reference Information:
{retrieved_docs}

Question: {query}

Answer:""",
                requires_context=False,
                requires_docs=True
            ),
            
            "medication_check": PromptTemplate(
                name="medication_check",
                system_prompt="""You are a medication safety assistant. Help verify medication appropriateness and identify potential issues.

Guidelines:
- Check for common interactions
- Verify dosing ranges
- Note allergies and contraindications
- Highlight high-alert medications
- Always recommend pharmacist verification for concerns""",
                user_template="""
Patient Information:
{context}

Current Medications and Allergies:
{retrieved_docs}

Query: {query}

Medication Safety Assessment:""",
                requires_context=True,
                requires_docs=True
            ),
            
            "handoff_report": PromptTemplate(
                name="handoff_report",
                system_prompt="""You are a shift handoff assistant. Generate structured handoff reports for nursing shift changes.

Use I-PASS format:
- Illness severity
- Patient summary
- Action list
- Situation awareness
- Synthesis by receiver

Keep reports concise but comprehensive.""",
                user_template="""
Patient Data:
{context}

Recent Events:
{retrieved_docs}

Generate shift handoff report:""",
                requires_context=True,
                requires_docs=True
            ),
            
            "vital_interpretation": PromptTemplate(
                name="vital_interpretation",
                system_prompt="""You are a vital signs interpretation assistant. Help interpret vital sign readings in clinical context.

Guidelines:
- Reference normal ranges
- Consider patient-specific factors
- Note concerning combinations
- Suggest appropriate responses
- Use clinical staging when applicable""",
                user_template="""
Patient Context:
{context}

Current Vital Signs:
{retrieved_docs}

Interpretation Request: {query}

Clinical Interpretation:""",
                requires_context=True,
                requires_docs=True
            ),
            
            "simple_response": PromptTemplate(
                name="simple_response",
                system_prompt="""You are a helpful clinical assistant. Provide brief, direct answers to clinical questions.""",
                user_template="""{query}""",
                requires_context=False,
                requires_docs=False
            )
        }
    
    def get_template(self, name: str) -> Optional[PromptTemplate]:
        return self.templates.get(name)
    
    def build_prompt(
        self,
        template_name: str,
        query: str,
        context: str = "",
        retrieved_docs: List = None
    ) -> str:
        template = self.templates.get(template_name)
        
        if template is None:
            template = self.templates["clinical_assistant"]
        
        docs_text = ""
        if retrieved_docs:
            docs_text = "\n".join([
                f"- {doc.content}" if hasattr(doc, 'content') else f"- {doc}"
                for doc in retrieved_docs[:5]
            ])
        
        if not docs_text:
            docs_text = "No additional reference information available."
        
        if not context:
            context = "No specific patient context provided."
        
        user_prompt = template.user_template.format(
            query=query,
            context=context,
            retrieved_docs=docs_text
        )
        
        full_prompt = f"""<|system|>
{template.system_prompt}</s>
<|user|>
{user_prompt}</s>
<|assistant|>
"""
        
        return full_prompt.strip()
    
    def build_messages(
        self,
        template_name: str,
        query: str,
        context: str = "",
        retrieved_docs: List = None
    ) -> List[Dict[str, str]]:
        template = self.templates.get(template_name)
        
        if template is None:
            template = self.templates["clinical_assistant"]
        
        docs_text = ""
        if retrieved_docs:
            docs_text = "\n".join([
                f"- {doc.content}" if hasattr(doc, 'content') else f"- {doc}"
                for doc in retrieved_docs[:5]
            ])
        
        if not docs_text:
            docs_text = "No additional reference information available."
        
        if not context:
            context = "No specific patient context provided."
        
        user_prompt = template.user_template.format(
            query=query,
            context=context,
            retrieved_docs=docs_text
        )
        
        return [
            {"role": "system", "content": template.system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    
    def list_templates(self) -> List[Dict]:
        return [
            {
                "name": t.name,
                "requires_context": t.requires_context,
                "requires_docs": t.requires_docs
            }
            for t in self.templates.values()
        ]
    
    def add_custom_template(
        self,
        name: str,
        system_prompt: str,
        user_template: str,
        requires_context: bool = False,
        requires_docs: bool = False
    ) -> None:
        self.templates[name] = PromptTemplate(
            name=name,
            system_prompt=system_prompt,
            user_template=user_template,
            requires_context=requires_context,
            requires_docs=requires_docs
        )
    
    def get_quick_prompts(self) -> Dict[str, str]:
        return {
            "vitals_check": "Review the current vital signs and identify any concerning values.",
            "med_due": "What medications are due for this patient?",
            "summary": "Provide a brief summary of the patient's current status.",
            "trend": "How have the vital signs trended over the past 24 hours?",
            "concerns": "Are there any clinical concerns that need attention?",
            "handoff": "Generate a shift handoff summary for this patient."
        }
    
    def format_for_display(
        self,
        response: str,
        format_type: str = "default"
    ) -> str:
        if format_type == "bullet":
            lines = response.split(". ")
            return "\n".join([f"- {line.strip()}" for line in lines if line.strip()])
        
        elif format_type == "numbered":
            lines = response.split(". ")
            return "\n".join([
                f"{i+1}. {line.strip()}"
                for i, line in enumerate(lines) if line.strip()
            ])
        
        elif format_type == "compact":
            return " ".join(response.split())
        
        return response