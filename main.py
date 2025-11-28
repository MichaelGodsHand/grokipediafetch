from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from datetime import datetime
import time
import re


app = FastAPI(title="Grokipedia Scraper API")


class SearchRequest(BaseModel):
    query: str
    headless: bool = True


def format_content_with_sections(content_text, section_titles):
    """
    Post-process content to add section headers based on found titles
    
    Args:
        content_text: Raw text content
        section_titles: List of section titles found in the page
    
    Returns:
        Formatted text with section headers
    """
    if not section_titles or not content_text:
        return content_text
    
    print(f"🔧 Post-processing content with {len(section_titles)} section titles...")
    
    formatted_parts = []
    lines = content_text.split('\n')
    
    for i, line in enumerate(lines):
        line_stripped = line.strip()
        
        # Check if this line matches any section title
        is_section_title = False
        for title in section_titles:
            if line_stripped == title or line_stripped.startswith(title):
                # Add formatted section header
                formatted_parts.append(f"\n\n{'='*70}\n{title}\n{'='*70}\n\n")
                is_section_title = True
                break
        
        # If not a section title, add the line as-is
        if not is_section_title and line_stripped:
            formatted_parts.append(line)
    
    formatted_text = '\n'.join(formatted_parts)
    
    # Clean up excessive newlines
    formatted_text = re.sub(r'\n{4,}', '\n\n', formatted_text)
    
    print(f"✓ Content formatted with section headers")
    return formatted_text


