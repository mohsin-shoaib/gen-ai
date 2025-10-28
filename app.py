import streamlit as st
from streamlit_chat import message
from langchain.chains import ConversationalRetrievalChain
from langchain_community.document_loaders import TextLoader  # For loading MD file
from langchain_huggingface import HuggingFaceEmbeddings  # Updated import to address deprecation
from langchain.llms import CTransformers
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.vectorstores import FAISS  # Updated import to avoid deprecation warning
from langchain.memory import ConversationBufferMemory
from langchain.prompts import PromptTemplate
import os
import re
import torch  # Added for GPU detection (though not used here)
import time  # For benchmarking (optional)

# Function to load MD documents
def load_documents(md_file_path='scraped_data/all_scraped_data.md'):
    if not os.path.exists(md_file_path):
        raise FileNotFoundError(f"MD file not found: {md_file_path}. Ensure the scraper has run successfully to generate it.")
    
    loader = TextLoader(md_file_path, encoding='utf-8')
    documents = loader.load()
    for doc in documents:
        doc.metadata['source'] = md_file_path
    return documents

# Enhanced function to split text into chunks with metadata extraction, focused on key fields
def split_text_into_chunks(documents):
    # Load raw text for parsing
    raw_text = documents[0].page_content  # Assuming single MD file
    
    # Improved regex to match the structure: ### Title, then **Field:** values, until next ### or end
    # Captures: title, organization, url, purpose, target_audience, mission, contact_info
    section_pattern = r'###\s*(.*?)\n\*\*Organization:\*\*\s*(.*?)\n\*\*URL:\*\*\s*(.*?)\n\*\*Purpose:\*\*\s*(.*?)\n\*\*Target audience:\*\*\s*(.*?)\n\*\*Mission:\*\*\s*(.*?)\n\*\*Contact information:\*\*\s*(.*?)(?=\n###|\Z)'
    sections = re.findall(section_pattern, raw_text, re.DOTALL | re.MULTILINE)
    
    chunks = []
    for i, (title, org, url, purpose, target_audience, mission, contact_info) in enumerate(sections):
        # Clean up fields (remove JS artifacts or extra text if present)
        purpose = re.sub(r'function\s*teVinden\(\).*?Last modified:.*', '', purpose, flags=re.DOTALL).strip()
        target_audience = re.sub(r'function\s*teVinden\(\).*?Last modified:.*', '', target_audience, flags=re.DOTALL).strip()
        
        # Create a structured chunk combining all key fields for semantic similarity
        structured_content = f"Service: {title}\nOrganization: {org.strip()}\nURL: {url.strip()}\nPurpose: {purpose}\nTarget Audience: {target_audience}\nMission: {mission.strip()}\nContact Information: {contact_info.strip()}"
        
        # Use smaller splitter for the structured content to ensure key fields stay intact
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=150)  # Adjusted for structured content
        sub_docs = text_splitter.create_documents([structured_content])
        
        for sub_doc in sub_docs:
            sub_doc.metadata.update({
                'organization': org.strip(),
                'url': url.strip(),
                'purpose': purpose,
                'target_audience': target_audience,
                'mission': mission.strip(),
                'contact_info': contact_info.strip(),
                'section_type': title.strip(),  # e.g., "Bicycle"
                'source': 'all_scraped_data.md'
            })
            chunks.append(sub_doc)
    
    return chunks

# Enhanced function to create embeddings with multilingual model
def create_embeddings():
    device = "cpu"  # Explicitly CPU since no GPU
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",  # Multilingual, higher accuracy
        model_kwargs={'device': device}
    )
    return embeddings

# Function to create or load vector store with native FAISS persistence
def create_or_load_vector_store(text_chunks, embeddings):
    index_path = 'faiss_index'
    if os.path.exists(index_path):
        vector_store = FAISS.load_local(index_path, embeddings, allow_dangerous_deserialization=True)
        st.info("Loaded pre-built FAISS index for faster startup.")
        return vector_store
    
    # Fallback: Create new vector store
    vector_store = FAISS.from_documents(text_chunks, embeddings)
    vector_store.save_local(index_path)
    st.info("Created and saved new FAISS index.")
    return vector_store

# Enhanced function to create LLMs model optimized for CPU with Mistral-7B
def create_llms_model(model_path="./mistral-7b"):
    # Determine physical cores for threading
    physical_cores = len(os.sched_getaffinity(0)) // 2 if hasattr(os, 'sched_getaffinity') else os.cpu_count() // 2 or 4
    
    config = {
        'max_new_tokens': 150,  # Reduced for faster generation
        'temperature': 0.1,  # Slightly higher for minor speed gains in sampling
        'gpu_layers': 0,  # Explicitly CPU-only
        'threads': physical_cores,  # Optimize for CPU cores
        'context_length': 2048,  # Reduced to lower memory and processing overhead
        'top_k': 20,  # Reduced for faster sampling
        'top_p': 0.9
    }
    llm = CTransformers(
        model=f"{model_path}/mistral-7b-instruct-v0.1.Q4_K_M.gguf",
        model_type="mistral",  # Explicitly specify for stability
        config=config
    )
    return llm

# Initialize Streamlit app
st.title("Community Services Assistant")
st.markdown('<style>h1{color: orange; text-align: center;}</style>', unsafe_allow_html=True)
st.subheader('Ask about Vught Community Services 💪')
st.markdown('<style>h3{color: pink; text-align: center;}</style>', unsafe_allow_html=True)

