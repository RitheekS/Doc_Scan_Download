import pandas as pd
import requests
from pathlib import Path
import re
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException

# --- Configuration ---
EXCEL_PATH = "C:/"  # Update this!
DOWNLOAD_DIR = Path.home() / "Downloads"
BASE_URL = "" #replace with initial (prefix) URL

def setup_environment():
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Downloads will be saved to: {DOWNLOAD_DIR}")

def main():
    setup_environment()
    
    print(f"Reading Excel file: {EXCEL_PATH}")
    try:
        df = pd.read_excel(EXCEL_PATH, usecols="R")
    except Exception as e:
        print(f"Failed to read Excel file: {e}")
        return
    
    identifiers = df.iloc[:, 0].dropna().tolist()
    print(f"Found {len(identifiers)} items to process.\n")
    
    # Initialize Chrome Browser
    print("Launching Chrome browser...")
    options = webdriver.ChromeOptions()
    # Mute audio in case of ads
    options.add_argument("--mute-audio") 
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    for item in identifiers:
        item = str(item).strip()
        if not item:
            continue
            
        safe_name = re.sub(r'[\\/*?:"<>|]', "_", item)
        file_path = DOWNLOAD_DIR / f"{safe_name}.pdf"
        
        if file_path.exists():
            print(f"[-] Skipping {safe_name} (Already exists)")
            continue

        url = f"{BASE_URL}{item}"
        print(f"Processing: {item}")
        driver.get(url)
        
        pdf_url = None
        timeout = 60  # Wait up to 60 seconds for a CAPTCHA to be solved
        elapsed = 0
        
        # Wait for the PDF embed to appear (or for you to solve the CAPTCHA)
        while elapsed < timeout:
            try:
                # Aggressive search: Check embeds, iframes, and ALL links/buttons for '.pdf'
                pdf_url = driver.execute_script("""
                    // 1. Check standard embeds
                    let embed = document.querySelector('embed');
                    if (embed && embed.src) return embed.src;
                    
                    let iframe = document.querySelector('iframe');
                    if (iframe && iframe.src && !iframe.src.includes('challenge')) return iframe.src;
                    
                    // 2. Check every single anchor tag on the page for a PDF link
                    let links = document.querySelectorAll('a');
                    for (let a of links) {
                        if (a.href && (a.href.includes('.pdf') || a.href.includes('download'))) return a.href;
                    }
                    
                    // 3. Check every single button on the page for a redirect script
                    let buttons = document.querySelectorAll('button');
                    for (let btn of buttons) {
                        let click = btn.getAttribute('onclick');
                        if (click && (click.includes('.pdf') || click.includes('location.href'))) {
                            let match = click.match(/['"]([^'"]+)['"]/);
                            if (match) return match[1];
                        }
                    }
                    
                    return null;
                """)

                if pdf_url:
                    break  # Successfully found the PDF link
                    
            except Exception:
                pass

            # Check if we hit a dead end
            page_text = driver.page_source.lower()
            
            # Common text and HTML elements Sci-Hub uses for missing papers
            missing_indicators = [
                "alas, the following paper is not yet available in my database",
                "recent papers are mostly unavailable",
                "i do not have any papers matching your request",
                "article not found",
                "unfortunately",
                "could not find",
                "doesn't have the requested",
                'id="smile"'
            ]
            
            # 1. Check if the page contains any 'missing paper' indicators
            if any(indicator in page_text for indicator in missing_indicators):
                print(f"[-] Article {item} does not exist on Sci-Hub.")
                break
                
            # 2. Check if it redirected to the main search page (has a search box but no captcha)
            if 'name="request"' in page_text and 'captcha' not in page_text:
                print(f"[-] Article {item} not found (Redirected to homepage).")
                break
                
            print("[!] Waiting for page to load or CAPTCHA to be solved...")
            
            # DEBUGGING: If we've been waiting for 15 seconds, save the HTML so we can inspect it
            if elapsed == 15:
                debug_file = DOWNLOAD_DIR / "debug_page.html"
                with open(debug_file, "w", encoding="utf-8") as f:
                    f.write(driver.page_source)
                print(f"[?] Saved page source to {debug_file} for inspection.")
                
            time.sleep(3)
            elapsed += 3

            # Check if we hit a dead end
            page_text = driver.page_source.lower()
            if "article not found" in page_text:
                print("[-] Article not found on Sci-Hub.")
                break
                
            print("[!] Waiting for page to load or CAPTCHA to be solved...")
            time.sleep(3)
            elapsed += 3
        
        # Download the file using the browser's cleared cookies
        if pdf_url:
            if pdf_url.startswith('//'):
                pdf_url = 'https:' + pdf_url
            elif pdf_url.startswith('/'):
                pdf_url = BASE_URL.rstrip('/') + pdf_url
            
            # Extract clearance cookies and User-Agent from Selenium
            cookies = {cookie['name']: cookie['value'] for cookie in driver.get_cookies()}
            headers = {'User-Agent': driver.execute_script("return navigator.userAgent;")}
            
            try:
                response = requests.get(pdf_url, cookies=cookies, headers=headers, stream=True, timeout=30)
                response.raise_for_status()
                
                with open(file_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                print(f"[+] Successfully downloaded: {safe_name}.pdf")
            except Exception as e:
                print(f"[!] Failed to download {pdf_url}: {e}")
        else:
            if elapsed >= timeout:
                print(f"[-] Timed out waiting for PDF link on {item}.")
                
        time.sleep(1)

    driver.quit()
    print("All downloads complete.")

if __name__ == "__main__":
    main()
