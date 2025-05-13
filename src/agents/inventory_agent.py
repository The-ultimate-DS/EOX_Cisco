from langchain_openai import ChatOpenAI
from crewai import Agent

def create_inventory_agent(tools=None):
    """
    Create the Inventory Agent responsible for processing device lists.
    
    Args:
        tools: List of tools available to the agent
        
    Returns:
        CrewAI Agent object
    """
    return Agent(
        role="Cisco Inventory Specialist",
        goal="Process device inventory lists and prepare them for EOL information extraction",
        backstory="""You are an experienced networking specialist with expertise in Cisco 
        device inventory management. Your job is to process raw device inventory data,
        identify valid Cisco product IDs, and prepare them for EOL information extraction.
        You know how to handle various inventory formats and can extract the right information
        even from messy data.""",
        verbose=True,
        allow_delegation=False,
        tools=tools or [],
        llm=ChatOpenAI(
            temperature=0,
            model="gpt-4o"
        )
    )