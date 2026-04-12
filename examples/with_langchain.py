"""
with_langchain.py -- LangChain agent with sandclaw-memory as long-term memory.

WHAT THIS EXAMPLE SHOWS:
    How to plug sandclaw-memory into a LangChain conversational agent.
    The agent gets persistent memory that grows smarter over time.

ARCHITECTURE:
    User <-> LangChain Agent <-> Tools
                  |
                  v
           sandclaw-memory
           (recall before, save after)

HOW IT WORKS:
    1. Before the agent responds, we recall relevant memories
    2. Inject memories into the system prompt
    3. After the agent responds, we save the conversation
    4. Important content auto-promotes to permanent storage

BEFORE YOU RUN THIS:
    1. pip install sandclaw-memory langchain langchain-openai
    2. Set your OPENAI_API_KEY environment variable
"""

from __future__ import annotations

import json

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from sandclaw_memory import BrainMemory


# ─── Tag extractor ───
def tag_extractor(content: str) -> list[str]:
    """Extract tags using a lightweight LLM call."""
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    resp = llm.invoke(
        "Extract 3-7 keyword tags from the text below. "
        "Return a JSON array of lowercase strings only.\n\n"
        f"Text: {content}"
    )
    return json.loads(resp.content)


# ─── Initialize memory ───
brain = BrainMemory(
    db_path="./langchain_memory",
    tag_extractor=tag_extractor,
    polling_interval=30,
)
brain.start_polling()


# ═══════════════════════════════════════════════════════════
# LangChain Agent with Memory
# ═══════════════════════════════════════════════════════════
llm = ChatOpenAI(model="gpt-4o", temperature=0.7)


def chat_with_memory(user_message: str) -> str:
    """One turn of conversation with persistent memory.

    HOW THIS WORKS:
        1. Recall relevant context from sandclaw-memory
        2. Build system prompt with memory context
        3. Get LLM response
        4. Save the full turn to memory

    HOW TO CUSTOMIZE:
        - Change the system prompt to fit your use case
        - Adjust depth manually: brain.recall(msg, depth="deep")
        - Add source="archive" for important saves
    """
    # ─── Step 1: Recall relevant memories ───
    # The dispatcher auto-detects depth from the query.
    # "What's the weather?" -> CASUAL (L1 only, fast)
    # "Summarize this week" -> STANDARD (L1 + L2)
    # "Why did we pick React?" -> DEEP (L1 + L2 + L3)
    context = brain.recall(user_message)

    # ─── Step 2: Build messages with memory context ───
    messages = [
        SystemMessage(content=(
            "You are a helpful assistant with persistent memory.\n"
            "Use the following memory context to personalize your responses.\n"
            "If the memory is relevant, reference it naturally.\n"
            "If not, just respond normally.\n\n"
            f"=== Memory Context ===\n{context}\n=== End Memory ==="
        )),
        HumanMessage(content=user_message),
    ]

    # ─── Step 3: Get response ───
    response = llm.invoke(messages)
    ai_response = response.content

    # ─── Step 4: Save the full conversation turn ───
    # Regular turns go to L1 (session log, rolling 3-day window).
    # The default promote_checker auto-promotes long/important content to L3.
    full_turn = f"User: {user_message}\nAssistant: {ai_response}"
    brain.save(full_turn)

    return ai_response


# ═══════════════════════════════════════════════════════════
# Demo Conversation
# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=== Chat with Memory (type 'quit' to exit) ===\n")

    # Some initial context
    brain.save(
        "User is a Python developer building a web app with FastAPI.",
        source="archive",
        tags=["python", "fastapi", "web"],
    )

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("quit", "exit", "q"):
            break

        response = chat_with_memory(user_input)
        print(f"AI: {response}\n")

    # ─── Cleanup ───
    brain.stop_polling()
    brain.close()
    print("\nMemory saved. Goodbye!")

    # Next time you run this script, the memory persists!
    # The AI will remember previous conversations.
