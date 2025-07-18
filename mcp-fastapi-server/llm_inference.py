import json
import re
from typing import Dict, Any, List, Optional, Tuple
import openai
from openai import OpenAI
import os
from dataclasses import dataclass
from enum import Enum


class LLMProvider(Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    LOCAL = "local"


@dataclass
class ToolCall:
    name: str
    arguments: Dict[str, Any]
    reasoning: str


@dataclass
class ExecutionPlan:
    tool_calls: List[ToolCall]
    execution_order: List[int]
    dependencies: Dict[int, List[int]]
    final_response_template: str


class LLMInferenceService:
    def __init__(self, provider: LLMProvider = LLMProvider.OPENAI, api_key: Optional[str] = None):
        self.provider = provider
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        
        if self.provider == LLMProvider.OPENAI:
            if not self.api_key:
                raise ValueError("OpenAI API key is required")
            self.client = OpenAI(api_key=self.api_key)
            self.model = "gpt-4-1106-preview"
        
        self.conversation_history = []
    
    async def analyze_query_and_plan_tools(self, 
                                         user_query: str, 
                                         available_tools: List[Dict[str, Any]], 
                                         available_resources: List[Dict[str, Any]] = None,
                                         context: Dict[str, Any] = None) -> ExecutionPlan:
        """
        Analyze user query and create an execution plan with tool calls
        """
        
        # Build system prompt for tool analysis
        system_prompt = self._build_tool_analysis_prompt(available_tools, available_resources, context)
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"User Query: {user_query}"}
        ]
        
        # Add conversation history for context
        if self.conversation_history:
            messages = messages[:-1] + self.conversation_history[-6:] + messages[-1:]
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            return self._parse_execution_plan(result)
            
        except Exception as e:
            # Fallback to simple tool matching
            return self._fallback_tool_selection(user_query, available_tools)
    
    async def generate_tool_arguments(self, 
                                    tool_name: str, 
                                    tool_schema: Dict[str, Any], 
                                    user_query: str,
                                    context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Generate arguments for a specific tool based on user query
        """
        
        system_prompt = f"""You are an expert at generating tool arguments from natural language queries.
        
Tool: {tool_name}
Schema: {json.dumps(tool_schema, indent=2)}

Instructions:
1. Analyze the user query and extract relevant information
2. Map the extracted information to the tool's parameter schema
3. Provide sensible defaults for optional parameters
4. Return ONLY valid JSON with the arguments

Context: {json.dumps(context or {}, indent=2)}"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Generate arguments for this query: {user_query}"}
        ]
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            return json.loads(response.choices[0].message.content)
            
        except Exception as e:
            # Return empty arguments as fallback
            return {}
    
    async def synthesize_response(self, 
                                user_query: str, 
                                tool_results: List[Dict[str, Any]], 
                                execution_plan: ExecutionPlan) -> str:
        """
        Synthesize a natural language response from tool execution results
        """
        
        system_prompt = """You are an expert at synthesizing natural language responses from tool execution results.

Instructions:
1. Analyze the user's original query and the results from tool executions
2. Provide a clear, comprehensive response that addresses the user's needs
3. Highlight key findings and insights
4. Format the response in a user-friendly way
5. If there were errors, explain them clearly and suggest alternatives"""

        results_summary = []
        for i, result in enumerate(tool_results):
            tool_call = execution_plan.tool_calls[i] if i < len(execution_plan.tool_calls) else None
            tool_name = tool_call.name if tool_call else f"Tool {i}"
            
            results_summary.append({
                "tool": tool_name,
                "result": result,
                "reasoning": tool_call.reasoning if tool_call else "Direct execution"
            })
        
        context = {
            "user_query": user_query,
            "tool_results": results_summary,
            "execution_plan": {
                "tools_used": [tc.name for tc in execution_plan.tool_calls],
                "execution_order": execution_plan.execution_order
            }
        }
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Please synthesize a response for this context:\n{json.dumps(context, indent=2)}"}
        ]
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.3,
                max_tokens=1000
            )
            
            synthesized_response = response.choices[0].message.content
            
            # Add to conversation history
            self.conversation_history.extend([
                {"role": "user", "content": user_query},
                {"role": "assistant", "content": synthesized_response}
            ])
            
            return synthesized_response
            
        except Exception as e:
            # Fallback response
            return self._fallback_response(user_query, tool_results)
    
    def _build_tool_analysis_prompt(self, 
                                  available_tools: List[Dict[str, Any]], 
                                  available_resources: List[Dict[str, Any]], 
                                  context: Dict[str, Any]) -> str:
        """Build system prompt for tool analysis"""
        
        tools_description = "Available Tools:\n"
        for tool in available_tools:
            tools_description += f"- {tool.get('name', 'Unknown')}: {tool.get('description', 'No description')}\n"
            if 'inputSchema' in tool:
                tools_description += f"  Parameters: {json.dumps(tool['inputSchema'], indent=2)}\n"
        
        resources_description = ""
        if available_resources:
            resources_description = "\nAvailable Resources:\n"
            for resource in available_resources:
                resources_description += f"- {resource.get('name', 'Unknown')}: {resource.get('description', 'No description')}\n"
        
        context_info = f"\nContext: {json.dumps(context or {}, indent=2)}" if context else ""
        
        return f"""You are an expert AI assistant that analyzes user queries and creates execution plans using available MCP tools.

{tools_description}{resources_description}{context_info}

Your task:
1. Analyze the user query to understand their intent
2. Select the most appropriate tools to fulfill the request
3. Determine the execution order and dependencies
4. Provide reasoning for each tool selection

Respond with JSON in this format:
{{
  "query_analysis": {{
    "intent": "Brief description of what the user wants",
    "key_entities": ["extracted", "entities"],
    "complexity": "simple|moderate|complex"
  }},
  "tool_calls": [
    {{
      "name": "tool_name",
      "arguments": {{"param": "value"}},
      "reasoning": "Why this tool was selected and how arguments were derived"
    }}
  ],
  "execution_order": [0, 1, 2],
  "dependencies": {{
    "1": [0],
    "2": [0, 1]
  }},
  "response_template": "Template for final response with placeholders for results"
}}

If no tools are suitable, return an empty tool_calls array and explain in response_template."""
    
    def _parse_execution_plan(self, llm_response: Dict[str, Any]) -> ExecutionPlan:
        """Parse LLM response into ExecutionPlan"""
        
        tool_calls = []
        for tc in llm_response.get("tool_calls", []):
            tool_calls.append(ToolCall(
                name=tc.get("name", ""),
                arguments=tc.get("arguments", {}),
                reasoning=tc.get("reasoning", "")
            ))
        
        return ExecutionPlan(
            tool_calls=tool_calls,
            execution_order=llm_response.get("execution_order", list(range(len(tool_calls)))),
            dependencies=llm_response.get("dependencies", {}),
            final_response_template=llm_response.get("response_template", "Results: {results}")
        )
    
    def _fallback_tool_selection(self, user_query: str, available_tools: List[Dict[str, Any]]) -> ExecutionPlan:
        """Fallback tool selection using simple keyword matching"""
        
        query_lower = user_query.lower()
        selected_tools = []
        
        # Simple keyword matching
        for tool in available_tools:
            tool_name = tool.get("name", "").lower()
            tool_desc = tool.get("description", "").lower()
            
            # Check if query contains tool name or description keywords
            if any(keyword in query_lower for keyword in [tool_name] + tool_desc.split()):
                selected_tools.append(ToolCall(
                    name=tool.get("name", ""),
                    arguments={},
                    reasoning=f"Keyword match with query"
                ))
                break
        
        return ExecutionPlan(
            tool_calls=selected_tools,
            execution_order=list(range(len(selected_tools))),
            dependencies={},
            final_response_template="Executed {tool_names}: {results}"
        )
    
    def _fallback_response(self, user_query: str, tool_results: List[Dict[str, Any]]) -> str:
        """Generate fallback response when LLM synthesis fails"""
        
        if not tool_results:
            return f"I wasn't able to find appropriate tools to handle your query: '{user_query}'"
        
        response = f"Here are the results for your query: '{user_query}'\n\n"
        for i, result in enumerate(tool_results):
            response += f"Result {i+1}:\n{json.dumps(result, indent=2)}\n\n"
        
        return response
    
    def clear_conversation_history(self):
        """Clear conversation history"""
        self.conversation_history = []