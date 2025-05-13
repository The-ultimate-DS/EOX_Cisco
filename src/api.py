import os
import json
import re
import pandas as pd
from flask import Flask, request, jsonify, send_file, render_template
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup
import io
import PyPDF2
from langchain_openai import ChatOpenAI
from langchain.chains import create_extraction_chain
from src.utils.helpers import save_json, load_json, write_file

# Load environment variables
load_dotenv()

# Check if running on Render
IS_RENDER = os.environ.get('RENDER') == 'true'

# Initialize Flask app with template directory and absolute paths
template_dir = os.path.abspath('templates')
app = Flask(__name__, template_folder=template_dir)

# Configure app paths
if IS_RENDER:
    # On Render, use absolute paths in the application directory
    app.config['UPLOAD_FOLDER'] = os.path.abspath('uploads')
    app.config['RESULTS_FOLDER'] = os.path.abspath('results')
else:
    # Local development
    app.config['UPLOAD_FOLDER'] = os.path.abspath('uploads')
    app.config['RESULTS_FOLDER'] = os.path.abspath('results')

app.config['ALLOWED_EXTENSIONS'] = {'xlsx', 'xls', 'csv'}

# Create necessary folders with absolute paths
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['RESULTS_FOLDER'], exist_ok=True)

# Cache for storing results
result_cache = {}

# Add CORS support
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# Error handler
@app.errorhandler(Exception)
def handle_exception(e):
    return jsonify({"error": str(e)}), 500

