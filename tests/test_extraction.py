import os
import unittest
import json
from src.tools import CiscoEOLSearchTool, CiscoEOLScraperTool, CiscoEOLPDFTool

class TestCiscoEOLTools(unittest.TestCase):
    """Tests for the Cisco EOL extraction tools."""
    
    def setUp(self):
        """Set up test environment."""
        # Create tool instances
        self.search_tool = CiscoEOLSearchTool()
        self.scraper_tool = CiscoEOLScraperTool()
        self.pdf_tool = CiscoEOLPDFTool()
        
        # Test product ID
        self.test_product_id = "WS-C3560G-24TS"
    
    def test_search_tool(self):
        """Test the search tool functionality."""
        result = self.search_tool._run(self.test_product_id)
        
        # Check basic structure
        self.assertIn("results", result)
        self.assertIn("total_results", result)
        
        # Should have at least some results
        self.assertTrue(len(result["results"]) > 0)
        
        # First result should have key fields
        first_result = result["results"][0]
        self.assertIn("title", first_result)
        self.assertIn("link", first_result)
        self.assertIn("snippet", first_result)
    
    def test_scraper_tool(self):
        """Test the scraper tool functionality."""
        # First get a URL from the search tool
        search_result = self.search_tool._run(self.test_product_id)
        if not search_result.get("results"):
            self.skipTest("No search results found to test scraper")
        
        # Find a Cisco domain URL
        test_url = None
        for result in search_result["results"]:
            if "cisco.com" in result["link"] and not result["link"].endswith(".pdf"):
                test_url = result["link"]
                break
        
        if not test_url:
            self.skipTest("No suitable Cisco URL found to test scraper")
        
        # Test the scraper
        scrape_result = self.scraper_tool._run(test_url, self.test_product_id)
        
        # Should have product_id at minimum
        self.assertIn("product_id", scrape_result)
        self.assertEqual(scrape_result["product_id"], self.test_product_id)

    def test_pdf_tool(self):
        """Test the PDF tool functionality."""
        # First get a URL from the search tool
        search_result = self.search_tool._run(self.test_product_id)
        if not search_result.get("results"):
            self.skipTest("No search results found to test PDF tool")
        
        # Find a PDF URL
        test_url = None
        for result in search_result["results"]:
            if result["link"].endswith(".pdf"):
                test_url = result["link"]
                break
        
        if not test_url:
            self.skipTest("No PDF URL found to test PDF tool")
        
        # Test the PDF tool
        pdf_result = self.pdf_tool._run(test_url, self.test_product_id)
        
        # Should have product_id at minimum
        self.assertIn("product_id", pdf_result)
        self.assertEqual(pdf_result["product_id"], self.test_product_id)

if __name__ == "__main__":
    unittest.main() 