# Loading of documents (MD file)
@st.cache_resource
def load_and_process_data():
    documents = load_documents()
    text_chunks = split_text_into_chunks(documents)
    embeddings = create_embeddings()
    vector_store = create_or_load_vector_store(text_chunks, embeddings)
    llm = create_llms_model()
    return vector_store, llm

vector_store, llm = load_and_process_data()

# Initialize conversation history
if 'history' not in st.session_state:
    st.session_state['history'] = []

if 'generated' not in st.session_state:
    st.session_state['generated'] = ["Hello! Ask me anything about community services in Vught."]

if 'past' not in st.session_state:
    st.session_state['past'] = ["Hey! 👋"]

# Create memory
memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

# Enhanced custom prompt for paragraph-style responses, emphasizing exact info extraction
template = """You are a helpful assistant for community services in Vught. Match the user's question to the most relevant service by focusing on its Purpose (what the service provides), Target Audience (who qualifies, e.g., low-income families aged 4-17), and Mission (overall goals like participation opportunities). Use the context to provide accurate, fast guidance on facilities.

Prioritize exact matches: If the question relates to eligibility (e.g., age, income), highlight Target Audience details in the response. For what the service offers, emphasize Purpose details. For broader support, reference Mission details. Respond in a single, cohesive paragraph that directly answers the question with exact information, integrating service name, key details, eligibility, goals, and contact info where relevant. Do not use bullets or lists; weave the information naturally into the paragraph for a conversational flow. If multiple services match, briefly describe the top 1-2 in sequence within the paragraph. Suggest alternatives if no exact match. Keep responses concise (100-150 words) but complete and precise, like a knowledgeable chatbot providing targeted help.

Context: {context}

Question: {question}

Complete Answer:"""
QA_CHAIN_PROMPT = PromptTemplate.from_template(template)

# Enhanced chain creation with MMR retriever and stuff chain type (compatible with custom prompt)
@st.cache_resource
def create_chain(_vector_store, _llm, _memory):
    retriever = _vector_store.as_retriever(
        search_type="mmr",  # Diversity in top-k results
        search_kwargs={"k": 2, "fetch_k": 4, "lambda_mult": 0.5}  # Reduced for faster retrieval
    )

    chain = ConversationalRetrievalChain.from_llm(
        llm=_llm,
        chain_type='stuff',  # Use 'stuff' for compatibility with custom prompt; larger context handles it
        retriever=retriever,
        memory=_memory,
        combine_docs_chain_kwargs={"prompt": QA_CHAIN_PROMPT}  # Enforce completeness
    )
    return chain

chain = create_chain(vector_store, llm, memory)

# Define chat function with adjusted truncation detection for speed
# Modified to return answer and response_time
def conversation_chat(query):
    start_time = time.time()
    result = chain({"question": query, "chat_history": st.session_state['history']})
    end_time = time.time()
    response_time = end_time - start_time
    answer = result["answer"]
    
    # Less aggressive truncation detection to avoid unnecessary retries (threshold increased)
    # if len(answer.split()) < 20 or not answer.strip().endswith(('.', '!', '?', '\n')):
    #     st.warning("Initial response may be incomplete; regenerating with extended focus...")
    #     # Retry with augmented query to encourage completeness
    #     retry_start = time.time()
    #     retry_result = chain({"question": f"{query} [Provide a complete, detailed response without truncation]", 
    #                           "chat_history": st.session_state['history']})
    #     answer = retry_result["answer"]
    #     retry_end = time.time()
    #     response_time = retry_end - start_time  # Update total time
    #     result = retry_result  # Update for logging
    
    # Enhanced logging
    with open('query_log.txt', 'a') as f:
        f.write(f"Query: {query}\nResponse: {answer}\nContext Length: {len(result.get('context', ''))}\n---\n")
    
    st.session_state['history'].append((query, answer))
    return answer, response_time

# Chat UI
reply_container = st.container()

# Display chat history
if st.session_state['generated']:
    with reply_container:
        for i in range(len(st.session_state['generated'])):
            message(st.session_state["past"][i], is_user=True, key=str(i) + '_user', avatar_style="thumbs")
            message(st.session_state["generated"][i], key=str(i), avatar_style="fun-emoji")

container = st.container()

with container:
    with st.form(key='my_form', clear_on_submit=True):
        user_input = st.text_input("Question:", placeholder="Ask about services in Vught", key='input')
        submit_button = st.form_submit_button(label='Send')

    if submit_button and user_input:
        # New submission: append and display immediately
        current_len = len(st.session_state['past'])
        st.session_state['past'].append(user_input)
        st.session_state['generated'].append("Processing your query...")
        
        # Immediately display the new user and processing message
        with reply_container:
            message(user_input, is_user=True, key=str(current_len) + '_user', avatar_style="thumbs")
            message("Processing your query...", key=str(current_len), avatar_style="fun-emoji")
        
        # Process the query
        output, response_time = conversation_chat(user_input)
        
        # Update the last generated response
        st.session_state['generated'][-1] = output
        
        # Show response time info
        st.info(f"Response generated in {response_time:.2f} seconds.")
        
        # Rerun to update the display with the final response
        st.rerun()