def allowed_file(filename):
    """Check if the file extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def extract_key_dates_directly(url, product_id):
    """Try to directly extract key dates from a Cisco EOL bulletin webpage."""
    try:
        # Direct HTTP request to get the page
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            return {}
            
        # Parse HTML
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Look for tables that contain EOL information
        dates = {}
        
        # Check for standard Cisco bulletin format with tables
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 2:
                    header = cells[0].get_text().strip().lower()
                    value = cells[1].get_text().strip()
                    
                    if "end of sale" in header or "last day to order" in header:
                        dates["end_of_sale_date"] = value
                    elif "software maintenance" in header:
                        dates["end_of_software_maintenance"] = value
                    elif "security" in header or "vulnerability" in header:
                        dates["end_of_security_support"] = value
                    elif "last date of support" in header or "end of support" in header:
                        dates["end_of_support"] = value
        
        return dates
        
    except Exception:
        return {}

def process_product_id(product_id):
    """Process a single product ID and get EOL information."""
    # Check cache first
    if product_id in result_cache:
        return result_cache[product_id]
    
    # Search for the product (direct implementation instead of using the tool)
    search_results = search_cisco_eol(product_id)
    
    if 'error' in search_results:
        return {"error": search_results["error"]}
    
    if not search_results.get('results') or len(search_results['results']) == 0:
        return {"error": f"No results found for {product_id}"}
    
    # Extract EOL information from the first relevant result
    eol_data = None
    
    for result in search_results['results']:
        url = result.get('link', '')
        if 'cisco.com' in url.lower():
            if url.lower().endswith('.pdf'):
                eol_data = extract_from_pdf(url, product_id)
            else:
                eol_data = scrape_cisco_webpage(url, product_id)
            
            if eol_data and 'error' not in eol_data:
                # Try supplementary extraction for key dates that might be missing
                supplementary_data = extract_key_dates_directly(url, product_id)
                
                # Add any missing dates from supplementary extraction
                for key, value in supplementary_data.items():
                    if key not in eol_data or not eol_data[key]:
                        eol_data[key] = value
                        
                break
    
    if not eol_data or 'error' in eol_data:
        return {"error": f"Failed to extract EOL data for {product_id}"}
    
    # Cache the result
    result_cache[product_id] = eol_data
    
    return eol_data

def search_cisco_eol(product_id):
    """Search for EOL information for a Cisco product."""
    # Clean the product ID and prepare search query
    cleaned_id = product_id.strip()
    query = f"Cisco {cleaned_id} end of life bulletin"
    
    try:
        # Get API key
        serper_api_key = os.getenv("SERPER_API_KEY")
        if not serper_api_key:
            return {"error": "SERPER_API_KEY environment variable is required"}
        
        # Use Serper API for Google search results
        headers = {
            'X-API-KEY': serper_api_key,
            'Content-Type': 'application/json'
        }
        payload = json.dumps({
            "q": query,
            "num": 10
        })
        
        response = requests.post(
            'https://google.serper.dev/search', 
            headers=headers, 
            data=payload
        )
        
        if response.status_code != 200:
            return {"error": f"Search API error: {response.text}"}
        
        results = response.json()
        organic_results = results.get('organic', [])
        
        # Filter and enhance results
        cisco_domains = ["cisco.com", "cisco.com/c/en", "cisco.com/go"]
        enhanced_results = []
        
        for result in organic_results:
            result_data = {
                "title": result.get("title", ""),
                "link": result.get("link", ""),
                "snippet": result.get("snippet", ""),
                "is_cisco_domain": any(domain in result.get("link", "").lower() for domain in cisco_domains),
                "is_pdf": result.get("link", "").lower().endswith(".pdf")
            }
            enhanced_results.append(result_data)
        
        return {
            "query": query,
            "results": enhanced_results,
            "total_results": len(enhanced_results)
        }
        
    except Exception as e:
        return {"error": f"Error searching for {product_id}: {str(e)}"}

def scrape_cisco_webpage(url, product_id):
    """Scrape a web page for EOL information for a specific Cisco product."""
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

def extract_from_pdf(url, product_id):
    """Extract EOL information from a PDF bulletin."""
    try:
        # Check if the URL is a PDF
        if not url.lower().endswith('.pdf'):
            return {"error": "URL does not point to a PDF file"}
        
        # Get API key
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            return {"error": "OPENAI_API_KEY environment variable is required"}
        
        llm = ChatOpenAI(temperature=0, model="gpt-4o")
        
        # Download the PDF
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code != 200:
            return {"error": f"Failed to download PDF: HTTP {response.status_code}"}
        
        # Parse PDF content
        pdf_text = extract_pdf_text(response.content)
        
        # Extract structured data using LLM
        extraction_result = extract_eol_data(pdf_text, product_id, llm)
        extraction_result["source_url"] = url
        extraction_result["source_type"] = "PDF bulletin"
        
        return extraction_result
        
    except Exception as e:
        return {"error": f"Error processing PDF {url}: {str(e)}"}

def extract_tables(tables):
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

def extract_pdf_text(pdf_content):
    """Extract text from PDF content."""
    pdf_file = io.BytesIO(pdf_content)
    pdf_reader = PyPDF2.PdfReader(pdf_file)
    
    # Extract text from all pages
    pdf_text = ""
    for page in pdf_reader.pages:
        page_text = page.extract_text()
        if page_text:
            pdf_text += page_text + "\n"
    
    return pdf_text

def extract_eol_data(text, product_id, llm):
    """Extract structured EOL data using LLM."""
    # Define the extraction schema with more product details
    schema = {
        "properties": {
            "product_id": {"type": "string"},
            "product_description": {"type": "string", "description": "Full description of the product including its purpose and features"},
            "product_type": {"type": "string", "description": "Type of product (e.g., Switch, Router, Access Point, etc.)"},
            "product_series": {"type": "string", "description": "Product series or family name"},
            "end_of_sale_date": {"type": "string", "description": "Last date to order the product or end of sale date"},
            "end_of_software_maintenance": {"type": "string", "description": "End of routine maintenance releases date"},
            "end_of_security_support": {"type": "string", "description": "End of vulnerability/security support date"},
            "end_of_service_contract_renewal": {"type": "string", "description": "Last date to renew service contracts"},
            "last_date_of_support": {"type": "string", "description": "End of service support or last date of support"},
            "recommended_replacement": {"type": "string", "description": "Migration or replacement product ID and description"},
            "bulletin_number": {"type": "string", "description": "EOL bulletin ID or announcement number"}
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
        f"""Extract the end-of-life information for Cisco product {product_id} from this text.
        
        IMPORTANT FIELDS TO EXTRACT:
        - Product Description (full description of what the product is and its main features)
        - Product Type (switch, router, access point, etc.)
        - Product Series (product family name)
        - End of Sale Date (may appear as 'Last Date to Order' or 'End-of-Sale Date')
        - End of Software Maintenance (may appear as 'End of SW Maintenance Releases Date')
        - End of Security Support (may appear as 'End of Vulnerability/Security Support Date')
        - End of Support (may appear as 'Last Date of Support' or 'End of Service Support Date')
        - Recommended Replacement (including both product ID and brief description if available)
        
        Be thorough in extracting the product description, type, and series information.
        If exact information isn't available, use the closest match or family information.
        Return 'Unknown' for dates that cannot be found.
        
        Text: {text}"""
    )
    
    if result and isinstance(result, list) and len(result) > 0:
        extracted_data = result[0]
        
        # Ensure product_id is correct
        extracted_data["product_id"] = product_id
        
        # Normalize field names and handle cases where date fields might have alternative names
        if "last_date_of_support" in extracted_data and extracted_data["last_date_of_support"]:
            extracted_data["end_of_support"] = extracted_data["last_date_of_support"]
        
        # Map end of sale date if it has another name in the source
        if "end_of_sale_date" not in extracted_data or not extracted_data["end_of_sale_date"]:
            # Try to find it in the text directly
            sale_patterns = [
                r"End.?of.?Sale.?Date:?\s*([A-Za-z]+ \d{1,2}, \d{4})",
                r"Last.?Date.?to.?Order:?\s*([A-Za-z]+ \d{1,2}, \d{4})",
                r"End.?of.?Sale:?\s*([A-Za-z]+ \d{1,2}, \d{4})"
            ]
            
            for pattern in sale_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    extracted_data["end_of_sale_date"] = match.group(1)
                    break
        
        # Format dates (if empty, set to null)
        for date_field in ["end_of_sale_date", "end_of_software_maintenance", 
                          "end_of_security_support", "end_of_support"]:
            if date_field in extracted_data:
                date_value = extracted_data[date_field]
                if not date_value or date_value.lower() in ["none", "n/a", "unknown"]:
                    extracted_data[date_field] = None
            else:
                extracted_data[date_field] = None
        
        return extracted_data
    
    # Return minimal data if extraction failed
    return {
        "product_id": product_id,
        "error": "Failed to extract EOL data"
    }

@app.route('/')
def home():
    """API homepage with web interface."""
    try:
        return render_template('index.html')
    except Exception as e:
        # Fallback to JSON if template isn't available
        return jsonify({
            "message": "Cisco EOL API is running",
            "endpoints": {
                "single_product": "/api/eol/<product_id>",
                "batch_processing": "/api/eol/batch",
                "file_upload": "/api/upload"
            },
            "example": "/api/eol/WS-C3560G-24TS"
        })

@app.route('/api/eol/<product_id>', methods=['GET'])
def get_eol_info(product_id):
    """Get EOL information for a single product ID."""
    result = process_product_id(product_id)
    return jsonify(result)

@app.route('/api/eol/batch', methods=['POST'])
def batch_eol_info():
    """Process multiple product IDs submitted as JSON."""
    data = request.json
    if not data or 'product_ids' not in data:
        return jsonify({"error": "Missing product_ids parameter"}), 400
    
    product_ids = data['product_ids']
    results = {}
    
    for product_id in product_ids:
        results[product_id] = process_product_id(product_id)
    
    # Save results with absolute path
    result_id = f"batch_{len(result_cache)}"
    result_path = os.path.join(app.config['RESULTS_FOLDER'], f"{result_id}.json")
    save_json(results, result_path)
    
    # Generate report
    generate_report(results, result_id)
    
    return jsonify({
        "result_id": result_id,
        "results": results,
        "download_links": {
            "json": f"/api/download/{result_id}/json",
            "excel": f"/api/download/{result_id}/excel",
            "markdown": f"/api/download/{result_id}/markdown",
        }
    })

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Upload and process an Excel file with product IDs."""
    # Check if the post request has the file part
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']
    
    # If user does not select file, browser also submits an empty part without filename
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Process the file
        try:
            if filename.endswith('.csv'):
                df = pd.read_csv(filepath)
            else:
                df = pd.read_excel(filepath)
            
            # Extract product IDs from the first column
            if len(df.columns) == 0:
                return jsonify({"error": "No columns found in the file"}), 400
            
            product_ids = df.iloc[:, 0].dropna().tolist()
            product_ids = [str(pid).strip() for pid in product_ids]
            
            if not product_ids:
                return jsonify({"error": "No product IDs found in the file"}), 400
            
            # Process each product ID
            results = {}
            for product_id in product_ids:
                results[product_id] = process_product_id(product_id)
            
            # Save results with absolute path
            result_id = f"file_{os.path.splitext(filename)[0]}_{len(result_cache)}"
            result_path = os.path.join(app.config['RESULTS_FOLDER'], f"{result_id}.json")
            save_json(results, result_path)
            
            # Generate report
            generate_report(results, result_id)
            
            return jsonify({
                "result_id": result_id,
                "results": results,
                "download_links": {
                    "json": f"/api/download/{result_id}/json",
                    "excel": f"/api/download/{result_id}/excel",
                    "markdown": f"/api/download/{result_id}/markdown",
                }
            })
        
        except Exception as e:
            return jsonify({"error": f"Error processing file: {str(e)}"}), 500
    
    return jsonify({"error": "File type not allowed"}), 400

