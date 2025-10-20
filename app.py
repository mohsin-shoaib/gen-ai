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

# Function to split text into chunks
def split_text_into_chunks(documents):
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    text_chunks = text_splitter.split_documents(documents)
    return text_chunks

# Function to create embeddings with CPU support
def create_embeddings():
    device = "cpu"  # Explicitly CPU since no GPU
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
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

# Function to create LLMs model optimized for CPU with Mistral-7B
def create_llms_model(model_path="./mistral-7b"):
    # Determine physical cores for threading
    physical_cores = len(os.sched_getaffinity(0)) // 2 if hasattr(os, 'sched_getaffinity') else os.cpu_count() // 2 or 4
    
    config = {
        'max_new_tokens': 80,  # Reduced for faster generation and brevity
        'temperature': 0.01,
        'gpu_layers': 0,  # Explicitly CPU-only
        'threads': physical_cores,  # Optimize for CPU cores
        'context_length': 2048  # Limit context to reduce KV cache overhead
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

# Custom prompt for brevity
template = """Use the following context to answer the question briefly. Limit response to essential details.
Context: {context}
Question: {question}
Concise Answer:"""
QA_CHAIN_PROMPT = PromptTemplate.from_template(template)

# Create chain with optimized parameters
@st.cache_resource
def create_chain(_vector_store, _llm, _memory):
    chain = ConversationalRetrievalChain.from_llm(
        llm=_llm,
        chain_type='stuff',
        retriever=_vector_store.as_retriever(
            search_type="similarity",
            search_kwargs={"k": 2}  # Reduced for faster retrieval
        ),
        memory=_memory,
        combine_docs_chain_kwargs={"prompt": QA_CHAIN_PROMPT}  # Enforce brevity
    )
    return chain

chain = create_chain(vector_store, llm, memory)

# Define chat function with optional benchmarking
def conversation_chat(query):
    start_time = time.time()
    result = chain({"question": query, "chat_history": st.session_state['history']})
    end_time = time.time()
    response_time = end_time - start_time
    st.info(f"Response generated in {response_time:.2f} seconds.")  # Optional feedback
    st.session_state['history'].append((query, result["answer"]))
    return result["answer"]

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
