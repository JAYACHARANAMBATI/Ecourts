import os
import time
import requests
from io import BytesIO
from PIL import Image
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from langchain_community.document_loaders import TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain.prompts import PromptTemplate
from langchain.chains import RetrievalQA

# === CONFIGURATION ===
CHROME_DRIVER_PATH = r"C:\\Users\\91964\\OneDrive\\Desktop\\Ecourts\\chromedriver-win64\\chromedriver.exe"
CNR_NUMBER = "APKR060043112021"
os.environ["GOOGLE_API_KEY"] = "AIzaSyCaiCtwdbOuUrWmuR6Z_RZPSPKj4v5dHT0"

# === Step 1: Open eCourts ===
service = Service(CHROME_DRIVER_PATH)
driver = webdriver.Chrome(service=service)
driver.get("https://services.ecourts.gov.in/ecourtindia_v6/")

# === Step 2: Enter CNR and show CAPTCHA ===
try:
    cnr_input = WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "cino")))
    cnr_input.clear()
    cnr_input.send_keys(CNR_NUMBER)
    print("✅ CNR number entered.")

    captcha_img_elem = WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "captcha_image")))
    captcha_img_url = captcha_img_elem.get_attribute("src")
    if captcha_img_url.startswith("/"):
        captcha_img_url = "https://services.ecourts.gov.in" + captcha_img_url

    img_data = requests.get(captcha_img_url).content
    image = Image.open(BytesIO(img_data))
    image.show()
    print("📸 CAPTCHA image opened.")
except Exception as e:
    print("❌ CAPTCHA loading failed:", e)
    driver.quit()
    exit()

# === Step 3: Ask user for CAPTCHA ===
captcha_text = input("🔡 Enter CAPTCHA as seen in image: ")

# === Step 4: Submit the form ===
try:
    captcha_input = driver.find_element(By.ID, "fcaptcha_code")
    captcha_input.clear()
    captcha_input.send_keys(captcha_text)
    driver.find_element(By.ID, "searchbtn").click()
    print("📨 Form submitted.")
except Exception as e:
    print("❌ CAPTCHA submission error:", e)
    driver.quit()
    exit()

# === Step 5: Extract base case details ===
time.sleep(5)
soup = BeautifulSoup(driver.page_source, "html.parser")
case_text = soup.get_text(separator="\n")

with open("case_data.txt", "w", encoding="utf-8") as f:
    f.write("=== BASE CASE DETAILS ===\n")
    f.write(case_text)

if "Case details not found" in case_text:
    print("⚠️ Invalid CNR or CAPTCHA.")
    driver.quit()
    exit()

# === Step 6: Extract hearing details ===
print("🔄 Extracting hearing details...")
links = driver.find_elements(By.XPATH, "//a[contains(@onclick, 'viewBusiness')]")
print(f"📅 Found {len(links)} hearing entries.")

with open("case_data.txt", "a", encoding="utf-8") as f:
    f.write("\n\n=== HEARING DETAILS ===\n")

    for index, link in enumerate(links):
        try:
            print(f"\n🔎 Extracting hearing {index + 1}...")
            driver.execute_script("arguments[0].scrollIntoView(true);", link)
            time.sleep(0.5)
            driver.execute_script("arguments[0].click();", link)
            time.sleep(2.5)

            full_text = driver.execute_script("return document.body.innerText")
            lines = full_text.splitlines()

            business = next((line for line in lines if "Business" in line), "Business: Not available")
            purpose = next((line for line in lines if "Next Purpose" in line), "Next Purpose: Not available")
            hearing_date = next((line for line in lines if "Date" in line), "Date: Not available")
            next_hearing = next((line for line in lines if "Next Hearing Date" in line), "Next Hearing Date: Not available")

            f.write(f"\n--- HEARING {index + 1} ---\n")
            f.write(f"📅 Hearing Date: {hearing_date}\n")
            f.write(f"📌 Business: {business}\n")
            f.write(f"🎯 Purpose: {purpose}\n")
            f.write(f"⏭️ Next Hearing Date: {next_hearing}\n")
            print(f"✅ Hearing {index + 1} saved.")
        except Exception as e:
            print(f"❌ Failed to extract hearing {index + 1}: {e}")

print("✅ All hearing details saved.")
driver.quit()

# === Step 7: Load data into Gemini Flash 1.5 + RAG chatbot ===
print("⚙️ Loading data into Gemini Flash 1.5...")

loader = TextLoader("case_data.txt", encoding="utf-8")
docs = loader.load()

splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
chunks = splitter.split_documents(docs)

embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001")
vectorstore = FAISS.from_documents(chunks, embeddings)

llm = ChatGoogleGenerativeAI(model="models/gemini-1.5-flash", temperature=0.2)

system_prompt = """You are an intelligent legal assistant chatbot working with Indian court hearing records.

You will be given context from official court case data. Your job is to extract and summarize key information for a specific date or all hearing dates.

When the user asks for a specific date (e.g., 28-01-2022), search the context for that date and return all available information in this format:

---

📅 Hearing Date: <hearing_date>  
📌 Business: <business or 'Not available'>  
🎯 Purpose: <purpose or 'Not available'>  
⏭️ Next Hearing Date: <next_hearing_date or 'Not available'>

---

✅ If the user doesn't specify a date and asks for *all* hearings, list each hearing in the above format.

❌ If no information is available for that date, respond with: "No information available for that date."

🎯 Keep your answers brief, structured, and complete.
"""

# IMPORTANT: Change input variable to 'documents'
prompt = PromptTemplate(
    input_variables=["documents", "question"],
    template=system_prompt + "\n\nQuestion: {question}\nAnswer:"
)

qa_chain = RetrievalQA.from_chain_type(
    llm=llm,
    chain_type="stuff",
    retriever=vectorstore.as_retriever(),
    chain_type_kwargs={"prompt": prompt}
)

# === Step 8: Interactive chatbot ===
print("\n🤖 Ask questions about the case (type 'exit' to quit):")
while True:
    query = input("❓ Question: ")
    if query.lower() == "exit":
        break
    result = qa_chain.run(query)
    print("\n💬 Answer:\n", result, "\n")