@app.route('/api/download/<result_id>/<format>', methods=['GET'])
def download_result(result_id, format):
    """Download results in the specified format."""
    # Check if the result exists
    result_path = os.path.join(app.config['RESULTS_FOLDER'], f"{result_id}.json")
    if not os.path.exists(result_path):
        return jsonify({"error": f"Result not found: {result_path}"}), 404
    
    results = load_json(result_path)
    
    if format == 'json':
        # Return the JSON file
        return send_file(result_path, as_attachment=True)
    
    elif format == 'excel':
        # Convert to Excel with improved tabular format
        excel_path = os.path.join(app.config['RESULTS_FOLDER'], f"{result_id}.xlsx")
        
        # Create a DataFrame from the results - one row per model
        data = []
        for product_id, eol_data in results.items():
            # Skip entries with errors
            if isinstance(eol_data, dict) and "error" in eol_data:
                continue
                
            row = {
                'Product ID': product_id,
                'Product Type': eol_data.get('product_type', ''),
                'Product Series': eol_data.get('product_series', ''),
                'Product Description': eol_data.get('product_description', ''),
                'End of Sale Date': eol_data.get('end_of_sale_date', ''),
                'End of Software Maintenance': eol_data.get('end_of_software_maintenance', ''),
                'End of Security Support': eol_data.get('end_of_security_support', ''),
                'End of Support': eol_data.get('end_of_support', ''),
                'Recommended Replacement': eol_data.get('recommended_replacement', ''),
                'Bulletin Number': eol_data.get('bulletin_number', ''),
                'Source URL': eol_data.get('source_url', '')
            }
            data.append(row)
        
        df = pd.DataFrame(data)
        
        # Apply formatting to make the Excel file more readable
        try:
            # Create a writer with xlsxwriter engine
            with pd.ExcelWriter(excel_path, engine='xlsxwriter') as writer:
                df.to_excel(writer, sheet_name='EOL Data', index=False)
                
                # Get workbook and worksheet objects
                workbook = writer.book
                worksheet = writer.sheets['EOL Data']
                
                # Define formats
                header_format = workbook.add_format({
                    'bold': True,
                    'bg_color': '#D9E1F2',  # Light blue
                    'border': 1,
                    'align': 'center',
                    'valign': 'vcenter'
                })
                
                cell_format = workbook.add_format({
                    'border': 1,
                    'valign': 'vcenter'
                })
                
                url_format = workbook.add_format({
                    'font_color': 'blue',
                    'underline': True,
                    'border': 1
                })
                
                # Apply formats
                for col_num, value in enumerate(df.columns.values):
                    worksheet.write(0, col_num, value, header_format)
                    # Set column width based on content
                    max_len = max(df[value].astype(str).map(len).max(), len(value))
                    worksheet.set_column(col_num, col_num, max_len + 2, cell_format)
                
                # Add hyperlinks for URLs
                for row_num, url in enumerate(df['Source URL']):
                    if url and isinstance(url, str) and url.startswith('http'):
                        worksheet.write_url(row_num + 1, df.columns.get_loc('Source URL'), 
                                          url, url_format, string=url)
        except Exception as e:
            # If xlsxwriter is not available or there's an error, use basic formatting
            print(f"Excel formatting error: {str(e)}")
            df.to_excel(excel_path, index=False)
        
        return send_file(excel_path, as_attachment=True)
    
    elif format == 'markdown':
        # Convert to Markdown
        md_path = os.path.join(app.config['RESULTS_FOLDER'], f"{result_id}.md")
        
        # Generate the markdown file if it doesn't exist
        if not os.path.exists(md_path):
            generate_report(results, result_id)
        
        # Check again after generation
        if not os.path.exists(md_path):
            return jsonify({"error": "Failed to generate Markdown report"}), 500
        
        return send_file(md_path, as_attachment=True)
    
    else:
        return jsonify({"error": "Unsupported format"}), 400

