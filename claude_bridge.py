"""
Claude CLI Subprocess Bridge
Runs Claude via subprocess — no API credits, uses subscription only.
"""

import subprocess
import json
import os
import threading
import time


PLATFORM_TONES = {
    "google_lsa": "Professional tone. Mention credentials, licensing, and certifications where relevant.",
    "yelp": "Friendly and approachable. Reference positive reviews and community reputation.",
    "thumbtack": "Direct and competitive. Emphasize value, quick response, and competitive pricing.",
    "angi": "Professional with emphasis on warranties, guarantees, and quality workmanship.",
    "chat_widget": "Conversational and concise. Use shorter messages, casual but helpful.",
    "contact_form": "Thorough email-style response. More detailed, complete sentences.",
    "duke_energy": "Professional. Reference utility rebate programs and energy efficiency.",
}


class RateLimiter:
    """Token bucket rate limiter."""

    def __init__(self, max_calls=10, period=60):
        self.max_calls = max_calls
        self.period = period
        self._calls = []
        self._lock = threading.Lock()

    def acquire(self):
        with self._lock:
            now = time.time()
            self._calls = [t for t in self._calls if now - t < self.period]
            if len(self._calls) >= self.max_calls:
                wait_time = self.period - (now - self._calls[0])
                time.sleep(max(0, wait_time))
                self._calls = [t for t in self._calls if time.time() - t < self.period]
            self._calls.append(time.time())


class BridgeMetrics:
    """Track bridge call metrics."""

    def __init__(self):
        self._lock = threading.Lock()
        self.total = 0
        self.success = 0
        self.fail = 0
        self.total_latency = 0.0
        self.last_call_at = None
        self.last_success_at = None

    def record(self, success, latency):
        with self._lock:
            self.total += 1
            self.total_latency += latency
            self.last_call_at = time.time()
            if success:
                self.success += 1
                self.last_success_at = time.time()
            else:
                self.fail += 1

    @property
    def avg_latency(self):
        return self.total_latency / self.total if self.total > 0 else 0

    def to_dict(self):
        with self._lock:
            return {
                "total_calls": self.total,
                "successful": self.success,
                "failed": self.fail,
                "avg_latency_seconds": round(self.avg_latency, 2),
                "last_call_at": self.last_call_at,
                "last_success_at": self.last_success_at,
            }


