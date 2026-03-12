import os
import logging
import json
from openai import OpenAI

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# API Key Configuration
# Set your OpenRouter API key via environment variable OPENROUTER_API_KEY
# Get your key from: https://openrouter.ai/keys
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "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")

class WhatsAppAIAgent:
    def __init__(self, api_key=None):
        self.api_key = api_key or OPENROUTER_API_KEY
        self.model = "stepfun/step-3.5-flash:free"
        
        if not self.api_key or "dummy" in self.api_key.lower():
            logger.error("OpenRouter API Key not configured! Please set OPENROUTER_API_KEY environment variable.")
            self.client = None
        else:
            try:
                # Configure OpenRouter using the OpenAI client format
                self.client = OpenAI(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=self.api_key,
                )
                
                # System instruction for the AI provided by user
                self.system_instruction = (
                    "You are the Secure Online Social Networks Assistant inside a Complaint Management System.\n\n"
                    "Your role is to assist registered Users in submitting and tracking complaints related to platform issues, account problems, "
                    "technical errors, service dissatisfaction, or other concerns listed in the Register Complaint section.\n\n"
                    "Rules:\n"
                    "1. When a User sends their first message, treat it as a complaint submission.\n"
                    "2. Help the User clearly describe the issue.\n"
                    "3. If information is missing, politely ask for:\n"
                    "   - Subject of complaint\n"
                    "   - Detailed description\n"
                    "   - Date of issue (if applicable)\n"
                    "4. Confirm that the complaint has been successfully registered.\n"
                    "5. Inform the User that an Employee will review and respond soon.\n"
                    "6. Keep responses professional, short, and support-focused.\n"
                    "7. Do not discuss system configuration, API keys, or technical backend details.\n"
                    "8. Do not generate unrelated topics.\n"
                    "9. Maintain a formal support tone at all times.\n\n"
                    "If the sender role is:\n"
                    "- 'user' → Assist in registering and clarifying the complaint.\n"
                    "- 'employee' → Help summarize the complaint and draft professional responses.\n\n"
                    "Your goal is to make complaint registration structured, clear, and efficient."
                )
                logger.info(f"WhatsApp AI Agent initialized with OpenRouter model: {self.model}")
            except Exception as e:
                logger.error(f"Failed to initialize OpenRouter AI: {str(e)}")
                self.client = None

    def generate_response(self, user_message, chat_history=None, files=None, user_data=None):
        """
        Generates a response using the OpenRouter API.
        user_data: string containing context like user complaints or secrets
        """
        if not self.client:
            return {
                "type": "text", 
                "content": "🔧 AI Assistant is currently unavailable.\n\n"
                          "**Configuration Required**: The AI service needs a valid OpenRouter API key to function.\n\n"
                          "**Admin Action Needed**:\n"
                          "1. Obtain an API key from [OpenRouter](https://openrouter.ai/keys)\n"
                          "2. Set the `OPENROUTER_API_KEY` environment variable, or update `whatsapp_agent.py`\n\n"
                          "Please contact your system administrator."
            }

        try:
            # Convert chat history to OpenAI format
            messages = [{"role": "system", "content": self.system_instruction}]
            
            if chat_history:
                for msg in chat_history:
                    role = msg.get("role")
                    content = msg.get("content", "")
                    
                    if role == "user":
                        messages.append({"role": "user", "content": content})
                    elif role == "assistant" or role == "model":
                        messages.append({"role": "assistant", "content": content})
            
            # Add user data context if provided
            if user_data:
                augmented_message = f"{user_message}\n\n---\nUSER_DATA:\n{user_data}"
                messages.append({"role": "user", "content": augmented_message})
            else:
                messages.append({"role": "user", "content": user_message})
            
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=150
            )
            
            response_text = completion.choices[0].message.content
            
            if response_text:
                if "INTERACTIVE_MENU" in response_text.upper():
                    return {
                        "type": "menu",
                        "content": "How can I help you today?",
                        "options": ["Check Complaint Status", "View My Secrets", "System FAQ", "Contact Support"]
                    }
                return {"type": "text", "content": response_text}
            else:
                return {"type": "text", "content": "I'm sorry, I couldn't generate a response at this moment."}

        except Exception as e:
            logger.error(f"Error generating OpenRouter response: {str(e)}")
            return {"type": "text", "content": f"AI Error: {str(e)}"}

    def classify_complaint(self, text):
        """
        Classifies a complaint text into Category, Priority, and Sentiment.
        Returns a JSON object.
        """
        if not self.client:
            return {"category": "General", "priority": "Medium", "sentiment": "Neutral"}
            
        try:
            prompt = f"""
            Analyze the following complaint text and classify it.
            
            Complaint: "{text}"
            
            Return a purely JSON response (no markdown, no code blocks) with the exact keys below:
            - "category": (Choose from: Network, Hardware, Software, Security, Account, Other)
            - "priority": (Choose from: Low, Medium, High, Critical)
            - "sentiment": (Positive, Neutral, Negative)
            - "summary": (A 5-word summary of the issue)
            
            Remember, Output ONLY JSON brackets.
            """
            
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150
            )
            response_text = completion.choices[0].message.content
            
            if response_text:
                cleaned_text = response_text.replace('```json', '').replace('```', '').strip()
                # Find first { and last }
                start = cleaned_text.find('{')
                end = cleaned_text.rfind('}') + 1
                if start != -1 and end != 0:
                    cleaned_text = cleaned_text[start:end]
                return json.loads(cleaned_text)
            
        except Exception as e:
            logger.error(f"Classification failed: {e}")
        
        return {"category": "General", "priority": "Medium", "sentiment": "Neutral"}

    def parse_registration_intent(self, user_message):
        """
        Analyzes if the user wants to register a complaint and extracts details.
        """
        if not self.client:
            return None

        try:
            prompt = f"""
            Analyze if the user intends to register a complaint.
            User Message: "{user_message}"
            
            If NO intent to complain, return null.
            If YES, return a purely JSON object with:
            - "intent": "register_complaint"
            - "title": (Extracted or generated short title)
            - "description": (The full complaint details)
            - "missing_info": (true if description is too vague, else false)
            
            Output ONLY raw JSON or null.
            """
            
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150
            )
            response_text = completion.choices[0].message.content
            
            if response_text:
                cleaned_text = response_text.replace('```json', '').replace('```', '').strip()
                if cleaned_text.lower() == 'null' or cleaned_text.lower() == 'none':
                    return None
                start = cleaned_text.find('{')
                end = cleaned_text.rfind('}') + 1
                if start != -1 and end != 0:
                    cleaned_text = cleaned_text[start:end]
                return json.loads(cleaned_text)
                
        except Exception as e:
            logger.error(f"Intent parsing failed: {e}")
            
        return None

    def analyze_trends(self, complaints_text):
        """
        Analyzes a list of complaints to identify trends and risks.
        """
        if not self.client:
            return "AI Analysis Unavailable."
            
        try:
            prompt = f"""
            Analyze the following list of recent user complaints and provide a predictive analysis.
            
            Complaints Data:
            {complaints_text}
            
            Please provide a report with:
            1. **Top Recurring Issues**: What are the most common problems?
            2. **Emerging Risks**: What problems are increasing in frequency?
            3. **Recommendations**: Suggested actions for the admin.
            
            Format the output in Markdown.
            """
            
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=250
            )
            response_text = completion.choices[0].message.content
            if response_text:
                return response_text
                
        except Exception as e:
            logger.error(f"Trend analysis failed: {e}")
            return f"Error analyzing trends: {e}"
            
        return "Analysis failed."

# Singleton instance
ai_agent = WhatsAppAIAgent()
