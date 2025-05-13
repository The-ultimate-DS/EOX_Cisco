from langchain_openai import ChatOpenAI
from crewai import Agent

def create_reporting_agent(tools=None):
    """
    Create the Reporting Agent responsible for generating actionable reports.
    
    Args:
        tools: List of tools available to the agent
        
    Returns:
        CrewAI Agent object
    """
    return Agent(
        role="Lifecycle Reporting Specialist",
        goal="Create actionable reports highlighting critical lifecycle milestones",
        backstory="""You are an expert in translating technical lifecycle data into 
        actionable business insights. Your reports help organizations plan for hardware
        refreshes, identify security risks from end-of-support devices, and optimize
        their IT budgets. You know how to prioritize the most critical information
        and present it in a clear, actionable format that both technical and 
        non-technical stakeholders can understand.""",
        verbose=True,
        allow_delegation=False,
        tools=tools or [],
        llm=ChatOpenAI(
            temperature=0.2,
            model="gpt-4o"
        )
    )