def generate_report(results, result_id):
    """Generate a markdown report from the results."""
    md_content = "# Cisco End-of-Life (EOL) Report\n\n"
    
    # Executive Summary
    md_content += "## Executive Summary\n"
    md_content += "This report provides information about the end-of-life status of the requested Cisco products.\n\n"
    
    # Detailed EOL Timeline
    md_content += "## Detailed EOL Timeline\n\n"
    
    for product_id, eol_data in results.items():
        # Skip entries with errors
        if isinstance(eol_data, dict) and "error" in eol_data:
            continue
            
        md_content += f"### {product_id}\n\n"
        
        if 'product_type' in eol_data and eol_data['product_type']:
            md_content += f"**Product Type**: {eol_data['product_type']}\n\n"
            
        if 'product_series' in eol_data and eol_data['product_series']:
            md_content += f"**Product Series**: {eol_data['product_series']}\n\n"
        
        if 'product_description' in eol_data and eol_data['product_description']:
            md_content += f"**Description**: {eol_data['product_description']}\n\n"
        
        md_content += "#### Key Dates\n\n"
        
        date_fields = [
            ('End of Sale Date', 'end_of_sale_date'),
            ('End of Software Maintenance', 'end_of_software_maintenance'),
            ('End of Security Support', 'end_of_security_support'),
            ('End of Support', 'end_of_support')
        ]
        
        for label, field in date_fields:
            if field in eol_data and eol_data[field]:
                md_content += f"- **{label}**: {eol_data[field]}\n"
        
        md_content += "\n"
        
        if 'recommended_replacement' in eol_data and eol_data['recommended_replacement']:
            md_content += f"**Recommended Replacement**: {eol_data['recommended_replacement']}\n\n"
        
        if 'source_url' in eol_data and eol_data['source_url']:
            md_content += f"**Source**: [{product_id} EOL Bulletin]({eol_data['source_url']})\n\n"
        
        md_content += "---\n\n"
    
    # Save the markdown report to the absolute path
    md_path = os.path.join(app.config['RESULTS_FOLDER'], f"{result_id}.md")
    write_file(md_content, md_path)

if __name__ == '__main__':
    app.run(debug=True, port=5000)