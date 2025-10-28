import streamlit as st
import httpx
import asyncio
import time
import uuid
from typing import Optional
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage

load_dotenv()

# Load custom CSS
def load_css():
    """Load custom CSS from external file"""
    import os
    css_file = os.path.join(os.path.dirname(__file__), "style.css")
    with open(css_file) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

load_css()

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "thread_id" not in st.session_state:
    st.session_state.thread_id = None
if "conversation_count" not in st.session_state:
    st.session_state.conversation_count = 0
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []  # List of {id, title, messages, timestamp}
if "active_chat_id" not in st.session_state:
    st.session_state.active_chat_id = None

# Helper function for API calls
async def query_rag(question: str, thread_id: Optional[str] = None):
    """Query the RAG system with optional thread_id for conversation continuity"""
    import os
    fastapi_url = os.getenv("FASTAPI_URL", "http://localhost:8000")
    params = {}
    if thread_id:
        params["thread_id"] = thread_id
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{fastapi_url}/api/v1/retrieval/query",
            json={
                "question": question,
                "max_iterations": 3
            },
            params=params,
            timeout=600.0
        )
        response.raise_for_status()
        return response.json()

st.title("SOW - Assistant")

st.markdown("""
**Smart SOW Search with Conversation Memory**

This assistant uses Redis-based memory to maintain conversation context across multiple questions.
- Ask follow-up questions and the AI will remember previous context
- Use the same conversation thread to ask related questions
- Start a new conversation anytime to discuss a different topic

💡 **Tip:** Ask follow-up questions like "Tell me more", "What about their deliverables?", or "Get me the names?"
""")

with st.sidebar:
    st.header("Conversations")
    
    # New Chat Button at the top
    if st.button("➕ New Chat", use_container_width=True, type="primary"):
        # Save current chat if it has messages
        if st.session_state.messages:
            first_message = None
            for msg in st.session_state.messages:
                if isinstance(msg, HumanMessage):
                    first_message = msg.content
                    break
            
            chat_title = first_message[:50] + "..." if first_message and len(first_message) > 50 else (first_message or "New Chat")
            
            # Update existing chat or add new one
            chat_exists = False
            if st.session_state.active_chat_id:
                for chat in st.session_state.chat_history:
                    if chat["id"] == st.session_state.active_chat_id:
                        chat["messages"] = st.session_state.messages.copy()
                        chat["thread_id"] = st.session_state.thread_id
                        chat["count"] = st.session_state.conversation_count
                        chat_exists = True
                        break
            
            if not chat_exists and st.session_state.messages:
                new_chat = {
                    "id": str(uuid.uuid4()),
                    "title": chat_title,
                    "messages": st.session_state.messages.copy(),
                    "thread_id": st.session_state.thread_id,
                    "count": st.session_state.conversation_count,
                    "timestamp": time.time()
                }
                st.session_state.chat_history.insert(0, new_chat)
        
        # Start new chat
        st.session_state.messages = []
        st.session_state.thread_id = None
        st.session_state.conversation_count = 0
        st.session_state.active_chat_id = None
        st.rerun()
    
    st.divider()
    
    # Display chat history
    if st.session_state.chat_history:
        st.subheader("Chat History")
        for idx, chat in enumerate(st.session_state.chat_history):
            col1, col2 = st.columns([4, 1])
            
            with col1:
                # Create a button for each chat
                if st.button(
                    f"💬 {chat['title']}", 
                    key=f"chat_{chat['id']}",
                    use_container_width=True,
                    type="secondary" if chat["id"] == st.session_state.active_chat_id else "primary"
                ):
                    # Load this chat
                    st.session_state.messages = chat["messages"].copy()
                    st.session_state.thread_id = chat["thread_id"]
                    st.session_state.conversation_count = chat["count"]
                    st.session_state.active_chat_id = chat["id"]
                    st.rerun()
            
            with col2:
                # Delete button
                if st.button("🗑️", key=f"del_{chat['id']}", help="Delete this chat"):
                    st.session_state.chat_history.pop(idx)
                    if chat["id"] == st.session_state.active_chat_id:
                        st.session_state.messages = []
                        st.session_state.thread_id = None
                        st.session_state.conversation_count = 0
                        st.session_state.active_chat_id = None
                    st.rerun()
            
            # Show message count
            st.caption(f"📊 {chat['count']} messages")
            st.divider()
    else:
        st.info("No chat history yet. Start a conversation!")
    
    st.divider()
    
    # Current Chat Info
    st.header("📊 Current Chat")
    if st.session_state.thread_id:
        st.write(f"**Thread ID:** `{st.session_state.thread_id[:12]}...`")
        st.write(f"**Messages:** {st.session_state.conversation_count}")
    else:
        st.write("**Status:** No active conversation")
    
    # Clear current chat button
    if st.session_state.messages:
        if st.button("🗑️ Clear Current Chat", use_container_width=True):
            st.session_state.messages = []
            st.session_state.thread_id = None
            st.session_state.conversation_count = 0
            st.session_state.active_chat_id = None
            st.rerun()


# Display the chat history
for message in st.session_state.messages:
    if isinstance(message, HumanMessage):
        with st.chat_message("user"):
            st.write(message.content)
    elif isinstance(message, AIMessage):
        with st.chat_message("assistant"):
            st.write(message.content)

# Handle new user input
# Handle new user input
if prompt := st.chat_input("Ask me anything about our SOWs..."):
    # Add user message to chat history
    user_message = HumanMessage(content=prompt)
    st.session_state.messages.append(user_message)
    
    # Display user message
    with st.chat_message("user"):
        st.write(prompt)

    # Query the RAG system
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        
        try:
            # Track response time
            start_time = time.time()
            
            # Show loading spinner while processing
            with st.spinner("🔍 Searching and analyzing..."):
                result = asyncio.run(query_rag(prompt, st.session_state.thread_id))
            
            # Calculate response time
            end_time = time.time()
            response_time = end_time - start_time
            
            # Extract response
            answer = result.get("answer", "No answer received")
            confidence = result.get("confidence", 0.0)
            
            # Display answer
            full_response = f"{answer}\n\n"
            
            # Add confidence indicator
            if confidence >= 8:
                confidence_emoji = "🟢"
                confidence_text = "High"
            elif confidence >= 6:
                confidence_emoji = "🟡"
                confidence_text = "Medium"
            else:
                confidence_emoji = "🔴"
                confidence_text = "Low"
            
            full_response += f"*Confidence: {confidence_emoji} {confidence_text} ({confidence:.1f}/10)*"
            
            message_placeholder.markdown(full_response)
            
            # Show response time
            st.caption(f"⏱️ Response time: {response_time:.2f}s")
            
            # Show thread info for first message
            if not st.session_state.thread_id:
                st.info("💡 Your conversation has started! Ask follow-up questions to continue this thread.")
            else:
                st.caption(f"💬 Conversation #{st.session_state.conversation_count + 1} in this thread")
            
            # Update session state
            if not st.session_state.thread_id:
                # First message - need to extract thread_id from logs or generate
                # Since API doesn't return it yet, we'll generate one
                st.session_state.thread_id = result.get("thread_id", str(uuid.uuid4()))
            
            st.session_state.conversation_count += 1
            
            # Add to chat history
            st.session_state.messages.append(AIMessage(content=full_response))
            
        except httpx.HTTPError as e:
            message_placeholder.error(f"❌ API request failed: {str(e)}")
        except Exception as e:
            message_placeholder.error(f"❌ An error occurred: {str(e)}")
            import traceback
            st.error(f"Details: {traceback.format_exc()}")
