import pandas as pd
import time
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager

# --- KONFIGURASI ---
LIST_URL = "https://www.komdigi.go.id/berita/berita-hoaks"
CSV_FILE = "hoax_data_complete.csv"
MAX_PAGES = 1298  # Ubah jumlah halaman yang ingin diambil

def setup_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    return driver

def remove_widgets(driver):
    """Hapus widget yang menutupi"""
    try:
        driver.execute_script("""
            var selectors = ['#widget_menu_disabilitas', '#hm-wrapper-translator', '.circle_aksesbilitas_popup', 'nav.fixed'];
            selectors.forEach(s => {
                var el = document.querySelector(s);
                if(el) el.remove();
            });
        """)
    except: pass

def visualize_click_point(driver, element):
    """Visualisasi titik merah sebelum klik"""
    try:
        driver.execute_script("""
            var rect = arguments[0].getBoundingClientRect();
            var x = rect.left + (rect.width / 2);
            var y = rect.top + (rect.height / 2);
            var dot = document.createElement('div');
            dot.style.position = 'fixed';
            dot.style.left = x + 'px';
            dot.style.top = y + 'px';
            dot.style.width = '10px';
            dot.style.height = '10px';
            dot.style.backgroundColor = 'red';
            dot.style.zIndex = '1000000';
            dot.style.borderRadius = '50%';
            dot.style.pointerEvents = 'none';
            document.body.appendChild(dot);
            arguments[0].style.border = '2px solid red';
        """, element)
        time.sleep(1.5) # Jeda sebentar untuk melihat titik
    except: pass

def scrape_listing_and_nav(driver, max_pages):
    existing_urls = set()
    all_data = []
    if os.path.exists(CSV_FILE):
        try:
            df_exist = pd.read_csv(CSV_FILE)
            existing_urls = set(df_exist['url'].tolist())
            all_data = df_exist.to_dict('records')
        except: pass

    print(f"Mengunjungi: {LIST_URL}")
    driver.get(LIST_URL)
    time.sleep(5) 

    current_page = 1
    
    while current_page <= max_pages:
        print(f"\n=== Sedang Scraping Halaman {current_page} ===")
        remove_widgets(driver)

        # -----------------------------------------------------------
        # 1. SCRAPE DATA (JUDUL, URL, TANGGAL)
        # -----------------------------------------------------------
        try:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.grid.lg\\:grid-cols-3")))
            articles = driver.find_elements(By.CSS_SELECTOR, "div.grid.lg\\:grid-cols-3 > div.flex.flex-col")
            
            count_new = 0
            for article in articles:
                try:
                    link_el = article.find_element(By.TAG_NAME, "a")
                    url = link_el.get_attribute("href")
                    title = link_el.text

                    if url in existing_urls: continue

                    try:
                        date = article.find_elements(By.CSS_SELECTOR, "div.font-medium span")[-1].text
                    except: date = "-"

                    all_data.append({
                        'title': title, 'date': date, 'url': url,
                        'content': None, 'scraped_at': time.strftime("%Y-%m-%d")
                    })
                    existing_urls.add(url)
                    count_new += 1
                except: continue
            
            print(f"   [+] Berhasil mengambil {count_new} data baru.")
            pd.DataFrame(all_data).to_csv(CSV_FILE, index=False)

        except Exception as e:
            print(f"[ERROR Scraping]: {e}")

        # -----------------------------------------------------------
        # 2. NAVIGASI (Tanpa Validasi Rumit)
        # -----------------------------------------------------------
        if current_page < max_pages:
            try:
                print(">> Mencari tombol Next...")
                
                # XPath Fingerprint SVG (Tetap dipakai karena akurat)
                xpath_fingerprint = "//*[name()='path' and contains(@d, 'M10.2 9L13.8')]/ancestor::button"
                candidates = driver.find_elements(By.XPATH, xpath_fingerprint)
                
                if not candidates:
                    print("[INFO] Tombol Next tidak ditemukan (Mungkin halaman terakhir).")
                    break
                
                next_btn = candidates[-1]

                # Scroll & Visualize
                driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});", next_btn)
                time.sleep(1)
                visualize_click_point(driver, next_btn)

                # KLIK
                print(">> Mengklik tombol...")
                actions = ActionChains(driver)
                actions.move_to_element(next_btn).click().perform()
                
                # --- PERUBAHAN: HANYA SLEEP SAJA ---
                print(">> Menunggu 5 detik untuk reload halaman...")
                time.sleep(5) 
                
                current_page += 1

            except Exception as e:
                print(f"[ERROR Navigasi]: {e}")
                break
        else:
            print("Mencapai batas halaman maksimum.")
            break

def scrape_details(driver):
    """TAHAP 2: Buka setiap link untuk ambil isi berita"""
    if not os.path.exists(CSV_FILE): return

    df = pd.read_csv(CSV_FILE)
    targets = df[df['content'].isnull()].index
    
    print(f"\n=== MENGAMBIL DETAIL KONTEN ({len(targets)} Artikel) ===")

    for i, idx in enumerate(targets):
        url = df.at[idx, 'url']
        print(f"[{i+1}/{len(targets)}] Membuka: {url}")
        
        try:
            driver.get(url)
            try:
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CLASS_NAME, "custom-body")))
                content = driver.find_element(By.CLASS_NAME, "custom-body").text
                df.at[idx, 'content'] = content
                print("   -> Konten tersimpan.")
            except:
                print("   -> Konten tidak ditemukan/Timeout.")
                df.at[idx, 'content'] = "ERR_NOT_FOUND"
        except Exception as e:
            print(f"   -> Error Link: {e}")
        
        if (i+1) % 5 == 0: df.to_csv(CSV_FILE, index=False)
        time.sleep(1)

    df.to_csv(CSV_FILE, index=False)
    print("\n=== SEMUA PROSES SELESAI ===")

if __name__ == "__main__":
    driver = setup_driver()
    try:
        scrape_listing_and_nav(driver, MAX_PAGES)
        scrape_details(driver)
    finally:
        print("Menutup browser...")
        driver.quit()