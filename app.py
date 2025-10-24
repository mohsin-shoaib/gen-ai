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

# Enhanced function to split text into chunks with metadata extraction
def split_text_into_chunks(documents):
    # Load raw text for parsing
    raw_text = documents[0].page_content  # Assuming single MD file
    
    # Regex to extract sections (adapt patterns to your MD format)
    section_pattern = r'###\s*(.*?)\n\*\*Organization:\*\*\s*(.*?)\n\*\*URL:\*\*\s*(.*?)\n\*\*Objective:\*\*\s*(.*?)(?=\n---\n###|\Z)'
    sections = re.findall(section_pattern, raw_text, re.DOTALL | re.MULTILINE)
    
    chunks = []
    for i, (title, org, url, content) in enumerate(sections):
        # Split content into sub-chunks if long, preserving metadata
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=400, chunk_overlap=100)  # Smaller chunks for structure
        sub_docs = text_splitter.create_documents([content])
        
        for sub_doc in sub_docs:
            sub_doc.metadata.update({
                'organization': org.strip(),
                'url': url.strip(),
                'section_type': title.strip(),  # e.g., "(Gym) clothing and shoes"
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
        'max_new_tokens': 300,  # Increased for fuller responses
        'temperature': 0.05,  # Lower for factual consistency
        'gpu_layers': 0,  # Explicitly CPU-only
        'threads': physical_cores,  # Optimize for CPU cores
        'context_length': 4096,  # Increased to accommodate larger contexts
        'top_k': 40,  # Limit sampling for speed
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

# Enhanced custom prompt for completeness and structure
template = """You are a helpful assistant for community services in Vught. Use the provided context to answer the question completely and accurately, focusing on key details like objectives, target audiences, missions, and contacts. Structure responses with bullets if multiple items are relevant. Limit to 200-250 words for brevity, but ensure all essential information is included without truncation. If no exact match, suggest related services.

Context: {context}

Question: {question}

Complete Answer:"""
QA_CHAIN_PROMPT = PromptTemplate.from_template(template)

# Enhanced chain creation with MMR retriever and stuff chain type (compatible with custom prompt)
@st.cache_resource
def create_chain(_vector_store, _llm, _memory):
    retriever = _vector_store.as_retriever(
        search_type="mmr",  # Diversity in top-k results
        search_kwargs={"k": 3, "fetch_k": 6, "lambda_mult": 0.5}  # Reduced fetch_k to fit context
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

# Define chat function with truncation detection, retry, benchmarking, and logging
def conversation_chat(query):
    start_time = time.time()
    result = chain({"question": query, "chat_history": st.session_state['history']})
    end_time = time.time()
    response_time = end_time - start_time
    answer = result["answer"]
    
    # Detect potential truncation (heuristic: short length or incomplete punctuation)
    if len(answer.split()) < 30 or not answer.strip().endswith(('.', '!', '?', '\n')):
        st.warning("Initial response may be incomplete; regenerating with extended focus...")
        # Retry with augmented query to encourage completeness
        retry_result = chain({"question": f"{query} [Provide a complete, detailed response without truncation]", 
                              "chat_history": st.session_state['history']})
        answer = retry_result["answer"]
        response_time = time.time() - start_time  # Update total time
    
    st.info(f"Response generated in {response_time:.2f} seconds.")
    
    # Enhanced logging
    with open('query_log.txt', 'a') as f:
        f.write(f"Query: {query}\nResponse: {answer}\nContext Length: {len(result.get('context', ''))}\n---\n")
    
    st.session_state['history'].append((query, answer))
    return answer

# Display chat history
reply_container = st.container()
container = st.container()

with container:
    with st.form(key='my_form', clear_on_submit=True):
        user_input = st.text_input("Question:", placeholder="Ask about services in Vught", key='input')
        submit_button = st.form_submit_button(label='Send')

    if submit_button and user_input:
        with st.spinner('Processing your query...'):
            output = conversation_chat(user_input)
        st.session_state['past'].append(user_input)
        st.session_state['generated'].append(output)

if st.session_state['generated']:
    with reply_container:
        for i in range(len(st.session_state['generated'])):
            message(st.session_state["past"][i], is_user=True, key=str(i) + '_user', avatar_style="thumbs")
            message(st.session_state["generated"][i], key=str(i), avatar_style="fun-emoji")