class ClaudeBridge:
    """Bridge to Claude CLI via subprocess for AI responses."""

    MAX_KB_CHARS = 8000

    def __init__(self, timeout=120):
        self.timeout = timeout
        self._semaphore = threading.Semaphore(3)
        self._rate_limiter = RateLimiter(max_calls=10, period=60)
        self.metrics = BridgeMetrics()

    def _truncate_kb(self, content):
        if content and len(content) > self.MAX_KB_CHARS:
            return content[:self.MAX_KB_CHARS] + "\n\n[Knowledge base truncated for length]"
        return content

    def query(self, prompt, system_prompt=None, max_retries=2):
        """Send a prompt to Claude CLI and get a response."""
        cmd = ["claude", "-p"]
        if system_prompt:
            cmd.extend(["--system", system_prompt])
        cmd.append(prompt)

        self._rate_limiter.acquire()

        for attempt in range(max_retries + 1):
            start_time = time.time()
            try:
                with self._semaphore:
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=self.timeout,
                        cwd=os.path.expanduser("~")
                    )
                latency = time.time() - start_time

                if result.returncode == 0 and result.stdout.strip():
                    self.metrics.record(True, latency)
                    return {
                        "success": True,
                        "response": result.stdout.strip(),
                        "error": None
                    }
                else:
                    error_msg = result.stderr.strip() if result.stderr else "Empty response"
                    if attempt < max_retries:
                        time.sleep(2)
                        continue
                    self.metrics.record(False, latency)
                    return {
                        "success": False,
                        "response": None,
                        "error": error_msg
                    }
            except subprocess.TimeoutExpired:
                self.metrics.record(False, time.time() - start_time)
                return {
                    "success": False,
                    "response": None,
                    "error": f"Claude CLI timed out after {self.timeout}s"
                }
            except FileNotFoundError:
                self.metrics.record(False, time.time() - start_time)
                return {
                    "success": False,
                    "response": None,
                    "error": "Claude CLI not found. Ensure 'claude' is installed and in PATH."
                }
            except Exception as e:
                self.metrics.record(False, time.time() - start_time)
                return {
                    "success": False,
                    "response": None,
                    "error": str(e)
                }

    def generate_lead_response(self, lead_context, knowledge_base_content, conversation_history, platform):
        """Generate an AI response for a lead conversation."""
        kb_content = self._truncate_kb(knowledge_base_content)
        tone_guidance = PLATFORM_TONES.get(platform, "Professional and helpful.")

        system_prompt = f"""You are a Speed-to-Lead AI chat agent for a home service company. Your goal is to respond to customer inquiries quickly, professionally, and helpfully to convert leads into booked jobs.

IMPORTANT RULES:
- Be warm, professional, and concise
- Answer questions about services using ONLY the knowledge base provided
- If you can gather enough info (name, address, phone, service needed, preferred time), suggest booking
- If the customer is angry, confused, or the request is out of scope, respond with ESCALATE: followed by the reason
- If the inquiry is spam, a vendor, or not a real lead, respond with NON_LEAD: followed by the reason
- Always respond on-brand for the business

PLATFORM TONE ({platform}):
{tone_guidance}

KNOWLEDGE BASE:
{kb_content}
"""

        history_text = ""
        for msg in conversation_history:
            role = msg.get("sender", "unknown")
            history_text += f"\n{role}: {msg.get('content', '')}"

        prompt = f"""Conversation history:{history_text}

Respond to the customer's latest message. Keep your response under 200 words."""

        return self.query(prompt, system_prompt=system_prompt)

    def generate_follow_up(self, lead_context, knowledge_base_content, follow_up_number):
        """Generate a follow-up drip message."""
        kb_content = self._truncate_kb(knowledge_base_content)

        system_prompt = f"""You are a Speed-to-Lead AI agent sending a follow-up message to a customer who hasn't responded.

KNOWLEDGE BASE:
{kb_content}

This is follow-up #{follow_up_number}. Be progressively more concise with each follow-up.
- Follow-up 1: Friendly check-in, restate availability
- Follow-up 2: Brief reminder with a value proposition
- Follow-up 3+: Short and direct, offer to help when ready
"""

        prompt = f"""Customer name: {lead_context.get('customer_name', 'there')}
Service requested: {lead_context.get('service_type', 'home service')}
Platform: {lead_context.get('platform', 'unknown')}

Generate a natural follow-up message (under 100 words)."""

        return self.query(prompt, system_prompt=system_prompt)

    def classify_unbooked_lead(self, conversation_history, knowledge_base_content):
        """Classify why a lead didn't book. Retries on malformed JSON."""
        system_prompt = """You are analyzing a lead conversation that did not result in a booking.
Provide a JSON response with:
- "reason": brief summary of why the lead didn't book
- "business_unit": the relevant business unit (HVAC, Plumbing, Electrical, General)
- "job_type": the type of job requested
- "tags": array of relevant tags (e.g., "price_sensitive", "competitor", "timing", "no_response")
Respond ONLY with valid JSON."""

        history_text = "\n".join([f"{m.get('sender','?')}: {m.get('content','')}" for m in conversation_history])
        prompt = f"Conversation:\n{history_text}\n\nClassify this unbooked lead."

        for attempt in range(2):
            result = self.query(prompt, system_prompt=system_prompt)
            if result["success"]:
                try:
                    json.loads(result["response"])
                    return result
                except json.JSONDecodeError:
                    if attempt == 0:
                        prompt = f"{prompt}\n\nIMPORTANT: Respond with ONLY valid JSON, no markdown or extra text."
                        continue
                    result["response"] = json.dumps({
                        "reason": result["response"][:200],
                        "business_unit": "General",
                        "job_type": "Unknown",
                        "tags": ["parse_error"]
                    })
            return result
        return result

    def test_knowledge_base(self, knowledge_base_content, test_question):
        """Test the knowledge base with a specific question."""
        kb_content = self._truncate_kb(knowledge_base_content)
        system_prompt = f"""You are a home service company AI agent. Answer the customer's question using ONLY the knowledge base below. If the answer is not in the knowledge base, say "I don't have that information in my knowledge base."

KNOWLEDGE BASE:
{kb_content}"""

        return self.query(test_question, system_prompt=system_prompt)

    def generate_platform_simulation(self, message, platforms, knowledge_base_content):
        """Generate responses for the same message across multiple platforms for comparison."""
        results = {}
        kb_content = self._truncate_kb(knowledge_base_content)
        for platform in platforms:
            tone = PLATFORM_TONES.get(platform, "Professional and helpful.")
            system_prompt = f"""You are a Speed-to-Lead AI chat agent for a home service company.
Respond to the customer message below. Adapt your tone for the {platform} platform.

PLATFORM TONE: {tone}

KNOWLEDGE BASE:
{kb_content}

Keep your response under 150 words."""

            result = self.query(message, system_prompt=system_prompt)
            results[platform] = {
                "response": result.get("response", result.get("error", "Failed")),
                "success": result["success"]
            }
        return results

    def health_check(self):
        """Check if Claude CLI is available and working."""
        result = self.query("Respond with exactly: OK")
        return result["success"]
