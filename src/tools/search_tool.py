import os
import json
import requests
from typing import Dict, List, Any
from dotenv import load_dotenv
from crewai import tools

# Load environment variables
load_dotenv()

@tools.tool
def cisco_eol_search(product_id: str) -> Dict[str, Any]:
    """
    Search for EOL information for a Cisco product.
    
    Args:
        product_id: The Cisco product ID to search for
        
    Returns:
        Dictionary containing search results
    """
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