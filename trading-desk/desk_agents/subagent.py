"""Sub-agent primitive: one role, one isolated conversation, shared meter.

Each sub-agent keeps its own message history so agents never see each
other's raw context — the orchestrator decides exactly which distilled
reports flow between them. That isolation is what keeps token burn flat:
an agent's prompt grows only with what it is explicitly handed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from desk_agents.llm import ChatClient, UsageMeter


@dataclass
class SubAgent:
    name: str
    system_prompt: str
    client: ChatClient
    meter: UsageMeter
    messages: list[dict[str, str]] = field(default_factory=list)

    def ask(self, prompt: str) -> str:
        """One LLM call within this agent's private history."""
        if not self.messages:
            self.messages.append({"role": "system", "content": self.system_prompt})
        self.messages.append({"role": "user", "content": prompt})
        reply = self.client.chat(self.messages, agent=self.name, meter=self.meter)
        self.messages.append({"role": "assistant", "content": reply})
        return reply.strip()

    @property
    def last_reply(self) -> str:
        for message in reversed(self.messages):
            if message["role"] == "assistant":
                return message["content"].strip()
        return ""