class GrokipediaSeleniumScraper:
    """Scraper for Grokipedia using Selenium WebDriver"""
    
    def __init__(self, headless=False):
        """
        Initialize the scraper with Chrome WebDriver
        
        Args:
            headless: Run browser in headless mode (no GUI)
        """
        options = webdriver.ChromeOptions()
        
        if headless:
            options.add_argument('--headless')
        
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        self.driver = webdriver.Chrome(options=options)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        self.wait = WebDriverWait(self.driver, 10)
    
    def search_and_scrape(self, query):
        """
        Search for a query on Grokipedia and scrape the first result
        
        Args:
            query: Search term
        
        Returns:
            Dictionary containing scraped data
        """
        try:
            print(f"🌐 Opening Grokipedia...")
            self.driver.get("https://grokipedia.com/")
            
            # Wait for page to load
            time.sleep(2)
            
            # Find the search input box
            print(f"🔍 Searching for: {query}")
            search_input = self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text'], input.w-full"))
            )
            
            # Clear any existing text and type the query
            search_input.clear()
            search_input.send_keys(query)
            time.sleep(1)
            
            # Press Enter to search
            search_input.send_keys(Keys.RETURN)
            print("⏳ Waiting for search results...")
            time.sleep(4)
            
            # Try to find and click the correct search result
            try:
                print("🔍 Looking for search results...")
                
                # Strategy 1: Find result that EXACTLY matches the query
                try:
                    # Look for elements with the exact query text
                    results = self.driver.find_elements(By.XPATH, 
                        f"//div[contains(@class, 'cursor-pointer')]//span[normalize-space(text())='{query.title()}']")
                    
                    if results:
                        result = results[0]
                        result_parent = result.find_element(By.XPATH, "./ancestor::div[contains(@class, 'cursor-pointer')]")
                        print(f"✓ Found exact match: '{result.text}'")
                        
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", result_parent)
                        time.sleep(0.5)
                        self.driver.execute_script("arguments[0].click();", result_parent)
                        print("✓ Clicked exact match!")
                        time.sleep(3)
                    else:
                        raise Exception("No exact match found")
                        
                except Exception as e:
                    print(f"⚠️ Exact match strategy failed: {str(e)}")
                    
                    # Strategy 2: Try case-insensitive match
                    print("Trying case-insensitive match...")
                    try:
                        results = self.driver.find_elements(By.XPATH, 
                            f"//div[contains(@class, 'cursor-pointer')]//span[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{query.lower()}')]")
                        
                        if results:
                            # Find the shortest matching text (most likely to be the main article)
                            best_result = min(results, key=lambda r: len(r.text))
                            result_parent = best_result.find_element(By.XPATH, "./ancestor::div[contains(@class, 'cursor-pointer')]")
                            print(f"✓ Found match: '{best_result.text}'")
                            
                            self.driver.execute_script("arguments[0].scrollIntoView(true);", result_parent)
                            time.sleep(0.5)
                            self.driver.execute_script("arguments[0].click();", result_parent)
                            print("✓ Clicked!")
                            time.sleep(3)
                        else:
                            raise Exception("No match found")
                            
                    except Exception as e2:
                        print(f"⚠️ Case-insensitive strategy failed: {str(e2)}")
                        
                        # Strategy 3: Direct navigation
                        print("Trying direct navigation...")
                        page_url = f"https://grokipedia.com/page/{query.replace(' ', '_').title()}"
                        print(f"📍 Navigating to: {page_url}")
                        self.driver.get(page_url)
                        time.sleep(3)
                        
            except Exception as e:
                print(f"⚠️ Error in result selection: {str(e)}")
                print("Attempting direct navigation as fallback...")
                page_url = f"https://grokipedia.com/page/{query.replace(' ', '_').title()}"
                self.driver.get(page_url)
                time.sleep(3)
            
            # Verify we're on the correct page
            current_url = self.driver.current_url
            if "search?q=" in current_url:
                print("⚠️ Still on search results page. Attempting direct navigation...")
                page_url = f"https://grokipedia.com/page/{query.replace(' ', '_').title()}"
                self.driver.get(page_url)
                time.sleep(3)
            
            # Now scrape the article content
            print("📖 Scraping article content...")
            data = self._scrape_article_page()
            
            return data
            
        except Exception as e:
            print(f"❌ Error during scraping: {str(e)}")
            return {"error": str(e)}
    
    def _scrape_article_page(self):
        """Scrape content from the article page with proper structure"""
        try:
            time.sleep(2)
            
            current_url = self.driver.current_url
            print(f"📍 Current URL: {current_url}")
            
            # Get the main title
            title = "Title not found"
            title_selectors = ["h1", "h1.text-3xl", "h1.font-bold"]
            
            for selector in title_selectors:
                try:
                    title_element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if title_element.text.strip():
                        title = title_element.text.strip()
                        print(f"✓ Found title: {title}")
                        break
                except NoSuchElementException:
                    continue
            
            url = self.driver.current_url
            
            # Find the main article container
            content_selectors = [
                "article",
                "main", 
                "[role='main']",
                "div.prose",
                "div[class*='content']"
            ]
            
            content_container = None
            for selector in content_selectors:
                try:
                    content_container = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if content_container:
                        print(f"✓ Found content container using: {selector}")
                        break
                except NoSuchElementException:
                    continue
            
            if not content_container:
                print("⚠️ No specific content container found, using body")
                content_container = self.driver.find_element(By.TAG_NAME, "body")
            
            # Extract structured content
            print("📝 Extracting structured content...")
            
            structured_content = []
            all_text_parts = []
            
            # Get all headings and paragraphs
            all_elements = content_container.find_elements(By.CSS_SELECTOR, "h1, h2, h3, h4, h5, h6, p")
            
            if not all_elements:
                print("⚠️ No structured elements found, trying alternative extraction...")
                all_elements = self.driver.find_elements(By.CSS_SELECTOR, "h1, h2, h3, h4, h5, h6, p")
            
            current_section = {
                'title': None,
                'level': 0,
                'content': []
            }
            
            section_count = 0
            paragraph_count = 0
            
            # First pass: identify all sections and paragraphs with their positions
            elements_data = []
            for idx, element in enumerate(all_elements):
                try:
                    tag_name = element.tag_name.lower()
                    text = element.text.strip()
                    
                    if not text or len(text) < 3:
                        continue
                    
                    # Store element info
                    if tag_name.startswith('h'):
                        level = int(tag_name[1])
                        elements_data.append({
                            'type': 'heading',
                            'text': text,
                            'level': level,
                            'index': idx
                        })
                        print(f"  📌 Section: {text}")
                    elif tag_name == 'p' and len(text) > 20:
                        elements_data.append({
                            'type': 'paragraph',
                            'text': text,
                            'index': idx
                        })
                        
                except Exception as e:
                    continue
            
            # Second pass: group paragraphs under their sections
            for i, elem in enumerate(elements_data):
                if elem['type'] == 'heading':
                    # Save previous section if it exists
                    if current_section['title'] and current_section['content']:
                        structured_content.append(current_section)
                        section_count += 1
                        
                        # Format section for output
                        all_text_parts.append(f"\n\n{'='*70}\n")
                        all_text_parts.append(f"{current_section['title']}\n")
                        all_text_parts.append(f"{'='*70}\n\n")
                        all_text_parts.append("\n\n".join(current_section['content']))
                    
                    # Start new section
                    current_section = {
                        'title': elem['text'],
                        'level': elem['level'],
                        'content': []
                    }
                    
                    # Collect all paragraphs until next heading
                    j = i + 1
                    while j < len(elements_data) and elements_data[j]['type'] == 'paragraph':
                        current_section['content'].append(elements_data[j]['text'])
                        paragraph_count += 1
                        j += 1
            
            # Add the last section
            if current_section['title'] and current_section['content']:
                structured_content.append(current_section)
                section_count += 1
                all_text_parts.append(f"\n\n{'='*70}\n")
                all_text_parts.append(f"{current_section['title']}\n")
                all_text_parts.append(f"{'='*70}\n\n")
                all_text_parts.append("\n\n".join(current_section['content']))
            
            # Combine all text
            content_text = "".join(all_text_parts)
            
            print(f"✓ Extracted {section_count} sections with {paragraph_count} paragraphs")
            
            # Fallback: if no structured content, try getting all paragraphs
            if not content_text or len(content_text) < 100:
                print("⚠️ Minimal structured content, trying paragraph extraction...")
                
                try:
                    all_paragraphs = content_container.find_elements(By.TAG_NAME, "p")
                    texts = []
                    
                    for p in all_paragraphs:
                        text = p.text.strip()
                        if text and len(text) > 20:
                            texts.append(text)
                    
                    if texts:
                        content_text = "\n\n".join(texts)
                        print(f"✓ Extracted {len(texts)} paragraphs as fallback")
                except Exception as e:
                    print(f"⚠️ Paragraph extraction failed: {str(e)}")
            
            # Final fallback: get all visible text
            if not content_text or len(content_text) < 50:
                print("⚠️ Using final fallback: extracting all visible text...")
                try:
                    # Try to get text from main content area only
                    content_text = content_container.text
                except:
                    # Last resort: get all body text
                    body = self.driver.find_element(By.TAG_NAME, "body")
                    content_text = body.text
            
            # Get metadata
            word_count = len(content_text.split())
            char_count = len(content_text)
            
            print(f"📊 Final stats: {word_count:,} words, {char_count:,} characters")
            
            # Extract references
            references = []
            try:
                ref_elements = self.driver.find_elements(By.CSS_SELECTOR, "a[href^='http']")
                seen_urls = set()
                
                for ref in ref_elements:
                    try:
                        href = ref.get_attribute('href')
                        if href and 'grokipedia.com' not in href and href not in seen_urls:
                            seen_urls.add(href)
                            references.append({
                                'number': len(references) + 1,
                                'url': href
                            })
                            
                            if len(references) >= 100:
                                break
                    except Exception:
                        continue
                        
                print(f"📚 Found {len(references)} external references")
            except Exception as e:
                print(f"⚠️ Could not extract references: {str(e)}")
            
            # Post-processing: Extract section titles for formatting even if structured extraction failed
            section_titles = []
            if not structured_content or len(structured_content) == 0:
                print("📝 Extracting section titles for post-processing...")
                try:
                    # Find all heading elements
                    heading_elements = content_container.find_elements(By.CSS_SELECTOR, "h1, h2, h3, h4, h5, h6")
                    for heading in heading_elements:
                        heading_text = heading.text.strip()
                        if heading_text and len(heading_text) > 2 and heading_text != title:
                            section_titles.append(heading_text)
                    
                    print(f"✓ Found {len(section_titles)} section titles for formatting")
                except Exception as e:
                    print(f"⚠️ Could not extract section titles: {str(e)}")
            
            # Apply post-processing if we have section titles but no structured content
            # This ensures the content_text matches the format after postprocessing
            if section_titles and (not structured_content or len(structured_content) == 0):
                print(f"🔧 Applying post-processing formatting...")
                content_text = format_content_with_sections(content_text, section_titles)
                # Recalculate word and char counts after postprocessing
                word_count = len(content_text.split())
                char_count = len(content_text)
                print(f"📊 Updated stats after post-processing: {word_count:,} words, {char_count:,} characters")
            
            return {
                'title': title,
                'url': url,
                'content_text': content_text,
                'word_count': word_count,
                'char_count': char_count,
                'references_count': len(references),
                'references': references,
                'structured_content': structured_content if structured_content else None,
                'section_titles': section_titles if section_titles else None
            }
            
        except Exception as e:
            print(f"❌ Error scraping article: {str(e)}")
            return {"error": f"Failed to scrape article: {str(e)}"}
    
    def close(self):
        """Close the browser"""
        if self.driver:
            self.driver.quit()


@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "Grokipedia Scraper API",
        "version": "1.0",
        "endpoints": {
            "/scrape": "POST - Scrape Grokipedia content for a query",
            "/health": "GET - Health check"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }


@app.post("/scrape")
async def scrape_grokipedia(request: SearchRequest):
    """
    Scrape Grokipedia for a given search query
    
    Args:
        request: SearchRequest with query and optional headless parameter
    
    Returns:
        Scraped content data
    """
    if not request.query or not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    
    scraper = None
    try:
        print(f"\n{'='*80}")
        print(f"NEW REQUEST: {request.query}")
        print(f"{'='*80}\n")
        
        scraper = GrokipediaSeleniumScraper(headless=request.headless)
        data = scraper.search_and_scrape(request.query)
        
        if "error" in data:
            raise HTTPException(status_code=500, detail=data["error"])
        
        # Add timestamp to response
        data['timestamp'] = datetime.now().isoformat()
        data['query'] = request.query
        
        print(f"\n✅ Request completed successfully")
        return data
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"\n❌ Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Scraping failed: {str(e)}")
    
    finally:
        if scraper:
            print("🔒 Closing browser...")
            scraper.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
