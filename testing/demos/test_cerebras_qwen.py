import os
import json
import logging
from datetime import datetime, timezone
from dotenv import load_dotenv
from cerebras.cloud.sdk import Cerebras, CerebrasError

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class CerebrasQwenClient:
    """
    A client to interact with the Cerebras Qwen Coder model for Graphiti entity extraction.
    """
    DEFAULT_MODEL = "qwen-3-coder-480b"
    
    def __init__(self, api_key: str = None, model: str = None):
        """
        Initializes the Cerebras client.
        """
        # Use the new API key you provided
        self.api_key = api_key or os.environ.get("CEREBRAS_API_KEY", "csk-v5pp234vww5hk53cjxkfern5nx262yv69xfn5fhvcrdt45jf")
        if not self.api_key:
            raise ValueError("Cerebras API key not provided")
        
        self.model = model or self.DEFAULT_MODEL
        
        try:
            self.client = Cerebras(api_key=self.api_key)
            logger.info(f"Cerebras client initialized for model: {self.model}")
        except CerebrasError as e:
            logger.error(f"Failed to initialize Cerebras client: {e}")
            raise

    def extract_entities(self, content: str, current_datetime: datetime):
        """
        Extract entities from content using Qwen Coder model with Graphiti-compatible schema.
        """
        # Create a system prompt similar to Graphiti's entity extraction
        system_prompt = """You are an AI assistant that extracts entities and relationships from text.
Extract the following from the given content:
1. Entities (people, organizations, concepts, events, etc.)
2. Relationships between entities
3. Temporal information if present

Return the result as a JSON object with 'entities' and 'edges' arrays."""

        # Create the extraction prompt with Graphiti-style schema
        extraction_prompt = f"""Extract entities and relationships from this content:

Content: {content}
Current DateTime: {current_datetime.isoformat()}

Return a JSON object with this structure:
{{
    "entities": [
        {{
            "name": "entity name",
            "entity_type": "type (Person, Organization, Event, Concept, etc.)",
            "summary": "brief description",
            "created_at": "ISO datetime string"
        }}
    ],
    "edges": [
        {{
            "source_entity_name": "source entity",
            "target_entity_name": "target entity",
            "relation_type": "relationship type",
            "created_at": "ISO datetime string"
        }}
    ]
}}"""

        try:
            # Define the JSON schema for structured output
            json_schema = {
                "name": "entity_extraction",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "entities": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "entity_type": {"type": "string"},
                                    "summary": {"type": "string"},
                                    "created_at": {"type": "string"}
                                },
                                "required": ["name", "entity_type", "summary", "created_at"],
                                "additionalProperties": False
                            }
                        },
                        "edges": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "source_entity_name": {"type": "string"},
                                    "target_entity_name": {"type": "string"},
                                    "relation_type": {"type": "string"},
                                    "created_at": {"type": "string"}
                                },
                                "required": ["source_entity_name", "target_entity_name", "relation_type", "created_at"],
                                "additionalProperties": False
                            }
                        }
                    },
                    "required": ["entities", "edges"],
                    "additionalProperties": False
                }
            }

            response_format = {"type": "json_schema", "json_schema": json_schema}

            # Use the chat completions API
            chat_completion = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": extraction_prompt}
                ],
                model=self.model,
                max_completion_tokens=4000,
                temperature=0.3,  # Lower temperature for more consistent extraction
                response_format=response_format
            )

            if chat_completion.choices and len(chat_completion.choices) > 0:
                content = chat_completion.choices[0].message.content
                logger.debug(f"Raw response: {content}")
                
                # Parse the JSON response
                result = json.loads(content)
                
                # Log token usage if available
                if hasattr(chat_completion, 'usage') and chat_completion.usage:
                    logger.info(f"Token usage - Prompt: {chat_completion.usage.prompt_tokens}, "
                              f"Completion: {chat_completion.usage.completion_tokens}, "
                              f"Total: {chat_completion.usage.total_tokens}")
                
                return result
            else:
                logger.error("No choices in response")
                return {"entities": [], "edges": []}

        except Exception as e:
            logger.error(f"Error during entity extraction: {e}")
            return {"entities": [], "edges": []}


def test_graphiti_ingestion():
    """
    Test entity extraction with a sample ingestion event similar to Graphiti's examples.
    """
    # Initialize the client
    client = CerebrasQwenClient()
    
    # Sample ingestion events (similar to Graphiti's test data)
    test_events = [
        {
            "content": "Alice is a software engineer at TechCorp. She collaborated with Bob on the GraphQL API project in January 2024. The project aims to modernize the company's data infrastructure.",
            "name": "Project collaboration update"
        },
        {
            "content": "The quantum computing research team at MIT published groundbreaking results on error correction. Dr. Sarah Chen leads the team and presented findings at the QC Summit 2024.",
            "name": "Research announcement"
        },
        {
            "content": "OpenAI released GPT-5 in collaboration with Microsoft. The model shows significant improvements in reasoning capabilities. Sam Altman announced the release at a press conference.",
            "name": "Product launch"
        }
    ]
    
    current_time = datetime.now(timezone.utc)
    
    print("\n" + "="*80)
    print("TESTING CEREBRAS QWEN CODER FOR GRAPHITI ENTITY EXTRACTION")
    print("="*80)
    
    for i, event in enumerate(test_events, 1):
        print(f"\n--- Test Event {i}: {event['name']} ---")
        print(f"Content: {event['content'][:100]}...")
        
        # Extract entities
        result = client.extract_entities(event['content'], current_time)
        
        # Display results
        print(f"\nExtracted {len(result['entities'])} entities:")
        for entity in result['entities']:
            print(f"  - {entity['name']} ({entity['entity_type']}): {entity['summary'][:50]}...")
        
        print(f"\nExtracted {len(result['edges'])} relationships:")
        for edge in result['edges']:
            print(f"  - {edge['source_entity_name']} --[{edge['relation_type']}]--> {edge['target_entity_name']}")
        
        print("\n" + "-"*40)
    
    print("\n" + "="*80)
    print("TEST COMPLETE - Qwen Coder can extract Graphiti-compatible entities!")
    print("="*80)


if __name__ == "__main__":
    # Set the API key as environment variable
    os.environ["CEREBRAS_API_KEY"] = "csk-v5pp234vww5hk53cjxkfern5nx262yv69xfn5fhvcrdt45jf"
    
    # Run the test
    test_graphiti_ingestion()