import os
import argparse
from dotenv import load_dotenv
from crewai import Crew, Process, Task
from src.tools import (
    cisco_eol_search, 
    cisco_eol_scraper, 
    cisco_eol_pdf,
    read_text_file,
    write_text_file,
    save_json_file,
    load_json_file
)
from src.agents import create_inventory_agent, create_research_agent, create_reporting_agent
from src.utils.helpers import (
    parse_product_list, 
    read_file, 
    write_file, 
    save_json, 
    load_json
)

# Load environment variables
load_dotenv()

def create_inventory_task(input_file):
    """Create the inventory processing task."""
    return Task(
        description=f"""
        Process the device inventory from {input_file} and prepare a clean list of Cisco product IDs.
        
        1. Read the file using the read_text_file tool: read_text_file("{input_file}")
        2. Verify that each ID follows Cisco's product ID format
        3. Remove any duplicates
        4. Format the list for EOL research
        5. Save the processed list using the save_json_file tool: save_json_file(product_ids, 'processed_inventory.json')
        
        YOU MUST ACTUALLY WRITE THE FILE using the save_json_file tool, not just mention it.
        The file must be saved as 'processed_inventory.json'.
        
        Your final output should be a JSON array of valid Cisco product IDs.
        """,
        expected_output="A JSON array of valid Cisco product IDs saved to 'processed_inventory.json'",
        agent=create_inventory_agent(
            tools=[read_text_file, write_text_file, save_json_file, load_json_file]
        )
    )

def create_research_task():
    """Create the EOL research task."""
    return Task(
        description="""
        Research and extract end-of-life information for each Cisco product ID in 'processed_inventory.json'.
        
        1. Read the processed inventory using the load_json_file tool: load_json_file('processed_inventory.json')
        2. For each product ID:
           a. Search for official Cisco EOL bulletins and documentation
           b. Extract the following information:
              - End-of-Sale Date
              - End-of-Software-Maintenance Date
              - End-of-Security/Vulnerability Support Date
              - End-of-Support (Last Day of Support) Date
              - Recommended replacement product (if available)
           c. If multiple sources are found, cross-reference them to ensure accuracy
           d. For products without official bulletins, use product family information
        3. Save all extracted data to disk using the save_json_file tool: save_json_file(eol_data, 'eol_research_results.json')
        
        YOU MUST ACTUALLY WRITE THE FILE using the save_json_file tool, not just mention it.
        The file must be saved as 'eol_research_results.json'.
        
        Your final output should be a comprehensive dataset of EOL information for all products.
        """,
        expected_output="Complete EOL dataset saved to 'eol_research_results.json'",
        agent=create_research_agent(
            tools=[
                cisco_eol_search,
                cisco_eol_scraper,
                cisco_eol_pdf,
                read_text_file, 
                write_text_file, 
                save_json_file, 
                load_json_file
            ]
        )
    )

def create_reporting_task():
    """Create the reporting task."""
    return Task(
        description="""
        Create a comprehensive EOL lifecycle report based on the data in 'eol_research_results.json'.
        
        1. Read the EOL data using the load_json_file tool: load_json_file('eol_research_results.json')
        2. Analyze the data to create:
           a. Executive Summary with key findings
           b. Critical devices requiring immediate attention (within 6 months of any EOL milestone)
           c. Breakdown of devices by lifecycle stage
           d. Detailed EOL timeline for all devices
           e. Recommended next steps and replacement options
        
        3. Write the report in markdown format to disk using the write_text_file tool: write_text_file(markdown_report, 'eol_report.md')
        4. Write the structured JSON report to disk using the save_json_file tool: save_json_file(json_report, 'eol_report.json')
        
        YOU MUST ACTUALLY WRITE THE FILES using the provided helper tools, not just generate the content.
        The files must be saved as 'eol_report.md' and 'eol_report.json'.
        
        Your final output should be actionable information that helps prioritize device upgrades.
        """,
        expected_output="Comprehensive EOL report in both markdown (eol_report.md) and JSON (eol_report.json) formats",
        agent=create_reporting_agent(
            tools=[read_text_file, write_text_file, save_json_file, load_json_file]
        )
    )

def main():
    """Main entry point for the Cisco EOL extraction application."""
    parser = argparse.ArgumentParser(description="Cisco EOL Information Extraction")
    parser.add_argument("input_file", help="Path to the file containing Cisco product IDs")
    args = parser.parse_args()
    
    # Verify input file exists
    if not os.path.exists(args.input_file):
        print(f"Error: Input file '{args.input_file}' not found.")
        return
    
    # Create the tasks and specify the agents with their tools
    inventory_task = create_inventory_task(args.input_file)
    research_task = create_research_task()
    reporting_task = create_reporting_task()
    
    # Create the crew
    lifecycle_crew = Crew(
        agents=[
            inventory_task.agent,
            research_task.agent,
            reporting_task.agent
        ],
        tasks=[inventory_task, research_task, reporting_task],
        verbose=True,
        process=Process.sequential  # Tasks must be completed in sequence
    )
    
    # Execute the crew's tasks
    result = lifecycle_crew.kickoff()
    
    print("\nCrew execution completed!")
    print(f"\nFinal result: {result}")
    
    # Verify output files were created
    expected_files = [
        "processed_inventory.json",
        "eol_research_results.json",
        "eol_report.md",
        "eol_report.json"
    ]
    
    print("\nOutput files:")
    for file in expected_files:
        if os.path.exists(file):
            print(f"✅ {file}")
        else:
            print(f"❌ {file} (not found)")

if __name__ == "__main__":
    main()