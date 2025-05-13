from langchain_openai import ChatOpenAI
from crewai import Agent

def create_research_agent(tools=None):
    """
    Create the Research Agent responsible for finding and extracting EOL data.
    
    Args:
        tools: List of tools available to the agent
        
    Returns:
        CrewAI Agent object
    """
    return Agent(
        role="Cisco EOL Research Specialist",
        goal="Find and extract accurate end-of-life information for Cisco products",
        backstory="""You are a detail-oriented research specialist with expertise in 
        finding and interpreting Cisco end-of-life information. You know how to navigate 
        technical documentation, bulletins, and web resources to extract critical lifecycle 
        dates for Cisco products. You're persistent and thorough, using multiple sources 
        when necessary to obtain the most accurate information.""",
        verbose=True,
        allow_delegation=True,
        tools=tools or [],
        llm=ChatOpenAI(
            temperature=0,
            model="gpt-4o"
        )
    )