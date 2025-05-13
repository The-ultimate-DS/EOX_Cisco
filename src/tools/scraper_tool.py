import os
import requests
from typing import Dict, Any
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from crewai import tools
from langchain_openai import ChatOpenAI
from langchain.chains import create_extraction_chain

# Load environment variables
load_dotenv()

@tools.tool
def cisco_eol_scraper(url: str, product_id: str) -> Dict[str, Any]:
    """
    Scrape a web page for EOL information for a specific Cisco product.
    
    Args:
        url: The URL of the web page to scrape
        product_id: The Cisco product ID to extract information for
        
    Returns:
        Dictionary containing the extracted EOL information
    """
    try:
        # Check if the URL is valid
        if not url.startswith(("http://", "https://")):
            return {"error": f"Invalid URL: {url}"}
        
        # Get API key
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            return {"error": "OPENAI_API_KEY environment variable is required"}
        
        llm = ChatOpenAI(temperature=0, model="gpt-4o")
        
        # Download the web page
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            return {"error": f"Failed to download page: HTTP {response.status_code}"}
        
        # Parse the HTML content
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extract text content
        text_content = soup.get_text(separator=' ', strip=True)
        
        # Extract tables (common in Cisco bulletins)
        tables = soup.find_all('table')
        table_text = extract_tables(tables)
        
        # Combine regular text and table data
        combined_text = f"{text_content}\n\nTABLE DATA:\n{table_text}"
        
        # Extract structured data using LLM
        extraction_result = extract_eol_data(combined_text, product_id, llm)
        extraction_result["source_url"] = url
        
        return extraction_result
        
    except Exception as e:
        return {"error": f"Error scraping {url}: {str(e)}"}

def extract_tables(tables) -> str:
    """Extract data from HTML tables."""
    table_text = ""
    
    for i, table in enumerate(tables):
        table_text += f"Table {i+1}:\n"
        
        # Extract headers
        headers = []
        header_row = table.find('tr')
        if header_row:
            headers = [th.text.strip() for th in header_row.find_all(['th', 'td'])]
        
        # Extract rows
        for row in table.find_all('tr')[1:]:  # Skip header row
            cells = row.find_all('td')
            if cells:
                row_data = [cell.text.strip() for cell in cells]
                if len(headers) == len(row_data):
                    for h, d in zip(headers, row_data):
                        table_text += f"{h}: {d}\n"
                else:
                    # If headers don't match, just output the cells
                    table_text += ' | '.join(row_data) + "\n"
                table_text += "---\n"
        
    return table_text

def extract_eol_data(text: str, product_id: str, llm) -> Dict[str, Any]:
    """Extract structured EOL data using LLM."""
    # Define the extraction schema
    schema = {
        "properties": {
            "product_id": {"type": "string"},
            "product_description": {"type": "string"},
            "end_of_sale_date": {"type": "string"},
            "end_of_software_maintenance": {"type": "string"},
            "end_of_security_support": {"type": "string", "description": "End of vulnerability/security support date"},
            "end_of_support": {"type": "string", "description": "Last date of support"},
            "recommended_replacement": {"type": "string"},
            "bulletin_number": {"type": "string", "description": "EOL bulletin ID or number"}
        },
        "required": ["product_id"]
    }
    
    # Limit text length to avoid token limits
    max_text_length = 10000
    if len(text) > max_text_length:
        # Find the most relevant section
        product_idx = text.lower().find(product_id.lower())
        if product_idx != -1:
            # Take text around the product ID mention
            start_idx = max(0, product_idx - 4000)
            end_idx = min(len(text), product_idx + 6000)
            text = text[start_idx:end_idx]
        else:
            # Just take the beginning of the text
            text = text[:max_text_length]
    
    # Use extraction chain to get structured data
    extraction_chain = create_extraction_chain(schema, llm)
    result = extraction_chain.run(
        f"Extract the end-of-life information for Cisco product {product_id} from this text. "
        f"If exact information isn't available, use the closest match or family information: {text}"
    )
    
    if result and isinstance(result, list) and len(result) > 0:
        extracted_data = result[0]
        
        # Ensure product_id is correct
        extracted_data["product_id"] = product_id
        
        # Format dates (if empty, set to null)
        for date_field in ["end_of_sale_date", "end_of_software_maintenance", 
                          "end_of_security_support", "end_of_support"]:
            if date_field in extracted_data:
                date_value = extracted_data[date_field]
                if not date_value or date_value.lower() in ["none", "n/a", "unknown"]:
                    extracted_data[date_field] = None
        
        return extracted_data
    
    # Return minimal data if extraction failed
    return {
        "product_id": product_id,
        "error": "Failed to extract EOL data"
    }