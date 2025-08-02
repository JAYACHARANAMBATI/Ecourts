import time, json
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

BASE_URL = "https://aphc.gov.in/csis_ap/"

chrome_options = Options()
chrome_options.add_argument("--start-maximized")
driver = webdriver.Chrome(options=chrome_options)
wait = WebDriverWait(driver, 20)

driver.get(BASE_URL)

# Click Advocate tab
advocate_tab = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@data-bs-target='#advocate']")))
advocate_tab.click()

# Select search type
print("\nSelect search type:")
print("1 - Advocate Code")
print("2 - Advocate Name")
print("3 - Advocate Phone Number")
choice = input("Enter choice (1/2/3): ").strip()

if choice == "1":
    search_type = "A"
elif choice == "2":
    search_type = "B"
elif choice == "3":
    search_type = "C"
else:
    print("Invalid choice")
    driver.quit()
    exit()

# Select radio button
radio_button = wait.until(EC.element_to_be_clickable(
    (By.XPATH, f"//input[@name='advsearchtype' and @value='{search_type}']")))
radio_button.click()

# Get inputs
adv_detail = input("Enter Advocate Name/Code/Phone: ").strip()
year = input("Enter Year (e.g., 2025): ").strip()

# Enter inputs
wait.until(EC.presence_of_element_located((By.ID, "advcode"))).send_keys(adv_detail)
wait.until(EC.presence_of_element_located((By.ID, "ayear"))).send_keys(year)

# Click submit
wait.until(EC.element_to_be_clickable((By.ID, "searchthree"))).click()

# Wait for results table OR no results message
try:
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.table-responsive.container-fluid table")))
    time.sleep(1)  # allow JS to fully render rows
except:
    print("\n[INFO] No results table found. Possibly no matches.")
    driver.quit()
    exit()

# Get table HTML
table_html = driver.find_element(By.CSS_SELECTOR, "div.table-responsive.container-fluid").get_attribute("outerHTML")
soup = BeautifulSoup(table_html, "html.parser")
rows = soup.find_all("tr")[1:]  # skip header

if not rows:
    print("\n[INFO] No records found for your search.")
    driver.quit()
    exit()

# Show advocate list
advocates = []
adv_links = driver.find_elements(By.CSS_SELECTOR, "div.table-responsive.container-fluid a")

print("\n[RESULTS]")
for idx, row in enumerate(rows, 1):
    cols = [td.get_text(strip=True) for td in row.find_all("td")]
    advocates.append({"index": idx, "details": cols})
    print(f"{idx}. {' | '.join(cols)}")

# Pick an advocate
try:
    adv_choice = int(input("\nEnter case number to open (1-N): ").strip())
except ValueError:
    print("Invalid selection")
    driver.quit()
    exit()

if not (1 <= adv_choice <= len(adv_links)):
    print("Invalid selection")
    driver.quit()
    exit()

# Open advocate modal
link_elem = adv_links[adv_choice - 1]
driver.execute_script("arguments[0].scrollIntoView(true);", link_elem)
time.sleep(0.5)
driver.execute_script("arguments[0].click();", link_elem)

# Wait for advocate modal table
wait.until(EC.visibility_of_element_located((By.ID, "mbody")))
time.sleep(1)

modal_html = driver.find_element(By.ID, "mbody").get_attribute("outerHTML")
modal_soup = BeautifulSoup(modal_html, "html.parser")

cases_data = []
case_rows = modal_soup.find_all("tr")

for case_row in case_rows:
    cols = [td.get_text(strip=True) for td in case_row.find_all("td")]
    if not cols:
        continue

    case_info = {
        "case_no": cols[1] if len(cols) > 1 else "",
        "details": cols
    }

    if "Not Registered" in cols[1]:
        case_info["status"] = "Not Registered"
        case_info["main_case_details"] = None
    else:
        try:
            # Find case link
            link_tag = case_row.find("a", onclick=True)
            if link_tag:
                case_link_elem = driver.find_element(By.XPATH, f"//a[@onclick=\"{link_tag['onclick']}\"]")
                driver.execute_script("arguments[0].scrollIntoView(true);", case_link_elem)
                time.sleep(0.5)
                driver.execute_script("arguments[0].click();", case_link_elem)

                wait.until(EC.visibility_of_element_located((By.ID, "compcasedet")))
                time.sleep(1)

                comp_html = driver.find_element(By.ID, "compcasedet").get_attribute("outerHTML")
                comp_soup = BeautifulSoup(comp_html, "html.parser")

                main_case_rows = []
                for tr in comp_soup.find_all("tr"):
                    tds = [td.get_text(strip=True) for td in tr.find_all("td")]
                    if tds:
                        main_case_rows.append(tds)

                case_info["status"] = "Registered"
                case_info["main_case_details"] = main_case_rows

                # Close modal
                driver.find_element(By.XPATH, "//div[@id='myModal']//button[@class='btn-close']").click()
                wait.until(EC.invisibility_of_element_located((By.ID, "compcasedet")))
        except Exception as e:
            case_info["status"] = "Error"
            case_info["error"] = str(e)

    cases_data.append(case_info)

# Save to JSON
filename = f"advocate_cases_{adv_detail}_{year}.json"
with open(filename, "w", encoding="utf-8") as f:
    json.dump(cases_data, f, ensure_ascii=False, indent=4)

print(f"\n✅ Saved all case data to {filename}")

input("\nPress ENTER to close browser...")
driver.quit()
